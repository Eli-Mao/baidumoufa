"""轨道传播与可见性计算。分区：**楼心荡**。

职责边界：
    输入 ``轨道.txt``（10000 颗 TLE）与 ``站址.txt``（10 个站），
    输出每一颗卫星 × 每一个站点的候选可见窗口。

可见性判定口径（登记在 config.py）：
    1. 站点仰角 ∈ [MIN_ELEV_DEG, MAX_ELEV_DEG] = [10, 85] 度（几何仰角，不含大气折射）；
    2. 测站太阳高度角 < SUN_ELEV_MAX_DEG = -6 度（测站处于暗夜）；
    3. 卫星本身受太阳照亮（REQUIRE_SAT_SUNLIT）。
主办方答疑：可见窗口以 Skyfield 计算结果为参考标准。本模块的坐标与光照口径都与 Skyfield 对齐：
    - SGP4 按 UTC 传播；TEME -> 地固系绕 z 轴转 IAU-82 GMST，GMST 按 UT1 计算
      （UT1−UTC 取 Skyfield 内置值），忽略极移——与 Skyfield 的 TEME->GCRS->ITRS 链等价；
    - 站点按 WGS84 大地坐标（含海拔），仰角相对椭球法向；
    - 测站太阳高度：(earth + 测站).at(t).observe(sun).apparent().altaz()，DE421 星历；
    - 卫星受照：判据同 Skyfield ``is_sunlit``（地球为半径 ERAD 的球、太阳为点光源、无半影）。

算法：
    粗扫（COARSE_STEP_S = 30 s，SatrecArray 整批传播）找可见性跳变 -> 跳变处二分到 EDGE_TOL_S；
    粗网格上仰角 > 30° 的局部极大再黄金分割，真实峰值 > 85° 就把窗口切开；
    一个粗步长内跨越多条约束的卫星（极低轨、外推发散的怪轨道）改用 ``step_s`` 细步长整星重算；
    几何窗口 ∩ 测站黑夜 ∩ 卫星受照（扫描线求区间交集）；
    最后去掉短于 config.MIN_DUR_S 的窗口，两端各向内收 SAFETY_S，保证窗口内处处满足约束。
SGP4 报错的时刻一律视为不可见。

实现依赖：``skyfield`` + ``sgp4``（只在本模块内部 import，避免全项目强依赖）。
实测性能：10000 星 × 10 站 × 6 天，8 进程约 50 秒，约 57 万个窗口（10.01~10.07 UTC）。
"""

from __future__ import annotations

import datetime as _dt
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, io_schema

# 实现参数（不是赛题口径，赛题口径在 config.py）
COARSE_STEP_S = 30.0      # 粗扫步长 s；LEO 从 10° 升到 85° 要几分钟，30 s 内最多跨一条约束
EDGE_TOL_S = 0.1          # 窗口边界二分精度 s
SAFETY_S = 0.2            # 窗口两端向内收缩 s，抵消二分精度与毫秒取整，保证窗口内处处合规
PEAK_CHECK_DEG = 30.0     # 粗网格局部极大高于此值的弧段，细查是否漏掉 >85° 的过顶段
CHUNK_SATS = 200          # 每批传播的卫星数（控制内存，每进程峰值约 0.5 GB）
SUN_STEP_S = 600.0        # 太阳位置网格（线性插值方向误差 < 1e-9 rad）
DARK_STEP_S = 60.0        # 测站黑夜时段的粗网格，跳变处二分到 0.01 s
EPHEMERIS = config.DATA_RAW / "de421.bsp"   # 不存在时 Skyfield 自动下载（约 16 MB）

WGS84_A = 6378.137
WGS84_F = 1 / 298.257223563


# --------------------------------------------------------------------------
# 几何与光照基础函数
# --------------------------------------------------------------------------


def station_frame(stations: pd.DataFrame) -> pd.DataFrame:
    """按 station_id 排序，经度换算到 [-180, 180)（站址.txt 里有 290°、358° 这种 0~360 写法）。"""
    st = stations.sort_values("station_id").reset_index(drop=True).copy()
    st["lon_deg"] = (st["lon_deg"].astype(float) + 180.0) % 360.0 - 180.0
    return st


def station_vectors(stations: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """站点 WGS84 地固系位置 (S,3) km 和当地天顶单位向量 (S,3)。"""
    lat = np.radians(stations["lat_deg"].to_numpy(float))
    lon = np.radians(stations["lon_deg"].to_numpy(float))
    h = stations["alt_m"].to_numpy(float) / 1000.0
    e2 = WGS84_F * (2 - WGS84_F)
    n = WGS84_A / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    pos = np.stack([(n + h) * np.cos(lat) * np.cos(lon),
                    (n + h) * np.cos(lat) * np.sin(lon),
                    (n * (1 - e2) + h) * np.sin(lat)], axis=1)
    up = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1)
    return pos, up


def gmst(jd, fr):
    """IAU-82 格林尼治平恒星时 (rad)。"""
    t = (jd - 2451545.0 + fr) / 36525.0
    sec = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t ** 2 - 6.2e-6 * t ** 3
    return (sec % 86400.0) / 86400.0 * 2 * np.pi


