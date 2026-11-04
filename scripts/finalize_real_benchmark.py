"""Add scheduling and independent physical checks to an existing real benchmark."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from satplan import io_schema, propagate, rules, scheduler


def finalize(outdir: Path) -> dict:
    report_path = outdir / "profile_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    windows = io_schema.load_windows(outdir / "windows.csv")
    tle = io_schema.read_tle_raw()
    meta = io_schema.build_sat_meta(tle, io_schema.read_priority_raw())
    selected = meta[meta["sat_id"].astype(int).isin(report["target_ids"])].copy()

    started = time.perf_counter()
    baseline = scheduler.greedy_schedule(windows, selected)
    baseline_wall = time.perf_counter() - started
    started = time.perf_counter()
    v4 = scheduler.local_search(baseline, windows, selected, iters=250, seed=report["seed"])
    v4_wall = time.perf_counter() - started
    violations = rules.plan_violations(v4, windows)
    v4.to_csv(outdir / "v4_plan.csv", index=False)

    started = time.perf_counter()
    physical = propagate.cross_validate(windows)
    physical.to_csv(outdir / "physical_samples.csv", index=False)
    physical_wall = time.perf_counter() - started
    physical_pass = bool(not physical.empty and physical["sampled_valid"].all())
    report["scheduler"] = {
        "baseline_wall_s": baseline_wall,
        "v4_wall_s": v4_wall,
        "baseline_score": rules.score_plan(baseline, windows, selected),
        "v4_score": rules.score_plan(v4, windows, selected),
        "constraint_pass": not violations,
        "constraint_violations": violations[:50],
    }
    report["physical_sampling"] = {
        "status": "passed" if physical_pass else "failed",
        "samples": int(len(physical)),
        "valid": int(physical["sampled_valid"].sum()) if not physical.empty else 0,
        "satellites_checked": int(physical["sat_id"].nunique()) if not physical.empty else 0,
        "runtime_s": physical_wall,
    }
    # This only checks candidate-window boundaries. Full scheduled-task interval
    # sampling is performed by audit_plan_physics.py and must remain explicit.
    report["status"] = ("completed_pending_full_task_audit"
                        if not violations and physical_pass and not windows.empty
                        else "failed_validation")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args()
    report = finalize(args.outdir)
    print(json.dumps({"status": report["status"], "targets": report["actual_targets"],
                      "windows": report["window_count"], "v4": report["scheduler"]["v4_score"],
                      "constraint_pass": report["scheduler"]["constraint_pass"],
                      "physical": report["physical_sampling"]}, indent=2))
    return 0 if report["status"] == "completed_pending_full_task_audit" else 2


if __name__ == "__main__":
    raise SystemExit(main())
