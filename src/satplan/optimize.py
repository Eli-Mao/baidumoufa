"""伐谋（FAMOU）Evaluator 入口。分区：**川谷**。

伐谋按"生成 → 评估 → 迭代"的演化闭环工作，其中**评估器（Evaluator）必须定制**：
它负责把一个候选解变成一个可比的分数，引导演化方向。本项目里 Evaluator 的职责是：
读入一份计划表 -> 用 :mod:`satplan.rules` 判定可行性与计分 -> 输出一个标量。

为什么必须复用 rules 而不是另写一套：
    如果 Evaluator 与最终评分口径不一致，演化会朝错误方向收敛，
    出现"伐谋里分数很高、实际提交被判违规"的情况。

用法::

    py -3 -m satplan.optimize --plan data/out/plan.csv
    py -3 -m satplan.optimize --plan data/out/plan.csv --coverage-weight 0.5

约定：把最终分数以裸浮点数打印到 stdout 最后一行，便于平台解析。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import config, io_schema, rules


def evaluate(
    plan_path: Path | str | None = None,
    *,
    windows_path: Path | str | None = None,
    sat_meta_path: Path | str | None = None,
    coverage_weight: float = 0.0,
    verbose: bool = False,
) -> float:
    """把一个候选计划折算成单一标量分数（供伐谋演化使用）。

    可行性优先：任何硬约束违规直接返回 ``-inf``，让演化立刻丢弃该候选，
    而不是靠罚分慢慢修正。

    Parameters
    ----------
    coverage_weight : float
        赛题同时考核"总得分"与"覆盖目标数"，用该权重把两者合成一个标量。
        建议在 0.0（纯总分）到 1.0（更强覆盖导向）之间调，并在报告里写明取值。
    """
    plan = io_schema.load_plan(Path(plan_path) if plan_path else config.PLAN_CSV)
    win = io_schema.load_windows(Path(windows_path) if windows_path else config.WINDOWS_CSV)
    meta = io_schema.load_sat_meta(Path(sat_meta_path) if sat_meta_path else config.SAT_META_CSV)

    if not rules.plan_is_feasible(plan, win):
        if verbose:
            print(json.dumps(rules.plan_violations(plan, win)[:5], ensure_ascii=False, indent=2))
        return float("-inf")

    rep = rules.score_plan(plan, win, meta)
    value = float(rep["weighted_score"]) + float(coverage_weight) * float(rep["n_covered"])
    if verbose:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    return value


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="伐谋 Evaluator：把计划表折算成标量分数")
    parser.add_argument("--plan", default=str(config.PLAN_CSV))
    parser.add_argument("--windows", default=str(config.WINDOWS_CSV))
    parser.add_argument("--sat-meta", default=str(config.SAT_META_CSV))
    parser.add_argument("--coverage-weight", type=float, default=0.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    value = evaluate(
        args.plan,
        windows_path=args.windows,
        sat_meta_path=args.sat_meta,
        coverage_weight=args.coverage_weight,
        verbose=args.verbose,
    )
    if value == float("-inf"):
        print("INFEASIBLE")
    # 最后一行输出裸分数，供平台解析
    print(f"{value:.6f}")
    return 0 if value != float("-inf") else 1


if __name__ == "__main__":
    raise SystemExit(main())
