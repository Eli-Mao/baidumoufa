"""Chunked Skyfield/SGP4 propagation and sampled visibility-window search."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

from . import config, io_schema


def _times(ts, start: datetime, offsets: np.ndarray):
    stamp = start + timedelta(seconds=float(offsets[0]))
    base = ts.utc(stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)
    return base + offsets / 86400.0


def _valid_at(sat, site, earth, sun, eph, ts, instant: datetime) -> tuple[bool, float]:
    t = ts.utc(instant.year, instant.month, instant.day, instant.hour,
               instant.minute, instant.second + instant.microsecond / 1e6)
    elevation = float((sat - site).at(t).altaz()[0].degrees)
    sun_alt = float((earth + site).at(t).observe(sun).apparent().altaz()[0].degrees)
    sunlit = bool(sat.at(t).is_sunlit(eph))
    return (np.isfinite(elevation) and np.isfinite(sun_alt)
            and config.MIN_ELEV_DEG <= elevation <= config.MAX_ELEV_DEG
            and sun_alt < config.SUN_ELEV_MAX_DEG
            and (sunlit or not config.REQUIRE_SAT_SUNLIT)), elevation


def _refine_edge(sat, site, earth, sun, eph, ts, left: datetime, right: datetime,
                 left_valid: bool, tolerance_s: float) -> datetime:
    while (right - left).total_seconds() > tolerance_s:
        mid = left + (right - left) / 2
        if _valid_at(sat, site, earth, sun, eph, ts, mid)[0] == left_valid:
            left = mid
        else:
            right = mid
    return right if not left_valid else left


def _runs(mask: np.ndarray):
    indexes = np.flatnonzero(mask)
    if not len(indexes):
        return
    first = previous = int(indexes[0])
    for idx in indexes[1:]:
        idx = int(idx)
        if idx != previous + 1:
            yield first, previous
            first = idx
        previous = idx
    yield first, previous


def propagate_windows(
    tle_df: pd.DataFrame | None = None,
    stations: pd.DataFrame | None = None,
    *,
    t0_utc: str | None = None,
    days: int | None = None,
    step_s: float | None = None,
    workers: int = 1,
    ephemeris_path: Path | None = None,
    checkpoint_path: Path | None = None,
) -> pd.DataFrame:
    """Propagate one satellite/site/time chunk at a time.

    ``step_s`` controls candidate detection only. Detected boundaries are
    bisected to ``WINDOW_BOUNDARY_TOLERANCE_S``; windows shorter than the
    official minimum observing duration are discarded. A coarse grid can miss
    wholly-contained short windows, so reports must retain its value.
    """
    del workers  # Serial chunking bounds memory; process parallelism is a later optimization.
    if step_s is None:
        step_s = config.WINDOW_COARSE_STEP_S
    if step_s <= 0 or days is None and config.PLAN_DAYS <= 0:
        raise ValueError("step_s and planning duration must be positive")
    tle_df = tle_df if tle_df is not None else io_schema.read_tle_raw()
    stations = stations if stations is not None else io_schema.read_stations_raw()
    start = io_schema.parse_utc(t0_utc or config.PLAN_T0_UTC).astimezone(timezone.utc)
    duration_days = int(days if days is not None else config.PLAN_DAYS)
    if duration_days <= 0:
        raise ValueError("days must be positive")
    end = start + timedelta(days=duration_days)
    eph_path = Path(ephemeris_path or config.EPHEMERIS_FILE)
    if not eph_path.is_file():
        raise FileNotFoundError(f"Skyfield ephemeris is required: {eph_path}")
    ts = load.timescale()
    eph = load(str(eph_path))
    earth, sun = eph["earth"], eph["sun"]
    station_objects = {
        int(row.station_id): wgs84.latlon(float(row.lat_deg), float(row.lon_deg), elevation_m=float(row.alt_m))
        for row in stations.itertuples(index=False)
    }
    step = float(step_s)
    chunk_s = config.PROPAGATION_CHUNK_DAYS * 86400
    records: list[dict[str, object]] = []
    checkpoint = Path(checkpoint_path) if checkpoint_path else None
    completed: set[tuple[int, int]] = set()
    if checkpoint and checkpoint.exists():
        previous = pd.read_csv(checkpoint)
        if not previous.empty:
            records.extend(previous.to_dict(orient="records"))
            completed = set(zip(previous["sat_id"].astype(int), previous["station_id"].astype(int)))
    for tle in tle_df.to_dict(orient="records"):
        sat = EarthSatellite(str(tle["line1"]), str(tle["line2"]), str(tle["name"]), ts)
        epoch = io_schema.parse_utc(io_schema._epoch_from_tle(pd.Series(tle)))
        sat_id = int(tle["sat_id"])
        for sid, site in station_objects.items():
            if (sat_id, sid) in completed:
                continue
            cursor = start
            carry_valid = None
            carry_elev = None
            open_start = None
            peak = -90.0
            while cursor < end:
                chunk_end = min(end, cursor + timedelta(seconds=chunk_s))
                total = (chunk_end - cursor).total_seconds()
                count = int(np.floor(total / step))
                offsets = np.arange(count + 1, dtype=np.float64) * step
                if offsets[-1] < total:
                    offsets = np.append(offsets, total)
                times = _times(ts, cursor, offsets)
                elevation = np.asarray((sat - site).at(times).altaz()[0].degrees, dtype=np.float64)
                sun_alt = np.asarray((earth + site).at(times).observe(sun).apparent().altaz()[0].degrees,
                                     dtype=np.float64)
                sunlit = np.asarray(sat.at(times).is_sunlit(eph), dtype=bool)
                valid = (np.isfinite(elevation) & np.isfinite(sun_alt)
                         & (elevation >= config.MIN_ELEV_DEG)
                         & (elevation <= config.MAX_ELEV_DEG)
                         & (sun_alt < config.SUN_ELEV_MAX_DEG))
                if config.REQUIRE_SAT_SUNLIT:
                    valid &= sunlit
                if carry_valid is not None and valid[0] != carry_valid:
                    edge = _refine_edge(sat, site, earth, sun, eph, ts,
                                        cursor - timedelta(seconds=step), cursor,
                                        bool(carry_valid), config.WINDOW_BOUNDARY_TOLERANCE_S)
                    if carry_valid and open_start is not None:
                        if (edge - open_start).total_seconds() >= config.MIN_DUR_S:
                            records.append(_window_record(sat_id, sid, open_start, edge, peak, start, epoch))
                        open_start, peak = None, -90.0
                    elif valid[0]:
                        open_start = edge
                for a, b in _runs(valid):
                    if a == 0 and carry_valid is True:
                        a = 1
                    if a > b:
                        continue
                    left_idx = a - 1 if a > 0 else a
                    right_idx = b + 1 if b + 1 < len(valid) else b
                    run_start = cursor + timedelta(seconds=float(offsets[a]))
                    run_end = cursor + timedelta(seconds=float(offsets[b]))
                    if a > 0 and not valid[a - 1]:
                        run_start = _refine_edge(sat, site, earth, sun, eph, ts,
                                                 cursor + timedelta(seconds=float(offsets[a - 1])), run_start,
                                                 False, config.WINDOW_BOUNDARY_TOLERANCE_S)
                    elif a == 0 and carry_valid is False:
                        run_start = _refine_edge(sat, site, earth, sun, eph, ts,
                                                 cursor - timedelta(seconds=step), cursor,
                                                 False, config.WINDOW_BOUNDARY_TOLERANCE_S)
                    if b + 1 < len(valid) and not valid[b + 1]:
                        run_end = _refine_edge(sat, site, earth, sun, eph, ts,
                                               run_end, cursor + timedelta(seconds=float(offsets[right_idx])),
                                               True, config.WINDOW_BOUNDARY_TOLERANCE_S)
                    window_peak = float(np.nanmax(elevation[a:b + 1]))
                    if open_start is None:
                        open_start, peak = run_start, window_peak
                    else:
                        peak = max(peak, window_peak)
                    if b + 1 < len(valid) and not valid[b + 1]:
                        if (run_end - open_start).total_seconds() >= config.MIN_DUR_S:
                            records.append(_window_record(sat_id, sid, open_start, run_end, peak, start, epoch))
                        open_start, peak = None, -90.0
                carry_valid = bool(valid[-1])
                carry_elev = float(elevation[-1])
                cursor = chunk_end
            if carry_valid and open_start is not None:
                if (end - open_start).total_seconds() >= config.MIN_DUR_S:
                    records.append(_window_record(sat_id, sid, open_start, end, peak, start, epoch))
            if checkpoint:
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(records).to_csv(checkpoint, index=False)
                completed.add((sat_id, sid))
    return pd.DataFrame(records, columns=["station_id", "sat_id", "t_start_s", "t_end_s", "max_elev_deg",
                                         "tle_epoch_utc", "tle_age_days", "window_detection_step_s"])


def _window_record(sat_id: int, station_id: int, start: datetime, end: datetime,
                   peak: float, t0: datetime, epoch: datetime) -> dict[str, object]:
    return {"station_id": station_id, "sat_id": sat_id,
            "t_start_s": (start - t0).total_seconds(),
            "t_end_s": (end - t0).total_seconds(),
            "max_elev_deg": peak, "tle_epoch_utc": io_schema.to_utc_str(epoch),
            "tle_age_days": (t0 - epoch).total_seconds() / 86400.0,
            "window_detection_step_s": config.WINDOW_COARSE_STEP_S}


def cross_validate(windows: pd.DataFrame, *, sample_sat_ids: list[int] | None = None,
                   step_s: float = 1.0) -> pd.DataFrame:
    """Recompute samples around stored boundaries for selected satellites."""
    if windows.empty:
        return pd.DataFrame(columns=["sat_id", "station_id", "boundary", "sampled_valid"])
    chosen = set(sample_sat_ids or windows["sat_id"].drop_duplicates().head(8).astype(int))
    tle_df = io_schema.read_tle_raw()
    stations = io_schema.read_stations_raw()
    by_id = {int(x.sat_id): x for x in tle_df.itertuples(index=False)}
    sites = {int(x.station_id): wgs84.latlon(float(x.lat_deg), float(x.lon_deg), elevation_m=float(x.alt_m))
             for x in stations.itertuples(index=False)}
    ts, eph = load.timescale(), load(str(config.EPHEMERIS_FILE))
    earth, sun = eph["earth"], eph["sun"]
    t0 = io_schema.parse_utc(config.PLAN_T0_UTC)
    rows = []
    for row in windows.loc[windows["sat_id"].isin(chosen)].itertuples(index=False):
        satrow = by_id[int(row.sat_id)]
        sat = EarthSatellite(satrow.line1, satrow.line2, satrow.name, ts)
        for label, offset in (("start_inside", row.t_start_s + step_s),
                              ("end_inside", row.t_end_s - step_s)):
            instant = t0 + timedelta(seconds=float(offset))
            ok, elev = _valid_at(sat, sites[int(row.station_id)], earth, sun, eph, ts, instant)
            rows.append({"sat_id": int(row.sat_id), "station_id": int(row.station_id),
                         "boundary": label, "sample_offset_s": offset,
                         "sampled_valid": ok, "elevation_deg": elev})
    return pd.DataFrame(rows)
