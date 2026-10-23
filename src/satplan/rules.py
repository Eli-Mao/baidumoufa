"""硬约束判定与计分内核。分区：Priime（**冻结接口**）。

为什么单独一个文件：调度的搜索方向（Iceswing）和最终评分（Priime）必须使用
**同一套判定**，否则会出现"搜索认为可行、评分判为违规"的矛盾。

本文件中的口径数字一律取自 :mod:`satplan.config`，不得在本文件写死。
本文件是冻结接口：改动需四人在群里确认，并同步 ``docs/scoring.md``。

注：本文件当前附带一份**参考实现**，Priime 负责按最终赛题口径校准与扩展
（尤其是 duration_score 的插值公式，见 docs/open_questions.md Q4）。
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from . import config


# --------------------------------------------------------------------------
# 基础公式
# --------------------------------------------------------------------------


def duration_score(dur_s: float) -> float:
    """观测时长 -> 时长得分系数。

    口径（说明.docx）：120 s 得 60% 分、240 s 及以上得 100% 分；
    超出 [120, 240] 的区间非法，返回 0 并交由 :func:`plan_violations` 判违规。
    """
    d = float(dur_s)
    if d < config.MIN_DUR_S or d > config.MAX_DUR_S:
        return 0.0
    if d >= config.MAX_DUR_S:
        return config.DUR_SCORE_AT_MAX
    span = config.MAX_DUR_S - config.MIN_DUR_S
    if span <= 0:
        return config.DUR_SCORE_AT_MAX
    ratio = (d - config.MIN_DUR_S) / span
    return config.DUR_SCORE_AT_MIN + (config.DUR_SCORE_AT_MAX - config.DUR_SCORE_AT_MIN) * ratio


def task_score(priority_score: int, dur_s: float) -> float:
    """单条任务的得分 = 优先级权重 × 时长系数。"""
    return float(priority_score) * duration_score(dur_s)


def duration_score_series(dur_s: pd.Series) -> pd.Series:
    """:func:`duration_score` 的向量化版本，供批量打分使用。

    空表、含 NaN 的输入都能安全处理。
    """
    d = pd.to_numeric(dur_s, errors="coerce").astype(float)
    span = float(config.MAX_DUR_S - config.MIN_DUR_S)
    ratio = (d - config.MIN_DUR_S) / span if span > 0 else d * 0.0 + 1.0
    out = config.DUR_SCORE_AT_MIN + (config.DUR_SCORE_AT_MAX - config.DUR_SCORE_AT_MIN) * ratio
    out = out.where(d < config.MAX_DUR_S, config.DUR_SCORE_AT_MAX)
    out = out.where((d >= config.MIN_DUR_S) & (d <= config.MAX_DUR_S), 0.0)
    return out.astype(float)


def task_score_series(priority_score: pd.Series, dur_s: pd.Series) -> pd.Series:
    """批量计算单条任务得分 = 优先级权重 × 时长系数。"""
    weight = pd.to_numeric(priority_score, errors="coerce").astype(float)
    return weight * duration_score_series(dur_s)


def plan_period_s() -> float:
    return float(config.PLAN_DAYS) * 86400.0


# --------------------------------------------------------------------------
# 硬约束判定
# --------------------------------------------------------------------------


def _window_containment(plan: pd.DataFrame, windows: pd.DataFrame) -> pd.Series:
    """判断每条计划是否被某个真实观测窗口完整包住（含同站同星的窗口匹配）。"""
    key = ["station_id", "sat_id"]
    if plan.empty:
        return pd.Series([], dtype=bool)
    w = windows[key + ["t_start_s", "t_end_s"]].rename(
        columns={"t_start_s": "w_start_s", "t_end_s": "w_end_s"}
    )
    merged = plan.assign(_pid=range(len(plan))).merge(w, on=key, how="left")
    merged["_ok"] = (merged["t_start_s"] >= merged["w_start_s"]) & (merged["t_end_s"] <= merged["w_end_s"])
    ok = merged.groupby("_pid")["_ok"].any()
    return ok.reindex(range(len(plan)), fill_value=False).astype(bool)


def _station_interval_violations(plan: pd.DataFrame) -> list[dict[str, Any]]:
    """同站任务冲突检查：不重叠，且相邻任务间隔 ≥ 切换时间。"""
    issues: list[dict[str, Any]] = []
    for station_id, grp in plan.sort_values(["station_id", "t_start_s"]).groupby("station_id"):
        prev_end: float | None = None
        prev_task: int | None = None
        for row in grp.to_dict(orient="records"):
            start, end = float(row["t_start_s"]), float(row["t_end_s"])
            if prev_end is not None:
                gap = start - prev_end
                if gap < -1e-9:
                    issues.append(
                        {
                            "type": "overlap",
                            "station_id": int(station_id),
                            "task_id": int(row["task_id"]),
                            "prev_task_id": prev_task,
                            "detail": f"与前一任务重叠 {-gap:.1f}s",
                        }
                    )
                elif gap < config.SWITCH_TIME_S - 1e-9:
                    issues.append(
                        {
                            "type": "switch_time",
                            "station_id": int(station_id),
                            "task_id": int(row["task_id"]),
                            "prev_task_id": prev_task,
                            "detail": f"切换间隔 {gap:.1f}s < {config.SWITCH_TIME_S:.0f}s",
                        }
                    )
            prev_end = end
            prev_task = int(row["task_id"])
    return issues


def _satellite_cooldown_violations(plan: pd.DataFrame) -> list[dict[str, Any]]:
    """Enforce the minimum gap between successive observations of one satellite."""
    issues: list[dict[str, Any]] = []
    for sat_id, group in plan.sort_values(["sat_id", "t_start_s"]).groupby("sat_id"):
        previous_end: float | None = None
        previous_task: int | None = None
        for row in group.itertuples(index=False):
            start, end = float(row.t_start_s), float(row.t_end_s)
            if previous_end is not None:
                gap = start - previous_end
                if gap < config.REPEAT_COOLDOWN_S - 1e-9:
                    issues.append({
                        "type": "satellite_cooldown",
                        "sat_id": int(sat_id),
                        "task_id": int(row.task_id),
                        "prev_task_id": previous_task,
                        "detail": (f"same-satellite gap {gap:.1f}s < "
                                   f"{config.REPEAT_COOLDOWN_S:.0f}s"),
                    })
            previous_end, previous_task = end, int(row.task_id)
    return issues


def plan_violations(
    plan: pd.DataFrame,
    windows: pd.DataFrame,
    *,
    max_report: int = 50,
) -> list[dict[str, Any]]:
    """返回计划表违反硬约束的明细列表；空列表表示完全可行。

    覆盖的硬约束：
      1. 观测时长必须在 [MIN_DUR_S, MAX_DUR_S] 内；
      2. 任务必须落在规划期内；
      3. 任务必须被某个真实观测窗口包住（即确实存在观测机会）；
      4. 同站任务不得重叠；
      5. 同站相邻任务间隔 ≥ SWITCH_TIME_S。
    """
    issues: list[dict[str, Any]] = []
    if plan.empty:
        return issues

    period = plan_period_s()

    dur_lo = plan["dur_s"] < config.MIN_DUR_S
    dur_hi = plan["dur_s"] > config.MAX_DUR_S
    for row in plan.loc[dur_lo | dur_hi, ["task_id", "station_id", "sat_id", "dur_s"]].to_dict(orient="records"):
        issues.append(
            {
                "type": "duration",
                "task_id": int(row["task_id"]),
                "station_id": int(row["station_id"]),
                "sat_id": int(row["sat_id"]),
                "detail": f"观测时长 {float(row['dur_s']):.1f}s 不在 [{config.MIN_DUR_S:.0f}, {config.MAX_DUR_S:.0f}]s",
            }
        )

    out_of_range = (plan["t_start_s"] < 0) | (plan["t_end_s"] > period)
    for row in plan.loc[out_of_range, ["task_id", "t_start_s", "t_end_s"]].to_dict(orient="records"):
        issues.append(
            {
                "type": "out_of_period",
                "task_id": int(row["task_id"]),
                "detail": f"任务 [{float(row['t_start_s']):.1f}, {float(row['t_end_s']):.1f}]s 超出规划期",
            }
        )

    contained = _window_containment(plan, windows)
    for row in plan.loc[~contained, ["task_id", "station_id", "sat_id", "t_start_s", "t_end_s"]].to_dict(orient="records"):
        issues.append(
            {
                "type": "no_opportunity",
                "task_id": int(row["task_id"]),
                "station_id": int(row["station_id"]),
                "sat_id": int(row["sat_id"]),
                "detail": "该任务在窗口表中找不到可包住它的观测窗口",
            }
        )

    # 时长字段自洽性
    inconsistent = (plan["t_end_s"] - plan["t_start_s"] - plan["dur_s"]).abs() > 1e-6
    for row in plan.loc[inconsistent, ["task_id", "t_start_s", "t_end_s", "dur_s"]].to_dict(orient="records"):
        issues.append(
            {
                "type": "duration_inconsistent",
                "task_id": int(row["task_id"]),
                "detail": "dur_s 与 t_end_s - t_start_s 不一致",
            }
        )

    issues.extend(_station_interval_violations(plan))
    issues.extend(_satellite_cooldown_violations(plan))
    return issues[:max_report]


def plan_is_feasible(plan: pd.DataFrame, windows: pd.DataFrame) -> bool:
    return not plan_violations(plan, windows, max_report=1)


# --------------------------------------------------------------------------
# 评分
# --------------------------------------------------------------------------


def score_plan(plan: pd.DataFrame, windows: pd.DataFrame, sat_meta: pd.DataFrame) -> dict[str, Any]:
    """对一份计划表打分。

    返回结构化结果，字段与 ``docs/scoring.md`` 一致，可直接序列化为 ``score.json``。
    内部评价指标（Priime 列表）：目标覆盖率、高优先级目标覆盖率、加权覆盖率、
    观测间隔、站点利用率。
    """
    n_total = int(len(sat_meta))
    n_hi_total = int((sat_meta["priority"] == "high").sum())
    period = plan_period_s()

    if plan.empty:
        return {
            "total_score": 0.0,
            "weighted_score": 0.0,
            "n_tasks": 0,
            "n_covered": 0,
            "coverage_rate": 0.0,
            "hi_covered": 0,
            "hi_coverage_rate": 0.0,
            "avg_dur_s": 0.0,
            "station_utilization": 0.0,
            "by_priority": {
                level: {"n_tasks": 0, "n_covered": 0, "coverage_rate": 0.0, "score": 0.0}
                for level in config.PRIORITY_ORDER
            },
            "violations": [],
            "n_violations": 0,
        }

    scored = plan.assign(_score=task_score_series(plan["priority_score"], plan["dur_s"]))
    weighted_score = float(scored["_score"].sum())

    covered = scored.drop_duplicates("sat_id")
    n_covered = int(len(covered))
    hi_covered = int((covered["priority"] == "high").sum())

    by_priority: dict[str, dict[str, float]] = {}
    for level in config.PRIORITY_ORDER:
        sub = scored[scored["priority"] == level]
        sub_cov = covered[covered["priority"] == level]
        tot = int((sat_meta["priority"] == level).sum())
        by_priority[level] = {
            "n_tasks": int(len(sub)),
            "n_covered": int(len(sub_cov)),
            "coverage_rate": (len(sub_cov) / tot) if tot else 0.0,
            "score": float(sub["_score"].sum()) if len(sub) else 0.0,
        }

    # 站点占用率：观测时长 + 每次切换开销（每个站少一次切换，只有任务间才有切换）
    n_stations_used = int(plan["station_id"].nunique())
    busy = float(plan["dur_s"].sum()) + config.SWITCH_TIME_S * max(0, int(len(plan)) - n_stations_used)
    capacity = float(len(config.STATION_IDS) * period)
    violations = plan_violations(plan, windows)

    return {
        "total_score": weighted_score,
        "weighted_score": weighted_score,
        "n_tasks": int(len(plan)),
        "n_covered": n_covered,
        "coverage_rate": n_covered / n_total if n_total else 0.0,
        "hi_covered": hi_covered,
        "hi_coverage_rate": hi_covered / n_hi_total if n_hi_total else 0.0,
        "avg_dur_s": float(plan["dur_s"].mean()),
        "station_utilization": busy / capacity if capacity else 0.0,
        "by_priority": by_priority,
        "violations": violations,
        "n_violations": len(violations),
    }


def objective(plan: pd.DataFrame, windows: pd.DataFrame, sat_meta: pd.DataFrame, *,
              coverage_weight: float = 0.0) -> float:
    """给优化器（Iceswing / 伐谋 Evaluator）用的单一标量目标。

    可行解优先：不可行直接返回极小值。
    ``coverage_weight`` 用于在"总分"与"覆盖目标数"之间加权（赛题同时考核两者）。
    """
    if not plan_is_feasible(plan, windows):
        return -math.inf
    rep = score_plan(plan, windows, sat_meta)
    return rep["weighted_score"] + coverage_weight * rep["n_covered"]