def teme_to_ecef(r, g):
    """r[..., 3] TEME (km) 绕 z 轴转 GMST 得到地固系；g 与 r[..., 0] 可广播。"""
    c, s = np.cos(g), np.sin(g)
    x, y = r[..., 0], r[..., 1]
    return np.stack([c * x + s * y, -s * x + c * y, r[..., 2]], axis=-1)


def elevation_deg(r_ecef, st_pos, st_up):
    rho = r_ecef - st_pos
    s = np.einsum("...i,...i->...", rho, st_up) / np.linalg.norm(rho, axis=-1)
    return np.degrees(np.arcsin(np.clip(s, -1.0, 1.0)))


def sunlit(r, sun):
    """卫星是否被太阳照亮，判据同 Skyfield ``ICRF.is_sunlit``。

    从卫星指向太阳的射线若在卫星前方与地球（半径 ERAD 的球）相交，卫星就在地影中。
    r、sun 为同一惯性系（TEME）的 km 坐标，可广播 (..., 3)；r 为 NaN（SGP4 报错）返回 False。
    """
    from skyfield.constants import ERAD

    center = -r
    end = sun - r
    minus_b = 2.0 * np.einsum("...i,...i->...", end, center) / np.linalg.norm(end, axis=-1)
    c = np.einsum("...i,...i->...", center, center) - (ERAD / 1000.0) ** 2
    with np.errstate(invalid="ignore"):
        far = 0.5 * (minus_b + np.sqrt(minus_b * minus_b - 4.0 * c))
        return ~(far > 0) & ~np.isnan(r[..., 0])


def bisect_edge(pred, lo, hi, vis_lo, tol):
    """[lo, hi] 两端 pred 取值不同（vis_lo 为 lo 端的值），二分到 tol 秒，返回 pred 为真一侧的端点。"""
    if len(lo) == 0:
        return lo
    lo, hi = lo.copy(), hi.copy()
    for _ in range(int(np.ceil(np.log2(max((hi - lo).max(), tol) / tol)))):
        mid = 0.5 * (lo + hi)
        same = pred(mid) == vis_lo
        lo = np.where(same, mid, lo)
        hi = np.where(same, hi, mid)
    return np.where(vis_lo, lo, hi)


def intersect_intervals(ka, a0, a1, kb, b0, b1):
    """按 key 求两组区间的交集，返回 (key, 起, 止)。每组在同一 key 内须互不重叠、长度 > 0。

    扫描线：起 +1、止 −1，覆盖数为 2 的段就是交集；同一时刻先处理"止"，首尾相接不算相交。
    """
    n, m = len(a0), len(b0)
    key = np.concatenate([ka, ka, kb, kb])
    tt = np.concatenate([a0, a1, b0, b1])
    kind = np.repeat(np.array([1, -1, 1, -1], np.int8), [n, n, m, m])
    o = np.lexsort((kind, tt, key))
    key, tt, kind = key[o], tt[o], kind[o]
    cov = np.cumsum(kind, dtype=np.int64)
    opens = (kind == 1) & (cov == 2)
    closes = (kind == -1) & (cov == 1)
    return key[opens], tt[opens], tt[closes]


def _skyfield_times(ts, t0_utc, secs):
    t0 = pd.Timestamp(t0_utc)
    return ts.utc(t0.year, t0.month, t0.day, t0.hour, t0.minute,
                  t0.second + t0.microsecond * 1e-6 + np.asarray(secs, float))


def load_ephemeris(path: Path | None = None):
    """读 JPL 星历（默认 data/raw/de421.bsp），不存在时 Skyfield 自动下载到同一目录。"""
    from skyfield.api import Loader

    path = Path(path or EPHEMERIS)
    path.parent.mkdir(parents=True, exist_ok=True)
    return Loader(str(path.parent), verbose=False)(path.name)


def ut1_utc(start_utc: str, duration_s: float, step: float = 3600.0):
    """Skyfield 内置时间尺度的 UT1−UTC（秒），返回 (相对起点的秒网格, 值)。

    Skyfield 把 TEME 转到地固系时用 UT1 算 GMST；规划期 2026-08-01 ~ 08-07 约 +0.08 s，GEO 仰角变化极慢，
    不用同一套 UT1 会让 GEO 窗口边界差出几秒。
    """
    from skyfield.api import load

    ts = load.timescale(builtin=True)
    t = np.append(np.arange(0.0, duration_s, step), duration_s)
    return t, np.asarray(_skyfield_times(ts, start_utc, t).dut1, float)


