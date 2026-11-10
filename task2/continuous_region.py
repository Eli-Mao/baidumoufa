"""Whole-area access without an evaluation grid (Q&A E41, E45, E49).

Earth is the existing 6371 km sphere. Region edges are minor great-circle arcs,
matching STK's Great Arc boundary convention on a sphere. The rectangular sensor
is nadir aligned with the Earth-fixed velocity constraint. Spatial intersection
is analytic; time is sampled and detected transitions are bisected. Windows that
contain no sampling time can still be missed: step-halving is required evidence.

This module deliberately does not bridge the old 300-second gaps. The metric
helper retains the project's interpretation of "unmerged" adjacent intervals;
that interpretation is reported separately from the geometric model.
"""
import numpy as np

from access_geometry import access_intervals
from coverage import ETA_DEG, ETA_ALONG_DEG
from fasteval import region_revisit
from propagate import propagate_j2_secular
from sso import R_EARTH, gmst_rad, j2_rates, DAY


def _unit_from_lonlat(lonlat):
    lon, lat = np.radians(np.asarray(lonlat, float)).T
    return np.column_stack((np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)))


def _camera(r, v):
    radius = np.linalg.norm(r, axis=-1)
    up = r / radius[:, None]
    tangent = v - np.sum(v*up, axis=-1)[:, None]*up
    speed = np.linalg.norm(tangent, axis=-1)
    if np.any(speed <= 1e-12):
        raise ValueError('Earth-fixed tangential velocity must be nonzero')
    along = tangent / speed[:, None]
    return radius, up, along, np.cross(up, along)


