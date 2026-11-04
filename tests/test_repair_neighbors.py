"""Check incremental repair decisions against full current-model validation."""
import sys,unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from repair_plan_physics import _candidate_hard_feasible
from satplan import rules

class TestRepairNeighbors(unittest.TestCase):
    def test_real_single_edit_equivalence(self):
        base=ROOT/'data/out/real_aug2026_10000'
        if not (base/'v4_plan.csv').exists():self.skipTest('local real benchmark unavailable')
        p=pd.read_csv(base/'v4_plan.csv');w=pd.read_csv(base/'windows.csv')
        grouped={int(sid):g for sid,g in w.groupby('sat_id')}
        idx=int(p.index[len(p)//2])
        actions=[{}, {'t_start_s':float(p.loc[idx,'t_start_s'])+30},
                 {'station_id':1 if int(p.loc[idx,'station_id'])!=1 else 2},
                 {'t_start_s':-1.,'t_end_s':119.,'dur_s':120.},
                 {'t_start_s':518300.,'t_end_s':518420.,'dur_s':120.},
                 {'dur_s':119.}, {'dur_s':241.}]
        for change in actions:
            candidate=p.copy()
            for k,v in change.items():candidate.at[idx,k]=v
            self.assertEqual(_candidate_hard_feasible(candidate,w,idx,grouped),not bool(rules.plan_violations(candidate,w)),change)

    def test_cooldown_and_station_neighbors(self):
        cols=['task_id','station_id','sat_id','priority','priority_score','t_start_s','t_end_s','dur_s','duration_score']
        p=pd.DataFrame([[1,1,1,'high',5,0.,120.,120.,.6],
                        [2,1,2,'mid',3,150.,270.,120.,.6],
                        [3,2,1,'high',5,173000.,173120.,120.,.6]],columns=cols)
        w=pd.DataFrame([{'station_id':st,'sat_id':sat,'t_start_s':0.,'t_end_s':518400.} for st in [1,2] for sat in [1,2]])
        self.assertFalse(rules.plan_violations(p,w))
        for idx,changes in [(1,{'t_start_s':149.,'t_end_s':269.}),(2,{'t_start_s':172919.,'t_end_s':173039.}),(2,{'t_start_s':172920.,'t_end_s':173040.}),(1,{'station_id':2})]:
            candidate=p.copy()
            for k,v in changes.items():candidate.at[idx,k]=v
            self.assertEqual(_candidate_hard_feasible(candidate,w,idx),not bool(rules.plan_violations(candidate,w)))

if __name__=='__main__':unittest.main()