def prepare_lighting(stations: pd.DataFrame, start_utc: str, duration_s: float,
                     sun_alt_max: float = config.SUN_ELEV_MAX_DEG, tol: float = 0.01):
    """测站黑夜时段（太阳高度 < sun_alt_max）与太阳在 TEME 系的位置，返回 (lighting dict, 黑夜表)。"""
    from skyfield.api import load, wgs84
    from skyfield.sgp4lib import TEME

    eph = load_ephemeris()
    ts = load.timescale(builtin=True)
    sun, earth = eph["sun"], eph["earth"]
    sun_t = np.append(np.arange(0.0, duration_s, SUN_STEP_S), duration_s)
    sun_xyz = (sun - earth).at(_skyfield_times(ts, start_utc, sun_t)).frame_xyz(TEME).km.T

    t = np.append(np.arange(0.0, duration_s, DARK_STEP_S), duration_s)
    rows = []
    for i, s in enumerate(stations.itertuples()):
        obs = earth + wgs84.latlon(s.lat_deg, s.lon_deg, elevation_m=s.alt_m)

        def dark(x, obs=obs):
            alt = obs.at(_skyfield_times(ts, start_utc, x)).observe(sun).apparent().altaz()[0].degrees
            return alt < sun_alt_max

        d = dark(t)
        up = np.nonzero(~d[:-1] & d[1:])[0]
        dn = np.nonzero(d[:-1] & ~d[1:])[0]
        a = bisect_edge(dark, t[up], t[up + 1], False, tol)
        b = bisect_edge(dark, t[dn], t[dn + 1], True, tol)
        if d[0]:
            a = np.r_[0.0, a]
        if d[-1]:
            b = np.r_[b, duration_s]
        for x, y in zip(np.sort(a), np.sort(b)):
            rows.append(dict(st_idx=i, station_id=s.station_id, dark_start_s=x, dark_end_s=y))

    dark_df = pd.DataFrame(rows, columns=["st_idx", "station_id", "dark_start_s", "dark_end_s"])
    lighting = dict(sun_t=sun_t, sun_xyz=sun_xyz, dark_st=dark_df["st_idx"].to_numpy(),
                    dark_a=dark_df["dark_start_s"].to_numpy(), dark_b=dark_df["dark_end_s"].to_numpy())
    return lighting, dark_df.drop(columns="st_idx")


# --------------------------------------------------------------------------
# 可见窗口模型
# --------------------------------------------------------------------------

_WORKER: dict = {}


def _init_worker(model, kws):
    _WORKER["model"], _WORKER["kws"] = model, kws


def _run_chunk(task):
    idx, which = task           # which：'coarse' 粗扫 / 'fine' 细步长重算
    return _WORKER["model"]._chunk(idx, **_WORKER["kws"][which])


