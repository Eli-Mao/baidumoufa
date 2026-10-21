"""覆盖与重访仿真的几何底座（逐步长扫描，exactsim.py 调用）；重访统计见 fasteval.revisit_stats。

几何约定（与赛题"统一设计与仿真条件"一致）：
- 地球按平均半径球体 R = 6371 km，卫星高度 h = a - R；
- 载荷为线阵推扫相机，幅宽 W(h) = 15 × h/530 km，交叉迹半视场角 η = 0.81°；
  沿迹方向按连续推扫处理（瞬时沿迹视场只有 0.001622°，推扫后成为连续条带），
  因此覆盖判据是"地面点到星下点轨迹的横向距离 ≤ 半幅宽"；
- 由 η 解地面半幅宽 d：tanη = sinλ / ((R+h)/R − cosλ)，d = R·λ。

两个指标：
- 全球覆盖 T90/T100：1°×1° 网格上首次覆盖时间（10 s 步长）。有效评价区有两种口径：
  星座可达纬度以内（|lat| ≤ 180° − i + 半幅宽，赛题文档"永久无法覆盖的区域不纳入"），
  或全部格点（答疑 #28"全球均为有效网格"）；
- 长三角重访 Tavg/Tmax：0.1°×0.1° 网格、1 s 步长。每个格点的间隔取前一次访问结束到
  下一次开始，并计入仿真首尾的不完整间隔（答疑 #28 / #41）；全部格点的间隔合并后
  取平均与最大（赛题文档公式）。
"""
import numpy as np

from sso import R_EARTH, j2_rates, gmst_rad

ETA_DEG = 0.81          # 交叉迹半视场角
ETA = np.radians(ETA_DEG)
SWATH_REF_H = 530.0     # 幅宽基准高度 km
SWATH_REF_W = 15.0      # 基准高度处幅宽 km


def swath_width(h_km):
    """幅宽 W(h) = 15 × h/530 km。"""
    return SWATH_REF_W * np.asarray(h_km, float) / SWATH_REF_H


def ground_half_width(h_km, eta=ETA):
    """交叉迹半视场角对应的地面横向半幅宽 (km)，球面精确解。"""
    h = np.asarray(h_km, float)
    lam = np.radians(0.0)
    lo, hi = 0.0, np.radians(10.0)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        rhs = np.sin(mid) / ((R_EARTH + h) / R_EARTH - np.cos(mid))
        if np.tan(eta) > rhs:
            lo = mid
        else:
            hi = mid
    lam = 0.5 * (lo + hi)
    return R_EARTH * lam


def max_reachable_lat(inc_deg, h_km):
    """星座可达的最高地心纬度（度）：逆行轨道取 180° − i，再加半幅宽。"""
    inc = np.asarray(inc_deg, float)
    base = np.where(inc <= 90.0, inc, 180.0 - inc)
    dlat = np.degrees(ground_half_width(np.min(h_km)) / R_EARTH)
    return float(base.max() + dlat)


class Grid:
    """等经纬度网格：格点中心 + 按格距分箱的一维编号。"""

    def __init__(self, lat0, lat1, dlat, lon0=-180.0, lon1=180.0, dlon=None):
        self.dlat = dlat
        self.dlon = dlon if dlon is not None else dlat
        self.nlat = int(round((lat1 - lat0) / self.dlat))
        self.nlon = int(round((lon1 - lon0) / self.dlon))
        j, i = np.meshgrid(np.arange(self.nlat), np.arange(self.nlon), indexing='ij')
        self.lat = lat0 + (j + 0.5) * self.dlat
        self.lon = lon0 + (i + 0.5) * self.dlon
        self.lat_c = self.lat.ravel()
        self.lon_c = self.lon.ravel()
        la, lo = np.radians(self.lat_c), np.radians(self.lon_c)
        self.unit = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=1)
        self.size = self.nlat * self.nlon
        self.lat0, self.lon0 = lat0, lon0

    def bin_of(self, lat, lon):
        """经纬度 -> (行号, 列号)，列号按 360° 环绕。"""
        i = np.floor((lat - self.lat0) / self.dlat).astype(np.int64)
        j = np.floor((lon - self.lon0) / self.dlon).astype(np.int64) % self.nlon
        return i, j


def _ecef_states(elems, t_jd):
    """J2 长期项传播，返回地固系位置 (N, T, 3)。"""
    a = R_EARTH + np.asarray(elems['h'], float)
    inc = np.radians(np.asarray(elems['inc'], float))
    raan_dot, argp_dot, m_dot = j2_rates(a, 0.0, inc)
    dt = (t_jd - t_jd[0]) * 86400.0
    raan = np.radians(np.asarray(elems['raan'], float))[:, None] + raan_dot[:, None] * dt
    u = np.radians(np.asarray(elems['u'], float))[:, None] + (argp_dot + m_dot)[:, None] * dt
    P = np.stack([np.cos(raan), np.sin(raan), np.zeros_like(raan)], axis=-1)
    Q = np.stack([-np.sin(raan) * np.cos(inc)[:, None],
                  np.cos(raan) * np.cos(inc)[:, None],
                  np.sin(inc)[:, None] * np.ones_like(raan)], axis=-1)
    r = a[:, None, None] * (np.cos(u)[..., None] * P + np.sin(u)[..., None] * Q)
    g = gmst_rad(t_jd)
    c, s = np.cos(g), np.sin(g)
    x, y = r[..., 0], r[..., 1]
    return np.stack([c * x + s * y, -s * x + c * y, r[..., 2]], axis=-1)


