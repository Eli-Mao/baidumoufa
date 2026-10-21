"""Window assembly, schema validation, statistics and cache management."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config, io_schema


def assemble_windows(raw_windows: pd.DataFrame, sat_meta: pd.DataFrame) -> pd.DataFrame:
    if raw_windows.empty:
        raise ValueError("Propagation produced no usable observation windows")
    meta = sat_meta.set_index("sat_id")
    raw = raw_windows.copy()
    unknown = set(raw["sat_id"].astype(int)) - set(meta.index.astype(int))
    if unknown:
        raise ValueError(f"Window rows reference unknown satellites: {sorted(unknown)[:10]}")
    raw["priority"] = raw["sat_id"].map(meta["priority"])
    raw["priority_score"] = raw["sat_id"].map(meta["priority_score"]).astype("int64")
    raw["dur_s"] = raw["t_end_s"] - raw["t_start_s"]
    raw = raw.loc[(raw["dur_s"] >= config.MIN_DUR_S) & (raw["dur_s"] > 0)].copy()
    raw = raw.sort_values(["station_id", "sat_id", "t_start_s"]).reset_index(drop=True)
    prior_end: dict[tuple[int, int], float] = {}
    for row in raw.itertuples(index=False):
        key = (int(row.station_id), int(row.sat_id))
        if row.t_start_s < prior_end.get(key, float("-inf")) - 1e-6:
            raise ValueError(f"Overlapping windows for station/satellite {key}")
        prior_end[key] = float(row.t_end_s)
    raw = raw.sort_values(["t_start_s", "station_id", "sat_id"]).reset_index(drop=True)
    raw.insert(0, "window_id", range(1, len(raw) + 1))
    raw["t_start_utc"] = raw["t_start_s"].map(io_schema.offset_to_utc)
    raw["t_end_utc"] = raw["t_end_s"].map(io_schema.offset_to_utc)
    return io_schema.validate_frame(raw, "windows")


def window_statistics(windows: pd.DataFrame, sat_meta: pd.DataFrame | None = None) -> dict[str, object]:
    total = int(sat_meta["sat_id"].nunique()) if sat_meta is not None else int(windows["sat_id"].nunique())
    visible = int(windows["sat_id"].nunique()) if not windows.empty else 0
    durations = windows["dur_s"] if not windows.empty else pd.Series(dtype=float)
    return {"window_count": int(len(windows)), "satellites_with_windows": visible,
            "satellites_without_windows": max(0, total - visible),
            "duration_seconds": {"min": float(durations.min()) if len(durations) else None,
                                 "median": float(durations.median()) if len(durations) else None,
                                 "max": float(durations.max()) if len(durations) else None}}


def load_or_build(*, tle_df=None, stations=None, sat_meta=None, force: bool = False,
                  target_ids: list[int] | None = None, step_s: float | None = None,
                  days: int | None = None, cache_path: Path | None = None) -> pd.DataFrame:
    cache = Path(cache_path or config.WINDOWS_CSV)
    # Subset experiments use their own cache to avoid poisoning the full catalog cache.
    if cache_path is None and target_ids is not None:
        raise ValueError("Subset propagation requires an explicit cache_path")
    if cache.exists() and not force:
        return io_schema.load_windows(cache)
    from . import propagate
    tle_df = tle_df if tle_df is not None else io_schema.read_tle_raw()
    stations = stations if stations is not None else io_schema.read_stations_raw()
    if sat_meta is None:
        sat_meta = io_schema.build_sat_meta(tle_df, io_schema.read_priority_raw())
    if target_ids is not None:
        selected = set(map(int, target_ids))
        tle_df = tle_df[tle_df["sat_id"].isin(selected)].copy()
        sat_meta = sat_meta[sat_meta["sat_id"].isin(selected)].copy()
        if len(tle_df) != len(selected):
            raise ValueError("At least one selected target is missing from the TLE catalog")
    raw = propagate.propagate_windows(tle_df, stations, days=days, step_s=step_s)
    windows = assemble_windows(raw, sat_meta)
    io_schema.save_windows(windows, cache)
    return windows
