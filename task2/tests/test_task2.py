"""赛题二自测（标准库 unittest）。task2 目录下运行：python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import designs as D  # noqa: E402
from constellation import epoch_jd  # noqa: E402
from exactsim import simulate  # noqa: E402
from fasteval import FastEvaluator, revisit_stats  # noqa: E402
from optimizer import Optimizer  # noqa: E402
from sso import R_EARTH, DAY, SSO_RATE_DEG_DAY, j2_rates, sso_inclination  # noqa: E402

COLS = ['alt_km', 'inc_deg', 'raan_deg', 'u_deg']


class TestOrbitModel(unittest.TestCase):
    def test_sso_rate(self):
        for h in (500.0, 600.0, 700.0):
            i = sso_inclination(h)
            rd = j2_rates(R_EARTH + h, 0.0, np.radians(i))[0]
            self.assertAlmostEqual(np.degrees(rd) * DAY, SSO_RATE_DEG_DAY, places=9)

    def test_track_offsets_roundtrip(self):
        c = np.array([0.0, 12.5, 200.0, 359.0])
        dt = np.array([0.0, 100.0, 2500.0, 5000.0])
        df = D.from_track_offsets(650.0, c, dt)
        h, c2, dt2 = D.to_track_offsets(df)
        self.assertAlmostEqual(h, 650.0)
        np.testing.assert_allclose(np.mod(c2 - c + 180, 360) - 180, 0, atol=1e-9)
        np.testing.assert_allclose(dt2, dt, atol=1e-6)

    def test_rgt_altitude_repeats(self):
        for Q, Dd, h in D.rgt_options(max_days=6):
            self.assertTrue(500.0 <= h <= 700.0)
            self.assertAlmostEqual(D.revs_per_day(h) * Dd, Q, places=6)


class TestMetrics(unittest.TestCase):
    def test_revisit_stats(self):
        # 仿真 100 s：格点0 在 10、50 s 被访问，格点1 在 30 s，格点2 从未被访问
        m = revisit_stats(np.array([0, 0, 1]), np.array([10.0, 50.0, 30.0]), 3, 100.0)
        exp = [10, 40, 50, 30, 70, 100]
        self.assertEqual(m['n_intervals'], len(exp))
        self.assertAlmostEqual(m['Tavg_s'], np.mean(exp))
        self.assertAlmostEqual(m['Tmax_s'], 100.0)
        self.assertEqual((m['n_cells_0'], m['n_cells_1'], m['n_cells_2plus']), (1, 1, 1))

    def test_fast_matches_exact(self):
        jd0 = epoch_jd()
        el = D.walker(14, 7, 1, 600.0)
        fe = FastEvaluator(jd0)
        fe.set_constellation(el[COLS].to_numpy())
        mf, me = fe.metrics(), simulate(el, jd0)
        for k in ('reachable', 'all'):
            self.assertAlmostEqual(mf['global_coverage'][k]['coverage'], me['global_coverage'][k]['coverage'], delta=1e-3)
        rf, re = mf['region_revisit'], me['region_revisit']
        self.assertAlmostEqual(rf['Tavg_s'], re['Tavg_s'], delta=0.01 * re['Tavg_s'])
        self.assertAlmostEqual(rf['Tmax_s'], re['Tmax_s'], delta=3600.0)

    def test_rotation_keeps_global_coverage(self):
        jd0 = epoch_jd()
        el = D.walker(12, 6, 1, 700.0)[COLS].to_numpy()
        fe = FastEvaluator(jd0)
        fe.set_constellation(el)
        a = fe.global_metrics()['reachable']['coverage']
        el2 = el.copy()
        el2[:, 2] = (el2[:, 2] + 37.0) % 360.0
        fe.set_constellation(el2)
        self.assertAlmostEqual(fe.global_metrics()['reachable']['coverage'], a, delta=2e-3)


class TestGenerator(unittest.TestCase):
    def test_small_constellation_is_valid(self):
        opt = Optimizer(6, epoch_jd(), budget_s=15.0, log=lambda *_: None)
        df, info = opt.run()
        self.assertEqual(len(df), 6)
        self.assertTrue(df['alt_km'].between(500.0, 700.0).all())
        np.testing.assert_allclose(df['inc_deg'], [sso_inclination(h) for h in df['alt_km']], atol=1e-9)
        self.assertTrue(df['raan_deg'].between(0, 360).all() and df['u_deg'].between(0, 360).all())


if __name__ == '__main__':
    unittest.main()
