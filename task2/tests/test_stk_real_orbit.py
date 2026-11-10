"""Regression against independent STK 11.6 output, not our own ephemeris export."""
from pathlib import Path
import json
import unittest
import numpy as np
import pandas as pd
from propagate import propagate_j2_secular
from run_sim import load_elements
from sso import sso_inclination,sso_altitude


class StkMeasuredOrbit(unittest.TestCase):
    def test_sso_design_matches_independent_native_node_rate(self):
        path=Path(__file__).parent/'data/stk116_sso_reference.json'
        d=json.loads(path.read_text())
        self.assertLess(abs(d['measured_node_rate_deg_day']-d['target_deg_day']),1e-6)
        inc=sso_inclination(d['height_km'],rate_model='stk')
        from earth_frames import EarthFrames,StkOrbit
        from types import SimpleNamespace
        from sso import DAY,design_inclination
        frames=EarthFrames()
        el=SimpleNamespace(alt_km=700.,inc_deg=d['inclination_deg'],raan_deg=0.,u_deg=0.)
        measured_prediction=np.degrees(StkOrbit(el,frames).rd)*DAY
        self.assertAlmostEqual(measured_prediction,d['measured_node_rate_deg_day'],delta=1e-6)
        el.inc_deg=design_inclination(700.,0.)
        self.assertAlmostEqual(np.degrees(StkOrbit(el,frames).rd)*DAY,d['target_deg_day'],places=9)
        self.assertAlmostEqual(sso_altitude(inc,rate_model='stk'),700,places=8)
        self.assertGreater(abs(inc-sso_inclination(700,rate_model='first_order')),.004)

    def test_independent_measured_positions(self):
        root=Path(__file__).resolve().parents[1]
        elements=load_elements(root/'tests/data/stk116_alignment_elements.csv').set_index('sat_id')
        data=pd.read_csv(root/'tests/data/stk116_j2000_reference.csv')
        old_errors=[]
        for sid, rows in data.groupby('sat_id'):
            e=elements.loc[sid]
            args=(6371+e.alt_km,e.inc_deg,e.raan_deg,e.u_deg,rows.t_s.to_numpy())
            expected=rows[['x_km','y_km','z_km']].to_numpy()
            actual,_=propagate_j2_secular(*args,rate_model='stk')
            self.assertLess(np.linalg.norm(actual[0]-expected,axis=1).max(),.002)
            legacy,_=propagate_j2_secular(*args,rate_model='first_order')
            old_errors.extend(np.linalg.norm(legacy[0]-expected,axis=1))
        self.assertGreater(max(old_errors),1.)

    def test_stk_velocity_is_derivative(self):
        args=(7071,98.158925,156,.3125)
        t=np.array([100.,600000.])
        _,v=propagate_j2_secular(*args,t,rate_model='stk')
        rp,_=propagate_j2_secular(*args,t+.01,rate_model='stk')
        rm,_=propagate_j2_secular(*args,t-.01,rate_model='stk')
        np.testing.assert_allclose(v,(rp-rm)/.02,rtol=0,atol=1e-7)


if __name__=='__main__': unittest.main()
