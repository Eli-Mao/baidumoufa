"""Exact-endpoint one-second predicate for provisional V5 moves.

Final acceptance uses the separate, unchanged audit_plan_physics.py program.
"""
from datetime import timedelta
import numpy as np
from skyfield.api import load, EarthSatellite, wgs84
from . import config, io_schema

class PhysicalOracle:
    def __init__(self):
        self.ts=load.timescale();self.eph=load(str(config.EPHEMERIS_FILE));self.t0=io_schema.parse_utc(config.PLAN_T0_UTC)
        self.tles={int(r.sat_id):r for r in io_schema.read_tle_raw().itertuples(index=False)}
        self.sites={int(r.station_id):wgs84.latlon(float(r.lat_deg),float(r.lon_deg),elevation_m=float(r.alt_m)) for r in io_schema.read_stations_raw().itertuples(index=False)}
        self.satellites={};self.cache={};self.calls=0;self.hits=0;self.samples=0
    def __call__(self,task):
        key=(task.station,task.sat,task.start,task.end)
        if key in self.cache:self.hits+=1;return self.cache[key]
        if task.sat not in self.satellites:
            r=self.tles[task.sat];self.satellites[task.sat]=EarthSatellite(r.line1,r.line2,r.name,self.ts)
        sat=self.satellites[task.sat];site=self.sites[task.station]
        offsets=np.unique(np.append(np.arange(0.,task.end-task.start+1e-9,1.),task.end-task.start))
        datetimes=[self.t0+timedelta(seconds=float(task.start+x)) for x in offsets]
        t=self.ts.from_datetimes(datetimes)
        position=sat.at(t);elev=np.asarray((sat-site).at(t).altaz()[0].degrees)
        sun=np.asarray((self.eph['earth']+site).at(t).observe(self.eph['sun']).apparent().altaz()[0].degrees)
        valid=np.isfinite(elev)&np.isfinite(sun)&(elev>=config.MIN_ELEV_DEG)&(elev<=config.MAX_ELEV_DEG)&(sun<config.SUN_ELEV_MAX_DEG)
        if config.REQUIRE_SAT_SUNLIT:valid &= position.is_sunlit(self.eph)
        valid &= np.asarray([message is None for message in position.message])
        answer=bool(valid.all());self.cache[key]=answer;self.calls+=1;self.samples+=len(t)
        return answer
