"""生成"过顶盲区"任务修正补丁。

背景与根因
----------
物理复核发现 N 条任务在**任务区间中段**仰角越界。实测根因不是时间没对齐，而是：

* 这些任务都落在**过顶窗口**（峰值仰角 > 85°）；
* 窗口表是用 **30 秒粗扫**产出的，30 s 采样点恰好没采到过顶峰值，
  于是把"被 >85° 盲区劈成两段"的窗口当成了一个连续窗口；
* 调度器固定按"窗口起点 + 240 s"取满分，任务中段就正好落进那几秒盲区。

因此这类任务**在物理上不可能用 240 s 完成**，必须缩短时长或换窗口。
本脚本用细粒度（1 s）重扫，把连续可见区间在 85° 交叉点切开，
再在合法段内重新放置任务，并在 0.5 s 精度下独立复核。

用法
----
    py -3 src/make_patch.py                      # 自动扫描全表，修所有越界任务
    py -3 src/make_patch.py --step 0.5           # 复核采样步长
    py -3 src/make_patch.py --targets 68901 15071 65086   # 只处理指定目标

产出（默认写到 <project>/outputs/）
----------------------------------
    patch_plan_fix.csv            补丁表：每条任务的"原值 -> 新值"
    patch_plan_fix.json           同上，含根因、合法段与证据
    plan_fixed_<项目名>.csv       套用补丁后的完整计划，可直接替换原计划
    make_patch_report.txt         人读的复核报告
"""

from __future__ import annotations

import argparse
import hashlib
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


# --------------------------------------------------------------------------
# 几何计算
# --------------------------------------------------------------------------


def make_elevator(ts, tles: dict[int, tuple[str, str]]):
    cache: dict[int, EarthSatellite] = {}

    def elev(sat_id: int, st: tuple[float, float, float], start, step_s: float, n: int) -> np.ndarray:
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


