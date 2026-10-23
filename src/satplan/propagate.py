"""Chunked Skyfield/SGP4 propagation and sampled visibility-window search."""
from __future__ import annotations

import hashlib
import json
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
    return (sat.at(t).message is None and np.isfinite(elevation) and np.isfinite(sun_alt)
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


def _valid_many_at(sat, site, earth, sun, eph, ts, instants: list[datetime]) -> np.ndarray:
    """Evaluate the unchanged physical predicate for many boundary times at once."""
    years = np.fromiter((x.year for x in instants), dtype=np.int64)
    months = np.fromiter((x.month for x in instants), dtype=np.int64)
    days = np.fromiter((x.day for x in instants), dtype=np.int64)
    hours = np.fromiter((x.hour for x in instants), dtype=np.int64)
    minutes = np.fromiter((x.minute for x in instants), dtype=np.int64)
    seconds = np.fromiter((x.second + x.microsecond / 1e6 for x in instants), dtype=np.float64)
    t = ts.utc(years, months, days, hours, minutes, seconds)
    elevation = np.asarray((sat - site).at(t).altaz()[0].degrees, dtype=np.float64)
    sun_alt = np.asarray((earth + site).at(t).observe(sun).apparent().altaz()[0].degrees,
                         dtype=np.float64)
    valid = (np.isfinite(elevation) & np.isfinite(sun_alt)
             & (elevation >= config.MIN_ELEV_DEG)
             & (elevation <= config.MAX_ELEV_DEG)
             & (sun_alt < config.SUN_ELEV_MAX_DEG))
    if config.REQUIRE_SAT_SUNLIT:
        valid &= np.asarray(sat.at(t).is_sunlit(eph), dtype=bool)
    valid &= np.asarray([message is None for message in sat.at(t).message], dtype=bool)
    return valid


def _refine_edges(sat, site, earth, sun, eph, ts,
                  edges: list[tuple[datetime, datetime, bool]], tolerance_s: float
                  ) -> list[datetime]:
    """Bisect multiple edges in vectorized Skyfield calls without changing predicates."""
    left = [edge[0] for edge in edges]
    right = [edge[1] for edge in edges]
    left_valid = np.asarray([edge[2] for edge in edges], dtype=bool)
    while True:
        active = [i for i, (lo, hi) in enumerate(zip(left, right))
                  if (hi - lo).total_seconds() > tolerance_s]
        if not active:
            break
        mids = [left[i] + (right[i] - left[i]) / 2 for i in active]
        mid_valid = _valid_many_at(sat, site, earth, sun, eph, ts, mids)
        for i, mid, valid in zip(active, mids, mid_valid):
            if bool(valid) == bool(left_valid[i]):
                left[i] = mid
            else:
                right[i] = mid
    return [hi if not valid else lo for lo, hi, valid in zip(left, right, left_valid)]


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


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _checkpoint_signature(tle_df: pd.DataFrame, stations: pd.DataFrame, start: datetime,
                          days: int, step_s: float, ephemeris_path: Path) -> str:
    digest = hashlib.sha256()
    for frame, columns in ((tle_df, ("sat_id", "line1", "line2")),
                           (stations, ("station_id", "lat_deg", "lon_deg", "alt_m"))):
        digest.update(frame.loc[:, list(columns)].to_csv(index=False).encode("utf-8"))
    settings = {"start_utc": start.isoformat(), "days": days, "step_s": step_s,
                "min_elev_deg": config.MIN_ELEV_DEG, "max_elev_deg": config.MAX_ELEV_DEG,
                "sun_elev_max_deg": config.SUN_ELEV_MAX_DEG,
                "require_sat_sunlit": config.REQUIRE_SAT_SUNLIT,
                "min_duration_s": config.MIN_DUR_S,
                "edge_tolerance_s": config.WINDOW_BOUNDARY_TOLERANCE_S}
    digest.update(json.dumps(settings, sort_keys=True).encode("utf-8"))
    with ephemeris_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    # Build the complete six-day UTC grid once and share it across all targets.
    total_s = duration_days * 86400.0
    offsets = np.arange(int(total_s // step) + 1, dtype=np.float64) * step
    if offsets[-1] < total_s:
        offsets = np.append(offsets, total_s)
    grid_times = _times(ts, start, offsets)
    chunk_points = max(1, int(config.PROPAGATION_CHUNK_DAYS * 86400 / step))
    time_chunks = [grid_times[lo:min(len(offsets), lo + chunk_points)]
                   for lo in range(0, len(offsets), chunk_points)]
    sun_alt_cache: dict[int, np.ndarray] = {}
    sunlit_cache: dict[int, np.ndarray] = {}
    records: list[dict[str, object]] = []
    checkpoint = Path(checkpoint_path) if checkpoint_path else None
    completed: set[tuple[int, int]] = set()
    completed_satellites: set[int] = set()
    signature = _checkpoint_signature(tle_df, stations, start, duration_days, step, eph_path)
    metadata = checkpoint.with_suffix(checkpoint.suffix + ".meta.json") if checkpoint else None
    chunk_dir = checkpoint.with_name(checkpoint.name + ".chunks") if checkpoint else None
    if checkpoint and (checkpoint.exists() or metadata.exists()):
        if metadata is None or not metadata.exists():
            raise ValueError(f"Checkpoint metadata missing; refusing unsafe resume: {checkpoint}")
        checkpoint_info = json.loads(metadata.read_text(encoding="utf-8"))
        if checkpoint_info.get("signature") != signature:
            raise ValueError(f"Checkpoint inputs/settings do not match this run: {checkpoint}")
        chunk_dir.mkdir(parents=True, exist_ok=True)
        if checkpoint_info.get("format") != "target_chunks_v1":
            # Migrate only satellite/site pairs known complete in the legacy journal.
            previous = pd.read_csv(checkpoint) if checkpoint.exists() else pd.DataFrame(columns=[
                "station_id", "sat_id", "t_start_s", "t_end_s", "max_elev_deg",
                "tle_epoch_utc", "tle_age_days", "window_detection_step_s"])
            old_pairs = {tuple(map(int, pair)) for pair in checkpoint_info.get("completed_pairs", [])}
            completed_satellites = {sid for sid in tle_df["sat_id"].astype(int).unique()
                                    if all((sid, st) in old_pairs for st in station_objects)}
            for sid in completed_satellites:
                chunk = chunk_dir / f"sat_{sid}.csv"
                temporary = chunk.with_name(chunk.name + ".tmp")
                previous.loc[previous["sat_id"].astype(int) == sid].to_csv(temporary, index=False)
                temporary.replace(chunk)
            checkpoint_info = {"format": "target_chunks_v1", "status": "running",
                               "signature": signature,
                               "completed_satellites": sorted(completed_satellites),
                               "row_count": sum(len(pd.read_csv(chunk_dir / f"sat_{sid}.csv"))
                                                for sid in completed_satellites)}
            _atomic_text(metadata, json.dumps(checkpoint_info, indent=2))
        completed_satellites = set(map(int, checkpoint_info.get("completed_satellites", [])))
        completed = {(sid, int(station_id)) for sid in completed_satellites
                     for station_id in station_objects}
        for sat_id in sorted(completed_satellites):
            chunk = chunk_dir / f"sat_{sat_id}.csv"
            if not chunk.is_file():
                raise ValueError(f"Checkpoint chunk missing for completed satellite {sat_id}: {chunk}")
            previous = pd.read_csv(chunk)
            records.extend(previous.to_dict(orient="records"))
    for target_index, tle in enumerate(tle_df.to_dict(orient="records"), start=1):
        sat = EarthSatellite(str(tle["line1"]), str(tle["line2"]), str(tle["name"]), ts)
        epoch = io_schema.parse_utc(io_schema._epoch_from_tle(pd.Series(tle)))
        sat_id = int(tle["sat_id"])
        if all((sat_id, sid) in completed for sid in station_objects):
            print(f"[propagate] target={target_index}/{len(tle_df)} sat_id={sat_id} "
                  f"pairs_done={len(completed)} windows={len(records)} (checkpoint)", flush=True)
            continue
        if checkpoint:
            import psutil, shutil
            if psutil.virtual_memory().available < 200 * 1024**2:
                raise MemoryError("Less than 200 MiB available RAM; resume from saved target chunks")
            if shutil.disk_usage(checkpoint.parent).free < 2 * 1024**3:
                raise OSError("Less than 2 GiB disk free; resume from saved target chunks")
        target_records: list[dict[str, object]] = []
        if config.REQUIRE_SAT_SUNLIT and sat_id not in sunlit_cache:
            chunks = []
            for times in time_chunks:
                chunks.append(np.asarray(sat.at(times).is_sunlit(eph), dtype=bool))
            sunlit_cache[sat_id] = np.concatenate(chunks)
        sgp4_valid = np.concatenate([
            np.asarray([message is None for message in sat.at(times).message], dtype=bool)
            for times in time_chunks])
        for sid, site in station_objects.items():
            if (sat_id, sid) in completed:
                continue
            if sid not in sun_alt_cache:
                site_sun = []
                for times in time_chunks:
                    site_sun.append(np.asarray(
                        (earth + site).at(times).observe(sun).apparent().altaz()[0].degrees,
                        dtype=np.float64))
                sun_alt_cache[sid] = np.concatenate(site_sun)
            elevations = []
            for times in time_chunks:
                elevations.append(np.asarray((sat - site).at(times).altaz()[0].degrees,
                                             dtype=np.float64))
            elevation = np.concatenate(elevations)
            sun_alt = sun_alt_cache[sid]
            valid = (sgp4_valid & np.isfinite(elevation) & np.isfinite(sun_alt)
                     & (elevation >= config.MIN_ELEV_DEG)
                     & (elevation <= config.MAX_ELEV_DEG)
                     & (sun_alt < config.SUN_ELEV_MAX_DEG))
            if config.REQUIRE_SAT_SUNLIT:
                valid &= sunlit_cache[sat_id]
            detected = []
            edges = []
            for a, b in _runs(valid):
                run_start = start + timedelta(seconds=float(offsets[a]))
                run_end = start + timedelta(seconds=float(offsets[b]))
                if a > 0 and not valid[a - 1]:
                    edges.append((start + timedelta(seconds=float(offsets[a - 1])), run_start, False))
                    start_edge = len(edges) - 1
                else:
                    start_edge = None
                if b + 1 < len(valid) and not valid[b + 1]:
                    edges.append((run_end, start + timedelta(seconds=float(offsets[b + 1])), True))
                    end_edge = len(edges) - 1
                else:
                    end_edge = None
                detected.append((a, b, run_start, run_end, start_edge, end_edge))
            refined = _refine_edges(sat, site, earth, sun, eph, ts, edges,
                                    config.WINDOW_BOUNDARY_TOLERANCE_S) if edges else []
            for a, b, run_start, run_end, start_edge, end_edge in detected:
                if start_edge is not None:
                    run_start = refined[start_edge]
                if end_edge is not None:
                    run_end = refined[end_edge]
                if (run_end - run_start).total_seconds() >= config.MIN_DUR_S:
                    record = _window_record(sat_id, sid, run_start, run_end,
                                            float(np.nanmax(elevation[a:b + 1])), start, epoch)
                    records.append(record)
                    target_records.append(record)
            completed.add((sat_id, sid))
        sunlit_cache.pop(sat_id, None)  # Only the current target needs illumination samples.
        if checkpoint:
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            chunk_dir.mkdir(parents=True, exist_ok=True)
            chunk = chunk_dir / f"sat_{sat_id}.csv"
            temporary = chunk.with_name(chunk.name + ".tmp")
            columns = ["station_id", "sat_id", "t_start_s", "t_end_s", "max_elev_deg",
                       "tle_epoch_utc", "tle_age_days", "window_detection_step_s"]
            pd.DataFrame(target_records, columns=columns).to_csv(temporary, index=False)
            temporary.replace(chunk)
            completed_satellites.add(sat_id)
            _atomic_text(metadata, json.dumps({"format": "target_chunks_v1", "status": "running",
                                               "signature": signature,
                                               "completed_satellites": sorted(completed_satellites),
                                               "row_count": len(records)}, indent=2))
        print(f"[propagate] target={target_index}/{len(tle_df)} sat_id={sat_id} "
              f"pairs_done={len(completed)} windows={len(records)}", flush=True)
    columns = ["station_id", "sat_id", "t_start_s", "t_end_s", "max_elev_deg",
               "tle_epoch_utc", "tle_age_days", "window_detection_step_s"]
    if checkpoint:
        temporary = checkpoint.with_name(checkpoint.name + ".tmp")
        pd.DataFrame(records, columns=columns).to_csv(temporary, index=False)
        temporary.replace(checkpoint)
        _atomic_text(metadata, json.dumps({"format": "target_chunks_v1", "status": "completed",
                                           "signature": signature,
                                           "completed_satellites": sorted(completed_satellites),
                                           "row_count": len(records)}, indent=2))
    return pd.DataFrame(records, columns=columns)


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
