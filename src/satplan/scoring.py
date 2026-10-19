"""评分与约束校验的报告层。分区：**Priime**。

职责边界：
    * 判定内核（时长得分公式、硬约束检查、标量目标）在 :mod:`satplan.rules`，
      与 Iceswing 共用，**本模块不重复实现**；
    * 本模块负责把它组装成可提交的 ``score.json``、约束报告与算法对比实验。

Priime 当前已在本地实现的内容（任务时间范围、可见窗口、站点冲突、资源切换时间、
最低观测时长、站点故障等硬约束，以及目标覆盖率/高优先级覆盖率/加权覆盖率/
观测间隔/站点利用率），请迁移到本模块与 :mod:`satplan.rules`，不要留在各自脚本里。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config, io_schema, rules


# --------------------------------------------------------------------------
# 可提交产物
# --------------------------------------------------------------------------


def build_score_report(
    plan: pd.DataFrame,
    windows: pd.DataFrame,
    sat_meta: pd.DataFrame,
) -> dict:
    """组装 ``score.json``。字段与 ``docs/scoring.md`` 一致。"""
    report = rules.score_plan(plan, windows, sat_meta)
    report["feasible"] = not report.get("violations")
    report["n_stations"] = int(len(config.STATION_IDS))
    report["plan_days"] = int(config.PLAN_DAYS)
    report["plan_t0_utc"] = config.PLAN_T0_UTC
    return report


def save_score_report(report: dict, path: Path | None = None) -> Path:
    path = Path(path or config.SCORE_JSON)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_constraint_report(plan: pd.DataFrame, windows: pd.DataFrame) -> dict:
    """单独的硬约束报告，便于主办方复核。"""
    violations = rules.plan_violations(plan, windows)
    by_type: dict[str, int] = {}
    for v in violations:
        by_type[v["type"]] = by_type.get(v["type"], 0) + 1
    return {
        "feasible": not violations,
        "n_violations": len(violations),
        "by_type": by_type,
        "details": violations[:100],
    }


# --------------------------------------------------------------------------
# 待 Priime 实现
# --------------------------------------------------------------------------


def compare_algorithms(
    algorithms: dict[str, object],
    windows: pd.DataFrame,
    sat_meta: pd.DataFrame,
    *,
    repeats: int = 1,
) -> pd.DataFrame:
    """算法对比实验：对多个调度算法跑同一份窗口表，输出统一口径的对比表。

    ``algorithms`` 形如 ``{"greedy": scheduler.greedy_schedule, "local": ...}``。
    对比列至少包含：``algorithm`` / ``total_score`` / ``n_covered`` /
    ``coverage_rate`` / ``hi_coverage_rate`` / ``n_violations`` /
    ``runtime_s`` / ``station_utilization``。

    注意：运行时要用 :func:`satplan.config.RANDOM_SEED` 固定随机种子，
    满足提交要求里的可复现性。
    """
    raise NotImplementedError("Priime：实现算法对比实验表，作为报告里的横向对比章节。")


def calibrate_duration_score() -> pd.DataFrame:
    """校准时长-得分插值（★见 docs/open_questions.md Q4）。

    请向组委会确认 120 s（60% 分）到 240 s（100% 分）之间是**线性**、
    还是**分段阶跃**；确认后更新 :func:`satplan.rules.duration_score`，
    并把校准表贴进报告。
    """
    raise NotImplementedError("Priime：确认并固化时长-得分插值公式。")
