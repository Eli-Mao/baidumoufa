"""Compare V1/V2 policies and fixed V3/V4 plans on one real window set."""
from __future__ import annotations

import json
import time
from bisect import bisect_left
from pathlib import Path

import pandas as pd

from satplan import io_schema, rules
from audit_plan_physics import run as audit_physics
from repair_plan_physics import run as repair_physics


WINDOW_DIR = Path("data/out/fair_v3_v4_50")
OUTPUT_DIR = WINDOW_DIR / "v1_v4_common_candidates"
STEP_S = 30.0
EDGE_BUFFER_S = 30.0
DURATIONS_S = (120.0, 180.0, 240.0)


def make_candidates(windows: pd.DataFrame) -> list[dict]:
    rows = []
    for window in windows.itertuples(index=False):
        earliest = float(window.t_start_s) + EDGE_BUFFER_S
        latest = float(window.t_end_s) - EDGE_BUFFER_S
        for duration in DURATIONS_S:
            start = earliest
            while start + duration <= latest + 1e-9:
                rows.append({
                    "station_id": int(window.station_id), "sat_id": int(window.sat_id),
                    "priority": window.priority, "priority_score": int(window.priority_score),
                    "t_start_s": start, "t_end_s": start + duration, "dur_s": duration,
                    "duration_score": rules.duration_score(duration),
                })
                start += STEP_S
    return rows


def can_insert(task: dict, by_station: dict, by_satellite: dict) -> bool:
    start, end = task["t_start_s"], task["t_end_s"]
    sid, sat = task["station_id"], task["sat_id"]
    site = by_station.get(sid, [])
    at = bisect_left([r["t_start_s"] for r in site], start)
    if at and site[at - 1]["t_end_s"] + 30.0 > start + 1e-9:
        return False
    if at < len(site) and end + 30.0 > site[at]["t_start_s"] + 1e-9:
        return False
    prior = by_satellite.get(sat, [])
    pos = bisect_left([r["t_start_s"] for r in prior], start)
    if pos and prior[pos - 1]["t_end_s"] + 172800.0 > start + 1e-9:
        return False
    if pos < len(prior) and end + 172800.0 > prior[pos]["t_start_s"] + 1e-9:
        return False
    return True


def build_plan(candidates: list[dict], policy: str) -> tuple[pd.DataFrame, float]:
    started = time.perf_counter()
    if policy == "v1_time_first":
        ordered = sorted(candidates, key=lambda r: (r["t_start_s"], -rules.task_score(
            r["priority_score"], r["dur_s"]), r["station_id"], r["sat_id"]))
    elif policy == "v2_global_value":
        ordered = sorted(candidates, key=lambda r: (-rules.task_score(
            r["priority_score"], r["dur_s"]), r["t_start_s"], r["station_id"], r["sat_id"]))
    else:
        raise ValueError(policy)
    by_station: dict[int, list[dict]] = {}
    by_satellite: dict[int, list[dict]] = {}
    chosen = []
    for candidate in ordered:
        if not can_insert(candidate, by_station, by_satellite):
            continue
        chosen.append(candidate.copy())
        for index, key in ((by_station, "station_id"), (by_satellite, "sat_id")):
            timeline = index.setdefault(candidate[key], [])
            at = bisect_left([r["t_start_s"] for r in timeline], candidate["t_start_s"])
            timeline.insert(at, candidate)
    plan = pd.DataFrame(chosen).sort_values(["station_id", "t_start_s"]).reset_index(drop=True)
    if not plan.empty:
        plan.insert(0, "task_id", range(1, len(plan) + 1))
    elapsed = time.perf_counter() - started
    return plan, elapsed


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    windows = io_schema.load_windows(WINDOW_DIR / "windows.csv")
    tle = io_schema.read_tle_raw()
    meta = io_schema.build_sat_meta(tle, io_schema.read_priority_raw())
    # Match the exact target denominator from the fair-comparison artifact.
    target_ids = json.loads((WINDOW_DIR / "current_rules_fair_comparison.json").read_text())["target_ids"]
    selected_meta = meta[meta["sat_id"].astype(int).isin(target_ids)].copy()
    candidates = make_candidates(windows)
    result = {
        "status": "completed",
        "provenance": "real_skyfield_windows_same_legacy_50_target_ids",
        "target_ids": target_ids,
        "window_count": len(windows),
        "candidate_count": len(candidates),
        "common_candidate_policy": {"start_step_s": STEP_S, "edge_buffer_s": EDGE_BUFFER_S,
                                    "durations_s": list(DURATIONS_S)},
        "algorithms": {},
        "limitations": [
            "V1/V2 use a shared discrete candidate grid; their action set is narrower than V3/V4 continuous-duration plans.",
            "All four metrics use the current common scorer and current hard-rule validator.",
            "The 30-second candidate edge buffer is an engineering benchmark setting, not an official rule.",
        ],
    }
    for name in ("v1_time_first", "v2_global_value"):
        plan, elapsed = build_plan(candidates, name)
        plan_path = OUTPUT_DIR / f"{name}.csv"
        plan.to_csv(plan_path, index=False)
        repair_path = OUTPUT_DIR / f"{name}_repair.json"
        repair = repair_physics(plan_path, WINDOW_DIR / "windows.csv", repair_path, step_s=1.0)
        audit_path = OUTPUT_DIR / f"{name}_physics_1s.json"
        audit = audit_physics(repair_path.with_suffix(".csv"), audit_path, step_s=1.0)
        final = pd.read_csv(repair_path.with_suffix(".csv"))
        score = rules.score_plan(final, windows, selected_meta)
        violations = rules.plan_violations(final, windows)
        result["algorithms"][name] = {
            "runtime_s": elapsed, "tasks": len(final), "score": score,
            "hard_rule_violations": violations, "physical_audit": audit,
            "plan_path": str(repair_path.with_suffix(".csv")),
            "dropped_tasks": repair.get("dropped_unrepairable_tasks", []),
        }
    v34 = json.loads((WINDOW_DIR / "current_rules_fair_comparison.json").read_text())["v3_v4"]
    result["algorithms"]["v3_fixed_repaired"] = {
        "runtime_s": None,
        "tasks": v34["v3"]["tasks_after_physics_repair"],
        "score": v34["v3"]["score_after_physics_repair"],
        "hard_rule_violations": v34["v3"]["final_violations"],
        "physical_audit": v34["v3"]["full_interval_physics"],
        "plan_path": v34["v3"]["plan_csv"],
    }
    result["algorithms"]["v4_local_search_repaired"] = {
        "runtime_s": None,
        "tasks": v34["v4"]["tasks_after_physics_repair"],
        "score": v34["v4"]["score_after_physics_repair"],
        "hard_rule_violations": v34["v4"]["final_violations"],
        "physical_audit": v34["v4"]["full_interval_physics"],
        "plan_path": v34["v4"]["plan_csv"],
    }
    report_path = OUTPUT_DIR / "comparison.json"
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({name: {"tasks": value["tasks"],
                             "score": value["score"]["total_score"],
                             "covered": value["score"]["n_covered"],
                             "violations": len(value["hard_rule_violations"]),
                             "physics_pass": value["physical_audit"]["all_pass"]}
                      for name, value in result["algorithms"].items()}, indent=2))
    print(f"report={report_path}; candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
