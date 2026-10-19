"""窗口表组装与自检。分区：**楼心荡**。

本模块负责把 :mod:`satplan.propagate` 算出的原始可见区间，
整理成全队统一使用的 ``windows.csv``，并在落盘前自检。

★窗口表是全队**唯一的数据源**：Iceswing 的调度、Priime 的评分都只读它。
因此这里的产物一旦定版，改动必须通知全队。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config, io_schema


def assemble_windows(
    raw_windows: pd.DataFrame,
    sat_meta: pd.DataFrame,
) -> pd.DataFrame:
    """把原始可见区间补全成完整契约的窗口表。

    需要补齐的字段：
      * ``window_id``  ：全表唯一、连续
      * ``priority`` / ``priority_score`` ：由 ``sat_meta`` 关联填入
      * ``dur_s``      ：``t_end_s - t_start_s``
      * ``t_start_utc`` / ``t_end_utc`` ：由 ``io_schema.offset_to_utc`` 换算

    自检项（不通过直接抛错，不要静默产出坏数据）：
      * 每颗卫星在每个站点的窗口不重叠；
      * ``dur_s > 0``；
      * 所有 ``sat_id`` 都能在 ``sat_meta`` 中找到（否则说明有 Alpha-5 星被漏掉）。
    """
    raise NotImplementedError("楼心荡：实现窗口表组装与自检。")


def window_statistics(windows: pd.DataFrame) -> dict[str, object]:
    """产出可直接贴进群里的统计：窗口总数、有窗口卫星数、无窗口卫星数、时长分布。"""
    raise NotImplementedError("楼心荡：实现窗口统计。")


def load_or_build(
    *,
    tle_df: pd.DataFrame | None = None,
    stations: pd.DataFrame | None = None,
    sat_meta: pd.DataFrame | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """缓存友好的入口：``data/interim/windows.csv`` 存在且未强制重算时直接加载。

    这是 pipeline 默认调用的入口——避免每次跑全链路都重算 6 天窗口。
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
    return windows
