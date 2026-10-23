"""逐步长仿真（"精确"评估）：按赛题推荐步长采样轨迹，逐点判断格点是否在视场内。

与 fasteval.py 的解析穿越法相互独立，用于：
1. 核对 fasteval 的结果（validate.py）；
2. 给最终输出的星座出一份按赛题仿真条件算的指标（全球 10 s、区域 1 s）。

指标口径与 fasteval 相同：全球 T90/T100（reachable / all 两种有效区）；
区域重访按长三角整体统计（某颗星在某个 1 s 采样时刻有任一区域格点落入视场即为命中，
同一颗星相邻命中相隔超过 300 s 切成两次访问，访问区间 = [首次命中采样, 末次命中采样]），
不合并（计分）与合并两种口径都输出；逐格点旧口径作参考。
"""
import numpy as np
import pandas as pd

from coverage import (Grid, global_coverage, coverage_metrics, region_access,
                      ground_half_width, max_reachable_lat, merge_visits, ETA_ALONG)
from fasteval import revisit_stats, region_revisit, sat_passes, DEFAULT_BBOX, VISIT_SPLIT_S
from propagate import propagate_j2_secular
from region import points_in_polygon, bbox
from sso import R_EARTH, gmst_rad


def ecef_track(elems, t_sec, jd0):
    """按 J2 长期项模型算地固系轨迹 (N, T, 3)。elems 需含 alt_km / inc_deg / raan_deg / u_deg。"""
    n = len(elems)
    out = np.empty((n, len(t_sec), 3), np.float64)
    g = gmst_rad(jd0 + t_sec / 86400.0)
    c, s = np.cos(g), np.sin(g)
    for c0 in range(0, n, 8):
        idx = np.arange(c0, min(c0 + 8, n))
        e = elems.iloc[idx]
        r, _ = propagate_j2_secular(R_EARTH + e['alt_km'].to_numpy(), e['inc_deg'].to_numpy(),
                                    e['raan_deg'].to_numpy(), e['u_deg'].to_numpy(), t_sec)
        x, y = r[..., 0], r[..., 1]
        out[idx] = np.stack([c * x + s * y, -s * x + c * y, r[..., 2]], axis=-1)
    return out


def simulate(elems, jd0, days=7.0, step=10.0, step_region=1.0, region_polys=None,
             never_visited=True, do_region=True, split_s=VISIT_SPLIT_S):
    """返回与 FastEvaluator.metrics() 相同结构的指标。"""
    elems = elems.reset_index(drop=True)
    dur = days * 86400.0
    dmax = np.array([ground_half_width(h) for h in elems['alt_km']], float)
    dalong = np.array([ground_half_width(h, ETA_ALONG) for h in elems['alt_km']], float)

    t = np.arange(0.0, dur + step / 2, step)
    grid = Grid(-90.0, 90.0, 1.0)
    first = global_coverage(ecef_track(elems, t, jd0), t, grid, dmax)
    reach = max_reachable_lat(elems['inc_deg'].to_numpy(), elems['alt_km'].to_numpy())
    glob = {'reachable': coverage_metrics(first, grid, np.abs(grid.lat_c) <= reach),
            'all': coverage_metrics(first, grid)}
    out = dict(global_coverage=glob)
    if not do_region:
        return out

    la0, la1, lo0, lo1 = bbox(region_polys) if region_polys else DEFAULT_BBOX
    rg = Grid(la0, la1, 0.1, lo0, lo1, 0.1)
    mask = points_in_polygon(rg.lat_c, rg.lon_c, region_polys)
    cells = np.nonzero(mask)[0]
    posmap = np.full(rg.size, -1, np.int64)
    posmap[cells] = np.arange(len(cells))

    # 粗步长圈出卫星经过区域附近的时段，再在时段内按 step_region 采样
    tc = np.arange(0.0, dur + 30.0, 30.0)
    trc = ecef_track(elems, tc, jd0)
    rho = np.linalg.norm(trc, axis=-1)
    lat = np.degrees(np.arcsin(np.clip(trc[..., 2] / rho, -1, 1)))
    lon = np.degrees(np.arctan2(trc[..., 1], trc[..., 0]))
    near = ((lat > la0 - 3) & (lat < la1 + 3) &
            (np.abs(((lon - lo0 + 180) % 360) - 180 - (lo1 - lo0) / 2) < (lo1 - lo0) / 2 + 3))
    pos_all, t_all = [], []          # 逐格点（旧口径）
    ps_all, pe_all = [], []          # 逐星对整个区域的访问区间
    for n in range(len(elems)):
        idx = np.nonzero(near[n])[0]
        hits = []                    # 本星命中区域的采样时刻
        for seg in (np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1) if len(idx) else []):
            a, b = tc[seg[0]] - 30.0, tc[seg[-1]] + 30.0
            ts = np.arange(max(0.0, a), min(dur, b) + step_region / 2, step_region)
            if len(ts) < 2:
                continue
            acc = region_access(ecef_track(elems.iloc[n:n + 1], ts, jd0), ts, rg,
                                dmax[n:n + 1], dalong[n:n + 1])
            for c, tt in acc.items():
                p = posmap[c]
                if p < 0:
                    continue
                hits.append(tt)
                starts, _ = merge_visits(tt, 3.0)       # 同一颗星连续采样合并成一次访问
                pos_all.append(np.full(len(starts), p))
                t_all.append(starts)
        s, e = sat_passes(np.unique(np.concatenate(hits)) if hits else np.empty(0), 0.0, split_s)
        ps_all.append(s)
        pe_all.append(e)
    ps, pe = np.concatenate(ps_all), np.concatenate(pe_all)
    reg = region_revisit(ps, pe, dur)
    reg['merged'] = region_revisit(ps, pe, dur, merge=True)
    out['region_revisit'] = reg
    pos = np.concatenate(pos_all) if pos_all else np.empty(0, int)
    tv = np.concatenate(t_all) if t_all else np.empty(0)
    out['region_revisit_cell'] = revisit_stats(pos, tv, len(cells), dur, never_visited)
    return out
