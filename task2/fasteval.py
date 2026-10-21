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

评估口径（赛题文档 + 答疑 #28 / #41）：
- 全球覆盖：1°×1° 格点（格心），有效区 reachable（剔除永远覆盖不到的极区）或 all；
  T90 = 累计覆盖率首次达到 90% 的时刻，T100 = 有效区全部覆盖的时刻；
- 区域重访：长三角 0.1°×0.1° 格点；每个格点的间隔 = [开始→首次访问]、相邻访问之差、[末次访问→结束]，
  从未访问的格点计一个整段间隔；全部格点的间隔合并后取平均（Tavg）与最大（Tmax）。
  访问持续时间只有毫秒级（沿迹视场 30 m），间隔按访问时刻相减。
"""
import numpy as np

from coverage import Grid, ground_half_width, coverage_metrics
from region import points_in_polygon, load_geojson, bbox
from sso import R_EARTH, OMEGA_EARTH, j2_rates, gmst_rad

SIM_DAYS = 7.0
T_END = SIM_DAYS * 86400.0
DEFAULT_BBOX = (27.0, 35.3, 114.0, 123.0)


def sat_rates(alt_km, inc_deg):
    """每颗星的派生量：(倾角 rad, Ω̇, u̇, 地面半幅宽 km)。"""
    alt = np.asarray(alt_km, float)
    inc = np.radians(np.asarray(inc_deg, float))
    raan_dot, argp_dot, m_dot = j2_rates(R_EARTH + alt, 0.0, inc)
    dmax = np.array([ground_half_width(h) for h in np.atleast_1d(alt)], float)
    return inc, raan_dot, argp_dot + m_dot, dmax


def crossings(alt_km, inc_deg, raan_deg, u_deg, lat_rows_deg, jd0, t_end=T_END):
    """一颗星穿过各纬度行的全部时刻。

    返回扁平数组 (row, t, lon_deg, hw_deg)：行号、时刻（s，相对仿真起点）、
    穿越点经度（−180~180）、该行上被覆盖的经度半宽（度）。
    """
    inc, raan_dot, u_dot, dmax = sat_rates(alt_km, inc_deg)
    inc, raan_dot, u_dot, dmax = float(inc), float(raan_dot), float(u_dot), float(dmax[0])
    phi = np.radians(np.asarray(lat_rows_deg, float))
    s = np.sin(phi) / np.sin(inc)
    rows = np.nonzero(np.abs(s) < 1.0 - 1e-12)[0]
    if len(rows) == 0:
        return (np.empty(0, int),) + (np.empty(0),) * 3
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
    hw = dmax * np.hypot(ve, vn) / (R_EARTH * cphi * np.maximum(np.abs(vn), 1e-12))
    hw = np.degrees(np.minimum(hw, np.pi))
    return row_c[rr], t, lon, hw[rr]


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


class FastEvaluator:
    """星座评估器：逐星缓存（全球首次覆盖时刻、区域访问），改一颗星只重算这一颗。"""

    def __init__(self, jd0, t_end=T_END, region_polys=None, region_bbox=None,
                 never_visited=True, global_dlat=1.0, region_dlat=0.1, region_only=False):
        self.jd0, self.t_end, self.never_visited = jd0, float(t_end), never_visited
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
        self.r_visits = []         # 每星 (区域格点序号, 时刻)

    # ------------------------------------------------------------ 单星
    def _sat_cache(self, el):
        alt, inc, raan, u = el
        first = np.full(self.g.size, np.inf)
        row, t, lon, hw = (crossings(alt, inc, raan, u, self.g_rows, self.jd0, self.t_end)
                           if not self.region_only else (np.empty(0, int),) + (np.empty(0),) * 3)
        if len(t):
            idx, col = _paint(row, lon, hw, -180.0 + 0.5 * self.g.dlon, self.g.dlon, self.g.nlon, True)
            np.minimum.at(first, row[idx] * self.g.nlon + col, t[idx])
        row, t, lon, hw = crossings(alt, inc, raan, u, self.r_rows, self.jd0, self.t_end)
        lo0 = self.rg.lon0
        lo1 = lo0 + self.rg.nlon * self.rg.dlon
        near = (lon + hw >= lo0) & (lon - hw <= lo1)
        row, t, lon, hw = row[near], t[near], lon[near], hw[near]
        idx, col = _paint(row, lon, hw, lo0 + 0.5 * self.rg.dlon, self.rg.dlon, self.rg.nlon, False)
        cell = row[idx] * self.rg.nlon + col
        pos = self.r_pos[cell]
        ok = pos >= 0
        return first, (pos[ok], t[idx][ok])

    def set_constellation(self, elems):
        """elems: 可迭代的 (alt_km, inc_deg, raan_deg, u_deg)。"""
        self.sats = [tuple(map(float, e)) for e in elems]
        caches = [self._sat_cache(e) for e in self.sats]
        self.g_first = np.vstack([c[0] for c in caches])          # (N, 网格数)
        self.r_visits = [c[1] for c in caches]
        self._gmin = None

    def update_sat(self, j, el):
        """改第 j 颗星；返回旧缓存，可交给 revert_sat 撤销。"""
        old = (self.sats[j], self.g_first[j].copy(), self.r_visits[j])
        self.sats[j] = tuple(map(float, el))
        self.g_first[j], self.r_visits[j] = self._sat_cache(self.sats[j])
        self._gmin = None
        return old

    def revert_sat(self, j, old):
        self.sats[j], self.g_first[j], self.r_visits[j] = old[0], old[1], old[2]
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

    def region_metrics(self):
        pos = np.concatenate([v[0] for v in self.r_visits]) if self.r_visits else np.empty(0, int)
        t = np.concatenate([v[1] for v in self.r_visits]) if self.r_visits else np.empty(0)
        return revisit_stats(pos, t, len(self.r_cells), self.t_end, self.never_visited)

    def metrics(self):
        return dict(global_coverage=self.global_metrics(), region_revisit=self.region_metrics())

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
            Tavg=r['Tavg_s'], Tmax=r['Tmax_s'], Tq99=r['Tq99_s'], Tavg_cell=r['Tavg_cellmean_s'],
            vmin=r['visits_min'], n_lt2=r['n_cells_0'] + r['n_cells_1'], n_cells=r['n_cells'])


def revisit_stats(pos, t, n_cells, t_end, never_visited=True):
    """区域格点重访统计（访问时刻已按格点给出）。"""
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