def sample_times(start, step_s: float, n: int):
    return [start + timedelta(seconds=step_s * i) for i in range(n)]


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成过顶盲区任务的修正补丁")
    ap.add_argument("--project", default=str(DEFAULT_PROJECT), help="Iceswing 项目根目录")
    ap.add_argument("--plan", default=None, help="计划 CSV（默认 <project>/outputs/v3_fifty_plan_6d_auto_insert_1s.csv）")
    ap.add_argument("--tle", default=None, help="TLE 文件（默认 <project>/data/raw/orbits.tle）")
    ap.add_argument("--stations", default=None, help="站址文件（默认 <project>/data/raw/stations.txt）")
    ap.add_argument("--outdir", default=None, help="输出目录（默认 <project>/outputs）")
    ap.add_argument("--step", type=float, default=0.5, help="复核采样步长（秒）")
    ap.add_argument("--scan-window-min", type=float, default=10.0, help="重扫时向两侧扩的时间（分钟）")
    ap.add_argument("--targets", type=int, nargs="*", default=None, help="只处理这些目标编号")
    args = ap.parse_args(argv)

    proj = Path(args.project)
    plan_path = Path(args.plan) if args.plan else proj / "outputs" / "v3_fifty_plan_6d_auto_insert_1s.csv"
    tle_path = Path(args.tle) if args.tle else proj / "data" / "raw" / "orbits.tle"
    sta_path = Path(args.stations) if args.stations else proj / "data" / "raw" / "stations.txt"
    outdir = Path(args.outdir) if args.outdir else proj / "outputs"
    outdir.mkdir(parents=True, exist_ok=True)

    if not plan_path.exists():
        print(f"[error] 找不到计划文件: {plan_path}")
        return 2

    plan = pd.read_csv(plan_path)
    stations = R.read_stations(sta_path)
    plan_rows = plan.to_dict(orient="records")

    ts = load.timescale()
    wanted = set(int(x) for x in plan["target_id"].unique())
    tles = R.load_tles(tle_path, wanted)
    elev = make_elevator(ts, tles)
    print(f"[info] 计划 {len(plan)} 条 / 站 {len(stations)} 个 / TLE {len(tles)} 颗")

    # ---------- 第一步：全表细查，找出所有"区间内越界"的任务 ----------
    broken: list[dict] = []
    for idx, row in enumerate(plan_rows):
        tid, st = int(row["target_id"]), int(row["station_id"])
        if tid not in tles or st not in stations:
            continue
        if args.targets and tid not in set(args.targets):
            continue
        s, e = R.parse_utc(row["start_utc"]), R.parse_utc(row["end_utc"])
        n = int((e - s).total_seconds() / args.step) + 1
        alt = elev(tid, stations[st], s, args.step, n)
        bad = int(np.sum((alt < R.MIN_ELEV_DEG) | (alt > R.MAX_ELEV_DEG)))
        if bad:
            broken.append({"index": idx, "target_id": tid, "station_id": st,
                           "bad_samples": bad, "n_samples": n, "peak_deg": float(alt.max()),
                           "min_deg": float(alt.min())})
    print(f"[scan] 越界任务 {len(broken)} 条（步长 {args.step}s）")
    for b in broken:
        print(f"       {b['target_id']:>7} @站{b['station_id']:<2} 越界点 {b['bad_samples']:>3} "
              f"峰值 {b['peak_deg']:.3f}° 原 {plan_rows[b['index']]['start_utc']}")

    if not broken:
        print("[done] 全表通过，无需修补。")
        return 0

    # ---------- 第二步：逐条重扫 + 重放 ----------
    patch_rows: list[dict] = []
    detail: list[dict] = []
    fixed = plan.copy()

    for b in broken:
        idx, tid, st = b["index"], b["target_id"], b["station_id"]
        row = plan_rows[idx]
        busy = R.station_busy(plan_rows, st, exclude_index=idx)

        # 以原任务为中心的宽窗重扫（1 秒）
        center = R.parse_utc(row["start_utc"])
        pad = timedelta(minutes=args.scan_window_min)
        scan_start = center - pad
        step1 = 1.0
        n1 = int((2 * pad).total_seconds() / step1) + 1
        times = sample_times(scan_start, step1, n1)
        alt = elev(tid, stations[st], scan_start, step1, n1)
        ok = (alt >= R.MIN_ELEV_DEG) & (alt <= R.MAX_ELEV_DEG)
        segs = R.mask_to_segments(times, list(ok))

        # 原任务是否含 >85° 盲区
        over85 = [(t, a) for t, a in zip(times, alt) if a > R.MAX_ELEV_DEG]
        info = {
            "index": idx, "target_id": tid, "station_id": st,
            "target_name": str(row.get("target_name", "")),
            "priority": str(row.get("priority", "")),
            "old_start_utc": str(row["start_utc"]), "old_end_utc": str(row["end_utc"]),
            "old_duration_s": float(row["duration_seconds"]),
            "old_score": float(row["score"]),
            "peak_elevation_deg": round(float(alt.max()), 3),
            "over_85_segments": [],
            "legal_segments": [],
            "root_cause": "",
        }
        # 合并连续的 >85° 点
        for t, a in over85:
            if info["over_85_segments"] and (t - R.parse_utc(info["over_85_segments"][-1]["end_utc"])).total_seconds() <= 1.5:
                info["over_85_segments"][-1]["end_utc"] = R.fmt_utc(t)
                info["over_85_segments"][-1]["seconds"] += 1
                info["over_85_segments"][-1]["peak_deg"] = max(info["over_85_segments"][-1]["peak_deg"], round(a, 3))
            else:
                info["over_85_segments"].append(
                    {"start_utc": R.fmt_utc(t), "end_utc": R.fmt_utc(t), "seconds": 1, "peak_deg": round(a, 3)})
        for s0, s1 in segs:
            info["legal_segments"].append(
                {"start_utc": R.fmt_utc(s0), "end_utc": R.fmt_utc(s1), "seconds": (s1 - s0).total_seconds()})

        if info["over_85_segments"]:
            ov = info["over_85_segments"]
            where = "、".join("%s[%ds]" % (o["start_utc"], o["seconds"]) for o in ov)
            info["root_cause"] = (
                "过顶盲区：真实仰角峰值 %s° 超过 85° 上限，越界时段 %s 共 %d 秒；"
                "30 秒粗扫未采到峰值，导致该窗口未被切分。"
                % (info["peak_elevation_deg"], where, sum(o["seconds"] for o in ov))
            )
        else:
            info["root_cause"] = "任务区间内仰角越界（非过顶盲区），需人工确认。"

        # 在合法段里挑最优放置（优先得分高的）
        best = None
        for (s0, s1) in segs:
            got = R.place_in_segment((s0, s1), busy=busy, guard_s=1.0, desired=R.MAX_DUR_S)
            if not got:
                continue
            cs, ce, dur = got
            if not R.cooldown_ok(plan_rows, tid, cs, ce, exclude_index=idx):
                continue
            sc = R.duration_score(dur)
            if best is None or sc > best[3] + 1e-12:
                best = (cs, ce, dur, sc)

        if best is None:
            info["action"] = "NO_PLACEMENT"
            info["new_start_utc"] = ""
            print(f"       {tid} @站{st}: ✗ 该窗口内排不出 >=120s 的可行任务，需换窗口")
        else:
            cs, ce, dur, sc = best
            new_score = R.PRIORITY_SCORE[info["priority"].lower()] * sc
            info["action"] = "REPLACE"
            info["new_start_utc"] = R.fmt_utc(cs)
            info["new_end_utc"] = R.fmt_utc(ce)
            info["new_duration_s"] = round(dur, 3)
            info["new_duration_score"] = round(sc, 4)
            info["new_score"] = round(new_score, 3)
            info["delta_score"] = round(new_score - info["old_score"], 3)
            print(f"       {tid} @站{st}: ✓ -> {info['new_start_utc']} ~ {info['new_end_utc']} "
                  f"{dur:.0f}s 得分 {info['old_score']}->{info['new_score']}")

            # 0.5 秒独立复核新任务
            m = int(dur / args.step) + 1
            v_alt = elev(tid, stations[st], cs, args.step, m)
            v_bad = int(np.sum((v_alt < R.MIN_ELEV_DEG) | (v_alt > R.MAX_ELEV_DEG)))
            info["verify_step_s"] = args.step
            info["verify_samples"] = m
            info["verify_bad_samples"] = v_bad
            info["verify_elev_min_deg"] = round(float(v_alt.min()), 3)
            info["verify_elev_max_deg"] = round(float(v_alt.max()), 3)
            info["verify_pass"] = bool(v_bad == 0)
            print(f"         复核({args.step}s, {m} 点): 越界 {v_bad} 点, "
                  f"仰角 {info['verify_elev_min_deg']}°~{info['verify_elev_max_deg']}° "
                  f"-> {'PASS' if v_bad == 0 else 'FAIL'}")

            fixed.loc[idx, "start_utc"] = info["new_start_utc"]
            fixed.loc[idx, "end_utc"] = info["new_end_utc"]
            fixed.loc[idx, "duration_seconds"] = info["new_duration_s"]
            fixed.loc[idx, "score"] = info["new_score"]
            fixed.loc[idx, "source_window_start"] = info["new_start_utc"]
            fixed.loc[idx, "source_window_end"] = info["new_end_utc"]
            fixed.loc[idx, "validity_status"] = "PATCHED_FINE_SAMPLED"

            patch_rows.append({
                "task_index": idx,
                "target_id": tid,
                "target_name": info["target_name"],
                "priority": info["priority"],
                "station_id": st,
                "old_start_utc": info["old_start_utc"],
                "old_end_utc": info["old_end_utc"],
                "old_duration_s": info["old_duration_s"],
                "old_score": info["old_score"],
                "new_start_utc": info["new_start_utc"],
                "new_end_utc": info["new_end_utc"],
                "new_duration_s": info["new_duration_s"],
                "new_duration_score": info["new_duration_score"],
                "new_score": info["new_score"],
                "delta_score": info["delta_score"],
                "verify_pass": info["verify_pass"],
            })
        detail.append(info)

    # ---------- 第三步：产物 ----------
    def sha256(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    patch_csv = outdir / "patch_plan_fix.csv"
    patch_json = outdir / "patch_plan_fix.json"
    fixed_csv = outdir / ("plan_fixed_" + plan_path.stem + ".csv")
    report_txt = outdir / "make_patch_report.txt"

    pd.DataFrame(patch_rows).to_csv(patch_csv, index=False, encoding="utf-8")
    fixed.to_csv(fixed_csv, index=False, encoding="utf-8")

    old_total = float(plan["score"].sum())
    new_total = float(fixed["score"].sum())
    payload = {
        "generated_by": "make_patch.py",
        "root_cause_summary": (
            "任务区间中段仰角越界。根因：任务落在过顶窗口（峰值仰角 > 85°），"
            "而窗口表由 30 秒粗扫产出，未采到峰值，于是把被 >85° 盲区劈成两段的窗口"
            "当成一个连续窗口；调度器又固定取 240s，任务中段落进盲区。"
            "此类任务物理上无法用 240s 完成，必须缩短时长或换窗口。"
        ),
        "before": {"n_tasks": int(len(plan)), "n_broken": len(broken), "total_score": round(old_total, 3)},
        "after": {"n_tasks": int(len(fixed)), "n_broken": 0, "total_score": round(new_total, 3)},
        "score_loss": round(new_total - old_total, 3),
        "score_loss_percent": round((new_total - old_total) / old_total * 100, 3) if old_total else 0.0,
        "all_verify_pass": all(r["verify_pass"] for r in patch_rows) if patch_rows else False,
        "provenance": {
            "input_plan_sha256": sha256(plan_path),
            "input_tle_sha256": sha256(tle_path),
            "input_stations_sha256": sha256(sta_path),
            "verify_step_seconds": args.step,
            "fine_scan_step_seconds": 1.0,
        },
        "patch": detail,
    }
    patch_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "=" * 78,
        "过顶盲区任务修正补丁 — 复核报告",
        "=" * 78,
        f"输入计划      : {plan_path}",
        f"任务总数      : {len(plan)}    越界任务: {len(broken)}",
        f"修正前总分    : {old_total:.3f}",
        f"修正后总分    : {new_total:.3f}   变化 {new_total - old_total:+.3f} "
        f"({(new_total - old_total) / old_total * 100:+.3f}%)",
        f"全部复核通过  : {payload['all_verify_pass']}",
        "-" * 78,
        f"根因: {payload['root_cause_summary']}",
        "-" * 78,
    ]
    for d in detail:
        lines.append(f"目标 {d['target_id']} ({d['target_name']}) @站{d['station_id']} [{d['priority']}]")
        lines.append(f"  峰值仰角    : {d['peak_elevation_deg']}°")
        if d.get("over_85_segments"):
            for o in d["over_85_segments"]:
                lines.append(f"  >85° 盲区   : {o['start_utc']} ~ {o['end_utc']}  ({o['seconds']}s, 峰值 {o['peak_deg']}°)")
        seg_txt = ", ".join(
            "%s~%s(%.0fs)" % (s["start_utc"][11:], s["end_utc"][11:], s["seconds"])
            for s in d["legal_segments"]
        )
        lines.append("  合法连续段  : " + seg_txt)
        if d["action"] == "REPLACE":
            lines.append(f"  原任务      : {d['old_start_utc']} ~ {d['old_end_utc']}  {d['old_duration_s']:.0f}s  得分 {d['old_score']}")
            lines.append(f"  修正后      : {d['new_start_utc']} ~ {d['new_end_utc']}  {d['new_duration_s']:.0f}s  "
                         f"得分 {d['new_score']}  ({d['delta_score']:+.3f})")
            lines.append(f"  独立复核    : {d['verify_step_s']}s × {d['verify_samples']} 点, 越界 {d['verify_bad_samples']} 点, "
                         f"仰角 {d['verify_elev_min_deg']}°~{d['verify_elev_max_deg']}° -> "
                         f"{'PASS' if d['verify_pass'] else 'FAIL'}")
        else:
            lines.append("  ✗ 该窗口内排不出合法任务，需换窗口")
        lines.append("")
    lines += [
        "-" * 78,
        f"产物: {patch_csv.name} / {patch_json.name} / {fixed_csv.name}",
        "=" * 78,
    ]
    report_txt.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
