"""快速评估器：解析求每颗星穿过各纬度行的时刻与经度，代替逐步长扫描。

原理（J2 长期项、圆轨道，与 propagate.propagate_j2_secular 同一模型）：
  纬度 φ(t) = asin(sin i · sin u(t))，u(t) = u0 + u̇·t。穿过某一纬度行 φr 时 u 只有两个值：
  升段 u_a = asin(sin φr / sin i)，降段 u_d = π − u_a；对应时刻是公差 2π/u̇ 的等差数列。
  该时刻的经度 λ = Ω0 + Ω̇·t − GMST(t) + atan2(cos i · sin u, cos u)。
  在穿越点附近把地面轨迹看成直线：同一纬度行上与轨迹横向距离 ≤ d（地面半幅宽）的点，
  经度偏差满足 |Δλ| ≤ d·|v| / (R·cos φ·|v_N|)，v 为地固系地面速度、v_N 为其北向分量。
于是"某格点何时被扫到"只需对每次穿越算一个经度区间，不用按 10 s / 1 s 逐点扫描。

近似只在轨迹最高纬度附近（|φ| > 80°，轨迹几乎平行于纬线）偏粗，那里的格点每天被扫很多次，
不影响 T90 / T100；validate.py 用逐步长仿真（run_sim / coverage.py）核对两者一致。

评估口径（赛题文档 + 答疑 #28 / #41 / #45 / #46 / #49）：
- 全球覆盖：1°×1° 格点（格心），有效区 reachable（剔除永远覆盖不到的极区）或 all；
  T90 = 累计覆盖率首次达到 90% 的时刻，T100 = 有效区全部覆盖的时刻；
- 区域重访（计分）：统计对象是长三角整体（#45-3）。某颗星只要有任一长三角 0.1° 格点落入视场，
  就算它在访问区域；同一颗星相邻两次命中相隔超过 300 s 切成两次访问，访问区间取
  [首次命中, 末次命中]（连续时间下即首个格点进入视场到末个格点离开视场，沿迹视场 0.81°，#46）。
  默认不合并（#28"重访不合并"）：所有星的访问按开始时刻排序，间隔 = [仿真开始→首次访问开始]、
  相邻两次 max(0, 后一次开始 − 前一次结束)、[末次访问结束→仿真结束]；另给"合并"口径
  （各星访问区间取并集后再算间隔）作参考。Tavg / Tmax 为全部间隔的平均 / 最大；
  整体访问次数 < 2 时重访项判 0（#49-1）。见 region_revisit；
- 区域重访（旧口径，仅作参考）：逐格点统计，见 revisit_stats。
"""
import numpy as np

from coverage import Grid, ground_half_width, coverage_metrics, ETA_ALONG
from region import points_in_polygon, load_geojson, bbox
from sso import R_EARTH, OMEGA_EARTH, j2_rates, gmst_rad

SIM_DAYS = 7.0
T_END = SIM_DAYS * 86400.0
DEFAULT_BBOX = (27.0, 35.3, 114.0, 123.0)
VISIT_SPLIT_S = 300.0      # 同一颗星相邻命中相隔超过这么久，算两次访问


def sat_rates(alt_km, inc_deg):
    """每颗星的派生量：(倾角 rad, Ω̇, u̇, 地面半幅宽 km)。"""
    alt = np.asarray(alt_km, float)
    inc = np.radians(np.asarray(inc_deg, float))
    raan_dot, argp_dot, m_dot = j2_rates(R_EARTH + alt, 0.0, inc)
    dmax = np.array([ground_half_width(h) for h in np.atleast_1d(alt)], float)
    return inc, raan_dot, argp_dot + m_dot, dmax