class SphericalRegion:
    """Union of exterior rings, each an (N,2) array of longitude/latitude degrees.

    All rings must lie in one open hemisphere. Nested rings are rejected because
    an untagged ring list cannot distinguish an island from a polygon hole.
    Longitude wrapping is supported geometrically, but the simulator prefilter
    intentionally accepts only non-antimeridian regional domains such as YRD.
    """
    def __init__(self, exterior_rings):
        self.lonlat = []
        for ring in exterior_rings:
            ring = np.asarray(ring, float)
            if ring.ndim != 2 or ring.shape[1] != 2 or len(ring) < 3 or not np.isfinite(ring).all():
                raise ValueError('each exterior must be a finite (N,2) ring')
            if np.any(np.abs(ring[:, 1]) > 90):
                raise ValueError('latitude outside [-90,90]')
            if np.allclose(ring[0], ring[-1], rtol=0, atol=1e-12):
                ring = ring[:-1]
            if len(ring) < 3:
                raise ValueError('ring must have at least three vertices')
            self.lonlat.append(ring)
        if not self.lonlat:
            raise ValueError('empty region')
        self.rings = [_unit_from_lonlat(ring) for ring in self.lonlat]
        self.vertices = np.vstack(self.rings)
        center = np.mean(self.vertices, axis=0)
        if np.linalg.norm(center) < 1e-12:
            raise ValueError('region is not contained in one hemisphere')
        self.center = center / np.linalg.norm(center)
        if np.any(self.vertices @ self.center <= 1e-6):
            raise ValueError('region must lie within one open hemisphere')
        axis = np.array([0., 0., 1.])
        if abs(self.center[2]) > .99:
            axis = np.array([0., 1., 0.])
        self.east = np.cross(axis, self.center)
        self.east /= np.linalg.norm(self.east)
        self.north = np.cross(self.center, self.east)
        self.xy_rings = [self._project(ring)[0] for ring in self.rings]
        for k, xy in enumerate(self.xy_rings):
            # Only tagged exterior rings are accepted; avoid silently filling holes.
            for j, other in enumerate(self.xy_rings):
                if j != k and self._inside_xy(xy, other).all():
                    raise ValueError('nested rings need explicit hole topology; unsupported exterior list')
        self.a = np.vstack(self.rings)
        self.b = np.vstack([np.roll(ring, -1, axis=0) for ring in self.rings])
        dot = np.clip(np.sum(self.a*self.b, axis=1), -1., 1.)
        self.alpha = np.arccos(dot)
        if np.any(self.alpha < 1e-12) or np.any(self.alpha >= np.pi-1e-9):
            raise ValueError('duplicate or antipodal consecutive vertices')
        self.q = (self.b-dot[:, None]*self.a) / np.sin(self.alpha)[:, None]

    def _project(self, points):
        den = np.asarray(points) @ self.center
        xy = np.column_stack((np.asarray(points) @ self.east, np.asarray(points) @ self.north))
        return xy / np.maximum(den, 1e-15)[:, None], den > 0

    @staticmethod
    def _inside_xy(points, ring):
        """Boundary-inclusive ray casting in a gnomonic plane (Great Arcs are lines)."""
        x, y = np.asarray(points).T
        inside = np.zeros(len(x), bool)
        boundary = np.zeros(len(x), bool)
        for a, b in zip(ring, np.roll(ring, -1, axis=0)):
            dx, dy = b-a
            area = (x-a[0])*dy-(y-a[1])*dx
            scale = max(float(np.hypot(dx, dy)), 1e-15)
            boundary |= ((np.abs(area) <= 1e-12*scale)
                         & (x >= min(a[0], b[0])-1e-12) & (x <= max(a[0], b[0])+1e-12)
                         & (y >= min(a[1], b[1])-1e-12) & (y <= max(a[1], b[1])+1e-12))
            crossed = (a[1] > y) != (b[1] > y)
            if dy != 0:
                inside ^= crossed & (x < a[0]+(y-a[1])*dx/dy)
        return inside | boundary

    def contains(self, unit_points):
        points = np.atleast_2d(np.asarray(unit_points, float))
        xy, front = self._project(points)
        inside = np.zeros(len(points), bool)
        for ring in self.xy_rings:
            inside |= self._inside_xy(xy, ring)
        return inside & front

    def intersects(self, r, v, along_half_deg=ETA_ALONG_DEG, cross_half_deg=ETA_DEG):
        """Exact spatial existence test for a visible point shared by region and FOV.

        A nonempty intersection either contains the boresight, contains a region
        vertex, or intersects a region edge with a sensor boundary. Edge crossings
        solve A*cos(theta)+B*sin(theta)+C=0 analytically, not by edge sampling.
        """
        r, v = np.asarray(r, float), np.asarray(v, float)
        if r.ndim == 1:
            r, v = r[None], v[None]
        if r.ndim != 2 or r.shape[1] != 3 or v.shape != r.shape or not (
                np.isfinite(r).all() and np.isfinite(v).all()):
            raise ValueError('positions/velocities must have matching finite (T,3) shapes')
        if not (0 < along_half_deg < 90 and 0 < cross_half_deg < 90):
            raise ValueError('invalid sensor half angles')
        radius, up, along, cross = _camera(r, v)
        if np.any(radius <= R_EARTH):
            raise ValueError('satellite must be outside the Earth sphere')
        ta, tc = np.tan(np.radians([along_half_deg, cross_half_deg]))
        corner_angle = np.arctan(np.hypot(ta, tc))
        arg = radius/R_EARTH*np.sin(corner_angle)
        if np.any(arg >= 1):
            raise ValueError('sensor corner reaches beyond Earth limb')
        cap = np.arcsin(arg)-corner_angle
        hit = self.contains(up)
        pending = np.flatnonzero(~hit)
        # Bounded batches keep memory independent of propagation duration.
        for begin in range(0, len(pending), 1024):
            ids = pending[begin:begin+1024]
            u, x, y, rho = up[ids], along[ids], cross[ids], radius[ids]
            vertex_dot = u @ self.vertices.T
            z = rho[:, None]-R_EARTH*vertex_dot
            vertex_hit = ((vertex_dot >= R_EARTH/rho[:, None])
                          & (np.abs(R_EARTH*(x @ self.vertices.T)) <= ta*z+1e-9)
                          & (np.abs(R_EARTH*(y @ self.vertices.T)) <= tc*z+1e-9))
            good = np.any(vertex_hit, axis=1)
            hit[ids[good]] = True
            ids = ids[~good]
            if not len(ids):
                continue
            u = up[ids]
            # Exact nearest point on each minor great-circle arc, used only to prune.
            ua, uq = u @ self.a.T, u @ self.q.T
            theta = np.arctan2(uq, ua)
            max_dot = np.maximum(ua, u @ self.b.T)
            within = (theta >= 0) & (theta <= self.alpha[None])
            max_dot = np.where(within, np.maximum(max_dot, np.hypot(ua, uq)), max_dot)
            sample, edge = np.nonzero(max_dot >= np.cos(cap[ids, None])-1e-12)
            if not len(sample):
                continue
            ti = ids[sample]
            a, q, alpha = self.a[edge], self.q[edge], self.alpha[edge]
            for axis, tangent in ((along, ta), (cross, tc)):
                for sign in (-1, 1):
                    plane = sign*axis[ti]-tangent*up[ti]
                    aa = R_EARTH*np.sum(plane*a, axis=1)
                    bb = R_EARTH*np.sum(plane*q, axis=1)
                    cc = tangent*radius[ti]
                    amplitude = np.hypot(aa, bb)
                    possible = amplitude >= np.abs(cc)-1e-9
                    phase = np.arctan2(bb, aa)
                    angle = np.arccos(np.clip(-cc/np.maximum(amplitude, 1e-30), -1, 1))
                    for branch in (-1, 1):
                        root = (phase+branch*angle) % (2*np.pi)
                        root = np.where(np.abs(root-2*np.pi) < 1e-10, 0, root)
                        valid = possible & (root <= alpha+1e-10)
                        if not valid.any():
                            continue
                        jj = ti[valid]
                        t = root[valid]
                        p = R_EARTH*(a[valid]*np.cos(t)[:, None]+q[valid]*np.sin(t)[:, None])
                        udot = np.sum(p*up[jj], axis=1)
                        zz = radius[jj]-udot
                        okay = ((radius[jj]*udot >= R_EARTH**2-1e-6)
                                & (np.abs(np.sum(p*along[jj], axis=1)) <= ta*zz+1e-7)
                                & (np.abs(np.sum(p*cross[jj], axis=1)) <= tc*zz+1e-7))
                        hit[jj[okay]] = True
        return hit


