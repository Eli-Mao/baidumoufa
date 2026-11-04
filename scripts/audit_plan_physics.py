"""Independently sample every scheduled task interval with Skyfield predicates."""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

from satplan import config, io_schema


def run(plan_path: Path, out: Path, step_s: float = 1.0) -> dict:
    plan = pd.read_csv(plan_path)
    tle = io_schema.read_tle_raw()
    stations = io_schema.read_stations_raw()
    by_sat = {int(row.sat_id): row for row in tle.itertuples(index=False)}
    by_site = {int(row.station_id): wgs84.latlon(float(row.lat_deg), float(row.lon_deg),
                                                  elevation_m=float(row.alt_m))
               for row in stations.itertuples(index=False)}
    ts = load.timescale()
    eph = load(str(config.EPHEMERIS_FILE))
    earth, sun = eph["earth"], eph["sun"]
    t0 = io_schema.parse_utc(config.PLAN_T0_UTC)
    details = []
    for row in plan.itertuples(index=False):
        satrow = by_sat[int(row.sat_id)]
        sat = EarthSatellite(satrow.line1, satrow.line2, satrow.name, ts)
        site = by_site[int(row.station_id)]
        offsets = np.arange(0.0, float(row.t_end_s - row.t_start_s) + 1e-9, step_s)
        offsets = np.unique(np.append(offsets, float(row.t_end_s - row.t_start_s)))
        instants = [t0 + timedelta(seconds=float(row.t_start_s + offset)) for offset in offsets]
        years = np.array([x.year for x in instants], dtype=np.int64)
        months = np.array([x.month for x in instants], dtype=np.int64)
        days = np.array([x.day for x in instants], dtype=np.int64)
        hours = np.array([x.hour for x in instants], dtype=np.int64)
        minutes = np.array([x.minute for x in instants], dtype=np.int64)
        seconds = np.array([x.second + x.microsecond / 1e6 for x in instants])
        t = ts.utc(years, months, days, hours, minutes, seconds)
        elevation = np.asarray((sat - site).at(t).altaz()[0].degrees, dtype=float)
        sun_alt = np.asarray((earth + site).at(t).observe(sun).apparent().altaz()[0].degrees, dtype=float)
        geocentric = sat.at(t)
        sunlit = np.asarray(geocentric.is_sunlit(eph), dtype=bool)
        bad_sgp4 = np.asarray([x is not None for x in geocentric.message], dtype=bool)
        bad_elev = (~np.isfinite(elevation)) | (elevation < config.MIN_ELEV_DEG) | (elevation > config.MAX_ELEV_DEG)
        bad_dark = (~np.isfinite(sun_alt)) | (sun_alt >= config.SUN_ELEV_MAX_DEG)
        bad_light = ~sunlit if config.REQUIRE_SAT_SUNLIT else np.zeros_like(sunlit)
        details.append({
            "task_id": int(row.task_id), "sat_id": int(row.sat_id), "station_id": int(row.station_id),
            "samples": len(instants), "exact_end_included": bool(offsets[-1] == float(row.t_end_s - row.t_start_s)),
            "bad_sgp4_samples": int(bad_sgp4.sum()), "min_elev_deg": float(np.nanmin(elevation)),
            "max_elev_deg": float(np.nanmax(elevation)), "max_sun_alt_deg": float(np.nanmax(sun_alt)),
            "bad_elevation_samples": int(bad_elev.sum()), "bad_darkness_samples": int(bad_dark.sum()),
            "bad_satellite_illumination_samples": int(bad_light.sum()),
            "pass": not bool((bad_elev | bad_dark | bad_light | bad_sgp4).any()),
        })
    frame = pd.DataFrame(details)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out.with_suffix(".csv"), index=False)
    report = {"plan": str(plan_path), "step_s": step_s, "tasks": len(frame),
              "passed": int(frame["pass"].sum()), "failed": int((~frame["pass"]).sum()),
              "all_pass": bool(len(frame) and frame["pass"].all()),
              "max_bad_elevation": int(frame["bad_elevation_samples"].max()) if len(frame) else 0,
              "max_bad_darkness": int(frame["bad_darkness_samples"].max()) if len(frame) else 0,
              "max_bad_illumination": int(frame["bad_satellite_illumination_samples"].max()) if len(frame) else 0,
              "exact_endpoints_included": bool(frame["exact_end_included"].all()),
              "bad_sgp4_samples": int(frame["bad_sgp4_samples"].sum()),
              "warning": "Discrete sampling is not a continuous-time proof; TLEs from Aug 2-4 are extrapolated around the Aug 1-7, 2026 UTC planning interval."}
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--step", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.out, args.step), indent=2))
