"""重点区域（长三角：上海 + 江苏 + 浙江 + 安徽）几何。

赛题由主办方在 STK 中用 AreaTarget 定义该区域，脚本只给了生成方法、没有给边界
文件（需要联网下载 geoBoundaries）。这里内置一个按省界轮廓简化的多边形，
作为离线仿真的替代；用 `--region <geojson>` 可以换成官方边界。

多边形只用于判断"评价格点是否属于重点区域"，格点仍按 0.1°×0.1° 均匀铺设。
"""
import json
import math

import numpy as np

# 简化省界（经度, 纬度），逆时针，覆盖沪苏浙皖主体
YANGTZE_DELTA = [
    (119.30, 35.05), (119.90, 34.75), (120.30, 34.30), (120.90, 33.70),
    (121.40, 32.90), (121.90, 32.10), (121.95, 31.40), (121.50, 30.80),
    (122.20, 30.30), (121.70, 29.70), (121.90, 29.00), (121.60, 28.40),
    (121.00, 27.80), (120.40, 27.30), (119.30, 27.20), (118.40, 27.60),
    (117.70, 28.10), (117.20, 28.60), (116.90, 29.20), (116.30, 29.60),
    (115.80, 29.90), (115.30, 30.20), (114.80, 30.70), (114.60, 31.20),
    (114.40, 31.60), (115.00, 32.20), (115.60, 32.80), (116.20, 33.40),
    (116.50, 34.10), (117.20, 34.50), (118.10, 34.90),
]

LAT_RANGE = (27.0, 35.3)
LON_RANGE = (114.0, 123.0)


def rings(polygon=None):
    """返回多边形环列表（默认单环）。"""
    return [np.asarray(polygon if polygon is not None else YANGTZE_DELTA, float)]


def load_geojson(path):
    """从 GeoJSON 读若干个多边形环（支持 Polygon / MultiPolygon / Feature / FeatureCollection）。"""
    data = json.loads(open(path, encoding='utf-8').read())
    out = []

    def walk(obj):
        t = obj.get('type')
        if t == 'FeatureCollection':
            for f in obj['features']:
                walk(f)
        elif t == 'Feature':
            walk(obj['geometry'])
        elif t == 'Polygon':
            out.append(np.asarray(obj['coordinates'][0], float))
        elif t == 'MultiPolygon':
            for poly in obj['coordinates']:
                out.append(np.asarray(poly[0], float))

    walk(data)
    if not out:
        raise ValueError(f'{path}: 没有找到多边形')
    return out


def points_in_polygon(lat, lon, polygons=None):
    """射线法判断点是否落在任一多边形内（lon/lat 与多边形顶点顺序一致）。"""
    polygons = rings() if polygons is None else polygons
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    inside = np.zeros(len(lat), bool)
    for ring in polygons:
        ring_in = np.zeros(len(lat), bool)
        x, y = ring[:, 0], ring[:, 1]
        for k in range(len(ring)):
            x1, y1 = x[k], y[k]
            x2, y2 = x[(k + 1) % len(ring)], y[(k + 1) % len(ring)]
            cond = ((y1 > lat) != (y2 > lat))
            if not cond.any():
                continue
            xin = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            ring_in ^= cond & (lon < xin)
        inside |= ring_in
    return inside


def bbox(polygons=None):
    polygons = rings() if polygons is None else polygons
    allp = np.vstack(polygons)
    return allp[:, 1].min(), allp[:, 1].max(), allp[:, 0].min(), allp[:, 0].max()


def approximate_area_km2(polygons=None):
    """球面多边形面积（km²），用于检查替代边界与官方区域是否同一量级。"""
    polygons = rings() if polygons is None else polygons
    R = 6371.0
    total = 0.0
    for ring in polygons:
        lon = np.radians(ring[:, 0])
        lat = np.radians(ring[:, 1])
        # 球面多边形面积（Chamberlain & Duquette 近似）
        s = 0.0
        for k in range(len(ring)):
            x1, y1 = lon[k], lat[k]
            x2, y2 = lon[(k + 1) % len(ring)], lat[(k + 1) % len(ring)]
            s += (x2 - x1) * (2 + math.sin(y1) + math.sin(y2))
        total += abs(s) * R * R / 2.0
    return total
