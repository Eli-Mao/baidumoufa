"""Repair scheduled tasks whose full interval fails independent physical sampling."""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

from satplan import config, io_schema, rules



def _candidate_hard_feasible(plan: pd.DataFrame, win: pd.DataFrame, idx,
                             by_sat_windows: dict | None = None) -> bool:
    """Check a one-task edit with the frozen kernel on its immediate neighbors.

    The caller establishes that the current full plan is hard-feasible. A
    single edit changes only its own duration/window/period and its two
    station/satellite timeline adjacencies. Untouched constraints stay valid.
    A final full-plan check remains mandatory.
    """
    task = plan.loc[idx]
    other = plan.drop(index=idx)
    neighbors = {idx}
    for column in ("station_id", "sat_id"):
        group = other[other[column] == task[column]]
        before = group[group.t_start_s < float(task.t_start_s)]
        after = group[group.t_start_s >= float(task.t_start_s)]
        if not before.empty:
            neighbors.add(before.t_start_s.idxmax())
        if not after.empty:
            neighbors.add(after.t_start_s.idxmin())
    subset = plan.loc[sorted(neighbors)].reset_index(drop=True)
    if by_sat_windows is None:
        source = win[win.sat_id.isin(subset.sat_id)]
    else:
        source = pd.concat([by_sat_windows[int(sid)] for sid in subset.sat_id.unique()], ignore_index=True)
    return not rules.plan_violations(subset, source)


