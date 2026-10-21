"""太阳同步轨道（SSO）建模。

包含三部分：
1. J2 一阶长期项（节点/近地点/平近点角速率）；
2. 由太阳同步条件 Ω̇ = 360°/365.2422 d 反解轨道倾角 i(h)，以及反问题；
3. 太阳方向、升交点地方时（LTAN）与 β 角的低精度解析式，用于校核"太阳同步"是否成立。

约定（与赛题统一条件一致）：
- 轨道高度按平均半径 R = 6371 km 换算：a = R + h，e = 0；地面几何（幅宽、网格）也用该球面；
- J2 长期项里的参考半径取 WGS84 赤道半径 6378.137 km（STK J2 传播器的口径），
  这样按 i(h) 建的轨道在 STK 里节点进动率正好等于太阳同步速率；
- 参考系 J2000，时间 UTC，忽略章动/极移/大气阻力。
"""
import numpy as np
from datetime import datetime

MU = 398600.4418          # km^3/s^2
R_EARTH = 6371.0          # km，赛题规定按平均半径考虑（高度与地面几何）
RE_J2 = 6378.137          # km，J2 项参考半径（WGS84 赤道半径，STK J2 传播器所用）
J2 = 1.08262668e-3
OMEGA_EARTH = 7.2921158553e-5   # rad/s，地球自转角速度（与 IAU-82 GMST 速率一致）
DAY = 86400.0
TROPICAL_YEAR_DAYS = 365.2422
# 太阳同步所需节点进动率（rad/s），即太阳平黄经的年变化率
SSO_RATE = 2 * np.pi / (TROPICAL_YEAR_DAYS * DAY)
SSO_RATE_DEG_DAY = 360.0 / TROPICAL_YEAR_DAYS


def mean_motion(a):
    """圆轨道平均角速度 (rad/s)。"""
    return np.sqrt(MU / np.asarray(a, float) ** 3)


def j2_rates(a, ecc=0.0, inc=0.0):
    """J2 长期项速率 (rad/s)：返回 (raan_dot, argp_dot, m_dot)，inc 为弧度。"""
    a = np.asarray(a, float)
    n = mean_motion(a)
    p = a * (1 - ecc ** 2)
    k = J2 * (RE_J2 / p) ** 2 * n
    raan_dot = -1.5 * k * np.cos(inc)
    argp_dot = 0.75 * k * (4 - 5 * np.sin(inc) ** 2)
    m_dot = n * (1 + 0.75 * J2 * (RE_J2 / p) ** 2 * np.sqrt(1 - ecc ** 2)
                 * (2 - 3 * np.sin(inc) ** 2))
    return raan_dot, argp_dot, m_dot


def sso_inclination(h_km, ecc=0.0):
    """太阳同步圆轨道所需倾角（度）。h 为相对平均半径的轨道高度。

    由 Ω̇ = -1.5 J2 n (Re/a)^2 cos i 反解，i 落在 (90°, 180°) 的逆行段。
    """
    a = R_EARTH + np.asarray(h_km, float)
    n = mean_motion(a)
    p = a * (1 - ecc ** 2)
    cos_i = -SSO_RATE / (1.5 * J2 * n * (RE_J2 / p) ** 2)
    if np.any(np.abs(cos_i) > 1):
        raise ValueError('该高度不存在太阳同步解')
    return np.degrees(np.arccos(cos_i))


def sso_altitude(inc_deg, ecc=0.0, h_lo=300.0, h_hi=2000.0):
    """太阳同步圆轨道的反问题：给定倾角（度）求轨道高度（km）。二分求解，单调递减。"""
    lo, hi = h_lo, h_hi
    f = lambda h: sso_inclination(h, ecc) - inc_deg
    if f(lo) * f(hi) > 0:
        raise ValueError(f'倾角 {inc_deg}° 在 {h_lo}–{h_hi} km 内无太阳同步解')
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def nodal_period(a, ecc=0.0, inc=0.0):
    """J2 修正后的升交点周期 (s)。"""
    _, _, m_dot = j2_rates(a, ecc, inc)
    return 2 * np.pi / m_dot


def revs_per_day(a, ecc=0.0, inc=0.0):
    return DAY / nodal_period(a, ecc, inc)


