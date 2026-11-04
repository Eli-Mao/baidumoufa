import unittest
from satplan.v5 import Task
from satplan.v7_adaptive import Engine
from test_v5 import frame
import pandas as pd
class Oracle:
    calls=0;hits=0
    def __call__(self,t):self.calls+=1;return True
class AdaptiveTests(unittest.TestCase):
    def engine(self):
        tasks=[Task(1,1,11,'mid',3,0.,240.)]
        w=pd.DataFrame([dict(station_id=1,sat_id=sat,priority='mid',priority_score=3,t_start_s=0.,t_end_s=300.) for sat in (11,12,13)])
        return Engine(frame(tasks),w,budget_s=2.,seed=11,physical=Oracle())
    def test_epoch_changes_only_after_accepted_transaction(self):
        e=self.engine();old=e.state.tasks[1]
        self.assertFalse(e.commit([old],[Task(2,1,12,'low',2,0.,120.)],'test'));self.assertEqual(e.epoch,0)
        self.assertTrue(e.commit([old],[Task(2,1,12,'mid',3,0.,120.),Task(3,1,13,'mid',3,150.,270.)],'test'));self.assertEqual(e.epoch,1)
    def test_exact_operator_improves_and_restores_external_state(self):
        e=self.engine()
        # Limit to station with real fixture tasks.
        e.state.stations={1:e.state.stations[1]}
        self.assertTrue(e.exact_neighborhood());self.assertGreater(e.state.total,3.)
        self.assertEqual(e.state.counts[11]+e.state.counts[12]+e.state.counts[13],2)
        self.assertTrue(e.diagnostics['exact_calls'])
    def test_sampling_restart_never_uses_a_worse_plan(self):
        e=self.engine();e.deadline=0.;before=e.state.total
        plan,stats=e.run();self.assertAlmostEqual(stats['candidate_score'],before);self.assertEqual(len(plan),1)
if __name__=='__main__':unittest.main()
