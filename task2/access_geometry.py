"""独立的球面、矩形视场几何核。使用地固速度约束沿迹方向，无侧摆。

不使用切平面地面距离近似；目标必须位于半径 radius_km 的球面上。
用于验证快速扫描的几何假设。大批量调用由 numpy 广播控制内存。
"""
import numpy as np

from sso import R_EARTH


def rectangular_access(satellite, velocity, target, along_half_deg=0.81,
                       cross_half_deg=0.81, radius_km=R_EARTH):
    """同一地固坐标系下的位置 km、速度 km/s -> 布尔访问，末轴均为 3。"""
    r, v, p = np.broadcast_arrays(*[np.asarray(x, float) for x in (satellite, velocity, target)])
    if r.shape[-1] != 3 or not all(np.isfinite(x).all() for x in (r, v, p)):
        raise ValueError('位置速度必须为有限三维矢量')
    if not (0 < along_half_deg < 90 and 0 < cross_half_deg < 90 and radius_km > 0):
        raise ValueError('半视场角必须在 (0,90)，地球半径必须为正')
    rho = np.linalg.norm(r, axis=-1, keepdims=True)
    if np.any(rho <= radius_km) or not np.allclose(np.linalg.norm(p, axis=-1), radius_km, rtol=0, atol=1e-6):
        raise ValueError('卫星必须位于球面外，目标必须位于指定球面')
    up = r / rho
    vt = v - np.sum(v * up, axis=-1, keepdims=True) * up
    speed = np.linalg.norm(vt, axis=-1, keepdims=True)
    if np.any(speed < 1e-12):
        raise ValueError('切向速度为零，沿迹方向未定义')
    along = vt / speed
    cross = np.cross(up, along)
    ray = p - r
    z = -np.sum(ray * up, axis=-1)
    x = np.sum(ray * along, axis=-1)
    y = np.sum(ray * cross, axis=-1)
    # 球面目标的外法向与目标→卫星方向同侧，排除地球遮挡。
    visible = np.sum((r - p) * p, axis=-1) >= 0
    return (visible & (z > 0) & (np.abs(x) <= z * np.tan(np.radians(along_half_deg)))
            & (np.abs(y) <= z * np.tan(np.radians(cross_half_deg))))


def access_intervals(predicate, start_s, stop_s, step_s=1.0, tolerance_s=0.001):
    """扫描布尔访问函数并二分细化边界，返回 (K,2) 起止秒。

    仅能保证发现至少包含一个采样点的窗口；不声称粗扫描不会遗漏窄窗口。
    predicate 接受时间一维数组并返回同形状布尔数组。
    """
    if not all(np.isfinite(x) for x in (start_s, stop_s, step_s, tolerance_s)) or not (
            stop_s > start_s and step_s > 0 and tolerance_s > 0):
        raise ValueError('非法时间区间或步长')
    t = np.r_[np.arange(start_s, stop_s, step_s), stop_s]
    hit = np.asarray(predicate(t), bool)
    if hit.shape != t.shape:
        raise ValueError('predicate 必须返回与时间同形状的数组')
    boundaries = []
    if hit[0]:
        boundaries.append(start_s)
    for k in np.flatnonzero(hit[:-1] != hit[1:]):
        lo, hi = t[k], t[k+1]
        while hi - lo > tolerance_s:
            mid = (lo + hi) / 2
            if bool(predicate(np.array([mid]))[0]) == hit[k]:
                lo = mid
            else:
                hi = mid
        boundaries.append((lo + hi) / 2)
    if hit[-1]:
        boundaries.append(stop_s)
    return np.asarray(boundaries, float).reshape(-1, 2)
