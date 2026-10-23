"""赛题二自测（标准库 unittest）。task2 目录下运行：python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import designs as D  # noqa: E402
import score as S  # noqa: E402
from constellation import epoch_jd  # noqa: E402
from exactsim import simulate  # noqa: E402
from fasteval import FastEvaluator, revisit_stats, region_revisit, sat_passes  # noqa: E402
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


class TestRegionRevisit(unittest.TestCase):
    """长三角整体重访（答疑 #45-3 / #49-1），仿真 100 s 的人工算例。"""

    def test_unmerged_with_overlap(self):
        # 访问 [10,20]、[15,30]（与前一次重叠）、[50,60]：间隔 10、max(0,15−20)=0、50−30=20、100−60=40
        m = region_revisit([15.0, 10.0, 50.0], [30.0, 20.0, 60.0], 100.0)
        self.assertEqual((m['n_visits'], m['n_intervals']), (3, 4))
        self.assertAlmostEqual(m['Tavg_s'], 70.0 / 4)
        self.assertAlmostEqual(m['Tmax_s'], 40.0)
        self.assertTrue(m['valid'])

    def test_merged(self):
        # 并集 [10,30]、[50,60]：间隔 10、20、40
        m = region_revisit([15.0, 10.0, 50.0], [30.0, 20.0, 60.0], 100.0, merge=True)
        self.assertEqual((m['n_visits'], m['n_intervals']), (2, 3))
        self.assertAlmostEqual(m['Tavg_s'], 70.0 / 3)
        self.assertAlmostEqual(m['Tmax_s'], 40.0)

    def test_nested_visit(self):
        # [20,30] 被 [10,50] 包含：不合并时按开始时刻排序逐对相减 → 10、0、60−30=30、30；合并时 10、10、30
        s, e = [10.0, 20.0, 60.0], [50.0, 30.0, 70.0]
        m = region_revisit(s, e, 100.0)
        self.assertAlmostEqual(m['Tavg_s'], 70.0 / 4)
        self.assertAlmostEqual(m['Tmax_s'], 30.0)
        m = region_revisit(s, e, 100.0, merge=True)
        self.assertAlmostEqual(m['Tavg_s'], 50.0 / 3)
        self.assertAlmostEqual(m['Tmax_s'], 30.0)

    def test_fewer_than_two_visits(self):
        m = region_revisit([10.0], [20.0], 100.0)
        self.assertEqual(m['n_visits'], 1)
        self.assertFalse(m['valid'])
        self.assertAlmostEqual(m['Tavg_s'], 45.0)
        self.assertAlmostEqual(m['Tmax_s'], 80.0)
        m = region_revisit([], [], 100.0)
        self.assertEqual((m['n_visits'], m['Tavg_s'], m['Tmax_s'], m['valid']), (0, 100.0, 100.0, False))
        # 整体不足两次访问 → 重访项 0 分；--lenient 时照常计分
        flat = dict(T90=1.0, T100=None, Tavg=45.0, Tmax=80.0, n_visits=1)
        refs = dict(T90=1.0, T100=1.0, Tavg=45.0, Tmax=80.0)
        self.assertEqual(S.official(flat, refs)[1]['Tavg'], 0.0)
        self.assertAlmostEqual(S.official(flat, refs, strict_two_visits=False)[0], 28.0 + 42.0 + 18.0)

    def test_sat_passes_split(self):
        # 同一颗星相邻命中相隔 > 300 s 切开；pad 为格点在视场内停留的半时长
        s, e = sat_passes([100.0, 101.0, 102.0, 500.0, 501.0, 1000.0])
        np.testing.assert_allclose(s, [100.0, 500.0, 1000.0])
        np.testing.assert_allclose(e, [102.0, 501.0, 1000.0])
        s, e = sat_passes([0.0, 200.0, 400.0], pad=1.5)
        np.testing.assert_allclose(s, [-1.5])
        np.testing.assert_allclose(e, [401.5])


class TestMetrics(unittest.TestCase):
    def test_revisit_stats(self):
        # 逐格点旧口径（仅作参考）。仿真 100 s：格点0 在 10、50 s 被访问，格点1 在 30 s，格点2 从未被访问
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
        self.assertLessEqual(abs(rf['n_visits'] - re['n_visits']), 1)
        for r1, r2 in ((rf, re), (rf['merged'], re['merged'])):
            self.assertAlmostEqual(r1['Tavg_s'], r2['Tavg_s'], delta=36.0)       # 0.01 h
            self.assertAlmostEqual(r1['Tmax_s'], r2['Tmax_s'], delta=36.0)
        cf, ce = mf['region_revisit_cell'], me['region_revisit_cell']
        self.assertAlmostEqual(cf['Tavg_s'], ce['Tavg_s'], delta=0.01 * ce['Tavg_s'])

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
