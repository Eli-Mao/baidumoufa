"""轨道传播：共享的 STK J2 长期项约定 + 数值积分（用于交叉校验）。

两种模型：
- `propagate_j2_secular`：默认 STK 约定、ICRF 内传播并输出 J2000；历史 first_order 需明确选择；
- `propagate_rk4`：J2000 下的二体 + J2 加速度，RK4 定步长数值积分。

两者差异主要来自 J2 短周期项（量级几公里），因此校验时比较的是 7 天尺度的
节点/纬度幅角漂移，而不是逐点位置。
"""
import numpy as np

from sso import MU, RE_J2, J2, j2_rates, mean_motion
from model_convention import rate_model as resolve_rate_model


def _pq(raan, inc):
    """轨道面内的 P/Q 单位矢量（J2000）。"""
    O, i = np.radians(raan), np.radians(inc)
    P = np.stack([np.cos(O), np.sin(O), np.zeros_like(O)], axis=-1)
    Q = np.stack([-np.sin(O) * np.cos(i), np.cos(O) * np.cos(i), np.sin(i)], axis=-1)
    return P, Q


def propagate_j2_secular(a_km, inc_deg, raan_deg, u_deg, times_s, ecc=0.0,
                         velocity_mode='derivative', rate_model=None,epoch_jd=2461406.5,eop_path=None):
    """解析 J2 长期项传播。

    a_km/inc_deg/raan_deg/u_deg 可为标量或 (N,) 数组；times_s 为 (T,) 或标量。
    返回 (r, v)，形状 (N, T, 3)（标量时刻返回 (N,3)）。
    默认速度为位置的时间导数，用于诊断星历。STK 相机定向另采用
    earth_frames.StkOrbit 的 keplerian 速度约定；该约定不是平均根数到瞬时根数的转换。
    """
    if np.any(np.asarray(ecc) != 0):
        raise ValueError('解析传播仅支持圆轨道 ecc=0')
    if velocity_mode not in ('derivative', 'keplerian'):
        raise ValueError('unknown velocity_mode')
    a, inc, raan0, u0 = np.broadcast_arrays(*[
        np.atleast_1d(np.asarray(x, float)) for x in (a_km, inc_deg, raan_deg, u_deg)])
    t = np.atleast_1d(np.asarray(times_s, float))
    if any(x.ndim != 1 or not np.isfinite(x).all() for x in (a, inc, raan0, u0, t)):
        raise ValueError('轨道参数和时间必须为有限标量或一维数组')
    if not len(a) or np.any(a <= 0) or np.any((inc < 0) | (inc > 180)):
        raise ValueError('非法半长轴或倾角')
    rate_model=resolve_rate_model(rate_model)
    if rate_model=='stk':
        from types import SimpleNamespace
        from earth_frames import EarthFrames,StkOrbit,DEFAULT_EOP
        frames=EarthFrames(epoch_jd,max(1.,float(t.max())),eop_path or DEFAULT_EOP)
        rotation=np.swapaxes(frames.j2000_to_icrf(t),-1,-2)
        dr=(np.swapaxes(frames.j2000_to_icrf(t+.5),-1,-2)-
            np.swapaxes(frames.j2000_to_icrf(t-.5),-1,-2))
        states=[]
        for aa,ii,oo,uu in zip(a,inc,raan0,u0):
            orbit=StkOrbit(SimpleNamespace(alt_km=aa-6371.,inc_deg=ii,raan_deg=oo,u_deg=uu),frames)
            ri,vi=orbit.inertial(t,'derivative' if velocity_mode=='derivative' else 'stk')
            rr=np.einsum('tij,tj->ti',rotation,ri)
            vv=np.einsum('tij,tj->ti',rotation,vi)
            if velocity_mode=='derivative':vv+=np.einsum('tij,tj->ti',dr,ri)
            states.append((rr,vv))
        r,v=np.array([x[0] for x in states]),np.array([x[1] for x in states])
        return (r[:,0],v[:,0]) if np.ndim(times_s)==0 else (r,v)
    t = t[None, :]

    raan_dot, argp_dot, m_dot = j2_rates(a, ecc, np.radians(inc), rate_model=rate_model)
    raan_dot = raan_dot[:, None]
    # 圆轨道：纬度幅角 u = ω + M，长期漂移为两项之和
    u_dot = (argp_dot + m_dot)[:, None]
    # Keplerian 模式构造瞬时圆轨道；不能据此宣称已完成平均/瞬时根数转换。
    n0 = mean_motion(a,rate_model)

    raan = np.radians(raan0)[:, None] + raan_dot * t
    u = np.radians(u0)[:, None] + u_dot * t

    P, Q = _pq(np.degrees(raan), np.repeat(inc[:, None], t.shape[1], axis=1))
    r = a[:, None, None] * (np.cos(u)[..., None] * P + np.sin(u)[..., None] * Q)
    v = (a * n0)[:, None, None] * (-np.sin(u)[..., None] * P + np.cos(u)[..., None] * Q)
    if velocity_mode == 'derivative':
        tangent = -np.sin(u)[..., None] * P + np.cos(u)[..., None] * Q
        v = a[:, None, None] * u_dot[..., None] * tangent
        v += raan_dot[..., None] * np.cross(np.array([0., 0., 1.]), r)
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

    每个输出时刻缩短最后一步，精确积分至该时刻；支持重复、乱序的非负时刻。
    """
    r0 = np.atleast_2d(np.asarray(r0, float))
    v0 = np.atleast_2d(np.asarray(v0, float))
    t = np.atleast_1d(np.asarray(times_s, float))
    if (r0.shape != v0.shape or r0.ndim != 2 or r0.shape[1] != 3
            or not np.isfinite(r0).all() or not np.isfinite(v0).all()
            or np.any(np.linalg.norm(r0, axis=1) == 0)):
        raise ValueError('初始位置速度必须为同形状的有限 (N,3) 数组，位置非零')
    if t.ndim != 1 or not np.isfinite(t).all() or np.any(t < 0) or not np.isfinite(dt) or dt <= 0:
        raise ValueError('时间必须为非负有限一维数组，dt 必须为正')
    r, v = r0.copy(), v0.copy()
    out_r = np.empty((len(r0), len(t), 3))
    out_v = np.empty((len(r0), len(t), 3))
    cur = 0.0
    for j in np.argsort(t, kind='stable'):
        while cur < t[j]:
            h = min(dt, t[j] - cur)
            k1r, k1v = v, _accel_j2(r, use_j2)
            k2r, k2v = v + 0.5 * h * k1v, _accel_j2(r + 0.5 * h * k1r, use_j2)
            k3r, k3v = v + 0.5 * h * k2v, _accel_j2(r + 0.5 * h * k2r, use_j2)
            k4r, k4v = v + h * k3v, _accel_j2(r + h * k3r, use_j2)
            r = r + h / 6.0 * (k1r + 2 * k2r + 2 * k3r + k4r)
            v = v + h / 6.0 * (k1v + 2 * k2v + 2 * k3v + k4v)
            cur = min(cur + h, t[j])
        out_r[:, j], out_v[:, j] = r, v
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