def crossings(alt_km, inc_deg, raan_deg, u_deg, lat_rows_deg, jd0, t_end=T_END):
    """一颗星穿过各纬度行的全部时刻。

    返回扁平数组 (row, t, lon_deg, hw_deg, vg)：行号、时刻（s，相对仿真起点）、
    穿越点经度（−180~180）、该行上被覆盖的经度半宽（度）、地面速度（km/s，地固系）。
    """
    inc, raan_dot, u_dot, dmax = sat_rates(alt_km, inc_deg)
    inc, raan_dot, u_dot, dmax = float(inc), float(raan_dot), float(u_dot), float(dmax[0])
    phi = np.radians(np.asarray(lat_rows_deg, float))
    s = np.sin(phi) / np.sin(inc)
    rows = np.nonzero(np.abs(s) < 1.0 - 1e-12)[0]
    if len(rows) == 0:
        return (np.empty(0, int),) + (np.empty(0),) * 4
    phi_r, s_r = phi[rows], s[rows]
    ua = np.arcsin(s_r)
    u_c = np.concatenate([ua, np.pi - ua])               # 升段 / 降段
    row_c = np.concatenate([rows, rows])
    phi_c = np.concatenate([phi_r, phi_r])

    period = 2 * np.pi / u_dot
    t0 = np.mod(u_c - np.radians(u_deg), 2 * np.pi) / u_dot
    kmax = int(np.ceil(t_end / period)) + 1
    t = t0[:, None] + period * np.arange(kmax)[None, :]
    keep = t <= t_end
    cnt = keep.sum(axis=1)
    t = t[keep]
    rr = np.repeat(np.arange(len(u_c)), cnt)

    cu, su = np.cos(u_c), np.sin(u_c)
    A = np.arctan2(np.cos(inc) * su, cu)                 # 轨道面内相对升交点的经度差
    lon = np.radians(raan_deg) + raan_dot * t - gmst_rad(jd0 + t / 86400.0) + A[rr]
    lon = (np.degrees(lon) + 180.0) % 360.0 - 180.0

    cphi = np.cos(phi_c)
    lam_dot = raan_dot - OMEGA_EARTH + u_dot * np.cos(inc) / (cu ** 2 + np.cos(inc) ** 2 * su ** 2)
    ve = R_EARTH * cphi * lam_dot
    vn = R_EARTH * u_dot * np.sin(inc) * cu / cphi
    vg = np.hypot(ve, vn)
    hw = dmax * vg / (R_EARTH * cphi * np.maximum(np.abs(vn), 1e-12))
    hw = np.degrees(np.minimum(hw, np.pi))
    return row_c[rr], t, lon, hw[rr], vg[rr]


def _paint(row, lon, hw, x0, dx, ncol, wrap):
    """把每次穿越的经度区间展开成被覆盖的列号。返回 (穿越序号, 列号)。"""
    x = (lon - x0) / dx
    w = hw / dx
    kl = np.ceil(x - w).astype(np.int64)
    kh = np.floor(x + w).astype(np.int64)
    if not wrap:
        kl = np.maximum(kl, 0)
        kh = np.minimum(kh, ncol - 1)
    n = np.maximum(kh - kl + 1, 0)
    idx = np.repeat(np.arange(len(lon)), n)
    off = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    col = kl[idx] + off
    if wrap:
        col %= ncol
    return idx, col


def sat_passes(t_hit, pad=0.0, split=VISIT_SPLIT_S):
    """一颗星对整个区域的访问区间 (starts, ends)。

    t_hit：该星的命中时刻（有区域格点落入视场的时刻）；相邻命中相隔 > split 切开。
    pad：每次命中前后格点在视场内停留的时长（沿迹半宽 / 地速，标量或与 t_hit 等长），
    区间取 [首次命中 − pad, 末次命中 + pad]；逐步长仿真按采样判定时 pad = 0。
    """
    t = np.asarray(t_hit, float)
    if len(t) == 0:
        return np.empty(0), np.empty(0)
    o = np.argsort(t, kind='stable')
    t = t[o]
    pad = np.broadcast_to(np.asarray(pad, float), t.shape)[o]
    brk = np.nonzero(np.diff(t) > split)[0]
    first, last = np.r_[0, brk + 1], np.r_[brk, len(t) - 1]
    return t[first] - pad[first], t[last] + pad[last]