class VisibilityModel:
    """一批卫星 × 全部站点的可见窗口。时间一律是相对场景起点的秒（UTC）。"""

    def __init__(self, tles, stations, start_utc, duration_s, *, min_el=config.MIN_ELEV_DEG,
                 max_el=config.MAX_ELEV_DEG, lighting=None, require_sunlit=config.REQUIRE_SAT_SUNLIT,
                 dut1=None):
        """tles：[(line1, line2)]；stations：station_frame() 的结果；lighting：prepare_lighting() 的第一个返回值。"""
        from sgp4.api import Satrec, jday

        self.tles = [tuple(x) for x in tles]
        self.sats = [Satrec.twoline2rv(l1, l2) for l1, l2 in self.tles]
        self.station_ids = stations["station_id"].to_numpy()
        self.st_pos, self.st_up = station_vectors(stations)
        t0 = pd.Timestamp(start_utc)
        self.duration = float(duration_s)
        self.jd0, self.fr0 = jday(t0.year, t0.month, t0.day, t0.hour, t0.minute,
                                  t0.second + t0.microsecond * 1e-6)
        self.min_el, self.max_el = min_el, max_el
        self.lighting, self.require_sunlit, self.dut1 = lighting, require_sunlit, dut1

    # Satrec 不能 pickle：传给子进程时只带 TLE 原文，在子进程里重建
    def __getstate__(self):
        state = self.__dict__.copy()
        del state["sats"]
        return state

    def __setstate__(self, state):
        from sgp4.api import Satrec

        self.__dict__.update(state)
        self.sats = [Satrec.twoline2rv(l1, l2) for l1, l2 in self.tles]

    def _jdfr(self, t):
        return np.full(t.shape, self.jd0), self.fr0 + t / 86400.0

    def _gmst(self, t):
        jd, fr = self._jdfr(t)
        if self.dut1 is not None:
            fr = fr + np.interp(t, *self.dut1) / 86400.0
        return gmst(jd, fr)

    def visible(self, el):
        return (el >= self.min_el) & (el <= self.max_el)

    def _teme_at(self, sat_idx, t):
        """逐点 (卫星, 时刻) 的 TEME 位置 km；SGP4 报错的点为 NaN。"""
        r = np.full((len(t), 3), np.nan)
        order = np.argsort(sat_idx, kind="stable")
        uniq, first = np.unique(sat_idx[order], return_index=True)
        for u, a, b in zip(uniq, first, np.append(first[1:], len(order))):
            ii = order[a:b]
            e, rr, _ = self.sats[u].sgp4_array(*self._jdfr(t[ii]))
            r[ii] = np.where((e == 0)[:, None], rr, np.nan)
        return r

    def _sun_at(self, t):
        L = self.lighting
        return np.stack([np.interp(t, L["sun_t"], L["sun_xyz"][:, i]) for i in range(3)], axis=-1)

    def elevation_at(self, sat_idx, st_idx, t):
        """逐点 (卫星, 站, 时刻) 的仰角；SGP4 报错的点记为 -90°。"""
        r = self._teme_at(sat_idx, t)
        with np.errstate(invalid="ignore"):
            el = elevation_deg(teme_to_ecef(r, self._gmst(t)), self.st_pos[st_idx], self.st_up[st_idx])
        return np.where(np.isnan(el), -90.0, el)

    def sunlit_at(self, sat_idx, t):
        return sunlit(self._teme_at(sat_idx, t), self._sun_at(t))

    def _bisect(self, sat, st, lo, hi, vis_lo, tol):
        return bisect_edge(lambda m: self.visible(self.elevation_at(sat, st, m)), lo, hi, vis_lo, tol)

    def _golden_max(self, sat, st, a, b, tol):
        """[a, b] 上黄金分割找仰角极大，返回实际算过的最高点 (t, el)。"""
        k = (np.sqrt(5) - 1) / 2
        c, d = b - k * (b - a), a + k * (b - a)
        fc, fd = self.elevation_at(sat, st, c), self.elevation_at(sat, st, d)
        while len(a) and (b - a).max() > tol:
            left = fc > fd
            a, b = np.where(left, a, c), np.where(left, d, b)
            t_new = np.where(left, b - k * (b - a), a + k * (b - a))
            f_new = self.elevation_at(sat, st, t_new)
            c, d, fc, fd = (np.where(left, t_new, d), np.where(left, c, t_new),
                            np.where(left, f_new, fd), np.where(left, fc, f_new))
        best = fc > fd
        return np.where(best, c, d), np.where(best, fc, fd)

    def compute_windows(self, step=COARSE_STEP_S, tol=EDGE_TOL_S, chunk=CHUNK_SATS, workers=1,
                        fine_step=1.0, fine_chunk=4, log=print):
        """返回 (窗口 DataFrame, stats)。窗口列：sat_idx, station_id, start_s, end_s, max_el_deg, t_peak_s。"""
        grid = lambda h: np.append(np.arange(0.0, self.duration, h), self.duration)
        base = dict(tol=tol, peak_tol=tol / 2)
        kws = dict(coarse=dict(t=grid(step), **base),
                   fine=None if not fine_step else dict(t=grid(fine_step), **base))
        n_sat = len(self.sats)
        tasks = [(np.arange(c0, min(c0 + chunk, n_sat)), "coarse") for c0 in range(0, n_sat, chunk)]
        sgp4_error_s = np.full(n_sat, np.nan)
        alt_min, alt_max = np.full(n_sat, np.nan), np.full(n_sat, np.nan)
        stats = dict(anomalies=0, peak_split=0, n_geometric=0, fine_anomalies=0)
        coarse_parts, fine_parts, suspect = [], [], []
        tic = time.perf_counter()

        def collect(task, res):
            idx, which = task
            part, cnt, err_s, (amin, amax), anom = res
            sgp4_error_s[idx], alt_min[idx], alt_max[idx] = err_s, amin, amax
            if which == "coarse":
                coarse_parts.append(part)
                suspect.extend(anom.tolist())
                for k in ("anomalies", "peak_split", "n_geometric"):
                    stats[k] += cnt[k]
            else:
                fine_parts.append(part)
                stats["fine_anomalies"] += cnt["anomalies"]
            log(f"  [{'粗扫' if which == 'coarse' else f'{fine_step:g}s 重算'}] 卫星 {idx[-1] + 1}/{n_sat}"
                f"  已用 {time.perf_counter() - tic:.1f}s")

        def fine_tasks():
            if kws["fine"] is None:
                return []
            s = np.array(sorted(suspect), dtype=np.int64)
            return [(s[i:i + fine_chunk], "fine") for i in range(0, len(s), fine_chunk)]

        def run(ts_, mapper):
            for task, res in zip(ts_, mapper(ts_)):
                collect(task, res)

        if workers > 1 and len(tasks) > 1:
            with ProcessPoolExecutor(min(workers, len(tasks)), initializer=_init_worker,
                                     initargs=(self, kws)) as ex:
                mapper = lambda ts_: ex.map(_run_chunk, ts_)
                run(tasks, mapper)
                run(fine_tasks(), mapper)
        else:
            mapper = lambda ts_: (self._chunk(i, **kws[w]) for i, w in ts_)
            run(tasks, mapper)
            run(fine_tasks(), mapper)
        win = pd.concat(coarse_parts, ignore_index=True)
        if fine_parts:
            win = pd.concat([win[~win["sat_idx"].isin(suspect)]] + fine_parts, ignore_index=True)
        stats.update(t_wall=round(time.perf_counter() - tic, 2), anomaly_sats=len(suspect),
                     sgp4_error_s=sgp4_error_s, alt_min_km=alt_min, alt_max_km=alt_max)
        return win, stats

    def _chunk(self, idx, t, tol, peak_tol):
        """一批卫星（全局下标 idx）在时间网格 t 上的窗口。"""
        from sgp4.api import SatrecArray

        T, S = len(t), len(self.station_ids)
        jd, fr = self._jdfr(t)
        g = self._gmst(t)
        cnt = dict(anomalies=0, peak_split=0, n_geometric=0)
        e, r, _ = SatrecArray([self.sats[i] for i in idx]).sgp4(jd, fr)
        bad = e != 0
        first_bad = bad.argmax(axis=1)
        err_s = np.where(bad.any(axis=1), t[first_bad], np.nan)
        # 规划期内的高度范围：用来标出外推失效（高得离谱）或已再入（低于 100 km）的目标
        alt = np.linalg.norm(r, axis=-1) - WGS84_A
        any_ok = ~bad.all(axis=1)
        alt_rng = (np.where(any_ok, np.where(bad, np.inf, alt).min(axis=1), np.nan),
                   np.where(any_ok, np.where(bad, -np.inf, alt).max(axis=1), np.nan))
        del alt
        lit = None
        if self.lighting is not None and self.require_sunlit:
            lit = sunlit(r, self._sun_at(t)) & ~bad
        r_ecef = teme_to_ecef(r, g)
        del r
        edges, peaks, ends, els, anom_rows = [], [], [], [], []
        for s in range(S):
            el = elevation_deg(r_ecef, self.st_pos[s], self.st_up[s])
            el[bad] = -90.0
            vis = self.visible(el)
            els.append(el.astype(np.float32))
            for col, kind in ((0, 1), (T - 1, -1)):          # 场景起止时刻可见 -> 窗口截在边界
                rows = np.nonzero(vis[:, col])[0]
                ends.append((rows, np.full(len(rows), s), np.full(len(rows), t[col]), np.full(len(rows), kind)))
            for kind, (rows, k) in ((1, np.nonzero(~vis[:, :-1] & vis[:, 1:])),
                                    (-1, np.nonzero(vis[:, :-1] & ~vis[:, 1:]))):
                edges.append((rows, np.full(len(rows), s), t[k], t[k + 1], np.full(len(rows), kind)))
            # 可能漏掉的 >85° 过顶段：可见且仰角较高的局部极大点
            pk = vis & (el > PEAK_CHECK_DEG)
            pk[:, 1:] &= el[:, 1:] >= el[:, :-1]
            pk[:, :-1] &= el[:, :-1] > el[:, 1:]
            rows, k = np.nonzero(pk)
            kl, kr = np.maximum(k - 1, 0), np.minimum(k + 1, T - 1)
            ok = vis[rows, kl] & vis[rows, kr]
            cnt["anomalies"] += int((~ok).sum())
            anom_rows.append(rows[~ok])
            rows, k, kl, kr = rows[ok], k[ok], kl[ok], kr[ok]
            peaks.append((rows, np.full(len(rows), s), t[kl], t[k], t[kr]))
        del r_ecef

        rows, st, lo, hi, kind = [np.concatenate(x) for x in zip(*edges)]
        ev = [(rows, st, self._bisect(idx[rows], st, lo, hi, kind == -1, tol), kind)]
        ev += ends
        rows, st, tl, tk, tr = [np.concatenate(x) for x in zip(*peaks)]
        tw, elw = self._golden_max(idx[rows], st, tl, tr, tol / 5)
        over = elw > self.max_el
        cnt["peak_split"] += int(over.sum())
        rows, st, tl, tk, tr, tw = rows[over], st[over], tl[over], tk[over], tr[over], tw[over]
        left, right = np.where(tw < tk, tl, tk), np.where(tw < tk, tk, tr)
        n = len(rows)
        ev.append((rows, st, self._bisect(idx[rows], st, left, tw, np.ones(n, bool), tol), -np.ones(n, int)))
        ev.append((rows, st, self._bisect(idx[rows], st, tw, right, np.zeros(n, bool), tol), np.ones(n, int)))

        rows, st, te, kind = [np.concatenate(x) for x in zip(*ev)]
        o = np.lexsort((-kind, te, st, rows))          # 同一时刻"起"排在"止"前面
        rows, st, te, kind = rows[o], st[o], te[o], kind[o]
        cum = np.cumsum(kind)
        cut = np.nonzero((rows[1:] != rows[:-1]) | (st[1:] != st[:-1]))[0] + 1
        if len(cut):                                     # cumsum 按 (卫星, 站) 分组清零
            starts = np.r_[0, cut]
            bases = np.r_[0, cum[cut - 1]]
            cum = cum - np.repeat(bases, np.diff(np.r_[starts, len(cum)]))
        opens = (kind == 1) & (cum == 1)
        closes = (kind == -1) & (cum == 0)
        if opens.sum() != closes.sum():
            raise RuntimeError(f"卫星 {idx[0]}–{idx[-1]}：窗口起止事件无法配对")
        rows, st, ts, tend = rows[opens], st[opens], te[opens], te[closes]
        cnt["n_geometric"] += len(rows)
        if self.lighting is not None:
            rows, st, ts, tend = self._apply_lighting(idx, lit, t, rows, st, ts, tend, tol)

        # 真实峰值：≤1 h 的窗口单峰，黄金分割；更长的（GEO/HEO）取粗网格最大值
        dur = tend - ts
        tw = np.full(len(rows), np.nan)
        elw = np.full(len(rows), np.nan)
        short = dur <= 3600.0
        if short.any():
            tw[short], elw[short] = self._golden_max(idx[rows[short]], st[short], ts[short], tend[short], peak_tol)
        if (~short).any():
            ka = np.searchsorted(t, ts, "left")
            kb = np.searchsorted(t, tend, "right")
            for j in np.nonzero(~short)[0]:
                a = int(ka[j])
                b = max(int(kb[j]), a + 1)
                row = els[st[j]][rows[j], a:b]
                k = a + int(np.argmax(row))
                elw[j], tw[j] = float(row[k - a]), t[min(k, T - 1)]
        part = pd.DataFrame(dict(sat_idx=idx[rows], station_id=self.station_ids[st],
                                 start_s=ts, end_s=tend, max_el_deg=elw, t_peak_s=tw))
        return part, cnt, err_s, alt_rng, np.unique(idx[np.concatenate(anom_rows)])

    def _apply_lighting(self, idx, lit, t, rows, st, ts, tend, tol):
        """几何窗口 ∩ 测站黑夜（∩ 卫星受照），返回新的 (rows, st, ts, tend)。"""
        n, S, L = len(idx), len(self.station_ids), self.lighting
        ok = tend > ts
        m = len(L["dark_st"])
        k_dark = np.repeat(np.arange(n), m) * S + np.tile(L["dark_st"], n)
        k, a, b = intersect_intervals(rows[ok] * S + st[ok], ts[ok], tend[ok],
                                      k_dark, np.tile(L["dark_a"], n), np.tile(L["dark_b"], n))
        if lit is not None:
            ev = []
            for kind, (r_, kk) in ((1, np.nonzero(~lit[:, :-1] & lit[:, 1:])),
                                   (-1, np.nonzero(lit[:, :-1] & ~lit[:, 1:]))):
                x = bisect_edge(lambda mm, s=idx[r_]: self.sunlit_at(s, mm), t[kk], t[kk + 1], kind == -1, tol)
                ev.append((r_, x, np.full(len(r_), kind)))
            for col, kind in ((0, 1), (len(t) - 1, -1)):
                r_ = np.nonzero(lit[:, col])[0]
                ev.append((r_, np.full(len(r_), t[col]), np.full(len(r_), kind)))
            r_, x, kind = [np.concatenate(v) for v in zip(*ev)]
            o = np.lexsort((-kind, x, r_))
            r_, x, kind = r_[o], x[o], kind[o]
            s_row, s_a, s_b = r_[kind == 1], x[kind == 1], x[kind == -1]
            keep = s_b > s_a
            s_row, s_a, s_b = s_row[keep], s_a[keep], s_b[keep]
            k_sun = np.repeat(s_row, S) * S + np.tile(np.arange(S), len(s_row))
            k, a, b = intersect_intervals(k, a, b, k_sun, np.repeat(s_a, S), np.repeat(s_b, S))
        return k // S, k % S, a, b


