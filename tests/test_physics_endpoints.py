"""Regression: a real fractional task endpoint beyond a visibility edge must fail."""
import sys,tempfile,unittest,json
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import audit_plan_physics

class TestExactEndpoint(unittest.TestCase):
    def test_real_fractional_endpoint_is_sampled_and_rejected(self):
        source=ROOT/'data/out/real_aug2026_5000/windows.csv'
        if not source.exists(): self.skipTest('local real-data window cache unavailable')
        w=pd.read_csv(source,nrows=100)
        row=w.loc[(w.dur_s>241)&(w.t_end_s<518399)].iloc[0]
        task={'task_id':1,'sat_id':int(row.sat_id),'station_id':int(row.station_id),
              't_start_s':float(row.t_end_s)-120.5,'t_end_s':float(row.t_end_s)+.25}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'task.csv';pd.DataFrame([task]).to_csv(p,index=False)
            result=audit_plan_physics.run(p,Path(d)/'audit.json')
            self.assertTrue(result['exact_endpoints_included'])
            self.assertEqual(result['failed'],1)
            detail=pd.read_csv(Path(d)/'audit.csv').iloc[0]
            self.assertEqual(detail.samples,122)
            self.assertEqual(int(detail.bad_elevation_samples+detail.bad_darkness_samples+detail.bad_satellite_illumination_samples),1)

if __name__=='__main__': unittest.main()
