"""Recompute the legacy V3 target set with the shared current scoring engine."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from satplan import config, io_schema, propagate, rules, scheduler, windows


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(legacy_dir: Path, out: Path) -> dict:
    selection = json.loads((legacy_dir / "outputs/fifty_target_selection.json").read_text(encoding="utf-8"))
    target_ids = sorted(map(int, selection["target_ids"]))
    tle_all = io_schema.read_tle_raw()
    stations = io_schema.read_stations_raw()
    meta_all = io_schema.build_sat_meta(tle_all, io_schema.read_priority_raw())
    meta = meta_all[meta_all["sat_id"].isin(target_ids)].copy()
    tle = tle_all[tle_all["sat_id"].isin(target_ids)].copy()
    if len(meta) != 50 or len(tle) != 50:
        raise ValueError("Legacy target set does not resolve to 50 current TLEs")
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    raw = propagate.propagate_windows(tle, stations, days=6, step_s=30.0,
                                      checkpoint_path=out / "propagation_checkpoint.csv")
    win = windows.assemble_windows(raw, meta)
    propagation_s = time.perf_counter() - started
    win.to_csv(out / "windows.csv", index=False)
    meta.to_csv(out / "selected_targets.csv", index=False)
    started = time.perf_counter()
    greedy = scheduler.greedy_schedule(win, meta)
    greedy_s = time.perf_counter() - started
    started = time.perf_counter()
    v4 = scheduler.local_search(greedy, win, meta, iters=1000, seed=20261020)
    v4_s = time.perf_counter() - started
    greedy.to_csv(out / "greedy_plan.csv", index=False)
    v4.to_csv(out / "v4_plan.csv", index=False)
    physical = propagate.cross_validate(win, sample_sat_ids=target_ids, step_s=1.0)
    physical.to_csv(out / "window_physical_samples.csv", index=False)
    legacy_outputs = Path(__file__).resolve().parents[1] / "delivery/2026-10-20_task4_overhead_fix/outputs"
    legacy_plan_path = legacy_outputs / "plan_fixed_v3_fifty_plan_6d_auto_insert_1s.csv"
    legacy_report_path = legacy_dir / "outputs/v3_fifty_plan_6d_auto_insert_1s.json"
    legacy_plan = pd.read_csv(legacy_plan_path)
    legacy_report = json.loads(legacy_report_path.read_text(encoding="utf-8"))
    v3 = pd.DataFrame({
        "task_id": range(1, len(legacy_plan) + 1),
        "station_id": legacy_plan["station_id"].astype(int),
        "sat_id": legacy_plan["target_id"].astype(int),
        "priority": legacy_plan["priority"].str.lower().replace({"medium": "mid"}),
        "priority_score": legacy_plan["priority"].str.lower().replace({"medium": "mid"}).map(config.PRIORITY_SCORE),
        "t_start_s": (pd.to_datetime(legacy_plan["start_utc"]) - pd.Timestamp("2026-10-01")).dt.total_seconds(),
        "t_end_s": (pd.to_datetime(legacy_plan["end_utc"]) - pd.Timestamp("2026-10-01")).dt.total_seconds(),
        "dur_s": legacy_plan["duration_seconds"].astype(float),
    })
    v3["duration_score"] = v3["dur_s"].map(rules.duration_score)
    v3.to_csv(out / "v3_plan_shared_schema.csv", index=False)
    v3_violations = rules.plan_violations(v3, win)
    result = {
        "status": "completed",
        "target_ids": target_ids,
        "target_count": len(target_ids),
        "legacy_selection_ids_match": target_ids == sorted(map(int, selection["target_ids"])),
        "input_hashes": {"tle": sha(config.RAW_TLE_FILE), "stations": sha(config.RAW_STATION_FILE),
                         "priorities": {k: sha(v) for k, v in config.RAW_PRIORITY_FILES.items()}},
        "rules": {"planning_start_utc": config.PLAN_T0_UTC, "planning_days": 6,
                  "coarse_step_s": 30.0, "boundary_tolerance_s": config.WINDOW_BOUNDARY_TOLERANCE_S,
                  "min_elev_deg": config.MIN_ELEV_DEG, "max_elev_deg": config.MAX_ELEV_DEG,
                  "min_duration_s": config.MIN_DUR_S, "max_duration_s": config.MAX_DUR_S,
                  "station_sun_alt_max_deg": config.SUN_ELEV_MAX_DEG,
                  "require_sat_sunlit": config.REQUIRE_SAT_SUNLIT,
                  "priority_score": config.PRIORITY_SCORE},
        "windows": {"count": len(win), "targets_with_windows": int(win["sat_id"].nunique()),
                    "propagation_wall_s": propagation_s},
        "legacy_v3": {"tasks": len(legacy_plan), "reported_candidate_score": legacy_report["candidate"]["score"],
                      "reported_fixed_score": 459.223, "shared_score": rules.score_plan(v3, win, meta),
                      "shared_constraint_violations": v3_violations,
                      "window_generation_equivalent": False},
        "shared_engine": {
            "greedy": {"runtime_s": greedy_s, "score": rules.score_plan(greedy, win, meta),
                       "violations": rules.plan_violations(greedy, win)},
            "v4": {"runtime_s": v4_s, "score": rules.score_plan(v4, win, meta),
                   "violations": rules.plan_violations(v4, win)}},
        "window_boundary_sampling": {"samples": len(physical),
                                     "valid": int(physical["sampled_valid"].sum()) if len(physical) else 0,
                                     "pass": bool(len(physical) and physical["sampled_valid"].all())},
        "conclusion": "Legacy V3 and current V4 are not directly rankable until both use identical windows and scoring; this report supplies the shared-engine comparison on the exact legacy target IDs."}
    (out / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-dir", type=Path, default=Path(r"D:\SatelliteProject\Task4_Phase0_DataCheck"))
    parser.add_argument("--out", type=Path, default=Path("data/out/fair_v3_v4_50"))
    args = parser.parse_args()
    print(json.dumps(run(args.legacy_dir, args.out), indent=2))
