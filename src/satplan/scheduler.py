"""观测任务调度算法。分区：**Iceswing**。

任务链位置：
    windows.csv（楼心荡） -> **本模块** -> plan.csv（Priime 评分 / 川谷 提交）

本文件当前附带一份**参考基线贪心**（``_reference_greedy``），目的是让全链路先跑通、
并给后续改进提供一个可比对的分数基线。Iceswing 的任务：
    1. 先读通并复跑这份基线，确认输出满足契约；
    2. 再按下面的"改进方向"升级，或用伐谋做算法自演化；
    3. 每次改进都在群里报出总分与覆盖星数，便于横向对比。

改进方向（按性价比排序）：
    a. 排序键从"单点收益"改成"收益 / 机会成本"：抢占一个站点时段是有代价的；
    b. 引入卫星稀缺度：全网窗口数越少的星越应优先排（否则容易排不上）；
    c. 考虑"同星多站竞争"：同一时刻只能有一个站真正跟踪它；
    d. 局部搜索 / 交换 / 插入算子（见 :func:`local_search`）；
    e. 按站点维度分治后再全局合并，降低贪心的短视性。
"""

from __future__ import annotations

import pandas as pd

from . import config, rules


# --------------------------------------------------------------------------
# 参考基线（可运行，供 Iceswing 对标）
# --------------------------------------------------------------------------


def _prepare_candidates(windows: pd.DataFrame) -> pd.DataFrame:
    """把窗口裁剪成可执行的候选任务：观测时长取 ``min(窗口时长, 最长观测时长)``。"""
    cand = windows.copy()
    w_dur = cand["t_end_s"] - cand["t_start_s"]
    keep = w_dur >= config.MIN_DUR_S
    cand = cand.loc[keep].copy()
    cand["obs_dur_s"] = (cand["t_end_s"] - cand["t_start_s"]).clip(
        lower=config.MIN_DUR_S, upper=config.MAX_DUR_S
    )
    cand["obs_start_s"] = cand["t_start_s"]
    cand["obs_end_s"] = cand["obs_start_s"] + cand["obs_dur_s"]
    cand["duration_score"] = cand["obs_dur_s"].map(rules.duration_score)
    return cand.reset_index(drop=True)


def _reference_greedy(
    windows: pd.DataFrame,
    sat_meta: pd.DataFrame | None = None,
    *,
    scarcity_bonus: float = 0.5,
    allow_reobserve: bool = True,
    one_station_per_sat: bool = True,
) -> pd.DataFrame:
    """按"优先级 × 时长系数 × 稀缺度加权"降序贪心占位。

    Parameters
    ----------
    scarcity_bonus : float
        稀缺度加成权重。某星全网窗口数越少，加成越高，避免难排的目标被挤掉。
    allow_reobserve : bool
        是否允许同一颗星被重复观测（★口径待 Priime 确认，见 docs/open_questions.md Q5）。
    one_station_per_sat : bool
        同一时刻是否只允许一个站跟踪同一颗星（物理自洽保护）。
    """
    cand = _prepare_candidates(windows)
    if cand.empty:
        return _empty_plan()

    n_windows = cand.groupby("sat_id")["window_id"].transform("count")
    cand["_key"] = (
        cand["priority_score"].astype(float)
        * cand["duration_score"]
        * (1.0 + scarcity_bonus / n_windows.clip(lower=1))
    )
    cand = cand.sort_values(["_key", "obs_start_s"], ascending=[False, True])

    # 每站记录上一任务的结束时刻；None 表示该站尚未排班（此时不受切换时间约束）
    station_last_end: dict[int, float | None] = {int(s): None for s in config.STATION_IDS}
    sat_busy_until: dict[int, float] = {}
    covered: set[int] = set()
    rows: list[dict[str, object]] = []

    for row in cand.to_dict(orient="records"):
        station_id = int(row["station_id"])
        sat_id = int(row["sat_id"])
        start, end = float(row["obs_start_s"]), float(row["obs_end_s"])

        if not allow_reobserve and sat_id in covered:
            continue
        last_end = station_last_end.get(station_id)
        if last_end is not None and start < last_end + config.SWITCH_TIME_S - 1e-9:
            continue
        if one_station_per_sat and sat_busy_until.get(sat_id, -1.0) > start + 1e-9:
            continue

        station_last_end[station_id] = end
        sat_busy_until[sat_id] = end
        covered.add(sat_id)
        rows.append(
            {
                "station_id": station_id,
                "sat_id": sat_id,
                "priority": row["priority"],
                "priority_score": int(row["priority_score"]),
                "t_start_s": start,
                "t_end_s": end,
                "dur_s": float(row["obs_dur_s"]),
                "duration_score": float(row["duration_score"]),
            }
        )

    return _finish_plan(rows)


# --------------------------------------------------------------------------
# 待 Iceswing 实现
# --------------------------------------------------------------------------


def greedy_schedule(
    windows: pd.DataFrame,
    sat_meta: pd.DataFrame | None = None,
    *,
    coverage_weight: float = 0.0,
) -> pd.DataFrame:
    """正式入口：返回满足 ``plan`` 契约的调度方案。

    ★这是 Iceswing 的主战场。当前委托给参考基线，请在确认基线无误后替换为
    你自己的实现（保持签名与返回契约不变即可，调用方不用改）。
    """
    return _reference_greedy(windows, sat_meta)


def local_search(
    plan: pd.DataFrame,
    windows: pd.DataFrame,
    sat_meta: pd.DataFrame | None = None,
    *,
    iters: int = 2000,
    seed: int | None = None,
) -> pd.DataFrame:
    """在已有计划上做邻域改进（交换 / 插入 / 右移），返回改进后的计划。

    约束：**任何一次移动都必须先用 :func:`satplan.rules.plan_violations` 校验，
    不可行则回滚**。评分统一用 :func:`satplan.rules.score_plan`，
    不要自己另写一套判分逻辑。

    评估函数建议直接用 :func:`satplan.rules.objective`，与伐谋 Evaluator 保持一致。
    """
    raise NotImplementedError("Iceswing：实现局部搜索算子，并用 rules 做可行性回滚。")


# --------------------------------------------------------------------------
# 内部小工具
# --------------------------------------------------------------------------


def _empty_plan() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "task_id",
            "station_id",
            "sat_id",
            "priority",
            "priority_score",
            "t_start_s",
            "t_end_s",
            "dur_s",
            "duration_score",
        ]
    )


def _finish_plan(rows: list[dict[str, object]]) -> pd.DataFrame:
    """补 ``task_id`` 并按站点、时间排序，输出契约要求的列顺序。"""
    plan = pd.DataFrame(rows)
    if plan.empty:
        return _empty_plan()
    plan = plan.sort_values(["station_id", "t_start_s"]).reset_index(drop=True)
    plan.insert(0, "task_id", range(1, len(plan) + 1))
    return plan[
        [
            "task_id",
            "station_id",
            "sat_id",
            "priority",
            "priority_score",
            "t_start_s",
            "t_end_s",
            "dur_s",
            "duration_score",
        ]
    ]