# --------------------------------------------------------------------------
# 对外接口（签名已冻结）
# --------------------------------------------------------------------------


def _naive_utc(dt: _dt.datetime) -> str:
    return dt.astimezone(_dt.timezone.utc).replace(tzinfo=None).isoformat()


def _period(t0_utc: str | None, days: int | None) -> tuple[str, float, str]:
    """(场景起点的无时区 UTC ISO 串, 时长 s, 起点 ISO8601 'Z' 串)。"""
    t0 = io_schema.parse_utc(t0_utc or config.PLAN_T0_UTC)
    return _naive_utc(t0), float((days or config.PLAN_DAYS) * 86400), io_schema.to_utc_str(t0)


def propagate_windows(
    tle_df: pd.DataFrame | None = None,
    stations: pd.DataFrame | None = None,
    *,
    t0_utc: str | None = None,
    days: int | None = None,
    step_s: float = 1.0,
    workers: int = 8,
) -> pd.DataFrame:
    """计算全部候选可见窗口，返回原始窗口表（由 :func:`satplan.windows.assemble_windows` 补全成契约表）。

    Parameters
    ----------
    tle_df : DataFrame | None
        由 :func:`satplan.io_schema.read_tle_raw` 产出；为 None 时自行读取原始文件。
    stations : DataFrame | None
        由 :func:`satplan.io_schema.read_stations_raw` 产出；经度在本模块内部换算到 [-180, 180)。
    t0_utc : str | None
        规划期起点，默认取 ``config.PLAN_T0_UTC``。
    days : int | None
        规划期长度，默认 ``config.PLAN_DAYS``。
    step_s : float
        细步长 s：粗扫（COARSE_STEP_S）发现一个步长内跨越多条约束的卫星，改用此步长整星重算。
        窗口边界本身二分到 EDGE_TOL_S = 0.1 s，与 step_s 无关。
    workers : int
        并行进程数，1 为单进程（结果与多进程逐位一致）。

    Returns
    -------
    DataFrame
        列：``station_id, sat_id, t_start_s, t_end_s, max_elev_deg, t_peak_s``，
        已去掉短于 config.MIN_DUR_S 的窗口、两端各收 SAFETY_S、向内取整到毫秒。
        ``attrs``：``t0_utc``（ISO8601）、``days``、``stats``（计数与耗时），均可 JSON 序列化。
        每星的轨道状态（SGP4 报错、高度范围）用 :func:`orbit_health` 单独取。
    """
    tic = time.perf_counter()
    tle_df = tle_df if tle_df is not None else io_schema.read_tle_raw()
    stations = station_frame(stations if stations is not None else io_schema.read_stations_raw())
    start, duration, t0_iso = _period(t0_utc, days)
    lighting, _ = prepare_lighting(stations, start, duration)
    model = VisibilityModel(list(zip(tle_df["line1"], tle_df["line2"])), stations, start, duration,
                            lighting=lighting, dut1=ut1_utc(start, duration))
    win, stats = model.compute_windows(workers=workers, fine_step=step_s)

    min_len = config.MIN_DUR_S + 2 * SAFETY_S
    win = win[win["end_s"] - win["start_s"] >= min_len].copy()
    sat_id = tle_df["sat_id"].to_numpy()[win["sat_idx"].to_numpy()]
    out = pd.DataFrame({
        "station_id": win["station_id"].astype("int64").to_numpy(),
        "sat_id": sat_id.astype("int64"),
        "t_start_s": np.ceil((win["start_s"].to_numpy() + SAFETY_S) * 1000) / 1000,
        "t_end_s": np.floor((win["end_s"].to_numpy() - SAFETY_S) * 1000) / 1000,
        "max_elev_deg": win["max_el_deg"].round(2).to_numpy(),
    })
    out["t_peak_s"] = np.clip(win["t_peak_s"].to_numpy(), out["t_start_s"], out["t_end_s"]).round(3)
    out = out.sort_values(["sat_id", "station_id", "t_start_s"]).reset_index(drop=True)

    for k in ("sgp4_error_s", "alt_min_km", "alt_max_km"):    # 每星数组不放进 attrs（attrs 要能 JSON 序列化）
        stats.pop(k)
    out.attrs["t0_utc"] = t0_iso
    out.attrs["days"] = duration / 86400
    out.attrs["stats"] = {k: (float(v) if isinstance(v, float) else int(v)) for k, v in stats.items()}
    out.attrs["stats"].update(n_windows=len(out), t_total=round(time.perf_counter() - tic, 2))
    return out