def region_revisit(starts, ends, t_end, merge=False):
    """长三角整体重访统计（答疑 #45-3 / #49-1）。starts / ends：所有星的访问区间（秒）。

    merge=False（默认，#28"重访不合并"）：访问按开始时刻排序，间隔 = 首段 [0, 首次开始]、
        相邻两次 max(0, 后一次开始 − 前一次结束)、尾段 [末次结束, t_end]；
    merge=True：各星访问区间先取并集，再按同样方式取间隔（间隔都 > 0）。
    间隔全部计入（含 0），Tavg = 平均、Tmax = 最大；valid = 整体访问次数 ≥ 2。
    """
    s = np.clip(np.asarray(starts, float), 0.0, t_end)
    e = np.clip(np.asarray(ends, float), 0.0, t_end)
    n_raw = len(s)
    if n_raw == 0:
        return dict(Tavg_s=float(t_end), Tmax_s=float(t_end), Trms_s=float(t_end), n_visits=0,
                    n_intervals=1, valid=False, visit_time_s=0.0)
    o = np.argsort(s, kind='stable')
    s, e = s[o], e[o]
    if merge:
        emax = np.maximum.accumulate(e)
        new = np.r_[True, s[1:] > emax[:-1]]
        last = np.r_[np.nonzero(new)[0][1:] - 1, n_raw - 1]
        s, e = s[new], emax[last]
    gaps = np.r_[s[0], np.maximum(s[1:] - e[:-1], 0.0), max(t_end - e[-1], 0.0)]
    return dict(Tavg_s=float(gaps.mean()), Tmax_s=float(gaps.max()),
                Trms_s=float(np.sqrt(np.mean(gaps ** 2))),
                n_visits=int(len(s)), n_intervals=int(len(gaps)), valid=bool(len(s) >= 2),
                visit_time_s=float(np.sum(e - s)))


