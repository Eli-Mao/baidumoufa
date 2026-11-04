"""V7 continuation: cost-aware ALNS, anchor tabu and finite exact neighborhoods."""
from collections import Counter,deque
from itertools import product
import time
from math import sqrt
from .v7 import Engine as V7Engine,elastic_orders
from .v5 import insert_options
from .v7_exact import select_intervals

class Engine(V7Engine):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.epoch=0;self.failed_anchors=set();self.exact_regions=set();self.diagnostics=Counter()
    def commit(self,removed,added,operator):
        ok=super().commit(removed,added,operator)
        if ok:self.epoch+=1
        return ok
    def elastic_exchange(self):
        s=self.state;c=self.cat
        candidates=list(s.tasks.values())
        old=self.rng.choices(candidates,weights=[max(1.,t.duration-110.)/t.weight for t in candidates])[0]
        signature=(old.uid,self.epoch)
        if signature in self.failed_anchors:
            self.diagnostics['duplicate_anchor_skips']+=1;return False
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
            if self.commit(removed,added,'adaptive_elastic_2job' if len(removed)==1 else 'adaptive_elastic_3job'):return True
        if len(self.failed_anchors)>8192:self.failed_anchors.clear()
        self.failed_anchors.add(signature)
        return False

    def exact_neighborhood(self):
        s=self.state;c=self.cat;site=self.rng.choice(list(s.stations));line=s.stations[site]
        if not line:return False
        pos=self.rng.randrange(len(line));removed=[s.tasks[u] for _,u in line[pos:pos+self.rng.choice([4,6,8])]]
        signature=(site,tuple(t.uid for t in removed),self.epoch)
        if signature in self.exact_regions:self.diagnostics['duplicate_exact_skips']+=1;return False
        if len(self.exact_regions)>4096:self.exact_regions.clear()
        self.exact_regions.add(signature)
        lo=max(0.,removed[0].start-120.);hi=min(518400.,removed[-1].end+120.)
        idx=self.by_site[site];indices=idx[(c.start[idx]<hi)&(c.end[idx]>lo)]
        self.rng.shuffle(indices);indices=sorted(indices,key=lambda i:-c.weight[i])[:240]
        pool=list(removed);seen={(t.sat,t.start,t.end) for t in pool}
        for t in removed:s.remove(t.uid)
        required={t.sat for t in removed if t.priority=='high' and s.counts[t.sat]==0}
        result=None;info=None
        try:
            for i in indices:
                if not self.alive() or len(pool)>=56:break
                for a,b in s.free_intervals(site,int(c.sat[i]),max(lo,float(c.start[i])),min(hi,float(c.end[i]))):
                    for start,end in [(a,min(b,a+240.)),(max(a,b-240.),b),(a,a+120.),(b-120.,b)]:
                        key=(int(c.sat[i]),start,end)
                        if key in seen:continue
                        seen.add(key);task=c.task(int(i),start,end,s.next_id+len(pool))
                        if s.fits(task) and self.alive() and self.physical(task):pool.append(task)
                        if len(pool)>=56:break
                    if len(pool)>=56:break
            if self.alive():
                result,info=select_intervals(pool,range(len(removed)),required_sats=required,outside_counts=s.counts,
                    deadline=min(self.deadline-.02,time.perf_counter()+.3),max_nodes=12000)
        finally:
            for t in removed:s.add(t)
        if info:
            self.diagnostics['exact_calls']+=1;self.diagnostics['exact_nodes']+=info['nodes']
            self.diagnostics['exact_proved_finite_optimal']+=int(info['optimal_for_finite_pool'])
            self.diagnostics['exact_cutoffs']+=int(not info['optimal_for_finite_pool'])
        return bool(result) and self.commit(removed,result,'finite_exact_replace')

    def run(self):
        self.fill_gaps();self.extend_all()
        methods={'elastic':self.elastic_exchange,'cross_site':self.exchange,'repack':self.repack,'extend':self.extension,'exact':self.exact_neighborhood}
        history={k:deque(maxlen=25) for k in methods};weights=dict(elastic=6.,cross_site=2.,repack=1.,extend=.5,exact=1.)
        attempts=Counter();cost=Counter();gains=Counter();last_gain=time.perf_counter();restarts=0;last_restart=last_gain
        while self.alive():
            op=self.rng.choices(list(methods),weights=[weights[k] for k in methods])[0]
            tick=time.perf_counter();before=self.state.total;calls=self.physical.calls;hits=self.physical.hits
            methods[op]();elapsed=time.perf_counter()-tick;gain=max(0.,self.state.total-before)
            if gain<1e-7:gain=0.
            attempts[op]+=1;cost[op]+=elapsed;gains[op]+=gain
            history[op].append((gain,max(elapsed,.003)))
            rate=sum(g for g,t in history[op])/max(.02,sum(t for g,t in history[op]))
            weights[op]=.2+min(30.,rate**.75)
            self.diagnostics['oracle_calls_'+op]+=self.physical.calls-calls
            self.diagnostics['oracle_cache_hits_'+op]+=self.physical.hits-hits
            if gain:last_gain=time.perf_counter()
            if time.perf_counter()-max(last_gain,last_restart)>8.:
                # Restart neighborhood sampling from the incumbent; no worsening
                # plan is accepted and this is not an independent cold restart.
                self.failed_anchors.clear();self.exact_regions.clear();self.rng.shuffle(self.order);self.ptr=0
                for k in history:history[k].clear();weights[k]=1.
                last_restart=time.perf_counter();restarts+=1
        frame=self.state.frame()
        assert abs(float((frame.priority_score*frame.duration_score).sum())-self.state.total)<1e-6
        return frame,dict(seed=self.seed,budget_s=self.budget_s,search_wall_s=time.perf_counter()-self.started,
            initial_score=self.initial,candidate_score=self.state.total,statistics=dict(self.stats),operator_attempts=dict(attempts),
            operator_time_s=dict(cost),operator_gain=dict(gains),diagnostics=dict(self.diagnostics),sampling_restarts=restarts,
            final_operator_weights=weights,windows_scanned=self.window_scans,profile=self.profile,trace=self.trace)

