"""星座构型族：生成每颗星的 (h, i, Ω, u)，作为优化的初值。

所有构型都是太阳同步圆轨道：i 由 h 按 sso.sso_inclination 求出，e = 0。

1. Walker delta（`walker`）：P 个轨道面均布在 raan_span 内，面内均布，相邻面相位差 F·360°/N；
   N 不能被 P 整除时把余数分给前几个面。
2. 回归轨道交错构型（`rgt_interleaved`）：选一个 D 天回归 Q 圈的高度，所有星走"同一条回归轨迹、
   但在经度上错开"的地面轨迹。单星 D 天内升交点经度构成间距 360°/Q 的格子，N 颗星的轨迹
   再错开 360°/(QN)，于是 D 天后赤道上的穿越点间距 360°/(QN)（升降段交错时再减半）。
   只要间距不超过幅宽，D 天内就能覆盖全球，之后每 D 天整体重复一次——这同时保证了
   长三角每个格点每个周期都至少被访问一次（重访时间有上界）。
3. 回归轨道、升交点赤经均布（`rgt_uniform_raan`）：在 2 的子位置基础上，让各星升交点赤经在
   360°（或 180°）内均布，使各星过境长三角的地方时在一天里错开（长三角整体重访口径下的关键）。

地面轨迹的平移关系（同一高度、同一倾角的两颗星）：
    星 j 相对参考星的 (ΔΩ, Δu) ⇔ 轨迹整体东移 c = ΔΩ + (ω_E − Ω̇)·δt、时间提前 δt = Δu / u̇。
`from_track_offsets` 用这个关系由 (c_j, δt_j) 反算 (Ω_j, u_j)。
"""
import numpy as np
import pandas as pd

from sso import (R_EARTH, OMEGA_EARTH, j2_rates, sso_inclination, raan_from_ltan)

H_MIN, H_MAX = 500.0, 700.0
DAY = 86400.0


def rates(h_km):
    """太阳同步圆轨道在高度 h 的 (i°, Ω̇, u̇)，速率单位 rad/s。"""
    inc = float(sso_inclination(h_km))
    rd, ad, md = j2_rates(R_EARTH + h_km, 0.0, np.radians(inc))
    return inc, float(rd), float(ad + md)


def revs_per_day(h_km):
    """每个太阳日（相对地面）的圈数：太阳同步时 ω_E − Ω̇ = 2π/86400。"""
    _, rd, ud = rates(h_km)
    return ud / (OMEGA_EARTH - rd)


def rgt_altitude(Q, D, lo=H_MIN - 50, hi=H_MAX + 200):
    """D 天回归 Q 圈的太阳同步高度（km）；不在 [lo, hi] 内返回 None。"""
    target = Q / D
    f = lambda h: revs_per_day(h) - target
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def rgt_options(h_min=H_MIN, h_max=H_MAX, max_days=8):
    """赛题高度范围内的回归轨道 (Q, D, h)，Q 与 D 互质。"""
    out = []
    r_lo, r_hi = revs_per_day(h_max), revs_per_day(h_min)
    for D in range(1, max_days + 1):
        for Q in range(int(np.ceil(r_lo * D)), int(np.floor(r_hi * D)) + 1):
            if np.gcd(Q, D) != 1:
                continue
            h = rgt_altitude(Q, D)
            if h is not None and h_min - 1e-6 <= h <= h_max + 1e-6:
                out.append((Q, D, float(np.clip(h, h_min, h_max))))
    return out


def _frame(alt, raan, u, plane=None):
    alt = np.broadcast_to(np.asarray(alt, float), np.shape(raan)).copy()
    inc = np.array([sso_inclination(h) for h in alt])
    df = pd.DataFrame(dict(sat_id=np.arange(len(raan)), plane=plane if plane is not None else -1,
                           alt_km=alt, inc_deg=inc, raan_deg=np.mod(raan, 360.0), u_deg=np.mod(u, 360.0)))
    return df


def walker(N, P, F=1, h_km=H_MAX, ltan_h=10.5, jd0=None, raan_span=360.0, u0=0.0):
    """Walker delta（P 面，相位因子 F）；N 不整除 P 时前几个面多放一颗。"""
    raan0 = float(raan_from_ltan(ltan_h, jd0)) if jd0 is not None else 0.0
    base, rem = divmod(N, P)
    raan, u, plane = [], [], []
    for k in range(P):
        n_k = base + (1 if k < rem else 0)
        for j in range(n_k):
            raan.append(raan0 + k * raan_span / P)
            u.append(u0 + j * 360.0 / n_k + k * F * 360.0 / N)
            plane.append(k)
    return _frame(h_km, np.array(raan), np.array(u), np.array(plane))


