"""全局口径常量。分区：川谷（契约层）。

【重要】所有赛题口径只在本文件维护。口径变更时只改这里，其它模块一律不写死数字。
标注「★待确认」的项以 docs/open_questions.md 为准，未确认前不要当成事实。
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_INTERIM = PROJECT_ROOT / "data" / "interim"
DATA_OUT = PROJECT_ROOT / "data" / "out"
REPORTS_DIR = PROJECT_ROOT / "reports"
EPHEMERIS_FILE = PROJECT_ROOT / "de421.bsp"

# 原始数据文件名（scripts/prepare_raw_data.py 会把 zip 解出成这些名字）
RAW_TLE_FILE = DATA_RAW / "orbits.tle"
RAW_STATION_FILE = DATA_RAW / "stations.txt"
RAW_PRIORITY_FILES = {
    "high": DATA_RAW / "priority_high.txt",
    "mid": DATA_RAW / "priority_medium.txt",
    "low": DATA_RAW / "priority_low.txt",
}

# 各模块产物文件名
WINDOWS_CSV = DATA_INTERIM / "windows.csv"
SAT_META_CSV = DATA_INTERIM / "sat_meta.csv"
STATIONS_CSV = DATA_INTERIM / "stations.csv"
PLAN_CSV = DATA_OUT / "plan.csv"
SCORE_JSON = DATA_OUT / "score.json"

# --------------------------------------------------------------------------
# 规划期
# 最新赛题修改（用户提供）：2026-08-01 00:00 ~ 2026-08-07 00:00（6 天），沿用项目 UTC 口径。
# TLE 历元集中在 2026-08-02 ~ 08-04：规划开始时向前传播约 1~3 天，结束时向后传播约 3~5 天。
# SGP4 外推仍有不确定性，结果不可表述为连续时间或轨道精度认证。
# --------------------------------------------------------------------------
PLAN_T0_UTC = "2026-08-01T00:00:00Z"
PLAN_DAYS = 6
TIME_IS_UTC = True
WINDOW_COARSE_STEP_S = 30.0  # Prototype scan resolution; not an official constraint.
WINDOW_BOUNDARY_TOLERANCE_S = 0.1  # Numerical edge refinement tolerance.
PROPAGATION_CHUNK_DAYS = 1

# --------------------------------------------------------------------------
# 目标优先级（说明.docx：高优 5 分、中优 3 分、低优 2 分）
# --------------------------------------------------------------------------
PRIORITY_SCORE: dict[str, int] = {"high": 5, "mid": 3, "low": 2}
PRIORITY_ORDER: tuple[str, ...] = ("high", "mid", "low")

# --------------------------------------------------------------------------
# 观测与资源约束（说明.docx + 站址.txt）
# --------------------------------------------------------------------------
MIN_ELEV_DEG = 10.0          # 站址.txt：最低仰角不低于 10 度
MAX_ELEV_DEG = 85.0          # 站址.txt：最高不超过 85 度
STATION_IDS: tuple[int, ...] = tuple(range(1, 11))  # 全球 10 个站点

MIN_DUR_S = 120.0            # 定轨最短观测时长
MAX_DUR_S = 240.0            # 定轨最长观测时长（及以上得满分）
DUR_SCORE_AT_MIN = 0.60      # 观测到最短时长获得 60% 分数
DUR_SCORE_AT_MAX = 1.00      # 观测到最长时长及以上获得 100% 分数
SWITCH_TIME_S = 30.0         # 每次切换目标需要的调度时间
REPEAT_COOLDOWN_S = 172800.0 # 同一目标距上次观测结束满 48h 才可再观测；重复观测可再次计分

# --------------------------------------------------------------------------
# 窗口可见性判定（楼心荡已按问答实现，此处仅登记口径）
# --------------------------------------------------------------------------
SUN_ELEV_MAX_DEG = -6.0      # 测站太阳高度角 < -6 度（即测站处于暗夜/暮光以下）
REQUIRE_SAT_SUNLIT = True    # 卫星需受太阳照亮

# --------------------------------------------------------------------------
# 运行参数
# --------------------------------------------------------------------------
RANDOM_SEED = 42             # 提交要求：固定随机种子
