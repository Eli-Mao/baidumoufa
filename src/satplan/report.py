"""展示与交付物。分区：**川谷**。

负责把结果变成人看得懂的东西，直接对应评分里的"产品体验"维度：
    * 站点-时间甘特图（每站一条泳道，一眼看出资源是否用满）；
    * 优先级覆盖柱状图（高/中/低优的覆盖率对比）；
    * 累计得分随时间曲线（衡量前期是否"抢跑"）；
    * 卫星覆盖次数分布（发现是否有星被反复观测、部分星从未被观测）；
    * 摘要一页纸（关键指标 + 约束裕度 + 风险提示）。

★本文件为待实现骨架，函数签名已冻结。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config


def _setup_chinese_font() -> None:
    """中文字体设置（Windows 用 SimHei / 微软雅黑，缺字体时退化为英文标签）。"""
    try:
        import matplotlib

        matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:  # pragma: no cover - 字体为环境相关，不影响主流程
        pass


def make_figures(
    plan: pd.DataFrame,
    windows: pd.DataFrame,
    sat_meta: pd.DataFrame,
    *,
    outdir: Path | None = None,
) -> list[Path]:
    """生成全部图表，返回文件路径列表（PNG，300 dpi）。

    建议文件名与交付要求对齐：
        fig_station_gantt.png / fig_coverage.png / fig_cum_score.png / fig_sat_hist.png
    """
    raise NotImplementedError("川谷：实现甘特图、覆盖率柱状图、累计得分曲线与摘要页。")


def summary_sheet(plan: pd.DataFrame, report: dict) -> str:
    """生成"一页纸摘要"文本：关键指标 + 约束裕度 + 风险提示。"""
    raise NotImplementedError("川谷：实现一页纸摘要，供报告首页使用。")
