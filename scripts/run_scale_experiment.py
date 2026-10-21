"""Resumable V4 benchmark runner for real or explicitly synthetic windows.

The synthetic mode is for scheduler/performance validation only and labels all
artifacts accordingly. Real experiments require prepared ``sat_meta.csv`` and
``windows.csv`` and never fabricate orbit data.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

import pandas as pd

try:
    import psutil
except ImportError:  # pragma: no cover - optional Windows metric
    psutil = None

from satplan import config, io_schema, rules, scheduler


def synthetic(n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for sat in range(1, n + 1):
        station = (sat % len(config.STATION_IDS)) + 1
        start = float((sat * 173) % int(config.PLAN_DAYS * 86400 - 300))
        rows.append({"window_id": sat, "station_id": station, "sat_id": sat,
                     "priority": config.PRIORITY_ORDER[sat % 3],
                     "priority_score": config.PRIORITY_SCORE[config.PRIORITY_ORDER[sat % 3]],
                     "t_start_s": start, "t_end_s": start + 240.0,
                     "dur_s": 240.0, "t_start_utc": "2026-10-01T00:00:00Z",
                     "t_end_utc": "2026-10-01T00:04:00Z", "max_elev_deg": 45.0})
    windows = pd.DataFrame(rows)
    meta = pd.DataFrame([{"sat_id": i, "name": f"S{i}",
                           "priority": config.PRIORITY_ORDER[i % 3],
                           "priority_score": config.PRIORITY_SCORE[config.PRIORITY_ORDER[i % 3]],
                           "tle_epoch_utc": "2026-08-03T00:00:00.000Z"}
                         for i in range(1, n + 1)])
    return windows, meta


def run(args: argparse.Namespace) -> dict:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / "checkpoint.json"
    if args.synthetic:
        windows, meta = synthetic(args.targets)
        provenance = "synthetic_scheduler_only"
    else:
        windows = io_schema.load_windows(Path(args.windows)) if args.windows else io_schema.load_windows()
        meta = io_schema.load_sat_meta(Path(args.meta)) if args.meta else io_schema.load_sat_meta()
        provenance = "provided_orbit_dataset"
    peak_memory_kb = None
    stop_monitor = threading.Event()
    if psutil:
        process = psutil.Process()
        peak = [process.memory_info().rss]

        def sample_memory() -> None:
            while not stop_monitor.wait(0.05):
                try:
                    peak[0] = max(peak[0], process.memory_info().rss)
                except psutil.Error:
                    return

        monitor = threading.Thread(target=sample_memory, daemon=True)
        monitor.start()
    t0 = time.perf_counter()
    try:
        baseline = scheduler.greedy_schedule(windows, meta)
        v4 = scheduler.local_search(baseline, windows, meta, iters=args.iters, seed=args.seed)
    finally:
        elapsed = time.perf_counter() - t0
        stop_monitor.set()
        if psutil:
            monitor.join()
            peak_memory_kb = int(peak[0] / 1024)
    violations = rules.plan_violations(v4, windows)
    report = {"schema_version": 1, "provenance": provenance, "target_count": len(meta),
              "algorithm": "V4", "seed": args.seed, "iterations": args.iters,
              "runtime_s": round(elapsed, 4), "peak_memory_kb": peak_memory_kb,
              "baseline": rules.score_plan(baseline, windows, meta),
              "result": rules.score_plan(v4, windows, meta), "n_violations": len(violations),
              "violations": violations[:50]}
    (out / "v4_score.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    v4.to_csv(out / "v4_plan.csv", index=False)
    checkpoint.write_text(json.dumps({"completed": True, "target_count": len(meta),
                                      "score_file": str(out / "v4_score.json")}, indent=2), encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--targets", type=int, default=100)
    p.add_argument("--iters", type=int, default=500)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="data/out/v4_benchmark")
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--windows")
    p.add_argument("--meta")
    args = p.parse_args()
    report = run(args)
    print(json.dumps({"provenance": report["provenance"], "target_count": report["target_count"],
                      "runtime_s": report["runtime_s"], "n_violations": report["n_violations"]}))
    return 0 if report["n_violations"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