def ground_track_repeat(a, ecc=0.0, inc=0.0, max_days=30):
    """近似回归特性：返回 (卫星圈数, 天数, 每天圈数)，使 q/N 逼近整数比值。

    每天圈数 r = revs_per_day；对 k = 1..max_days 取 N = round(k*r)，
    返回 |k*r/N - 1| 最小的比值，用于给出重复地面轨迹周期。
    """
    r = revs_per_day(a, ecc, inc)
    best = None
    for k in range(1, max_days + 1):
        n_rev = round(k * r)
        if n_rev == 0:
            continue
        err = abs(k * r / n_rev - 1)
        if best is None or err < best[0]:
            best = (err, n_rev, k)
    return best[1], best[2], r


# ---------------------------------------------------------------- 时间与太阳

def jd_from_datetime(dt):
    """UTC datetime -> 儒略日（忽略闰秒）。"""
    y, m = dt.year, dt.month
    d = (dt.day + (dt.hour + (dt.minute + dt.second / 60.0) / 60.0) / 24.0)
    if m <= 2:
        y, m = y - 1, m + 12
    A = y // 100
    B = 2 - A + A // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5


def sun_vector_eci(jd):
    """太阳方向单位矢量（J2000 平赤道，低精度解析式，误差约 0.01°）。

    参考 Meeus《Astronomical Algorithms》低精度太阳位置（第 25 章）。
    """
    jd = np.asarray(jd, float)
    n = jd - 2451545.0
    L = np.radians(280.460 + 0.9856474 * n)          # 平黄经
    g = np.radians(357.528 + 0.9856003 * n)          # 平近点角
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    eps = np.radians(23.439 - 4e-7 * n)
    return np.stack([np.cos(lam),
                     np.cos(eps) * np.sin(lam),
                     np.sin(eps) * np.sin(lam)], axis=-1)


def sun_ra_deg(jd):
    s = sun_vector_eci(jd)
    return np.degrees(np.arctan2(s[..., 1], s[..., 0])) % 360.0


def orbit_normal(inc_deg, raan_deg):
    """轨道法向单位矢量（J2000）。"""
    i, O = np.radians(inc_deg), np.radians(raan_deg)
    return np.stack([np.sin(i) * np.sin(O), -np.sin(i) * np.cos(O), np.full_like(i, np.cos(i))],
                    axis=-1) if np.ndim(i) else np.array([np.sin(i) * np.sin(O),
                                                          -np.sin(i) * np.cos(O),
                                                          np.cos(i)])


def beta_angle_deg(inc_deg, raan_deg, jd):
    """β 角（轨道面法向与太阳方向夹角，度）。太阳同步轨道上应近似恒定。"""
    s = sun_vector_eci(jd)
    n = np.asarray(orbit_normal(inc_deg, raan_deg), float)
    return np.degrees(np.arcsin(np.clip(np.sum(s * n, axis=-1), -1, 1)))


def ltan_from_raan(raan_deg, jd):
    """由升交点赤经反算升交点地方时 LTAN（小时，0–24）。"""
    return (12.0 + (np.asarray(raan_deg) - sun_ra_deg(jd)) / 15.0) % 24.0


def raan_from_ltan(ltan_hours, jd):
    """由升交点地方时 LTAN（小时）反算历元升交点赤经（度）。"""
    return (sun_ra_deg(jd) + (np.asarray(ltan_hours) - 12.0) * 15.0) % 360.0


def gmst_rad(jd):
    """IAU-82 格林尼治平恒星时（rad）。"""
    t = (np.asarray(jd, float) - 2451545.0) / 36525.0
    sec = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t \
        + 0.093104 * t ** 2 - 6.2e-6 * t ** 3
    return (sec % DAY) / DAY * 2 * np.pi


def eci_to_ecef(r, jd):
    """J2000 惯性系 -> 地固系（绕 z 轴转 GMST；忽略极移与岁差）。"""
    g = gmst_rad(jd)
    c, s = np.cos(g), np.sin(g)
    x, y = r[..., 0], r[..., 1]
    return np.stack([c * x + s * y, -s * x + c * y, r[..., 2]], axis=-1)


def ecef_to_geodetic(r):
    """球面地固坐标 -> (纬度°, 经度°, 半径 km)。赛题按平均半径考虑，用球面近似。"""
    r = np.asarray(r, float)
    rho = np.linalg.norm(r, axis=-1)
    lat = np.degrees(np.arcsin(np.clip(r[..., 2] / rho, -1, 1)))
    lon = np.degrees(np.arctan2(r[..., 1], r[..., 0]))
    return lat, lon, rho