def _sample(sat_ecef, dt):
    """星下点方向、切平面内的沿迹/横迹单位矢量与地速 (km/s)。"""
    r = sat_ecef
    u = r / np.linalg.norm(r, axis=1, keepdims=True)
    v = np.gradient(r, dt, axis=0)              # 地固系速度，含地球自转
    v_t = v - np.einsum('ij,ij->i', v, u)[:, None] * u
    speed = np.linalg.norm(v_t, axis=1)
    that = v_t / np.maximum(speed, 1e-9)[:, None]
    chat = np.cross(u, that)
    chat /= np.maximum(np.linalg.norm(chat, axis=1), 1e-12)[:, None]
    lat = np.degrees(np.arcsin(np.clip(u[:, 2], -1, 1)))
    lon = np.degrees(np.arctan2(u[:, 1], u[:, 0]))
    return lat, lon, u, that, chat, speed


def _hits(grid, cu, u, that, chat, step_len, dmax):
    """格点相对星下点的横迹/沿迹距离（km），返回两个布尔。"""
    # 格点方向在星下点切平面上的投影
    p = cu - np.einsum('ij,ij->i', cu, u)[:, None] * u
    along = R_EARTH * np.einsum('ij,ij->i', p, that)
    cross = R_EARTH * np.einsum('ij,ij->i', p, chat)
    return (np.abs(cross) <= dmax) & (np.abs(along) <= 0.5 * step_len + dmax)


def global_coverage(sat_ecef, t_sec, grid, dmax, valid_mask=None, chunk=20000):
    """全球格点首次覆盖时间 (s)，未覆盖为 inf。dmax 可为标量或逐星数组（各星高度不同时）。"""
    first = np.full(grid.size, np.inf)
    dt = float(t_sec[1] - t_sec[0])
    dmaxs = np.broadcast_to(np.asarray(dmax, float), (sat_ecef.shape[0],))
    for n in range(sat_ecef.shape[0]):
        dmax = float(dmaxs[n])
        lat, lon, u, that, chat, speed = _sample(sat_ecef[n], dt)
        i0, j0 = grid.bin_of(lat, lon)
        step_len = float(np.mean(speed)) * dt
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                ii = i0 + di
                jj = (j0 + dj) % grid.nlon
                ok = (ii >= 0) & (ii < grid.nlat)
                idx = ii[ok] * grid.nlon + jj[ok]
                hit = _hits(grid, grid.unit[idx], u[ok], that[ok], chat[ok], step_len, dmax)
                if hit.any():
                    np.minimum.at(first, idx[hit], t_sec[ok][hit])
    return first


def coverage_metrics(first, grid, valid_mask=None, n_samples=None):
    """由格点首次覆盖时间算 T90 / T100 / 覆盖率。"""
    valid = np.ones(grid.size, bool) if valid_mask is None else valid_mask
    f = first[valid]
    n = len(f)
    covered = np.isfinite(f)
    out = dict(n_valid=int(n), n_covered=int(covered.sum()),
               coverage=float(covered.sum() / n) if n else 0.0)
    if covered.any():
        fs = np.sort(f[covered])
        k90 = int(np.ceil(0.9 * n)) - 1
        out['T90_s'] = float(fs[min(k90, len(fs) - 1)]) if covered.sum() >= k90 + 1 else None
        out['T100_s'] = float(fs[-1]) if covered.all() else None
    else:
        out['T90_s'] = out['T100_s'] = None
    return out


def region_access(sat_ecef, t_sec, grid, dmax, region_mask=None):
    """区域格点的访问时刻列表：返回 dict cell_idx -> np.array(times)。dmax 可为标量或逐星数组。"""
    dt = float(t_sec[1] - t_sec[0])
    out = {}
    dmaxs = np.broadcast_to(np.asarray(dmax, float), (sat_ecef.shape[0],))
    for n in range(sat_ecef.shape[0]):
        dmax = float(dmaxs[n])
        lat, lon, u, that, chat, speed = _sample(sat_ecef[n], dt)
        i0, j0 = grid.bin_of(lat, lon)
        step_len = float(np.mean(speed)) * dt
        hit_cells, hit_t = [], []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                ii = i0 + di
                jj = (j0 + dj) % grid.nlon
                ok = (ii >= 0) & (ii < grid.nlat)
                idx = ii[ok] * grid.nlon + jj[ok]
                hit = _hits(grid, grid.unit[idx], u[ok], that[ok], chat[ok], step_len, dmax)
                if hit.any():
                    hit_cells.append(idx[hit])
                    hit_t.append(t_sec[ok][hit])
        if hit_cells:
            cells = np.concatenate(hit_cells)
            times = np.concatenate(hit_t)
            o = np.lexsort((times, cells))
            cells, times = cells[o], times[o]
            for c in np.unique(cells):
                m = cells == c
                out.setdefault(int(c), []).append(times[m])
    return {k: np.sort(np.concatenate(v)) for k, v in out.items()}


def merge_visits(times, gap=3.0):
    """把连续覆盖的 1 s 采样合并成"一次访问"，返回每次访问的 (起始, 结束) 时刻；结束取最后一个覆盖采样。"""
    times = np.asarray(times, float)
    if len(times) == 0:
        return np.empty(0), np.empty(0)
    brk = np.nonzero(np.diff(times) > gap)[0]
    return np.r_[times[0], times[brk + 1]], np.r_[times[brk], times[-1]]


