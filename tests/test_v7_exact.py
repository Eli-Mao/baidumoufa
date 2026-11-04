import itertools,random,time,unittest
from satplan.v5 import Task
from satplan.v7_exact import select_intervals,conflict

class FiniteNeighborhoodTests(unittest.TestCase):
    def test_joint_replacement_beats_single_greedy_task(self):
        pool=[Task(1,1,11,'high',5,0.,240.),Task(2,1,12,'mid',3,0.,120.),Task(3,1,13,'mid',3,150.,270.)]
        # Use the same formal weights: two minimum mid jobs lose to full high.
        result,info=select_intervals(pool,[0],deadline=time.perf_counter()+1.)
        self.assertEqual([t.uid for t in result],[1]);self.assertTrue(info['optimal_for_finite_pool'])
        pool[0]=Task(1,1,11,'mid',3,0.,240.)
        result,info=select_intervals(pool,[0],deadline=time.perf_counter()+1.)
        self.assertEqual({t.uid for t in result},{2,3});self.assertAlmostEqual(info['score'],3.6)
    def test_mandatory_high_target_cannot_be_removed(self):
        pool=[Task(1,1,11,'high',5,0.,120.),Task(2,1,12,'high',5,0.,240.)]
        result,info=select_intervals(pool,[0],required_sats={11})
        self.assertEqual([t.uid for t in result],[1])
    def test_cooldown_applies_across_stations(self):
        a=Task(1,1,11,'high',5,0.,120.);b=Task(2,2,11,'high',5,172919.,173039.)
        self.assertTrue(conflict(a,b))
        b=Task(2,2,11,'high',5,172920.,173040.)
        self.assertFalse(conflict(a,b))
    def test_matches_bruteforce_small_random_graphs(self):
        rng=random.Random(4007)
        for _ in range(15):
            pool=[]
            for i in range(8):
                start=rng.randrange(0,2000,100)
                pool.append(Task(i+1,rng.choice([1,2]),rng.randrange(11,16),'mid',3,start,start+rng.choice([120,180,240])))
            expected=0.
            for mask in range(1<<len(pool)):
                tasks=[t for i,t in enumerate(pool) if mask>>i&1]
                if all(not conflict(a,b) for a,b in itertools.combinations(tasks,2)):expected=max(expected,sum(t.score for t in tasks))
            result,info=select_intervals(pool,[],deadline=time.perf_counter()+2.)
            self.assertTrue(info['optimal_for_finite_pool']);self.assertAlmostEqual(info['score'],expected)
    def test_timeout_retains_incumbent_without_proof(self):
        pool=[Task(1,1,11,'high',5,0.,120.)]
        result,info=select_intervals(pool,[0],deadline=0.)
        self.assertEqual([t.uid for t in result],[1]);self.assertFalse(info['optimal_for_finite_pool'])
    def test_bad_incumbent_is_rejected(self):
        pool=[Task(1,1,11,'high',5,0.,120.),Task(2,1,12,'high',5,100.,220.)]
        with self.assertRaises(ValueError):select_intervals(pool,[0,1])

if __name__=='__main__':unittest.main()
