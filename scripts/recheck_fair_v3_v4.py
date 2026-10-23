"""Recheck legacy V3 and V4 on identical windows under current hard rules."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from satplan import config, io_schema, rules, scheduler
from repair_plan_physics import run as repair_physics
from audit_plan_physics import run as audit_physics


def main() -> int:
    out = Path("data/out/fair_v3_v4_50")
    legacy = Path(r"D:\SatelliteProject\Task4_Phase0_DataCheck")
    win = io_schema.load_windows(out / "windows.csv")
    selection = json.loads((legacy / "outputs/fifty_target_selection.json").read_text(encoding="utf-8"))
    target_ids = sorted(map(int, selection["target_ids"]))
    tle = io_schema.read_tle_raw()
    meta = io_schema.build_sat_meta(tle, io_schema.read_priority_raw())
    meta = meta[meta["sat_id"].astype(int).isin(target_ids)].copy()
    legacy_plan_path = Path(
        "delivery/2026-10-20_task4_overhead_fix/outputs/"
        "plan_fixed_v3_fifty_plan_6d_auto_insert_1s.csv"
    )
    old = pd.read_csv(legacy_plan_path)
    v3 = pd.DataFrame({
        "task_id": range(1, len(old) + 1),
        "station_id": old["station_id"].astype(int),
        "sat_id": old["target_id"].astype(int),
        "priority": old["priority"].str.lower().replace({"medium": "mid"}),
        "priority_score": old["priority"].str.lower().replace({"medium": "mid"}).map(config.PRIORITY_SCORE),
        "t_start_s": (pd.to_datetime(old["start_utc"]) - pd.Timestamp("2026-10-01")).dt.total_seconds(),
        "t_end_s": (pd.to_datetime(old["end_utc"]) - pd.Timestamp("2026-10-01")).dt.total_seconds(),
        "dur_s": old["duration_seconds"].astype(float),
    })
    v3["duration_score"] = v3["dur_s"].map(rules.duration_score)
    v3.to_csv(out / "v3_plan_current_rules.csv", index=False)

    baseline = scheduler.greedy_schedule(win, meta)
    v4 = scheduler.local_search(baseline, win, meta, iters=1000, seed=20261020)
    v4.to_csv(out / "v4_plan_current_rules.csv", index=False)

    results = {}
    for name, plan_path in (("v3", out / "v3_plan_current_rules.csv"),
                            ("v4", out / "v4_plan_current_rules.csv")):
        before = pd.read_csv(plan_path)
        initial_violations = rules.plan_violations(before, win)
        repaired_json = out / f"{name}_current_rules_physics_repair.json"
        repaired = repair_physics(plan_path, out / "windows.csv", repaired_json, step_s=1.0)
        repaired_plan = repaired_json.with_suffix(".csv")
        audit_json = out / f"{name}_current_rules_full_physics_1s.json"
        audit = audit_physics(repaired_plan, audit_json, step_s=1.0)
        final_frame = pd.read_csv(repaired_plan)
        final_violations = rules.plan_violations(final_frame, win)
        results[name] = {
            "initial_tasks": len(before),
            "initial_score": rules.score_plan(before, win, meta),
            "initial_violations": initial_violations,
            "tasks_after_physics_repair": len(final_frame),
            "score_after_physics_repair": rules.score_plan(final_frame, win, meta),
            "final_violations": final_violations,
            "full_interval_physics": audit,
            "plan_csv": str(repaired_plan),
        }
    result = {
        "status": "completed",
        "target_ids": target_ids,
        "target_count": len(target_ids),
        "window_count": len(win),
        "window_source": str(out / "windows.csv"),
        "rules": {"planning_start_utc": config.PLAN_T0_UTC,
                  "planning_days": config.PLAN_DAYS,
                  "repeat_cooldown_s": config.REPEAT_COOLDOWN_S,
                  "station_switch_s": config.SWITCH_TIME_S},
        "v3_v4": results,
        "comparison_warning": (
            "The legacy V3 plan was produced by an older scheduler/window policy. "
            "Its reported 459.223 candidate score is not comparable to these "
            "re-evaluated scores until its planning behavior is normalized."
        ),
    }
    (out / "current_rules_fair_comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({name: {"tasks": data["tasks_after_physics_repair"],
                             "score": data["score_after_physics_repair"]["total_score"],
                             "coverage": data["score_after_physics_repair"]["n_covered"],
                             "violations": len(data["final_violations"]),
                             "physics_pass": data["full_interval_physics"]["all_pass"]}
                      for name, data in results.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
