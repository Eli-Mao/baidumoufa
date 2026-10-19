"""端到端编排。分区：**川谷**（总控 / 契约层）。

一条命令跑通全链路：

    原始数据 -> sat_meta/stations -> windows.csv -> plan.csv -> score.json -> 图表

用法::

    py -3 -m satplan.pipeline --stage meta      # 只做契约层解析与自检
    py -3 -m satplan.pipeline --stage windows   # 生成窗口表（需楼心荡的模块已实现）
    py -3 -m satplan.pipeline --stage plan      # 跑调度并校验
    py -3 -m satplan.pipeline                   # 全链路
    py -3 -m satplan.pipeline --with-report     # 全链路 + 出图
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from . import config, io_schema, rules, scoring, windows as windows_mod


def _say(msg: str) -> None:
    print(msg, flush=True)


def build_meta(*, force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """契约层：解析原始数据，产出 ``stations.csv`` 与 ``sat_meta.csv``。

    这一步**不依赖任何人的待实现模块**，随时可跑，是全队的地基。
    """
    t0 = time.time()
    if not force and config.STATIONS_CSV.exists() and config.SAT_META_CSV.exists():
        stations = io_schema.load_stations()
        sat_meta = io_schema.load_sat_meta()
        _say(f"[meta] 命中缓存：stations={len(stations)}  sat_meta={len(sat_meta)}")
        return stations, sat_meta

    stations = io_schema.read_stations_raw()
    tle_df = io_schema.read_tle_raw()
    priority_map = io_schema.read_priority_raw()
    sat_meta = io_schema.build_sat_meta(tle_df, priority_map)

    io_schema.save_stations(stations)
    io_schema.save_sat_meta(sat_meta)

    counts = sat_meta["priority"].value_counts().to_dict()
    _say(
        f"[meta] 站址 {len(stations)} 个；卫星 {len(sat_meta)} 颗 "
        f"(high={counts.get('high', 0)}, mid={counts.get('mid', 0)}, low={counts.get('low', 0)})；"
        f"耗时 {time.time() - t0:.2f}s"
    )
    return stations, sat_meta


def get_windows(
    stations: pd.DataFrame,
    sat_meta: pd.DataFrame,
    *,
    force: bool = False,
) -> pd.DataFrame:
    """取窗口表：优先读缓存，否则调用楼心荡的模块生成。"""
    t0 = time.time()
    try:
        df = windows_mod.load_or_build(stations=stations, sat_meta=sat_meta, force=force)
    except NotImplementedError as exc:
        raise SystemExit(
            "[windows] 窗口表尚未生成，且楼心荡的模块还未实现。\n"
            f"          -> {exc}\n"
            "          请先让楼心荡完成 propagate.py / windows.py，"
            f"或把现成的窗口表放到 {config.WINDOWS_CSV}"
        ) from exc
    _say(f"[windows] 窗口 {len(df)} 条；覆盖卫星 {df['sat_id'].nunique()} 颗；耗时 {time.time() - t0:.2f}s")
    return df


def run_pipeline(*, force: bool = False, with_report: bool = False) -> dict:
    """全链路：解析 -> 窗口 -> 调度 -> 校验 -> 评分 -> 落盘。"""
    stations, sat_meta = build_meta(force=force)
    win = get_windows(stations, sat_meta, force=force)

    from . import scheduler  # 延迟导入

    t0 = time.time()
    plan = scheduler.greedy_schedule(win, sat_meta)
    runtime = time.time() - t0
    _say(f"[plan] 任务 {len(plan)} 条；调度耗时 {runtime:.2f}s")

    violations = rules.plan_violations(plan, win)
    if violations:
        _say(f"[plan] ✗ 硬约束违规 {len(violations)} 条，示例：{violations[:3]}")
        raise SystemExit("调度结果不可行，已中止（不要提交不可行方案）。")
    _say("[plan] ✓ 硬约束全部通过")

    io_schema.save_plan(plan)

    report = scoring.build_score_report(plan, win, sat_meta)
    report["runtime_s_plan"] = round(runtime, 3)
    score_path = scoring.save_score_report(report)

    n_hi_total = int((sat_meta["priority"] == "high").sum())
    _say(
        f"[score] 总分 {report['weighted_score']:.1f} | 覆盖 {report['n_covered']}/{len(sat_meta)} "
        f"({report['coverage_rate']:.1%}) | 高优覆盖 {report['hi_covered']}/{n_hi_total} "
        f"({report['hi_coverage_rate']:.1%}) | 站点利用率 {report['station_utilization']:.3%}"
    )
    _say(f"[out]  {config.PLAN_CSV}\n       {score_path}")

    if with_report:
        from . import report as report_mod

        figures = report_mod.make_figures(plan, win, sat_meta)
        _say(f"[report] 图表 {len(figures)} 张 -> {config.REPORTS_DIR}")

    return report


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="赛题四 观测任务规划 全链路")
    parser.add_argument(
        "--stage",
        choices=["all", "meta", "windows", "plan"],
        default="all",
        help="只跑某个阶段",
    )
    parser.add_argument("--force", action="store_true", help="忽略缓存强制重算")
    parser.add_argument("--with-report", action="store_true", help="额外生成图表")
    args = parser.parse_args(argv)

    if args.stage == "meta":
        build_meta(force=args.force)
        return 0
    if args.stage == "windows":
        stations, sat_meta = build_meta(force=False)
        get_windows(stations, sat_meta, force=args.force)
        return 0

    run_pipeline(force=args.force, with_report=args.with_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
