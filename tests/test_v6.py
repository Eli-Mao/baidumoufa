import unittest
import pandas as pd
from satplan.v5 import Task,State
from satplan.v6 import Engine,Catalog
from test_v5 import frame

def windows():
    return pd.DataFrame([{'station_id':1,'sat_id':12,'priority':'mid','priority_score':3,'t_start_s':0.,'t_end_s':1000.}])
class V6Tests(unittest.TestCase):
    def engine(self,physical=lambda t:True):
        return Engine(frame([Task(1,1,11,'high',5,0.,240.),Task(2,2,11,'high',5,173100.,173340.)]),windows(),budget_s=1,seed=1,physical=physical)
    def test_reject_removing_last_high(self):
        e=self.engine();old=e.state.tasks[2];e.state.remove(1)
        self.assertFalse(e.commit([old],[Task(3,3,12,'high',5,1000.,1240.),Task(4,4,13,'high',5,1000.,1240.)],'test'))
        self.assertIn(old.uid,e.state.tasks)
    def test_partial_transaction_rolls_back(self):
        e=self.engine();before=e.state.frame();old=e.state.tasks[1]
        self.assertFalse(e.commit([old],[Task(3,1,12,'high',5,0.,240.),Task(4,1,13,'high',5,120.,360.)],'test'))
        pd.testing.assert_frame_equal(before,e.state.frame())
        self.assertAlmostEqual(e.state.total,10.)
    def test_physical_failure_preserves_plan(self):
        e=self.engine(lambda t:False);before=e.state.frame()
        self.assertFalse(e.commit([], [Task(3,3,12,'mid',3,1000.,1240.)],'test'))
        pd.testing.assert_frame_equal(before,e.state.frame())
    def test_profitable_replacement_keeps_high_and_incremental_score(self):
        e=self.engine();old=e.state.tasks[1]
        self.assertTrue(e.commit([old],[Task(3,1,12,'high',5,0.,120.),Task(4,1,13,'high',5,150.,270.)],'test'))
        self.assertAlmostEqual(e.state.total,11.)
        self.assertEqual(e.state.counts[11],1)
    def test_boundary_duration_is_declared_without_relaxing_geometry(self):
        c=Catalog(windows());t=c.task(0,123456.123456,123456.123456+240.,1)
        self.assertEqual(t.duration,240.);self.assertLess(abs(t.end-t.start-t.duration),1e-6)
    def test_expired_budget_does_not_mutate(self):
        e=self.engine();e.deadline=0;before=e.state.frame();self.assertFalse(e.commit([], [Task(3,3,12,'mid',3,1000.,1240.)],'test'))
        pd.testing.assert_frame_equal(before,e.state.frame())
if __name__=='__main__':unittest.main()