def run(plan_path: Path, windows_path: Path, out: Path, step_s: float = 1.0) -> dict:
    plan = pd.read_csv(plan_path)
    win = pd.read_csv(windows_path)
    initial_issues = rules.plan_violations(plan, win)
    if initial_issues:
        raise ValueError(f"Repair requires an initially hard-feasible plan: {initial_issues[:3]}")
    by_sat_windows = {int(sid): group for sid, group in win.groupby("sat_id")}
    tle = io_schema.read_tle_raw()
    stations = io_schema.read_stations_raw()
    by_sat = {int(row.sat_id): row for row in tle.itertuples(index=False)}
    by_site = {int(row.station_id): wgs84.latlon(float(row.lat_deg), float(row.lon_deg),
                                                  elevation_m=float(row.alt_m))
               for row in stations.itertuples(index=False)}
    ts, eph = load.timescale(), load(str(config.EPHEMERIS_FILE))
    earth, sun = eph["earth"], eph["sun"]
    t0 = io_schema.parse_utc(config.PLAN_T0_UTC)
    changed = []
    dropped = []
    for idx, row in plan.iterrows():
        satrow = by_sat[int(row.sat_id)]
        sat = EarthSatellite(satrow.line1, satrow.line2, satrow.name, ts)
        site = by_site[int(row.station_id)]
        offsets = np.arange(float(row.t_start_s), float(row.t_end_s) + 1e-9, step_s)
        offsets = np.unique(np.append(offsets, float(row.t_end_s)))
        instants = [t0 + timedelta(seconds=float(x)) for x in offsets]
        t = ts.utc(np.array([x.year for x in instants], dtype=np.int64),
                   np.array([x.month for x in instants], dtype=np.int64),
                   np.array([x.day for x in instants], dtype=np.int64),
                   np.array([x.hour for x in instants], dtype=np.int64),
                   np.array([x.minute for x in instants], dtype=np.int64),
                   np.array([x.second + x.microsecond / 1e6 for x in instants]))
        elev = np.asarray((sat - site).at(t).altaz()[0].degrees, dtype=float)
        sun_alt = np.asarray((earth + site).at(t).observe(sun).apparent().altaz()[0].degrees, dtype=float)
        valid = ((elev >= config.MIN_ELEV_DEG) & (elev <= config.MAX_ELEV_DEG) &
                 (sun_alt < config.SUN_ELEV_MAX_DEG) & np.asarray(sat.at(t).is_sunlit(eph), dtype=bool))
        valid &= np.asarray([x is None for x in sat.at(t).message], dtype=bool)
        if valid.all():
            continue
        # Sample each source window once, then choose a legal contiguous interval.
        source = win[win.sat_id == int(row.sat_id)]
        options = []
        for w in source.itertuples(index=False):
            source_station_id = int(w.station_id)
            source_site = by_site[source_station_id]
            points = np.arange(float(w.t_start_s), float(w.t_end_s) + 1e-9, step_s)
            points = np.unique(np.append(points, float(w.t_end_s)))
            inst = [t0 + timedelta(seconds=float(x)) for x in points]
            tt = ts.utc(np.array([x.year for x in inst], dtype=np.int64),
                        np.array([x.month for x in inst], dtype=np.int64),
                        np.array([x.day for x in inst], dtype=np.int64),
                        np.array([x.hour for x in inst], dtype=np.int64),
                        np.array([x.minute for x in inst], dtype=np.int64),
                        np.array([x.second + x.microsecond / 1e6 for x in inst]))
            ee = np.asarray((sat - source_site).at(tt).altaz()[0].degrees, dtype=float)
            ss = np.asarray((earth + source_site).at(tt).observe(sun).apparent().altaz()[0].degrees, dtype=float)
            ok = ((ee >= config.MIN_ELEV_DEG) & (ee <= config.MAX_ELEV_DEG) &
                  (ss < config.SUN_ELEV_MAX_DEG) & np.asarray(sat.at(tt).is_sunlit(eph), dtype=bool))
            ok &= np.asarray([x is None for x in sat.at(tt).message], dtype=bool)
            indexes = np.flatnonzero(ok)
            if len(indexes) == 0:
                continue
            cuts = np.flatnonzero(np.diff(indexes) > 1) + 1
            for segment in np.split(indexes, cuts):
                if len(segment) * step_s < config.MIN_DUR_S:
                    continue
                start = float(points[int(segment[0])])
                end = float(points[int(segment[-1])])
                options.append((source_station_id, start, end))
        desired = min(float(row.dur_s), config.MAX_DUR_S)
        candidates = []
        for source_station_id, start, end in options:
            duration = min(desired, end - start)
            if duration < config.MIN_DUR_S:
                continue
            candidate = (min(max(float(row.t_start_s), start), end - duration),
                         min(max(float(row.t_start_s), start), end - duration) + duration)
            candidates.append((source_station_id, *candidate))
        candidates.sort(key=lambda item: (item[0] != int(row.station_id),
                                          abs(item[1] - float(row.t_start_s))))
        old = (float(row.t_start_s), float(row.t_end_s))
        old_station = int(row.station_id)
        best = None
        for candidate_station, candidate_start, candidate_end in candidates:
            plan.at[idx, "station_id"] = candidate_station
            plan.at[idx, "t_start_s"], plan.at[idx, "t_end_s"] = candidate_start, candidate_end
            plan.at[idx, "dur_s"] = candidate_end - candidate_start
            plan.at[idx, "duration_score"] = rules.duration_score(plan.at[idx, "dur_s"])
            if _candidate_hard_feasible(plan, win, idx, by_sat_windows):
                best = (candidate_station, candidate_start, candidate_end)
                break
        if best is not None:
            changed.append({"task_id": int(row.task_id), "old_station": old_station,
                            "new_station": best[0], "old": old, "new": best[1:]})
        else:
            plan.at[idx, "station_id"] = old_station
            plan.at[idx, "t_start_s"], plan.at[idx, "t_end_s"] = old
            plan.at[idx, "dur_s"] = old[1] - old[0]
            plan.at[idx, "duration_score"] = rules.duration_score(plan.at[idx, "dur_s"])
            dropped.append(int(row.task_id))

    if dropped:
        plan = plan[~plan["task_id"].astype(int).isin(dropped)].copy().reset_index(drop=True)
    plan.to_csv(out.with_suffix(".csv"), index=False)
    violations = rules.plan_violations(plan, win)
    all_meta = io_schema.build_sat_meta(tle, io_schema.read_priority_raw())
    selected_meta = all_meta[all_meta["sat_id"].astype(int).isin(win["sat_id"].astype(int).unique())]
    report = {"tasks": len(plan), "changed": changed, "n_changed": len(changed),
              "dropped_unrepairable_tasks": dropped,
              "n_violations": len(violations), "violations": violations,
              "score": rules.score_plan(plan, win, selected_meta)}
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("windows", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.windows, args.out), indent=2))
