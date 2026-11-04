import unittest
import pandas as pd
from satplan import rules
from satplan.v5 import Task,State
from satplan.v7 import Engine,elastic_orders
from test_v5 import frame

class ElasticPackingTests(unittest.TestCase):
    def test_two_short_jobs_can_outscore_one_full_job(self):
        jobs=[Task(1,1,11,'mid',3,0.,240.),Task(2,1,12,'mid',3,0.,120.)]
        packed=list(elastic_orders(jobs,[(0.,300.),(0.,300.)]))
        self.assertTrue(packed)
        best=max(packed,key=lambda ts:sum(t.score for t in ts))
        self.assertGreater(sum(t.score for t in best),3.)
        for tasks in packed:
            p=frame(tasks);w=pd.DataFrame([dict(station_id=1,sat_id=t.sat,t_start_s=0.,t_end_s=300.) for t in tasks])
            self.assertFalse(rules.plan_violations(p,w))
    def test_respects_distinct_release_deadline_and_switch(self):
        jobs=[Task(1,1,11,'high',5,0.,120.),Task(2,1,12,'mid',3,200.,320.),Task(3,1,13,'low',2,400.,520.)]
        bounds=[(25.125,210.125),(200.125,390.125),(400.125,590.125)]
        packed=list(elastic_orders(jobs,bounds));self.assertTrue(packed)
        for tasks in packed:
            for t in tasks:
                a,b=bounds[t.uid-1];self.assertGreaterEqual(t.start,a);self.assertLessEqual(t.end,b)
                self.assertGreaterEqual(t.duration,120.);self.assertLessEqual(t.duration,240.)
            ordered=sorted(tasks,key=lambda t:t.start)
            self.assertTrue(all(b.start-a.end>=30.-1e-9 for a,b in zip(ordered,ordered[1:])))
    def test_infeasible_capacity_emits_no_packing(self):
        jobs=[Task(1,1,11,'high',5,0.,120.),Task(2,1,12,'mid',3,0.,120.)]
        self.assertFalse(list(elastic_orders(jobs,[(0.,269.99),(0.,269.99)])))
    def test_duplicate_task_ids_rejected(self):
        t=Task(1,1,11,'high',5,0.,120.)
        with self.assertRaises(ValueError):list(elastic_orders([t,t],[(0.,300.),(0.,300.)]))
    def engine(self,physical=lambda t:True):
        base=frame([Task(1,1,11,'high',5,0.,240.)])
        windows=pd.DataFrame([dict(station_id=1,sat_id=sat,priority='high',priority_score=5,t_start_s=0.,t_end_s=600.) for sat in (11,12)])
        return Engine(base,windows,budget_s=2,seed=11,physical=physical)
    def test_failed_physics_rolls_back_all_indexes_and_score(self):
        e=self.engine(lambda t:False);old=e.state.tasks[1];before=e.state.frame()
        self.assertFalse(e.commit([old],[Task(2,1,11,'high',5,0.,120.),Task(3,1,12,'high',5,150.,270.)],'elastic'))
        pd.testing.assert_frame_equal(before,e.state.frame());self.assertAlmostEqual(e.state.total,5.)
    def test_same_target_cooldown_applies_inside_elastic_transaction(self):
        e=self.engine();old=e.state.tasks[1];before=e.state.frame()
        self.assertFalse(e.commit([old],[Task(2,1,11,'high',5,0.,120.),Task(3,1,11,'high',5,150.,270.)],'elastic'))
        pd.testing.assert_frame_equal(before,e.state.frame());self.assertAlmostEqual(e.state.total,5.)
    def test_last_high_target_coverage_is_preserved(self):
        e=self.engine();old=e.state.tasks[1]
        self.assertFalse(e.commit([old],[Task(2,1,12,'high',5,0.,240.),Task(3,2,13,'high',5,0.,120.)],'elastic'))
        self.assertIn(old.uid,e.state.tasks)
    def test_expired_budget_cannot_publish_a_move(self):
        e=self.engine();e.deadline=0.;old=e.state.tasks[1]
        self.assertFalse(e.commit([old],[Task(2,1,11,'high',5,0.,120.),Task(3,1,12,'high',5,150.,270.)],'elastic'))
        self.assertAlmostEqual(e.state.total,5.)
    def test_missing_physical_oracle_is_error(self):
        with self.assertRaises(ValueError):self.engine(None)

if __name__=='__main__':unittest.main()