def from_track_offsets(h_km, c_deg, dt_s, raan_ref=0.0, u_ref=0.0):
    """由轨迹经度平移 c_j（度）与时间提前 δt_j（秒）反算各星 (Ω, u)。"""
    _, rd, ud = rates(h_km)
    c = np.asarray(c_deg, float)
    dt = np.asarray(dt_s, float)
    raan = raan_ref + c - np.degrees((OMEGA_EARTH - rd) * dt)
    u = u_ref + np.degrees(ud * dt)
    return _frame(h_km, raan, u)


def to_track_offsets(df, raan_ref=0.0, u_ref=0.0):
    """from_track_offsets 的逆：同一高度的星座 -> (c_j, δt_j)。"""
    h = float(df['alt_km'].iloc[0])
    _, rd, ud = rates(h)
    dt = np.radians(np.mod(df['u_deg'].to_numpy() - u_ref, 360.0)) / ud
    c = df['raan_deg'].to_numpy() - raan_ref + np.degrees((OMEGA_EARTH - rd) * dt)
    return h, np.mod(c, 360.0), dt


def half_orbit_step(h_km):
    """赤道上相邻两次穿越（升→降或降→升）的经度步长 β（度）：β = 180° − ΔL/2，ΔL 为每圈西移量。"""
    return 180.0 - 0.5 * 360.0 / revs_per_day(h_km)


def kronecker(N, h_km, q, dt_s=None, raan_ref=0.0, u_ref=0.0):
    """Kronecker 交错构型：轨迹经度平移 c_j = j·θ，θ = (β + 360°·q) / N。

    取 θ 后，N 颗星在赤道上的全部穿越点（不分升降段）恰好是一个 Kronecker 序列 {k·θ}：
    第 m 个半圈、第 j 颗星的穿越点 = c_j + m·β = (j + m·N)·θ (mod 360°)。
    θ/360° 的连分数越"无理"（越接近黄金分割），序列在任意时刻铺得越均匀，
    覆盖率增长越接近不重叠的理想速度。q ∈ {0, …, N−1} 给出 N 个候选 θ。
    dt_s 为各星时间提前（默认全 0：同时过赤道，保证穿越点按序号 k 依次出现）。
    """
    theta = (half_orbit_step(h_km) + 360.0 * q) / N
    c = np.arange(N) * theta
    dt = np.zeros(N) if dt_s is None else np.asarray(dt_s, float)
    return from_track_offsets(h_km, c, dt, raan_ref=raan_ref, u_ref=u_ref)


def rgt_interleaved(N, Q, D, h_km=None, order=None, time_spread=None, raan_ref=0.0):
    """回归轨道交错构型。

    轨迹经度平移 c_j = order_j · 360°/(Q·N)：order 是 0…N−1 的一个排列（默认 0,1,2,…）；
    时间提前 δt_j 默认按黄金分割数列铺满一圈周期，避免多颗星同时扫过同一区域。
    """
    h = rgt_altitude(Q, D) if h_km is None else h_km
    _, _, ud = rates(h)
    period = 2 * np.pi / ud
    order = np.arange(N) if order is None else np.asarray(order)
    c = order * 360.0 / (Q * N)
    if time_spread is None:
        time_spread = np.mod(np.arange(N) * 0.6180339887498949, 1.0)
    dt = np.asarray(time_spread) * period
    return from_track_offsets(h, c, dt, raan_ref=raan_ref)


def rgt_uniform_raan(N, Q, h_km, span=360.0, raan0=0.0):
    """回归轨道、升交点赤经均布构型：返回轨迹平移量 c_j（度）与时间提前量 δt_j（秒）。

    长三角整体重访（答疑 #45-3）主要看各星过境时刻在一天里是否均匀；太阳同步轨道过境的地方时
    由升交点赤经决定，所以让 Ω_j = raan0 + j·span/N 均布（span = 180° 时升、降段过境时刻交错）。
    同时保留回归交错构型的子位置 j·360°/(QN)（D 天内铺满全球）：c_j 取子位置加整数个格距 360°/Q
    中不小于 Ω_j 的最小者，再由 Ω_j = c_j − (ω_E − Ω̇)·δt_j 解出 δt_j ∈ [0, 格距 / (ω_E − Ω̇))。
    """
    _, rd, _ = rates(h_km)
    s = 360.0 / Q
    j = np.arange(N)
    sub = j * s / N
    target = raan0 + j * span / N
    c = sub + np.ceil((target - sub) / s) * s
    dt = np.radians(c - target) / (OMEGA_EARTH - rd)
    return c, dt
