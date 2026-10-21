"""按赛题评分公式给星座打分。

赛题（单个卫星数量工况，满分 100）：
    全球覆盖 40 分 = 28 × T90* / T90 + 12 × T100* / T100
    区域重访 60 分 = 42 × Tavg* / Tavg + 18 × Tmax* / Tmax
其中带 * 的是当届所有有效方案里的最优值。特殊规则：
    90% 覆盖率未达到 → 全球覆盖项 0 分；达到 90% 但未全覆盖 → T100 项 0 分；
    重点区域有格点在仿真期内不足两次有效访问 → 重访项可直接判 0 分（strict_two_visits，默认按此保守处理）。

我们拿不到别队的最优值，就用"参考值"代替：同一 N 下所有初选构型里各指标的最优值（refs），
这样打出的分数与真实评分同构——哪项比参考好多少，就按真实权重得多少分。

优化时另加几项平滑辅助量（soft），只用来给搜索提供梯度，不计入报告的赛题分：
    覆盖进度（99% 分位首次覆盖时刻、平均首次覆盖时刻）、重访间隔 99% 分位、
    未全覆盖时的覆盖率、不足两次访问的格点比例（惩罚）。
"""
import numpy as np

W = dict(T90=28.0, T100=12.0, Tavg=42.0, Tmax=18.0)
SOFT = dict(q99_first=3.0, mean_first=3.0, Tq99=3.0)


def official(m, refs, strict_two_visits=True):
    """赛题分（以 refs 为"最优值"）。返回 (总分, 分项 dict)。"""
    parts = dict(T90=0.0, T100=0.0, Tavg=0.0, Tmax=0.0)
    if m['T90']:
        parts['T90'] = W['T90'] * refs['T90'] / m['T90']
        if m['T100']:
            parts['T100'] = W['T100'] * refs['T100'] / m['T100']
    if m['Tavg'] and (m['vmin'] >= 2 or not strict_two_visits):
        parts['Tavg'] = W['Tavg'] * refs['Tavg'] / m['Tavg']
        parts['Tmax'] = W['Tmax'] * refs['Tmax'] / m['Tmax']
    return float(sum(parts.values())), parts


def objective(m, refs, strict_two_visits=True):
    """搜索目标 = 赛题分 + 平滑辅助项。"""
    s, _ = official(m, refs, strict_two_visits)
    s += sum(w * refs[k] / max(m[k], 1.0) for k, w in SOFT.items())
    if m['T100'] is None:
        s += 5.0 * m['cov']
    if strict_two_visits and m['vmin'] < 2:
        s -= 5.0 * m['n_lt2'] / max(m['n_cells'], 1)
    return float(s)


def make_refs(metric_list):
    """多组扁平指标 -> 各项最优值（越小越好）；未达到的项用仿真时长兜底。"""
    refs = {}
    for k in list(W) + list(SOFT):
        vals = [m[k] for m in metric_list if m.get(k)]
        refs[k] = float(min(vals)) if vals else 7 * 86400.0
    return refs