class FastEvaluator:
    """星座评估器：逐星缓存（全球首次覆盖时刻、区域访问），改一颗星只重算这一颗。"""

    def __init__(self, jd0, t_end=T_END, region_polys=None, region_bbox=None,
                 never_visited=True, global_dlat=1.0, region_dlat=0.1, region_only=False,
                 split_s=VISIT_SPLIT_S):
        self.jd0, self.t_end, self.never_visited = jd0, float(t_end), never_visited
        self.split_s = float(split_s)
        self.region_only = region_only        # True 时跳过全球覆盖（只算区域重访，用于整体旋转扫描）
        self.g = Grid(-90.0, 90.0, global_dlat)
        self.g_rows = -90.0 + (np.arange(self.g.nlat) + 0.5) * self.g.dlat
        la0, la1, lo0, lo1 = region_bbox or (bbox(region_polys) if region_polys else DEFAULT_BBOX)
        self.rg = Grid(la0, la1, region_dlat, lo0, lo1, region_dlat)
        self.r_rows = la0 + (np.arange(self.rg.nlat) + 0.5) * region_dlat
        self.r_mask = points_in_polygon(self.rg.lat_c, self.rg.lon_c, region_polys)
        self.r_cells = np.nonzero(self.r_mask)[0]
        self.r_pos = np.full(self.rg.size, -1, np.int64)
        self.r_pos[self.r_cells] = np.arange(len(self.r_cells))
        self.sats = []
        self.g_first = []          # 每星 (64800,) 首次覆盖时刻
        self.r_visits = []         # 每星 (区域格点序号, 时刻)：逐格点旧口径用
        self.r_passes = []         # 每星对整个区域的访问区间 (starts, ends)

    # ------------------------------------------------------------ 单星
    def _sat_cache(self, el):
        alt, inc, raan, u = el
        first = np.full(self.g.size, np.inf)
        row, t, lon, hw, _ = (crossings(alt, inc, raan, u, self.g_rows, self.jd0, self.t_end)
                              if not self.region_only else (np.empty(0, int),) + (np.empty(0),) * 4)
        if len(t):
            idx, col = _paint(row, lon, hw, -180.0 + 0.5 * self.g.dlon, self.g.dlon, self.g.nlon, True)
            np.minimum.at(first, row[idx] * self.g.nlon + col, t[idx])
        row, t, lon, hw, vg = crossings(alt, inc, raan, u, self.r_rows, self.jd0, self.t_end)
        lo0 = self.rg.lon0
        lo1 = lo0 + self.rg.nlon * self.rg.dlon
        near = (lon + hw >= lo0) & (lon - hw <= lo1)
        row, t, lon, hw, vg = row[near], t[near], lon[near], hw[near], vg[near]
        idx, col = _paint(row, lon, hw, lo0 + 0.5 * self.rg.dlon, self.rg.dlon, self.rg.nlon, False)
        cell = row[idx] * self.rg.nlon + col
        pos = self.r_pos[cell]
        ok = pos >= 0
        # 有区域格点落入视场的穿越 = 一次"命中"；格点在方形视场内停留 ±(沿迹半宽 / 地速)
        k = np.unique(idx[ok])
        pad = float(ground_half_width(alt, ETA_ALONG)) / vg[k]
        return first, (pos[ok], t[idx][ok]), sat_passes(t[k], pad, self.split_s)

    def set_constellation(self, elems):
        """elems: 可迭代的 (alt_km, inc_deg, raan_deg, u_deg)。"""
        self.sats = [tuple(map(float, e)) for e in elems]
        caches = [self._sat_cache(e) for e in self.sats]
        self.g_first = np.vstack([c[0] for c in caches])          # (N, 网格数)
        self.r_visits = [c[1] for c in caches]
        self.r_passes = [c[2] for c in caches]
        self._gmin = None

    def update_sat(self, j, el):
        """改第 j 颗星；返回旧缓存，可交给 revert_sat 撤销。"""
        old = (self.sats[j], self.g_first[j].copy(), self.r_visits[j], self.r_passes[j])
        self.sats[j] = tuple(map(float, el))
        self.g_first[j], self.r_visits[j], self.r_passes[j] = self._sat_cache(self.sats[j])
        self._gmin = None
        return old

    def revert_sat(self, j, old):
        self.sats[j], self.g_first[j], self.r_visits[j], self.r_passes[j] = old
        self._gmin = None

    def elements(self):
        return np.array(self.sats, float)

    # ------------------------------------------------------------ 指标
    def global_first(self):
        if self._gmin is None:
            self._gmin = self.g_first.min(axis=0)
        return self._gmin

    def reachable_mask(self):
        inc = np.array([s[1] for s in self.sats])
        alt = np.array([s[0] for s in self.sats])
        top = np.max(np.where(inc <= 90, inc, 180 - inc))
        dlat = np.degrees(ground_half_width(alt.min()) / R_EARTH)
        return np.abs(self.g.lat_c) <= top + dlat

    def global_metrics(self):
        first = self.global_first()
        return {'reachable': coverage_metrics(first, self.g, self.reachable_mask()),
                'all': coverage_metrics(first, self.g)}

    def passes(self):
        """所有星对整个区域的访问区间 (starts, ends)，未排序。"""
        if not self.r_passes:
            return np.empty(0), np.empty(0)
        return (np.concatenate([p[0] for p in self.r_passes]),
                np.concatenate([p[1] for p in self.r_passes]))

    def region_metrics(self):
        """长三角整体重访（计分口径，不合并），另附 merged（合并口径）。"""
        s, e = self.passes()
        r = region_revisit(s, e, self.t_end)
        r['merged'] = region_revisit(s, e, self.t_end, merge=True)
        return r

    def cell_metrics(self):
        """逐格点重访（旧口径，仅作参考）。"""
        pos = np.concatenate([v[0] for v in self.r_visits]) if self.r_visits else np.empty(0, int)
        t = np.concatenate([v[1] for v in self.r_visits]) if self.r_visits else np.empty(0)
        return revisit_stats(pos, t, len(self.r_cells), self.t_end, self.never_visited)

    def metrics(self):
        return dict(global_coverage=self.global_metrics(), region_revisit=self.region_metrics(),
                    region_revisit_cell=self.cell_metrics())

    def flat(self):
        """优化用的扁平指标（秒）：主指标 + 平滑辅助量，见 score.py。"""
        first = self.global_first()
        f = np.sort(first[self.reachable_mask()])
        n = len(f)
        fin = np.isfinite(f)
        k90 = int(np.ceil(0.9 * n)) - 1
        k99 = int(np.ceil(0.99 * n)) - 1
        fa = np.sort(first)
        na = len(fa)
        r = self.region_metrics()
        return dict(
            T90=float(f[k90]) if np.isfinite(f[k90]) else None,
            T100=float(f[-1]) if fin.all() else None,
            cov=float(fin.mean()),
            q99_first=float(min(f[k99], self.t_end * 1.5)),
            mean_first=float(np.minimum(f, self.t_end * 1.5).mean()),
            T90_all=float(fa[int(np.ceil(0.9 * na)) - 1]) if np.isfinite(fa[int(np.ceil(0.9 * na)) - 1]) else None,
            T100_all=float(fa[-1]) if np.isfinite(fa[-1]) else None,
            cov_all=float(np.isfinite(fa).mean()),
            Tavg=r['Tavg_s'], Tmax=r['Tmax_s'], Trms=r['Trms_s'], n_visits=r['n_visits'],
            Tavg_merged=r['merged']['Tavg_s'], Tmax_merged=r['merged']['Tmax_s'],
            n_visits_merged=r['merged']['n_visits'])


