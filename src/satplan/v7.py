"""V7: global gap pricing plus elastic ordered-job packing and V6 neighborhoods.

All proposals are provisional. The unchanged whole-plan Evaluator and independent
full-interval physical audit must accept the serialized output. No rule changes.
"""
from __future__ import annotations
from dataclasses import replace
from itertools import permutations, product
import time
import numpy as np
from . import config
from .v5 import insert_options
from .v6 import Engine as V6Engine

def elastic_orders(jobs, bounds, switch_s=None):
    """Generate feasible 2/3-job packings; enumerate order and slack priorities.

    A fixed order imposes contiguous-block duration capacities. Try greedy slack
    allocation in every priority order, then earliest/latest placements. This is
    a bounded neighborhood heuristic, not a claim of global LP optimality.
    """
    switch = config.SWITCH_TIME_S if switch_s is None else switch_s
    n = len(jobs)
    if not 1 <= n <= 3: raise ValueError('elastic neighborhood supports 1..3 jobs')
    if len({t.uid for t in jobs}) != n: raise ValueError('duplicate task identity')
    seen=set()
    for order in permutations(range(n)):
        ts=[jobs[k] for k in order]; ab=[bounds[k] for k in order]
        capacities=[(i,j,ab[j][1]-ab[i][0]-switch*(j-i)) for i in range(n) for j in range(i,n)]
        for allocation in permutations(range(n)):
            durations=[config.MIN_DUR_S]*n
            if any(sum(durations[i:j+1])>cap+1e-8 for i,j,cap in capacities): continue
            for k in allocation:
                slack=min([config.MAX_DUR_S-durations[k]] +
                    [cap-sum(durations[i:j+1]) for i,j,cap in capacities if i<=k<=j])
                durations[k]+=max(0.,slack)
            early=[]; cursor=-float('inf')
            for (a,b),d in zip(ab,durations):
                start=max(a,cursor);early.append(start);cursor=start+d+switch
            late=[0.]*n;cursor=float('inf')
            for k in reversed(range(n)):
                a,b=ab[k];late[k]=min(b,cursor)-durations[k];cursor=late[k]-switch
            for starts in (early,late):
                packed=[]
                for k,(old,(a,b),d,start) in enumerate(zip(ts,ab,durations,starts)):
                    end=start+d
                    # Re-evaluate geometry after floating point subtraction.
                    declared=120. if abs(d-120.)<1e-8 else (240. if abs(d-240.)<1e-8 else float(end-start))
                    if start<a or end>b or not 120.<=declared<=240.: break
                    packed.append(replace(old,start=float(start),end=float(end),declared_duration=declared))
                else:
                    key=tuple((t.uid,t.start,t.end) for t in packed)
                    if key not in seen:
                        seen.add(key);yield packed

