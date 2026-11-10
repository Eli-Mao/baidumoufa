import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from summarize_stk_region import aggregate


class TestStkRegionEvidence(unittest.TestCase):
    def test_component_union_does_not_bridge_gap_or_merge_satellites(self):
        m=dict(duration_s=100,satellite_ids=[1,2],region_area_targets=['a','b'])
        raw=pd.DataFrame([(1,'a',10,20),(1,'b',15,30),(1,'a',35,40),(2,'a',12,18)],
                         columns=['sat_id','component_id','start_s','stop_s'])
        status=[dict(sat_id=s,component_id=c,intervals=len(raw[(raw.sat_id==s)&(raw.component_id==c)]),computed=True)
                for s in [1,2] for c in ['a','b']]
        result=aggregate(raw,status,m)
        self.assertEqual(result['access_intervals'],[
            dict(sat_id=1,start_s=10.,stop_s=30.),dict(sat_id=1,start_s=35.,stop_s=40.),
            dict(sat_id=2,start_s=12.,stop_s=18.)])
        self.assertEqual(result['region_revisit']['n_visits'],3)
        self.assertFalse(result['stk_verified'])
        with self.assertRaises(ValueError): aggregate(raw,status[:-1],m)

    def test_missing_data_cannot_be_claimed_as_no_access(self):
        m=dict(duration_s=100,satellite_ids=[1],region_area_targets=['a'])
        empty=pd.DataFrame(columns=['sat_id','component_id','start_s','stop_s'])
        status=[dict(sat_id=1,component_id='a',intervals=1,computed=True)]
        with self.assertRaises(ValueError): aggregate(empty,status,m)
        status[0]['intervals']=0
        self.assertEqual(aggregate(empty,status,m)['region_revisit']['n_visits'],0)


if __name__=='__main__': unittest.main()
