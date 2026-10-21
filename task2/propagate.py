"""轨道传播：J2 一阶长期项（与 STK 的 J2 传播器同阶）+ 数值积分（用于交叉校验）。

两种模型：
- `propagate_j2_secular`：解析式，平均根数 + J2 长期项，圆轨道；
- `propagate_rk4`：J2000 下的二体 + J2 加速度，RK4 定步长数值积分。

两者差异主要来自 J2 短周期项（量级几公里），因此校验时比较的是 7 天尺度的
节点/纬度幅角漂移，而不是逐点位置。
"""
import numpy as np

from sso import MU, RE_J2, J2, j2_rates, mean_motion


def _pq(raan, inc):
    """轨道面内的 P/Q 单位矢量（J2000）。"""
    O, i = np.radians(raan), np.radians(inc)
    P = np.stack([np.cos(O), np.sin(O), np.zeros_like(O)], axis=-1)
    Q = np.stack([-np.sin(O) * np.cos(i), np.cos(O) * np.cos(i), np.sin(i)], axis=-1)
    return P, Q


def propagate_j2_secular(a_km, inc_deg, raan_deg, u_deg, times_s, ecc=0.0):
    """解析 J2 长期项传播。

    a_km/inc_deg/raan_deg/u_deg 可为标量或 (N,) 数组；times_s 为 (T,) 或标量。
    返回 (r, v)，形状 (N, T, 3)（输入标量时自动升维）。
    """
    a = np.atleast_1d(np.asarray(a_km, float))
    inc = np.atleast_1d(np.asarray(inc_deg, float))
    raan0 = np.atleast_1d(np.asarray(raan_deg, float))
    u0 = np.atleast_1d(np.asarray(u_deg, float))
    t = np.atleast_1d(np.asarray(times_s, float))
    n = len(a)
    t = t[None, :]

    raan_dot, argp_dot, m_dot = j2_rates(a, ecc, np.radians(inc))
    raan_dot = raan_dot[:, None]
    # 圆轨道：纬度幅角 u = ω + M，长期漂移为两项之和
    u_dot = (argp_dot + m_dot)[:, None]
    # 速度按该圆轨道的开普勒圆速度给出（与平均根数 a 自洽），
    # 而不是 a*u_dot（u_dot 含 J2 长期项，直接当速度用会让数值积分得到偏小的半长轴）
    n0 = mean_motion(a)

    raan = np.radians(raan0)[:, None] + raan_dot * t
    u = np.radians(u0)[:, None] + u_dot * t

    P, Q = _pq(np.degrees(raan), np.repeat(inc[:, None], t.shape[1], axis=1))
    r = a[:, None, None] * (np.cos(u)[..., None] * P + np.sin(u)[..., None] * Q)
    v = (a * n0)[:, None, None] * (-np.sin(u)[..., None] * P + np.cos(u)[..., None] * Q)
    if np.ndim(times_s) == 0:
        return r[:, 0], v[:, 0]
    return r, v


def _accel_j2(r, use_j2=True):
    """J2000 下二体 (+J2) 加速度，r 形状 (N,3) 或 (N,T,3)。"""
    rn = np.linalg.norm(r, axis=-1)
    a = -MU * r / rn[..., None] ** 3
    if use_j2:
        f = 5 * (r[..., 2] / rn) ** 2
        k = 1.5 * J2 * MU * RE_J2 ** 2 / rn ** 5
        a = a + k[..., None] * np.stack([r[..., 0] * (f - 1),
                                         r[..., 1] * (f - 1),
                                         r[..., 2] * (f - 3)], axis=-1)
    return a


def propagate_rk4(r0, v0, times_s, dt=30.0, use_j2=True):
    """RK4 定步长积分到 times_s（秒，相对 t=0）。返回 (N, T, 3) 位置与速度。

    只积分到 max(times_s)，然后线性插值到各输出时刻。
    """
    r0 = np.atleast_2d(np.asarray(r0, float))
    v0 = np.atleast_2d(np.asarray(v0, float))
    t = np.atleast_1d(np.asarray(times_s, float))
    n_steps = int(np.ceil(t.max() / dt)) + 1
    r, v = r0.copy(), v0.copy()
    out_r = np.empty((len(r0), len(t), 3))
    out_v = np.empty((len(r0), len(t), 3))
    j = 0
    cur = 0.0
    for k in range(n_steps + 1):
        while j < len(t) and t[j] <= cur + 1e-9:
            out_r[:, j], out_v[:, j] = r, v
            j += 1
        if j >= len(t):
            break
        k1r, k1v = v, _accel_j2(r, use_j2)
        k2r, k2v = v + 0.5 * dt * k1v, _accel_j2(r + 0.5 * dt * k1r, use_j2)
        k3r, k3v = v + 0.5 * dt * k2v, _accel_j2(r + 0.5 * dt * k2r, use_j2)
        k4r, k4v = v + dt * k3v, _accel_j2(r + dt * k3r, use_j2)
        r = r + dt / 6.0 * (k1r + 2 * k2r + 2 * k3r + k4r)
        v = v + dt / 6.0 * (k1v + 2 * k2v + 2 * k3v + k4v)
        cur += dt
    # 剩余时刻（t > 积分终点）用末值兜底
    while j < len(t):
        out_r[:, j], out_v[:, j] = r, v
        j += 1
    return out_r, out_v


def raan_from_state(r, v):
    """由位置速度反算升交点赤经（度）与倾角（度）。"""
    h = np.cross(r, v)
    hn = h / np.linalg.norm(h, axis=-1, keepdims=True)
    raan = np.degrees(np.arctan2(hn[..., 0], -hn[..., 1])) % 360.0
    inc = np.degrees(np.arccos(np.clip(hn[..., 2], -1, 1)))
    return raan, inc


def u_from_state(r, v, raan_deg, inc_deg):
    """由位置反算纬度幅角 u（度）。"""
    P, Q = _pq(raan_deg, inc_deg)
    x = np.sum(r * P, axis=-1)
    y = np.sum(r * Q, axis=-1)
    return np.degrees(np.arctan2(y, x)) % 360.0