def revisit_stats(pos, t, n_cells, t_end, never_visited=True):
    """逐格点重访统计（旧口径，10-23 答疑前使用，现仅作参考输出）。

    每个格点的间隔 = [开始→首次访问]、相邻访问之差、[末次访问→结束]，从未访问的格点计一个整段间隔；
    全部格点的间隔合并后取平均与最大。访问时刻已按格点给出。
    """
    if len(t) == 0:
        d = np.full(n_cells if never_visited else 0, float(t_end))
        return dict(Tavg_s=float(t_end) if len(d) else None, Tmax_s=float(t_end) if len(d) else None,
                    Tq99_s=float(t_end) if len(d) else None,
                    Tavg_cellmean_s=float(t_end) if len(d) else None, n_intervals=int(len(d)),
                    n_cells=int(n_cells), n_cells_0=int(n_cells), n_cells_1=0, n_cells_2plus=0,
                    visits_min=0, visits_mean=0.0)
    o = np.lexsort((t, pos))
    pos, t = pos[o], t[o]
    n_vis = np.bincount(pos, minlength=n_cells)
    same = pos[1:] == pos[:-1]
    gaps = np.diff(t)[same]
    start = np.r_[True, ~same]
    end = np.r_[~same, True]
    head = t[start]
    tail = t_end - t[end]
    parts = [gaps, head, tail]
    if never_visited:
        parts.append(np.full(int((n_vis == 0).sum()), t_end))
    d = np.concatenate(parts)
    d = d[d > 0]
    # 逐格点平均再平均（另一种可能的口径，作参考）
    per_cell_sum = np.bincount(pos[1:][same], weights=gaps, minlength=n_cells)
    per_cell_sum[pos[start]] += head
    per_cell_sum[pos[end]] += tail
    cnt = n_vis + 1.0
    if never_visited:
        per_cell_sum[n_vis == 0] = t_end
        cell_mean = per_cell_sum / cnt
    else:
        cell_mean = (per_cell_sum / cnt)[n_vis > 0]
    return dict(Tavg_s=float(d.mean()) if len(d) else None,
                Tmax_s=float(d.max()) if len(d) else None,
                Tq99_s=float(np.quantile(d, 0.99)) if len(d) else None,
                Tavg_cellmean_s=float(cell_mean.mean()) if len(cell_mean) else None,
                n_intervals=int(len(d)), n_cells=int(n_cells),
                n_cells_0=int((n_vis == 0).sum()), n_cells_1=int((n_vis == 1).sum()),
                n_cells_2plus=int((n_vis >= 2).sum()),
                visits_min=int(n_vis.min()) if n_cells else 0,
                visits_mean=float(n_vis.mean()) if n_cells else 0.0)
