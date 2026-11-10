import unittest
import pandas as pd

from engineering_run import compare_region_intervals


class RegionConvergenceTests(unittest.TestCase):
    def frame(self, rows):
        return pd.DataFrame(rows, columns=['sat_id','start_s','stop_s'])

    def test_counts_alone_do_not_prove_convergence(self):
        a=self.frame([[1,10,20],[2,30,40]])
        self.assertFalse(compare_region_intervals(a,self.frame([[1,10,20],[3,30,40]]))['ok'])
        self.assertFalse(compare_region_intervals(a,self.frame([[1,10,20],[2,31,41]]))['ok'])

    def test_compares_every_endpoint_after_sorting(self):
        a=self.frame([[2,30,40],[1,10,20]])
        b=self.frame([[1,10.005,20.005],[2,30,40]])
        result=compare_region_intervals(a,b)
        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['max_endpoint_difference_s'],.005)


if __name__=='__main__':
    unittest.main()
