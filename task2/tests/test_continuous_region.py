"""Independent analytic cases for whole-area contact (no region evaluation grid)."""
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from continuous_region import SphericalRegion, simulate_region, ecef_state, _unit_from_lonlat
from access_geometry import rectangular_access, access_intervals
from sso import R_EARTH
from constellation import epoch_jd


def box(x0, x1, y0, y1):
    return np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],float)


class TestContinuousRegionGeometry(unittest.TestCase):
    r=np.array([7071.,0,0])
    v=np.array([0,7.,0])

    def test_footprint_inside_region(self):
        region=SphericalRegion([box(-.5,.5,-.5,.5)])
        self.assertTrue(region.intersects(self.r,self.v)[0])

    def test_region_inside_footprint(self):
        region=SphericalRegion([box(.02,.04,.02,.04)])
        self.assertFalse(region.contains([[1,0,0]])[0])
        self.assertTrue(region.intersects(self.r,self.v)[0])

    def test_edge_crossings_without_region_vertices_or_boresight(self):
        ring=box(-.3,.3,.05,.06)
        region=SphericalRegion([ring])
        self.assertFalse(region.contains([[1,0,0]])[0])
        self.assertFalse(rectangular_access(self.r,self.v,R_EARTH*_unit_from_lonlat(ring)).any())
        self.assertTrue(region.intersects(self.r,self.v)[0])

    def test_outside_and_backside(self):
        self.assertFalse(SphericalRegion([box(.2,.3,-.01,.01)]).intersects(self.r,self.v)[0])
        self.assertFalse(SphericalRegion([box(179.8,180.2,-.1,.1)]).intersects(self.r,self.v)[0])

    def test_disjoint_parts_and_holes_rejected(self):
        rings=[box(1,2,1,2),box(.02,.04,.02,.04)]
        self.assertTrue(SphericalRegion(rings).intersects(self.r,self.v)[0])
        with self.assertRaises(ValueError): SphericalRegion([box(-1,1,-1,1),box(-.1,.1,-.1,.1)])

    def test_great_circle_boundary_not_lonlat_line(self):
        region=SphericalRegion([box(-20,20,50,60)])
        # The bottom edge bows north on a great circle; (0,51) remains outside.
        self.assertFalse(region.contains(_unit_from_lonlat([[0,51]]))[0])
        self.assertTrue(region.contains(_unit_from_lonlat([[0,55]]))[0])

    def test_detected_windows_are_not_bridged(self):
        intervals=access_intervals(lambda t: ((t>2)&(t<3))|((t>4)&(t<5)),0,10,.2,.001)
        self.assertEqual(len(intervals),2)
        np.testing.assert_allclose(intervals,[[2,3],[4,5]],atol=.001)


class TestWholeAreaPropagation(unittest.TestCase):
    def test_fixed_velocity_is_position_derivative(self):
        e=pd.DataFrame([dict(sat_id=1,alt_km=700,inc_deg=98,raan_deg=15,u_deg=30)]).iloc[0]
        t=np.array([100.,200.])
        r,v=ecef_state(e,t,epoch_jd())
        rp,_=ecef_state(e,t+.1,epoch_jd()); rm,_=ecef_state(e,t-.1,epoch_jd())
        # GMST evaluates via JD doubles, so submillimeter velocity error is expected.
        np.testing.assert_allclose(v,(rp-rm)/.2,atol=3e-5,rtol=0)

    def test_prefilter_matches_full_scan_and_step_halving(self):
        from sso import gmst_rad
        # Start over a small equatorial target and scan 100 s. This directly
        # checks clipped initial access and that the coarse prefilter loses none.
        raan=np.degrees(gmst_rad(epoch_jd()))
        e=pd.DataFrame([dict(sat_id=1,alt_km=700.,inc_deg=0.,raan_deg=raan,u_deg=0.)])
        rings=[box(-.1,.1,-.1,.1)]
        region=SphericalRegion(rings)
        end=100.
        expected=access_intervals(lambda t: region.intersects(*ecef_state(e.iloc[0],t,epoch_jd())),0,end,.5,.001)
        a=simulate_region(e,epoch_jd(),rings,days=end/86400,step=1,tolerance_s=.001)
        b=simulate_region(e,epoch_jd(),rings,days=end/86400,step=.5,tolerance_s=.001)
        aa=np.array([[row['start_s'],row['stop_s']] for row in a['access_intervals']])
        bb=np.array([[row['start_s'],row['stop_s']] for row in b['access_intervals']])
        np.testing.assert_allclose(aa,expected,atol=.002)
        np.testing.assert_allclose(bb,expected,atol=.002)
        self.assertEqual(a['region_revisit']['n_visits'],1)
        self.assertFalse(a['region_revisit']['valid'])
        self.assertEqual(a['model']['gap_bridging_s'],0)


if __name__=='__main__': unittest.main()
