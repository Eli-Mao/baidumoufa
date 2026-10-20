"""窗口表组装与自检。分区：**楼心荡**。

本模块负责把 :mod:`satplan.propagate` 算出的原始可见区间，
整理成全队统一使用的 ``windows.csv``，并在落盘前自检。

★窗口表是全队**唯一的数据源**：Iceswing 的调度、Priime 的评分都只读它。
因此这里的产物一旦定版，改动必须通知全队。
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, io_schema


def _utc_strings(t0_iso: str, secs: np.ndarray) -> np.ndarray:
    """t0 + 秒 -> 与 io_schema.offset_to_utc 相同格式的 ISO8601 串（毫秒、结尾 Z），向量化。"""
    t0 = io_schema.parse_utc(t0_iso).astimezone(_dt.timezone.utc).replace(tzinfo=None)
    base = np.datetime64(t0, "ms")
    ms = np.round(np.asarray(secs, float) * 1000).astype(np.int64).astype("timedelta64[ms]")
    return np.char.add(np.datetime_as_string(base + ms, unit="ms"), "Z").astype(object)


def _period_of(windows: pd.DataFrame) -> tuple[str, float]:
    """由窗口表反推规划期起点（ISO8601）与天数：起点 = t_start_utc − t_start_s。"""
    first = windows.iloc[0]
    t0 = io_schema.parse_utc(first["t_start_utc"]) - _dt.timedelta(seconds=float(first["t_start_s"]))
    return io_schema.to_utc_str(t0), float(windows.attrs.get("days", config.PLAN_DAYS))


def assemble_windows(
    raw_windows: pd.DataFrame,
    sat_meta: pd.DataFrame,
) -> pd.DataFrame:
    """把原始可见区间补全成完整契约的窗口表。

    需要补齐的字段：
      * ``window_id``  ：全表唯一、连续（从 1 开始，按 站、起点、卫星 排序）
      * ``priority`` / ``priority_score`` ：由 ``sat_meta`` 关联填入
      * ``dur_s``      ：``t_end_s - t_start_s``
      * ``t_start_utc`` / ``t_end_utc`` ：规划期起点 + 秒，格式与 ``io_schema.offset_to_utc`` 相同。
        起点取 ``raw_windows.attrs['t0_utc']``（propagate 实际用的起点），没有时取 ``config.PLAN_T0_UTC``。

    自检项（不通过直接抛错，不要静默产出坏数据）：
      * 每颗卫星在每个站点的窗口不重叠；
      * ``dur_s > 0``；
      * 所有 ``sat_id`` 都能在 ``sat_meta`` 中找到（否则说明有 Alpha-5 星被漏掉）。
    """
    need = ["station_id", "sat_id", "t_start_s", "t_end_s", "max_elev_deg"]
    missing = [c for c in need if c not in raw_windows.columns]
    if missing:
        raise io_schema.SchemaError(f"原始窗口表缺少列: {missing}")
    raw = raw_windows[need].copy()

    meta = sat_meta.set_index("sat_id")
    unknown = sorted(set(raw["sat_id"]) - set(meta.index))
    if unknown:
        raise io_schema.SchemaError(f"{len(unknown)} 颗卫星不在 sat_meta 中（Alpha-5 漏解码？）: {unknown[:10]}")

    dur = (raw["t_end_s"] - raw["t_start_s"]).round(3)
    if (dur <= 0).any():
        raise io_schema.SchemaError(f"{int((dur <= 0).sum())} 个窗口 dur_s <= 0")

    raw = raw.assign(dur_s=dur).sort_values(["station_id", "sat_id", "t_start_s"]).reset_index(drop=True)
    same = (raw["station_id"].to_numpy()[1:] == raw["station_id"].to_numpy()[:-1]) & \
           (raw["sat_id"].to_numpy()[1:] == raw["sat_id"].to_numpy()[:-1])
    overlap = same & (raw["t_start_s"].to_numpy()[1:] < raw["t_end_s"].to_numpy()[:-1])
    if overlap.any():
        raise io_schema.SchemaError(f"{int(overlap.sum())} 处同站同星的窗口重叠")

    t0_iso = raw_windows.attrs.get("t0_utc") or config.PLAN_T0_UTC
    w = raw.sort_values(["station_id", "t_start_s", "sat_id"]).reset_index(drop=True)
    out = pd.DataFrame({
        "window_id": np.arange(1, len(w) + 1, dtype=np.int64),
        "station_id": w["station_id"].astype("int64"),
        "sat_id": w["sat_id"].astype("int64"),
        "priority": w["sat_id"].map(meta["priority"]).astype(object),
        "priority_score": w["sat_id"].map(meta["priority_score"]).astype("int64"),
        "t_start_s": w["t_start_s"].astype(float),
        "t_end_s": w["t_end_s"].astype(float),
        "dur_s": w["dur_s"].astype(float),
        "t_start_utc": _utc_strings(t0_iso, w["t_start_s"]),
        "t_end_utc": _utc_strings(t0_iso, w["t_end_s"]),
        "max_elev_deg": w["max_elev_deg"].astype(float),
    })
    # 时间串与契约层的 offset_to_utc 必须逐字相同（抽几行核对）
    if len(out) and io_schema.parse_utc(t0_iso) == io_schema.t0():
        for i in np.linspace(0, len(out) - 1, min(5, len(out))).astype(int):
            if out.at[i, "t_start_utc"] != io_schema.offset_to_utc(out.at[i, "t_start_s"]):
                raise io_schema.SchemaError("t_start_utc 与 io_schema.offset_to_utc 不一致")
    out.attrs.update({k: v for k, v in raw_windows.attrs.items() if k in ("t0_utc", "days", "stats")})
    return io_schema.validate_frame(out, "windows", allow_extra=False)


def window_statistics(windows: pd.DataFrame) -> dict[str, object]:
    """产出可直接贴进群里的统计：窗口总数、有窗口卫星数、无窗口卫星数、时长分布。

    无窗口卫星按轨道状态分类（见 :func:`satplan.propagate.orbit_health`）：
    ``optically_unobservable``（轨道正常，但过站时测站是白天或卫星在地影中）、
    ``sgp4_error_at_start`` / ``implausible`` / ``reentered``（外推失效或已再入）。
    """
    from . import propagate  # 延迟导入，避免无 sgp4 环境下 import 失败

    t0_iso, days = _period_of(windows)
    orbit = propagate.orbit_health(t0_utc=t0_iso, days=int(round(days)))
    has = set(windows["sat_id"])
    no = orbit[~orbit["sat_id"].isin(has)]
    reason = no["orbit_flag"].replace({"ok": "optically_unobservable"}).value_counts()
    dur = windows["dur_s"]
    stats: dict[str, object] = {
        "t0_utc": t0_iso,
        "days": days,
        "n_windows": int(len(windows)),
        "n_sats_total": int(len(orbit)),
        "n_sats_with_windows": int(len(has)),
        "n_sats_without_windows": int(len(no)),
        "without_by_reason": {k: int(reason.get(k, 0)) for k in
                              ("optically_unobservable", "sgp4_error_at_start", "implausible", "reentered")},
        "sats_with_windows_by_priority": {k: int(v) for k, v in
                                          windows.drop_duplicates("sat_id")["priority"].value_counts().items()},
        "windows_per_station": {int(k): int(v) for k, v in windows["station_id"].value_counts().sort_index().items()},
        "dur_s": {"p10": round(float(dur.quantile(0.1)), 1), "p50": round(float(dur.median()), 1),
                  "p90": round(float(dur.quantile(0.9)), 1), "max": round(float(dur.max()), 1),
                  "total_h": round(float(dur.sum()) / 3600, 1)},
        "orbit_flag_all_sats": {k: int(v) for k, v in orbit["orbit_flag"].value_counts().items()},
    }
    if config.SAT_META_CSV.exists():
        meta = io_schema.load_sat_meta()
        no_pri = meta[~meta["sat_id"].isin(has)]["priority"].value_counts()
        stats["sats_without_windows_by_priority"] = {k: int(v) for k, v in no_pri.items()}
    return stats


def load_or_build(
    *,
    tle_df: pd.DataFrame | None = None,
    stations: pd.DataFrame | None = None,
    sat_meta: pd.DataFrame | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """缓存友好的入口：``data/interim/windows.csv`` 存在且未强制重算时直接加载。

    这是 pipeline 默认调用的入口——避免每次跑全链路都重算 6 天窗口。
    新算一遍时会打印窗口统计（可直接贴群）。
    """
    cache = Path(config.WINDOWS_CSV)
    if cache.exists() and not force:
        return io_schema.load_windows(cache)

    from . import propagate  # 延迟导入，避免无 skyfield 环境下 import 失败

    tle_df = tle_df if tle_df is not None else io_schema.read_tle_raw()
    stations = stations if stations is not None else io_schema.read_stations_raw()
    if sat_meta is None:
        priority_map = io_schema.read_priority_raw()
        sat_meta = io_schema.build_sat_meta(tle_df, priority_map)

    raw = propagate.propagate_windows(tle_df, stations)
    windows = assemble_windows(raw, sat_meta)
    io_schema.save_windows(windows, cache)
    print(json.dumps(window_statistics(windows), ensure_ascii=False, indent=2), flush=True)
    return windows