class Engine(V6Engine):
    def __init__(self,plan,windows,*,budget_s,seed,physical):
        if physical is None: raise ValueError('V7 requires a full-interval physical predicate')
        super().__init__(plan,windows,budget_s=budget_s,seed=seed,physical=physical)
        self.budget_s=budget_s
        self.profile={};self.window_scans=0

    def fill_gaps(self):
        """Price every visited window, rather than uniform random insertion."""
        tick=time.perf_counter();pool=[]
        scan_end=min(self.deadline-.1,self.started+self.budget_s*.38)
        # Seeded station-independent tie order, no precomputed audit input.
        for i in self.order:
            if self.window_scans%256==0 and time.perf_counter()>=scan_end:break
            i=int(i);self.window_scans+=1
            opts=insert_options(self.state,self.cat,i)
            if opts:
                t=opts[0]
                pool.append((t.score, self.state.counts[t.sat]==0, self.rng.random(), i))
        pool.sort(reverse=True)
        for _,_,_,i in pool:
            if not self.alive() or time.perf_counter()>self.started+self.budget_s*.53:break
            for t in insert_options(self.state,self.cat,i)[:2]:
                if self.commit([], [t], 'global_gap_insert'):break
        self.profile['gap_candidates']=len(pool);self.profile['gap_scan_s']=time.perf_counter()-tick

    def extend_all(self):
        tick=time.perf_counter()
        old_tasks=sorted(self.state.tasks.values(),key=lambda t:-(240.-t.duration)*t.weight)
        for old in old_tasks:
            if not self.alive() or time.perf_counter()>self.started+self.budget_s*.69:break
            if old.duration>=239.999999:continue
            self.state.remove(old.uid)
            try:
                opts=[]
                for i in self.cat.by_sat.get(old.sat,[]):
                    if self.cat.site[i]==old.station and self.cat.start[i]<=old.start and self.cat.end[i]>=old.end:
                        opts.extend(insert_options(self.state,self.cat,i,uid=old.uid))
            finally:self.state.add(old)
            for t in sorted(opts,key=lambda t:-t.score)[:2]:
                if t.score<=old.score+1e-8:break
                if self.commit([old],[t],'systematic_shift_extend'):break
        self.profile['extension_s']=time.perf_counter()-tick

    def job_intervals(self,t):
        """Local legal intervals including the task's current cached opportunity."""
        result=[]
        for i in self.cat.by_sat.get(t.sat,[]):
            if self.cat.site[i]!=t.station:continue
            if self.cat.start[i]<=t.start and self.cat.end[i]>=t.end:
                result.extend(self.state.free_intervals(t.station,t.sat,float(self.cat.start[i]),float(self.cat.end[i])))
        result=sorted(set(result),key=lambda ab:(not(ab[0]<=t.start and t.end<=ab[1]),-(ab[1]-ab[0])))
        return result[:2]

    def elastic_exchange(self):
        s=self.state;c=self.cat
        old=self.rng.choice(list(s.tasks.values()))
        site=old.station;ids=self.by_site[site]
        nearby=ids[(c.start[ids]<old.end+270.) & (c.end[ids]>old.start-270.) & (c.sat[ids]!=old.sat)]
        if not len(nearby):return False
        self.rng.shuffle(nearby)
        # Opportunity price values keeping the existing observation at minimum.
        nearby=sorted(nearby,key=lambda i:-float(c.weight[i]))[:32]
        best=[]
        removed=[old]
        if self.rng.random()<.3:
            line=s.stations[site];pos=next(k for k,(_,u) in enumerate(line) if u==old.uid)
            neighbors=[s.tasks[line[k][1]] for k in (pos-1,pos+1) if 0<=k<len(line)]
            if neighbors:
                other=self.rng.choice(neighbors)
                if abs(other.start-old.start)<600.:removed.append(other)
        for t in removed:s.remove(t.uid)
        try:
            old_intervals=[self.job_intervals(t) for t in removed]
            if any(not x for x in old_intervals):return False
            for i in nearby:
                if not self.alive():break
                new=c.task(int(i),float(c.start[i]),float(c.start[i])+120.,s.next_id)
                if new.sat in {t.sat for t in removed}:continue
                fresh=s.free_intervals(site,new.sat,float(c.start[i]),float(c.end[i]))
                for bounds in product(*old_intervals,fresh[:2]):
                    for packed in elastic_orders([*removed,new],bounds):
                        gain=sum(t.score for t in packed)-sum(t.score for t in removed)
                        if gain>1e-7:best.append((gain,self.rng.random(),packed))
        finally:
            for t in removed:s.add(t)
        for gain,_,added in sorted(best,key=lambda x:(-x[0],x[1]))[:8]:
            if not self.alive():break
            if self.commit(removed,added,'elastic_2job' if len(removed)==1 else 'elastic_3job'):return True
        return False

    def run(self):
        self.fill_gaps();self.extend_all()
        attempts={};cost={};gains={}
        methods={'elastic':self.elastic_exchange,'cross_site':self.exchange,'repack':self.repack,'extend':self.extension}
        while self.alive():
            op=self.rng.choices(list(methods),weights=[6.,2.,1.,1.])[0]
            tick=time.perf_counter();before=self.state.total
            methods[op]()
            attempts[op]=attempts.get(op,0)+1;cost[op]=cost.get(op,0.)+time.perf_counter()-tick
            gains[op]=gains.get(op,0.)+max(0.,self.state.total-before)
        frame=self.state.frame()
        assert abs(float((frame.priority_score*frame.duration_score).sum())-self.state.total)<1e-6
        return frame,dict(seed=self.seed,budget_s=self.budget_s,search_wall_s=time.perf_counter()-self.started,
            initial_score=self.initial,candidate_score=self.state.total,statistics=dict(self.stats),
            operator_attempts=attempts,operator_time_s=cost,operator_gain=gains,
            windows_scanned=self.window_scans,profile=self.profile,trace=self.trace)

def search(plan,windows,meta,*,budget_s,seed,physical):
    return Engine(plan,windows,budget_s=budget_s,seed=seed,physical=physical).run()