def orbit_health(tle_df: pd.DataFrame | None = None, *, t0_utc: str | None = None, days: int | None = None,
                 step_s: float = 300.0, chunk: int = 1000) -> pd.DataFrame:
    """每颗星在规划期内的轨道状态，用来区分"光学上看不到"与"外推失效"的无窗口卫星。

    返回列：sat_id, sgp4_error_at_s（首次报错时刻，NaN 为全程正常）, alt_min_km, alt_max_km,
    apogee_km, orbit_flag ∈ {ok, sgp4_error_at_start, implausible, reentered}：
      sgp4_error_at_start = 规划起点就已 SGP4 报错（多为已再入）；
      implausible = 最高点地心距 > 历元远地点地心距的 2 倍（外推发散）；
      reentered = 规划期内最低高度 < 100 km。
    """
    from sgp4.api import Satrec, SatrecArray, jday

    tle_df = tle_df if tle_df is not None else io_schema.read_tle_raw()
    start, duration, _ = _period(t0_utc, days)
    t0 = pd.Timestamp(start)
    jd0, fr0 = jday(t0.year, t0.month, t0.day, t0.hour, t0.minute, t0.second)
    t = np.append(np.arange(0.0, duration, step_s), duration)
    jd, fr = np.full(t.shape, jd0), fr0 + t / 86400.0
    sats = [Satrec.twoline2rv(a, b) for a, b in zip(tle_df["line1"], tle_df["line2"])]
    err_s, amin, amax = [], [], []
    for c0 in range(0, len(sats), chunk):
        e, r, _ = SatrecArray(sats[c0:c0 + chunk]).sgp4(jd, fr)
        bad = e != 0
        alt = np.linalg.norm(r, axis=-1) - WGS84_A
        any_ok = ~bad.all(axis=1)
        err_s.append(np.where(bad.any(axis=1), t[bad.argmax(axis=1)], np.nan))
        amin.append(np.where(any_ok, np.where(bad, np.inf, alt).min(axis=1), np.nan))
        amax.append(np.where(any_ok, np.where(bad, -np.inf, alt).max(axis=1), np.nan))
    df = pd.DataFrame({"sat_id": tle_df["sat_id"].to_numpy(), "sgp4_error_at_s": np.concatenate(err_s),
                       "alt_min_km": np.concatenate(amin), "alt_max_km": np.concatenate(amax),
                       "apogee_km": [s.alta * s.radiusearthkm for s in sats]})
    df["orbit_flag"] = np.select(
        [df["sgp4_error_at_s"] == 0,
         df["alt_max_km"] + WGS84_A > 2 * (df["apogee_km"] + WGS84_A),
         df["alt_min_km"] < 100],
        ["sgp4_error_at_start", "implausible", "reentered"], "ok")
    return df


