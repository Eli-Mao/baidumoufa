"""轨道传播与可见性计算。分区：**楼心荡**。

职责边界：
    输入 ``轨道.txt``（10000 颗 TLE）与 ``站址.txt``（10 个站），
    输出每一颗卫星 × 每一个站点的候选可见窗口。

可见性判定口径（已按问答实现，登记在 config.py）：
    1. 站点仰角 ∈ [MIN_ELEV_DEG, MAX_ELEV_DEG] = [10, 85] 度；
    2. 测站太阳高度角 < SUN_ELEV_MAX_DEG = -6 度（测站处于暗夜）；
    3. 卫星本身受太阳照亮（REQUIRE_SAT_SUNLIT）。

实现依赖：``skyfield`` + ``sgp4``（只在本模块内部 import，避免全项目强依赖）。
参考性能：10000 星 × 10 站 × 6 天，8 进程并行约 50 秒，产出约 57 万个窗口。

★本文件为待实现骨架，函数签名与返回契约已冻结。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config, io_schema


def propagate_windows(
    tle_df: pd.DataFrame | None = None,
    stations: pd.DataFrame | None = None,
    *,
    t0_utc: str | None = None,
    days: int | None = None,
    step_s: float = 1.0,
    workers: int = 8,
) -> pd.DataFrame:
    """计算全部候选可见窗口，返回满足 ``windows`` 契约的 DataFrame。

    Parameters
    ----------
    tle_df : DataFrame | None
        由 :func:`satplan.io_schema.read_tle_raw` 产出；为 None 时自行读取原始文件。
        列：``sat_id`` / ``satnum_raw`` / ``name`` / ``line1`` / ``line2``。
    stations : DataFrame | None
        由 :func:`satplan.io_schema.read_stations_raw` 产出。
    t0_utc : str | None
        规划期起点，默认取 ``config.PLAN_T0_UTC``（★该值待确认）。
    days : int | None
        规划期长度，默认 ``config.PLAN_DAYS``。
    step_s : float
        采样步长（秒）。先按 1 s 实现，若性能不够可先粗扫再细化。
    workers : int
        并行进程数。

    Returns
    -------
    DataFrame
        列必须与 :data:`satplan.io_schema.SCHEMA_WINDOWS` 完全一致：
        ``window_id, station_id, sat_id, priority, priority_score,
        t_start_s, t_end_s, dur_s, t_start_utc, t_end_utc, max_elev_deg``

    Notes
    -----
    实现完成后请务必：
      * 用 :func:`satplan.io_schema.save_windows` 落盘到 ``config.WINDOWS_CSV``；
      * 跑 :mod:`tests.test_contract` 确认列名/类型无误；
      * 在群里报出实测窗口总数、有窗口的卫星数、无窗口卫星数（用于交叉验证）。
    """
    raise NotImplementedError(
        "楼心荡：请在 propagate.py 中实现 SGP4 传播 + 可见性判定，"
        "输出满足 io_schema.SCHEMA_WINDOWS 的窗口表。"
    )


def cross_validate(
    windows: pd.DataFrame,
    *,
    sample_sat_ids: list[int] | None = None,
    step_s: float = 1.0,
) -> pd.DataFrame:
    """抽样逐秒复核：用独立路径重算若干卫星，比对窗口边界误差。

    这是楼心荡此前"逐秒交叉验证，0 违规、0 漏窗口，边界误差 < 1 秒"的固化版本，
    目的是让每个人都能一键复跑，而不是只在本地跑过一次。
    """
    raise NotImplementedError("楼心荡：把逐秒交叉验证固化成可复跑的函数。")


def save_windows_csv(windows: pd.DataFrame, path: Path | None = None) -> None:
    """窗口表落盘（走契约层，自动做列名校验）。"""
    io_schema.save_windows(windows, path or config.WINDOWS_CSV)
