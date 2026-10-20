"""复核计划表：独立重算全部任务的可见性，判定是否仍然存在越界。

定位
----
本脚本与 ``make_patch.py`` **共用** ``rules_fine.py`` 的物理口径，但走**独立执行路径**：
它不读补丁、不信任补丁，只按"计划表 + TLE + 站址"逐点重算仰角，
再与补丁里的预期值交叉比对。任何一方出错都会被发现。

典型用法
--------
    # 1) 复核 make_patch.py 产出的修正计划
    py -3 src/verify_patch.py --plan outputs/plan_fixed_v3_fifty_plan_6d_auto_insert_1s.csv

    # 2) 顺手与原计划对比，并交叉核对补丁的声明
    py -3 src/verify_patch.py --plan outputs/plan_fixed_....csv \
        --baseline <project>/outputs/v3_fifty_plan_6d_auto_insert_1s.csv \
        --patch outputs/patch_plan_fix.json

    # 3) 只查某几条任务
    py -3 src/verify_patch.py --plan ... --targets 68901 15071 65086

退出码
------
    0 = 全部任务通过；1 = 存在越界任务；2 = 输入不可用
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_fine as R  # noqa: E402

DEFAULT_PROJECT = Path(r"E:\SatelliteProject\Task4_Phase0_DataCheck")


def build_elev(ts, tles):
    cache: dict[int, EarthSatellite] = {}

    def elev(sat_id: int, st, start, step_s: float, n: int) -> np.ndarray:
        sat = cache.get(sat_id)
        if sat is None:
            sat = EarthSatellite(tles[sat_id][0], tles[sat_id][1], str(sat_id), ts)
            cache[sat_id] = sat
        site = wgs84.latlon(st[1], st[0], elevation_m=st[2])
        secs = [start + timedelta(seconds=step_s * i) for i in range(n)]
        t = ts.utc([s.year for s in secs], [s.month for s in secs], [s.day for s in secs],
                   [s.hour for s in secs], [s.minute for s in secs], [s.second for s in secs])
        return np.array([float(x) for x in (sat - site).at(t).altaz()[0].degrees], dtype=float)

    return elev


def check_plan(plan: pd.DataFrame, elev, stations, tles, step: float, targets=None):
    """逐条复核。返回 (结果列表, 越界条数)。"""
    results = []
    for row in plan.to_dict(orient="records"):
        tid, st = int(row["target_id"]), int(row["station_id"])
        if targets and tid not in targets:
            continue
        s, e = R.parse_utc(row["start_utc"]), R.parse_utc(row["end_utc"])
        dur = float(row["duration_seconds"])
        if tid not in tles or st not in stations:
            results.append({"target_id": tid, "station_id": st, "status": "SKIP_NO_TLE"})
            continue
        n = int((e - s).total_seconds() / step) + 1
        alt = elev(tid, stations[st], s, step, n)
        bad_mask = (alt < R.MIN_ELEV_DEG) | (alt > R.MAX_ELEV_DEG)
        bad = int(np.sum(bad_mask))
        r = {
            "target_id": tid,
            "target_name": str(row.get("target_name", "")),
            "priority": str(row.get("priority", "")),
            "station_id": st,
            "start_utc": str(row["start_utc"]),
            "end_utc": str(row["end_utc"]),
            "duration_s": dur,
            "score": float(row["score"]),
            "score_check": round(R.task_score(str(row.get("priority", "")), dur), 3),
            "duration_in_range": bool(R.MIN_DUR_S <= dur <= R.MAX_DUR_S),
            "n_samples": int(n),
            "bad_samples": bad,
            "elev_min_deg": round(float(alt.min()), 3),
            "elev_max_deg": round(float(alt.max()), 3),
            "pass": bool(bad == 0),
        }
        if bad:
            first = int(np.argmax(bad_mask))
            r["first_bad_utc"] = R.fmt_utc(s + timedelta(seconds=step * first))
            r["first_bad_kind"] = "above_85" if alt[first] > R.MAX_ELEV_DEG else "below_10"
            r["first_bad_elev_deg"] = round(float(alt[first]), 3)
        results.append(r)
    n_bad = sum(1 for r in results if r.get("pass") is False)
    return results, n_bad


def structural_checks(plan: pd.DataFrame):
    """与物理无关的结构性检查：时长范围、得分自洽、同站重叠与切换间隔、斜杠冷却。"""
    issues = []
    for row in plan.to_dict(orient="records"):
        dur = float(row["duration_seconds"])
        if not (R.MIN_DUR_S <= dur <= R.MAX_DUR_S):
            issues.append({"type": "duration", "target_id": int(row["target_id"]),
                           "detail": "时长 %.1fs 不在 [120,240]" % dur})
        expect = R.task_score(str(row.get("priority", "")), dur)
        if abs(expect - float(row["score"])) > 1e-3:
            issues.append({"type": "score_mismatch", "target_id": int(row["target_id"]),
                           "detail": "score=%.3f 与按口径计算 %.3f 不一致" % (float(row["score"]), expect)})
    rows = plan.to_dict(orient="records")
    for st in sorted({int(r["station_id"]) for r in rows}):
        seq = sorted(((R.parse_utc(r["start_utc"]), R.parse_utc(r["end_utc"]), int(r["target_id"]))
                      for r in rows if int(r["station_id"]) == st), key=lambda x: x[0])
        for a, b in zip(seq, seq[1:]):
            gap = (b[0] - a[1]).total_seconds()
            if gap < -1e-9:
                issues.append({"type": "overlap", "station_id": st,
                               "detail": "目标 %d 与 %d 在站 %d 重叠 %.1fs" % (a[2], b[2], st, -gap)})
            elif gap < R.SWITCH_S - 1e-9:
                issues.append({"type": "switch_gap", "station_id": st,
                               "detail": "站 %d 目标 %d->%d 间隔仅 %.1fs < 30s" % (st, a[2], b[2], gap)})
    # 48 小时冷却
    by_t = {}
    for r in rows:
        by_t.setdefault(int(r["target_id"]), []).append((R.parse_utc(r["start_utc"]), R.parse_utc(r["end_utc"])))
    for tid, seq in by_t.items():
        seq.sort()
        for a, b in zip(seq, seq[1:]):
            gap = (b[0] - a[1]).total_seconds()
            if gap < R.REPEAT_COOLDOWN_S - 1e-9:
                issues.append({"type": "cooldown", "target_id": tid,
                               "detail": "同一目标两次观测间隔仅 %.2f h < 48h" % (gap / 3600.0)})
    return issues


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="独立复核计划表的可见性与结构约束")
    ap.add_argument("--project", default=str(DEFAULT_PROJECT))
    ap.add_argument("--plan", required=True, help="待复核的计划 CSV")
    ap.add_argument("--tle", default=None)
    ap.add_argument("--stations", default=None)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--baseline", default=None, help="可选的原始计划，用于对比")
    ap.add_argument("--patch", default=None, help="可选的补丁 JSON，用于交叉核对声明值")
    ap.add_argument("--targets", type=int, nargs="*", default=None)
    args = ap.parse_args(argv)

    proj = Path(args.project)
    plan_path = Path(args.plan)
    tle_path = Path(args.tle) if args.tle else proj / "data" / "raw" / "orbits.tle"
    sta_path = Path(args.stations) if args.stations else proj / "data" / "raw" / "stations.txt"
    outdir = Path(args.outdir) if args.outdir else plan_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    for p in (plan_path, tle_path, sta_path):
        if not p.exists():
            print(f"[error] 缺少输入: {p}")
            return 2

    plan = pd.read_csv(plan_path)
    stations = R.read_stations(sta_path)
    ts = load.timescale()
    tles = R.load_tles(tle_path, {int(x) for x in plan["target_id"].unique()})
    elev = build_elev(ts, tles)
    print(f"[info] plan={plan_path.name}  tasks={len(plan)}  tle={len(tles)}  stations={len(stations)}")

    targets = set(args.targets) if args.targets else None
    results, n_bad = check_plan(plan, elev, stations, tles, args.step, targets)
    structural = structural_checks(plan)

    # 与补丁声明值交叉核对
    cross = []
    if args.patch and Path(args.patch).exists():
        pj = json.loads(Path(args.patch).read_text(encoding="utf-8"))
        by_key = {(int(d["target_id"]), str(d["new_start_utc"])): d
                  for d in pj.get("patch", []) if d.get("action") == "REPLACE"}
        for r in results:
            key = (r.get("target_id"), r.get("start_utc"))
            declared = by_key.get(key) or by_key.get((r.get("target_id"), r.get("start_utc", "").replace(" ", "")))
            if not declared:
                continue
            same = (abs(declared["new_duration_s"] - r["duration_s"]) < 1e-6
                    and declared["verify_pass"] == r["pass"])
            cross.append({"target_id": r["target_id"], "agrees": bool(same),
                          "declared_duration_s": declared["new_duration_s"],
                          "recomputed_duration_s": r["duration_s"],
                          "declared_verify_pass": declared["verify_pass"],
                          "recomputed_pass": r["pass"]})

    # 对比原计划
    baseline_info = None
    if args.baseline and Path(args.baseline).exists():
        base = pd.read_csv(args.baseline)
        b_results, b_bad = check_plan(base, elev, stations, tles, args.step, targets)
        baseline_info = {
            "plan": Path(args.baseline).name,
            "n_tasks": int(len(base)),
            "n_bad": b_bad,
            "total_score": round(float(base["score"].sum()), 3),
        }

    total_score = round(float(plan["score"].sum()), 3)
    payload = {
        "verified_by": "verify_patch.py",
        "plan": plan_path.name,
        "step_seconds": args.step,
        "n_tasks": int(len(plan)),
        "n_checked": len(results),
        "n_bad": n_bad,
        "all_pass": n_bad == 0 and not structural,
        "total_score": total_score,
        "n_structural_issues": len(structural),
        "structural_issues": structural[:200],
        "baseline": baseline_info,
        "patch_cross_check": cross,
        "tasks": results,
    }

    report = outdir / "verify_patch_report.txt"
    js = outdir / "verify_patch_result.json"
    js.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "=" * 78,
        "计划表独立复核报告",
        "=" * 78,
        f"计划文件        : {plan_path}",
        f"采样步长        : {args.step} s",
        f"任务数 / 已查   : {len(plan)} / {len(results)}",
        f"物理越界任务数  : {n_bad}",
        f"结构性违规数    : {len(structural)}",
        f"总分            : {total_score}",
    ]
    if baseline_info:
        lines.append(f"对比原始计划    : {baseline_info['plan']}  越界 {baseline_info['n_bad']} 条, "
                     f"总分 {baseline_info['total_score']}")
    if cross:
        ok = all(c["agrees"] for c in cross)
        lines.append(f"与补丁声明核对  : {len(cross)} 条, 全部一致={ok}")
    lines += ["-" * 78]
    for r in results:
        if r.get("status") == "SKIP_NO_TLE":
            continue
        flag = "PASS" if r["pass"] else ("FAIL@%s %.3f°" % (r.get("first_bad_utc", ""), r.get("first_bad_elev_deg", 0.0)))
        lines.append("%-8s %-16s 站%-3s %s ~ %s  %5.0fs  %s" % (
            r["target_id"], r["target_name"][:16], r["station_id"],
            r["start_utc"][11:], r["end_utc"][11:], r["duration_s"], flag))
    if structural:
        lines += ["-" * 78, "结构性违规："]
        for i in structural[:50]:
            lines.append("  [%s] %s" % (i["type"], i["detail"]))
    lines += ["-" * 78, "结论: " + ("全部通过 ✓" if payload["all_pass"] else "存在未通过项 ✗"),
              f"产物: {js.name} / {report.name}", "=" * 78]
    report.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if payload["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
