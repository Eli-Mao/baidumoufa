"""Profile fixed real-target propagation and emit stage/runtime/memory evidence."""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import pstats
import random
import time
from pathlib import Path

import psutil

from satplan import config, io_schema, propagate, rules, scheduler, windows


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(target_count: int, outdir: Path, seed: int, step_s: float, profile: bool) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    proc = psutil.Process()
    peak = [proc.memory_info().rss]
    import threading
    stop = threading.Event()

    def sample():
        while not stop.wait(0.05):
            peak[0] = max(peak[0], proc.memory_info().rss)

    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    t_all = time.perf_counter()
    cpu_all = time.process_time()
    stages = {}
    t = time.perf_counter()
    cpu = time.process_time()
    tle = io_schema.read_tle_raw()
    stations = io_schema.read_stations_raw()
    priority = io_schema.read_priority_raw()
    meta = io_schema.build_sat_meta(tle, priority)
    rng = random.Random(seed)
    ids = sorted(meta["sat_id"].astype(int).tolist())
    initial = rng.sample(ids, min(10, len(ids)))
    initial_set = set(initial)
    remaining = [sat_id for sat_id in ids if sat_id not in initial_set]
    rng.shuffle(remaining)
    ids = sorted(initial + remaining[:max(0, target_count - len(initial))])
    selected = meta[meta["sat_id"].isin(ids)].copy()
    tle_subset = tle[tle["sat_id"].isin(ids)].copy()
    stages["input_parse_and_selection_s"] = time.perf_counter() - t
    stages["input_parse_and_selection_cpu_s"] = time.process_time() - cpu

    cp = cProfile.Profile()
    t = time.perf_counter()
    cpu = time.process_time()
    if profile:
        cp.enable()
    raw = propagate.propagate_windows(tle_subset, stations, days=config.PLAN_DAYS, step_s=step_s,
                                      checkpoint_path=outdir / "propagation_checkpoint.csv")
    if profile:
        cp.disable()
        cp.dump_stats(str(outdir / "propagation.prof"))
        with (outdir / "cprofile_top.txt").open("w", encoding="utf-8") as f:
            pstats.Stats(cp, stream=f).strip_dirs().sort_stats("cumtime").print_stats(60)
    stages["orbit_and_visibility_propagation_s"] = time.perf_counter() - t
    stages["orbit_and_visibility_propagation_cpu_s"] = time.process_time() - cpu
    t = time.perf_counter()
    cpu = time.process_time()
    assembled = windows.assemble_windows(raw, selected) if not raw.empty else raw
    stages["window_assembly_s"] = time.perf_counter() - t
    stages["window_assembly_cpu_s"] = time.process_time() - cpu
    t = time.perf_counter()
    cpu = time.process_time()
    if not assembled.empty:
        io_schema.save_windows(assembled, outdir / "windows.csv")
    stages["window_csv_s"] = time.perf_counter() - t
    stages["window_csv_cpu_s"] = time.process_time() - cpu
    selected.to_csv(outdir / "selected_targets.csv", index=False)

    t = time.perf_counter()
    cpu = time.process_time()
    baseline = scheduler.greedy_schedule(assembled, selected)
    baseline_wall = time.perf_counter() - t
    baseline_cpu = time.process_time() - cpu
    t = time.perf_counter()
    cpu = time.process_time()
    v4 = scheduler.local_search(baseline, assembled, selected, iters=250, seed=seed)
    v4_wall = time.perf_counter() - t
    v4_cpu = time.process_time() - cpu
    violations = rules.plan_violations(v4, assembled)
    v4.to_csv(outdir / "v4_plan.csv", index=False)
    t = time.perf_counter()
    physical = propagate.cross_validate(assembled, step_s=1.0)
    physical.to_csv(outdir / "physical_samples.csv", index=False)
    physical_pass = bool(not physical.empty and physical["sampled_valid"].all())
    physical_wall = time.perf_counter() - t
    report = {
        "status": "completed_pending_full_task_audit" if not assembled.empty else "completed_no_windows",
        "provenance": "copied_local_real_TLE_Skyfield_SGP4",
        "seed": seed,
        "requested_targets": target_count,
        "actual_targets": len(selected),
        "target_ids": ids,
        "station_count": len(stations),
        "planning_start_utc": config.PLAN_T0_UTC,
        "planning_days": config.PLAN_DAYS,
        "coarse_step_s": step_s,
        "boundary_tolerance_s": config.WINDOW_BOUNDARY_TOLERANCE_S,
        "tle_sha256": sha(config.RAW_TLE_FILE),
        "stations_sha256": sha(config.RAW_STATION_FILE),
        "de421_sha256": sha(config.EPHEMERIS_FILE),
        "stages_s": stages,
        "runtime_total_s": round(time.perf_counter() - t_all, 4),
        "cpu_total_s": round(time.process_time() - cpu_all, 4),
        "peak_rss_mb": round(peak[0] / 1024**2, 3),
        "window_count": int(len(assembled)),
        "window_summary": windows.window_statistics(assembled, selected),
        "scheduler": {"baseline_wall_s": baseline_wall, "baseline_cpu_s": baseline_cpu,
                      "v4_wall_s": v4_wall, "v4_cpu_s": v4_cpu,
                      "baseline_score": rules.score_plan(baseline, assembled, selected),
                      "v4_score": rules.score_plan(v4, assembled, selected),
                      "constraint_pass": not violations, "constraint_violations": violations[:50]},
        "physical_sampling": {"status": "passed" if physical_pass else "failed",
                              "samples": int(len(physical)), "valid": int(physical["sampled_valid"].sum())
                              if not physical.empty else 0,
                              "satellites_checked": int(physical["sat_id"].nunique())
                              if not physical.empty else 0, "runtime_s": physical_wall},
        "warnings": ["TLE epochs span 2026-08-02 through 2026-08-04; for the Aug 1-7 UTC plan, SGP4 propagates backward up to about 1-3 days and forward about 3-5 days.",
                     "Sampled visibility does not certify continuous-time boundaries."],
    }
    if violations or not physical_pass:
        report["status"] = "failed_constraint_or_boundary_sampling"
    t = time.perf_counter()
    (outdir / "profile_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["stages_s"]["report_json_write_s"] = time.perf_counter() - t
    report["peak_rss_mb"] = round(max(peak[0], proc.memory_info().rss) / 1024**2, 3)
    (outdir / "profile_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    stop.set()
    monitor.join()
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--targets", type=int, default=10)
    p.add_argument("--seed", type=int, default=20261021)
    p.add_argument("--step", type=float, default=30.0)
    p.add_argument("--out", default="data/out/profile_real_10")
    p.add_argument("--profile", action="store_true")
    args = p.parse_args()
    report = run(args.targets, Path(args.out), args.seed, args.step, args.profile)
    print(json.dumps({k: report[k] for k in ("status", "actual_targets", "window_count",
                    "stages_s", "runtime_total_s", "peak_rss_mb")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
