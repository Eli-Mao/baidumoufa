import unittest,random
import pandas as pd
from satplan import rules
from satplan.v5 import State,Task,Catalog,insert_options,search

def frame(tasks):
    return pd.DataFrame([{'task_id':t.uid,'station_id':t.station,'sat_id':t.sat,'priority':t.priority,'priority_score':t.weight,'t_start_s':t.start,'t_end_s':t.end,'dur_s':t.end-t.start,'duration_score':rules.duration_score(t.end-t.start)} for t in tasks])

class TestV5(unittest.TestCase):
    def test_csv_duration_field_is_preserved_at_float_boundary(self):
        import numpy as np
        p=frame([Task(1,1,11,'high',5,0.,float(np.nextafter(240.,np.inf)))])
        p['dur_s']=240.;p['duration_score']=1.
        s=State(p)
        self.assertAlmostEqual(s.total,5.)
        self.assertEqual(s.frame().iloc[0].dur_s,240.)

    def test_incremental_conflict_equivalence(self):
        old=[Task(1,1,11,'high',5,100,340),Task(2,1,12,'mid',3,400,580),Task(3,2,11,'high',5,173200,173440)]
        base=frame(old);s=State(base);rng=random.Random(42)
        for i in range(80):
            start=rng.choice([70.,340.,370.,580.,610.,172900.,173170.])+rng.choice([-1e-6,0.,1e-6])
            t=Task(4,rng.choice([1,2]),rng.choice([11,12,13]),'high',5,start,start+120.)
            p=pd.concat([base,frame([t])],ignore_index=True)
            w=pd.DataFrame([{'station_id':site,'sat_id':sat,'t_start_s':0.,'t_end_s':518400.} for site in [1,2] for sat in [11,12,13]])
            self.assertEqual(s.fits(t),not bool(rules.plan_violations(p,w)))
    def test_short_gap_is_used_without_changing_cooldown(self):
        s=State(frame([Task(1,1,11,'high',5,0,240),Task(2,1,12,'mid',3,460,700)]))
        free=s.free_intervals(1,13,0,800)
        self.assertIn((270.,430.),free)
        self.assertFalse(s.free_intervals(2,11,0,172900))
    def test_remove_rollback_restores_indexes_and_score(self):
        s=State(frame([Task(1,1,11,'high',5,0,240),Task(2,1,12,'mid',3,300,540)]));before=s.frame()
        t=s.remove(1);s.add(t)
        pd.testing.assert_frame_equal(before,s.frame());self.assertEqual(s.total,8.)
    def test_tiny_search_keeps_rejected_physics_out(self):
        p=frame([Task(1,1,11,'high',5,0,240)])
        w=pd.DataFrame([{'window_id':1,'station_id':1,'sat_id':12,'priority':'mid','priority_score':3,'t_start_s':270.,'t_end_s':450.}])
        result,stats=search(p,w,None,budget_s=.1,seed=1,physical=lambda t:False)
        self.assertEqual(len(result),1);self.assertAlmostEqual(stats['candidate_score'],5.)

if __name__=='__main__':unittest.main()
