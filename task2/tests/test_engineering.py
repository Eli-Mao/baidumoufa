"""Regression tests against analytic physics, geometry and malformed external evidence."""
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sso import R_EARTH, MU, mean_motion, nodal_period, j2_rates, jd_from_datetime
from propagate import propagate_j2_secular, propagate_rk4
from access_geometry import rectangular_access, access_intervals
from coverage import ground_half_width, Grid, _hits, _sample, region_access
from stk_export import connect_script, write_ephemeris, export
from compare_stk import compare
from validate import check_output, _cmp
from run_sim import load_elements


class TestPropagation(unittest.TestCase):
    def test_velocity_is_position_derivative_and_broadcasts(self):
        t = np.array([13.3, 1000.1, 600000.0])
        args = (7071., [97., 98.], [0., 70.], 20.)
        r, v = propagate_j2_secular(*args, t)
        rp, _ = propagate_j2_secular(*args, t+.01)
        rm, _ = propagate_j2_secular(*args, t-.01)
        self.assertEqual(r.shape, (2, 3, 3))
        np.testing.assert_allclose(v, (rp-rm)/.02, atol=1e-7, rtol=0)

    def test_rk4_irregular_times_matches_two_body_analytic(self):
        a = 7000.; n = mean_motion(a,rate_model='first_order')
        t = np.array([51.2, 0., 0.7, 51.2, 101.1])
        r, v = propagate_rk4([a,0,0], [0,np.sqrt(MU/a),0], t, dt=2, use_j2=False)
        exact = np.c_[a*np.cos(n*t), a*np.sin(n*t), np.zeros(len(t))]
        np.testing.assert_allclose(r[0], exact, atol=1e-7, rtol=0)
        with self.assertRaises(ValueError):
            propagate_rk4([a,0,0], [0,7,0], [-1], dt=2)

    def test_nodal_period_includes_perigee_rate(self):
        rd, ad, md = j2_rates(7071., 0, np.radians(98))
        self.assertAlmostEqual(nodal_period(7071., 0, np.radians(98))*(ad+md), 2*np.pi)

    def test_timezone_and_subsecond(self):
        a = datetime(2027,1,1,tzinfo=timezone.utc)
        b = datetime(2027,1,1,8,tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(jd_from_datetime(a), jd_from_datetime(b))
        self.assertAlmostEqual((jd_from_datetime(a+timedelta(seconds=.5))-jd_from_datetime(a))*86400,.5,delta=5e-5)

    def test_non_circular_is_rejected(self):
        with self.assertRaises(ValueError):
            propagate_j2_secular(7000,98,0,0,[0],ecc=.1)


class TestGeometry(unittest.TestCase):
    def test_candidate_scan_matches_all_cells_at_high_latitude(self):
        grid=Grid(78,82,.1,10,15,.1)
        lat=np.radians([79.01,79.02,79.03]); lon=np.radians([12.01,12.03,12.05])
        track=7071*np.c_[np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)]
        _,_,u,along,cross,_=_sample(track,1)
        actual=region_access(track[None],np.arange(3.),grid,10.)
        expected={}
        for j in range(3):
            hit=_hits(grid.unit,np.broadcast_to(u[j],grid.unit.shape),
                      np.broadcast_to(along[j],grid.unit.shape),np.broadcast_to(cross[j],grid.unit.shape),10,10)
            for cell in np.flatnonzero(hit): expected.setdefault(cell,[]).append(j)
        self.assertEqual(set(actual),set(expected))
        for cell in expected: np.testing.assert_array_equal(actual[cell],expected[cell])

    def test_nadir_edge_backside_and_beyond_horizon(self):
        width = ground_half_width(700.)/R_EARTH
        angles = np.array([0, width*.999, width*1.001, np.pi])
        p = R_EARTH*np.c_[np.cos(angles),np.sin(angles),np.zeros(4)]
        np.testing.assert_array_equal(rectangular_access([7071,0,0],[0,7,0],p),[True,True,False,False])
        with self.assertRaises(ValueError):
            ground_half_width(700, np.radians(89))

    def test_interval_refinement_clipping_and_empty(self):
        pred = lambda t: ((t>=2.125)&(t<=3.375)) | (t>=8.2)
        np.testing.assert_allclose(access_intervals(pred,0,10),[[2.125,3.375],[8.2,10]],atol=.001)
        self.assertEqual(access_intervals(lambda t: np.zeros_like(t,bool),0,10).shape,(0,2))

    def test_no_region_longitude_wrap_or_antipodal_hit(self):
        g = Grid(27,35,.1,114,123,.1)
        _, col = g.bin_of(np.array([30.]),np.array([123.1]))
        self.assertGreaterEqual(col[0],g.nlon)
        self.assertFalse(_hits(np.array([[-1,0,0]]),np.array([[1,0,0]]),
                               np.array([[0,1,0]]),np.array([[0,0,1]]),10,10)[0])


class TestHandoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = load_elements(Path(__file__).resolve().parents[1]/'tests/data/stk116_alignment_elements.csv')

    def test_stk_units_attitude_and_ephemeris_validation(self):
        text = connect_script(self.e)
        self.assertIn('Distance Kilometer',text)
        self.assertIn('SetEpoch * "1 Jan 2027 00:00:00.000"',text)
        self.assertIn('7071.000000000',text)
        self.assertNotIn('7071000',text)
        self.assertEqual(text.count('Profile NadirECFVel Offset 0'),28)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                write_ephemeris(Path(d)/'bad.e',[0,1],np.zeros((1,3)),np.zeros((1,3)))
            export(self.e.iloc[:1],d,days=31/86400,step=30)
            lines=(Path(d)/'ephem/SAT_001.e').read_text().splitlines()
            self.assertTrue(lines[-2].startswith('31.000 '))
            self.assertIn('00:00:31.000',(Path(d)/'build_scenario.txt').read_text())
            import json
            self.assertEqual(json.loads((Path(d)/'manifest.json').read_text())['grid_counts']['YRD_GridDiagnostic'],3957)

    def test_output_fails_closed(self):
        self.assertFalse(check_output(self.e.drop(columns='inc_deg'))['ok'])
        for column,value in [('ecc',.1),('a_km',7071.01),('u_deg',360),('alt_km',np.nan)]:
            e=self.e.copy(); e.loc[0,column]=value
            self.assertFalse(check_output(e)['ok'],column)

    def test_metrics_missing_t100_is_failure(self):
        import copy
        g=dict(n_valid=10,n_covered=10,coverage=1.,T90_s=20.,T100_s=30.)
        r=dict(Tavg_s=10.,Tmax_s=20.,n_visits=2,valid=True)
        m=dict(global_coverage={'all':g},region_revisit=dict(r,merged=r.copy()),
               region_revisit_cell=dict(Tavg_s=10.,Tmax_s=20.,n_cells_0=0,n_cells_1=0))
        bad=copy.deepcopy(m); bad['global_coverage']['all']['T100_s']=None
        self.assertFalse(_cmp(m,bad)['ok'])

    def test_orbit_comparison_requires_complete_evidence(self):
        e=self.e.iloc[:1]; row=e.iloc[0]; t=np.array([0.,60.,120.])
        r,_=propagate_j2_secular(row.a_km,row.inc_deg,row.raan_deg,row.u_deg,t)
        s=pd.DataFrame(dict(sat_id=row.sat_id,t_s=t,x_km=r[0,:,0],y_km=r[0,:,1],z_km=r[0,:,2]))
        self.assertTrue(compare(e,s,duration_s=120)['orbit_ok'])
        with self.assertRaises(ValueError): compare(e,s.iloc[:1],duration_s=120)
        s.loc[1,'x_km']+=2
        self.assertFalse(compare(e,s,duration_s=120)['orbit_ok'])


if __name__ == '__main__':
    unittest.main()