def cross_validate(
    windows: pd.DataFrame,
    *,
    sample_sat_ids: list[int] | None = None,
    step_s: float = 1.0,
) -> pd.DataFrame:
    """抽样逐秒复核：用 Skyfield 自己的 API 独立重算若干卫星，比对窗口边界误差。

    仰角、测站太阳高度、卫星受照全部用 Skyfield 逐点计算，不调用本模块的任何几何代码；
    按 ``step_s`` 采样，边界分辨率 ±step_s。与本模块同一约定：SGP4 报错的时刻不可见。

    返回逐窗口明细（kind = ours 为本模块的窗口，missed 为 Skyfield 找到而本模块没有的窗口）：
    sat_id, station_id, kind, t_start_s, t_end_s, d_start, d_end（本模块边界 − Skyfield 采样边界）,
    bad_samples / bad_elev / bad_dark / bad_lit（窗口内违反约束的采样点数）。
    汇总在 ``attrs['summary']``：抽查卫星数、窗口数、违规窗口数、漏窗口数、|边界差| 分位数。
    """
    from skyfield.api import EarthSatellite, load, wgs84

    if not len(windows):
        raise ValueError("窗口表为空，无法交叉验证")
    first = windows.iloc[0]
    t0 = io_schema.parse_utc(first["t_start_utc"]) - _dt.timedelta(seconds=float(first["t_start_s"]))
    days = windows.attrs.get("days", config.PLAN_DAYS)
    tle_df = io_schema.read_tle_raw()
    stations = station_frame(io_schema.read_stations_raw())
    if sample_sat_ids is None:
        sample_sat_ids = tle_df["sat_id"].sample(10, random_state=config.RANDOM_SEED).tolist()
    sample = tle_df[tle_df["sat_id"].isin(sample_sat_ids)]

    eph = load_ephemeris()
    ts = load.timescale(builtin=True)
    sun, earth = eph["sun"], eph["earth"]
    duration = float(days) * 86400
    secs = np.arange(0.0, duration + step_s / 2, step_s)
    t = _skyfield_times(ts, _naive_utc(t0), secs)
    topos = {r.station_id: wgs84.latlon(r.lat_deg, r.lon_deg, elevation_m=r.alt_m) for r in stations.itertuples()}
    dark = {sid: (earth + top).at(t).observe(sun).apparent().altaz()[0].degrees < config.SUN_ELEV_MAX_DEG
            for sid, top in topos.items()}

    def runs(mask):
        d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
        return np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1

    rows = []
    for tg in sample.itertuples():
        sat = EarthSatellite(tg.line1, tg.line2, ts=ts)
        pos = sat.at(t)
        msg = pos.message
        ok = np.array([m is None for m in msg]) if isinstance(msg, list) else np.full(len(secs), msg is None)
        lit = pos.is_sunlit(eph) if config.REQUIRE_SAT_SUNLIT else np.ones(len(secs), bool)
        for sid, top in topos.items():
            el = (sat - top).at(t).altaz()[0].degrees
            geom = (el >= config.MIN_ELEV_DEG) & (el <= config.MAX_ELEV_DEG) & ok
            vis = geom & dark[sid] & lit
            a, b = runs(vis)
            sky = pd.DataFrame(dict(s=secs[a], e=secs[b]))
            sky = sky[sky.e - sky.s >= config.MIN_DUR_S - 2 * step_s]
            ours = windows[(windows.sat_id == tg.sat_id) & (windows.station_id == sid)]
            used = set()
            for w in ours.itertuples():
                inside = (secs >= w.t_start_s) & (secs <= w.t_end_s)
                ov = np.minimum(sky.e, w.t_end_s) - np.maximum(sky.s, w.t_start_s)
                j = ov.idxmax() if len(sky) and ov.max() > 0 else None
                if j is not None:
                    used.add(j)
                rows.append(dict(sat_id=tg.sat_id, station_id=sid, kind="ours",
                                 t_start_s=w.t_start_s, t_end_s=w.t_end_s,
                                 d_start=w.t_start_s - sky.s[j] if j is not None else np.nan,
                                 d_end=w.t_end_s - sky.e[j] if j is not None else np.nan,
                                 bad_samples=int((inside & ~vis).sum()), bad_elev=int((inside & ~geom).sum()),
                                 bad_dark=int((inside & ~dark[sid]).sum()), bad_lit=int((inside & ~lit).sum())))
            for j, s in sky.iterrows():
                if j not in used and s.e - s.s >= config.MIN_DUR_S + 2 * step_s:
                    rows.append(dict(sat_id=tg.sat_id, station_id=sid, kind="missed", t_start_s=s.s, t_end_s=s.e))

    df = pd.DataFrame(rows).reindex(columns=[
        "sat_id", "station_id", "kind", "t_start_s", "t_end_s", "d_start", "d_end",
        "bad_samples", "bad_elev", "bad_dark", "bad_lit"])
    ours = df[df.kind == "ours"]
    edge = ours[(ours.t_start_s > 0) & (ours.t_end_s < duration)]   # 不含被规划期边界截断的窗口
    q = lambda x: {str(k): round(float(v), 3) for k, v in x.abs().quantile([0.5, 0.99, 1.0]).items()} if len(x) else {}
    df.attrs["summary"] = dict(
        sats=int(len(sample)), step_s=step_s, windows_checked=int(len(ours)),
        windows_with_violation=int((ours.bad_samples > 0).sum()), violation_samples=int(ours.bad_samples.sum()),
        missed_windows=int((df.kind == "missed").sum()), unmatched_ours=int(ours.d_start.isna().sum()),
        abs_d_start=q(edge.d_start.dropna()), abs_d_end=q(edge.d_end.dropna()))
    return df


def save_windows_csv(windows: pd.DataFrame, path: Path | None = None) -> None:
    """窗口表落盘（走契约层，自动做列名校验）。"""
    io_schema.save_windows(windows, path or config.WINDOWS_CSV)