def ecef_state(element, times_s, jd0):
    """Secular J2 position/derivative with the same GMST rotation as local scoring."""
    t = np.atleast_1d(np.asarray(times_s, float))
    r, v = propagate_j2_secular(R_EARTH+float(element.alt_km), float(element.inc_deg),
                                float(element.raan_deg), float(element.u_deg), t,rate_model='first_order')
    r, v = r[0], v[0]
    jd = jd0+t/DAY
    g = gmst_rad(jd)
    c, s = np.cos(g), np.sin(g)
    rotate = lambda w: np.column_stack((c*w[:, 0]+s*w[:, 1], -s*w[:, 0]+c*w[:, 1], w[:, 2]))
    rf, vf = rotate(r), rotate(v)
    centuries = (jd-2451545.)/36525.
    rate = ((876600*3600+8640184.812866)+.186208*centuries-18.6e-6*centuries**2)
    rate *= 2*np.pi/(DAY**2*36525.)
    vf -= rate[:, None]*np.cross(np.array([0., 0., 1.]), rf)
    return rf, vf


def simulate_region(elems, jd0, region_polys, days=7., step=.125, tolerance_s=.01,
                    geometry_model='sphere', eop_path=None, progress=None):
    """Return actual per-satellite connected contact intervals and whole-area metrics.

    The region is a union of exterior rings. No 0.1-degree grid and no 300-second
    gap bridging is used. Sampling can miss sub-step grazing contacts; the output
    explicitly records this limitation instead of asserting temporal exactness.
    """
    if not all(np.isfinite(x) for x in (jd0, days, step, tolerance_s)) or not (
            days > 0 and step > 0 and tolerance_s > 0):
        raise ValueError('invalid time or sampling settings')
    cols = ['sat_id', 'alt_km', 'inc_deg', 'raan_deg', 'u_deg']
    if elems.empty or not set(cols).issubset(elems.columns) or not np.isfinite(elems[cols].to_numpy(float)).all():
        raise ValueError('empty or invalid elements')
    if elems.sat_id.duplicated().any():
        raise ValueError('duplicate satellite IDs')
    if geometry_model not in ('sphere','stk'): raise ValueError('unknown geometry model')
    if geometry_model=='stk':
        from earth_frames import EarthFrames, StkOrbit, DEFAULT_EOP
        from ellipsoid_access import EllipsoidRegion
        frames=EarthFrames(jd0,days*DAY,eop_path or DEFAULT_EOP)
        region=EllipsoidRegion(region_polys)
    else:
        region = SphericalRegion(region_polys)
    ll = np.vstack(region_polys)
    lo0, la0 = ll.min(axis=0)
    lo1, la1 = ll.max(axis=0)
    if lo1-lo0 >= 180 or max(abs(la0), abs(la1)) > 80:
        raise ValueError('simulator prefilter supports non-antimeridian regions below 80 degrees')
    dur = days*DAY
    coarse = 30. if geometry_model=='stk' else min(30., step*30)
    times = np.r_[np.arange(0, dur, coarse), dur]
    intervals = []
    for el in elems.itertuples():
        state = StkOrbit(el,frames).state if geometry_model=='stk' else lambda t: ecef_state(el,t,jd0)
        r, v = state(times)
        rho = np.linalg.norm(r, axis=1)
        lat = np.degrees(np.arcsin(np.clip(r[:, 2]/rho, -1, 1)))
        lon = np.degrees(np.arctan2(r[:, 1], r[:, 0]))
        rd, ad, md = j2_rates(R_EARTH+el.alt_km, 0, np.radians(el.inc_deg),
                              rate_model='stk' if geometry_model=='stk' else 'first_order')
        # A bound on unit-position angular motion over one coarse sample plus FOV.
        motion = abs(rd)+abs(ad+md)+7.3e-5
        eta = np.arctan(np.hypot(np.tan(np.radians(ETA_DEG)), np.tan(np.radians(ETA_ALONG_DEG))))
        arg = (R_EARTH+el.alt_km)/R_EARTH*np.sin(eta)
        if not 0 < arg < 1:
            raise ValueError('orbit/sensor does not intersect sphere')
        cap = np.arcsin(arg)-eta
        pad = np.degrees(motion*coarse+cap)+(.3 if geometry_model=='stk' else .02)
        maxlat = min(89.999, max(abs(la0), abs(la1))+pad)
        lonpad = np.degrees(np.arcsin(min(1., np.sin(np.radians(pad))/np.cos(np.radians(maxlat)))))
        # Great-circle edges may bulge beyond the vertex latitude extrema. The
        # additional margin bounds that bulge by each boundary edge's full length.
        edgepad = np.degrees(region.alpha.max())
        near = ((lat >= la0-pad-edgepad) & (lat <= la1+pad+edgepad)
                & (lon >= lo0-lonpad-edgepad) & (lon <= lo1+lonpad+edgepad))
        ids = np.flatnonzero(near)
        if not len(ids):
            continue
        segments = np.split(ids, np.flatnonzero(np.diff(ids)>1)+1)
        bounds = []
        for segment in segments:
            a, b = max(0., times[segment[0]]-coarse), min(dur, times[segment[-1]]+coarse)
            if bounds and a <= bounds[-1][1]:
                bounds[-1][1] = b
            else:
                bounds.append([a, b])
        predicate = lambda t: region.intersects(*state(t))
        for a, b in bounds:
            for start, stop in access_intervals(predicate, a, b, step, tolerance_s):
                intervals.append(dict(sat_id=int(el.sat_id), start_s=float(start), stop_s=float(stop)))
        if progress: progress(int(el.sat_id),len(intervals))
    intervals.sort(key=lambda row: (row['start_s'], row['sat_id'], row['stop_s']))
    starts, stops = [x['start_s'] for x in intervals], [x['stop_s'] for x in intervals]
    metric = region_revisit(starts, stops, dur)
    metric['merged'] = region_revisit(starts, stops, dur, merge=True)
    result = dict(region_revisit=metric, access_intervals=intervals,
                model=dict(region='union_of_great_circle_exterior_rings', region_grid=False,
                           earth_radius_km=R_EARTH, sensor='rectangular_nadir_ECF_velocity',
                           spatial_intersection='analytic_edge_plane_roots_plus_containment',
                           temporal_step_s=step, boundary_tolerance_s=tolerance_s,
                           gap_bridging_s=0, stk_verified=False,
                           temporal_limitation='Sub-step grazing contacts without a hit sample can be missed.',
                           statistics_assumption='Unmerged visits use adjacent sorted start-minus-previous-end; overlaps produce zero, endpoints included.'))
    if geometry_model=='stk':
        result['model'].update(earth='WGS84 ellipsoid',frame='ICRF -> IAU2006/2000A -> Fixed',
                               velocity='native J2 Keplerian velocity for attitude',
                               eop_sha256=frames.sha256,earth_radius_km=None,
                               region='union_of_ellipsoid_central_plane_exterior_rings')
    return result
