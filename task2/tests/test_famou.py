"""伐谋评估器自测：合法候选能打分，非法 / 报错 / 无输出 / 超时的候选判 0 分。

task2 目录下运行：python -m unittest tests.test_famou -v（约 20 s）
候选程序放在临时目录里，模拟平台把候选代码放在评估器目录之外的情形。
"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'famou'))

import evaluator as E  # noqa: E402

KEYS = {'validity', 'combined_score', 'cost_time', 'error_info', 'metric'}
HEAD = '''
import argparse
import numpy as np
import pandas as pd
import designs as D
p = argparse.ArgumentParser()
p.add_argument('--n', type=int)
p.add_argument('--budget', type=float)
p.add_argument('--out')
a = p.parse_args()
'''


class TestEvaluator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _cand(self, body):
        path = Path(self.tmp.name) / 'cand.py'
        path.write_text(HEAD + textwrap.dedent(body), encoding='utf-8')
        return str(path)

    def _invalid(self, r, words):
        self.assertEqual(set(r), KEYS)
        self.assertEqual((r['validity'], r['combined_score']), (0.0, 0.0))
        self.assertIn(words, r['error_info'])

    def test_legal_candidate_scores(self):
        r = E.evaluate(str(ROOT / 'famou' / 'build' / 'walker_baseline.py'), 'quick')
        self.assertEqual(set(r), KEYS)
        self.assertEqual((r['validity'], r['error_info']), (1.0, ''))
        self.assertGreater(r['combined_score'], 0.0)
        self.assertIn('n28', r['metric'])

    def test_wrong_inclination_is_invalid(self):
        r = E.evaluate(self._cand('''
            df = D.walker(a.n, 4, 1, 650.0)
            pd.DataFrame(dict(h_km=df.alt_km, inc_deg=df.inc_deg + 0.5, raan_deg=df.raan_deg,
                              u_deg=df.u_deg)).to_csv(a.out, index=False)
        '''), 'quick')
        self._invalid(r, '太阳同步')

    def test_wrong_count_is_invalid(self):
        r = E.evaluate(self._cand('''
            df = D.walker(a.n - 1, 4, 1, 650.0)
            pd.DataFrame(dict(h_km=df.alt_km, inc_deg=df.inc_deg, raan_deg=df.raan_deg,
                              u_deg=df.u_deg)).to_csv(a.out, index=False)
        '''), 'quick')
        self._invalid(r, '卫星数')

    def test_crash_is_invalid(self):
        self._invalid(E.evaluate(self._cand('raise RuntimeError("boom")'), 'quick'), 'boom')

    def test_missing_output_is_invalid(self):
        self._invalid(E.evaluate(self._cand('pass'), 'quick'), '没有写出')

    def test_timeout_is_invalid(self):
        old = E.SLACK
        E.SLACK = (0.0, 3.0)          # 硬超时压到 3 s
        self.addCleanup(setattr, E, 'SLACK', old)
        self._invalid(E.evaluate(self._cand('import time; time.sleep(30)'), 'quick'), '超时')


if __name__ == '__main__':
    unittest.main()
