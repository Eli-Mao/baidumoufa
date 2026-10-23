"""Budgeted adaptive ruin/recreate and ejection chains on frozen real windows.

Only incremental indexes are shared with V5. The frozen scoring, constraints,
baseline search and physical predicate remain unchanged. Every transaction is
rolled back before acceptance; final independent acceptance remains mandatory.
"""
from __future__ import annotations
from bisect import bisect_left
from collections import Counter
import random,time
import numpy as np
from . import config
from dataclasses import replace
from .v5 import State,Catalog as V5Catalog,insert_options,_protect_high

class Catalog(V5Catalog):
    def task(self,i,start,end,uid):
        t=super().task(i,start,end,uid)
        # Preserve exact legal requested bounds through floating point addition;
        # the frozen consistency check still requires <=1e-6 agreement.
        d=t.end-t.start
        for bound in (120.,240.):
            if abs(d-bound)<1e-9:return replace(t,declared_duration=bound)
        return t

class Engine:
    def __init__(self,plan,windows,*,budget_s,seed,physical):
        self.started=time.perf_counter();self.deadline=self.started+budget_s
        self.rng=random.Random(seed);self.state=State(plan);self.cat=Catalog(windows)
        self.physical=physical;self.trace=[];self.stats=Counter();self.seed=seed
        self.initial=self.state.total;self.initial_coverage=len(self.state.tasks)
        self.order=np.random.default_rng(seed).permutation(len(windows));self.ptr=0
        self.by_site={int(s):np.asarray(ids,dtype=int) for s,ids in windows.groupby('station_id',sort=False).indices.items()}
        self.reward={op:1. for op in ['insert','exchange','repack','extend']}
    def alive(self):return time.perf_counter()<self.deadline-.015
    def commit(self,removed,added,operator):
        s=self.state
        gain=sum(t.score for t in added)-sum(t.score for t in removed)
        delta=Counter(t.sat for t in added);delta.subtract(t.sat for t in removed)
        coverage=sum(int(s.counts[k]+v>0)-int(s.counts[k]>0) for k,v in delta.items())
        if gain<-1e-8 or (gain<1e-8 and coverage<=0):return False
        if not _protect_high(s,removed,added) or len({t.uid for t in added})!=len(added):return False
        for t in added:
            if not self.alive() or not self.physical(t):return False
        for t in removed:s.remove(t.uid)
        inserted=[];ok=False
        try:
            for t in added:
                if not s.fits(t):return False
                s.add(t);inserted.append(t)
            ok=True
        finally:
            if not ok:
                for t in reversed(inserted):s.remove(t.uid)
                for t in removed:s.add(t)
        self.trace.append({'elapsed_s':time.perf_counter()-self.started,'operator':operator,'delta_score':gain,'total_score':s.total,'covered':sum(v>0 for v in s.counts.values()),'coverage_change':coverage,'removed':[{'uid':t.uid,'sat':t.sat,'station':t.station,'start':t.start,'end':t.end} for t in removed],'added':[{'uid':t.uid,'sat':t.sat,'station':t.station,'start':t.start,'end':t.end} for t in added]})
        self.stats[operator]+=1
        return True
    def next_window(self):
        if self.ptr<len(self.order):i=int(self.order[self.ptr]);self.ptr+=1;return i
        return self.rng.randrange(len(self.order))
    def insertion(self):
        # Batch a random sample, rank exact available score rather than only
        # uncovered priority. Repeated high-value targets remain eligible.
        options=[];s=self.state
        for _ in range(48):
            if not self.alive():break
            i=self.next_window();opts=insert_options(s,self.cat,i)
            if opts:options.append((opts[0].score+.15*(s.counts[opts[0].sat]==0),i,opts))
        for _,i,opts in sorted(options,key=lambda x:-x[0]):
            for t in opts[:2]:
                if self.commit([], [t], 'free_insert'):return True
            if not self.alive():break
        return False
    def extension(self):
        short=[t for t in self.state.tasks.values() if t.duration<239.999]
        if not short:return False
        self.rng.shuffle(short)
        for old in short[:12]:
            if not self.alive():return False
            self.state.remove(old.uid);opts=[]
            try:
                for i in self.cat.by_sat.get(old.sat,[]):
                    if self.cat.site[i]==old.station and self.cat.start[i]<=old.start and self.cat.end[i]>=old.end:
                        opts.extend(insert_options(self.state,self.cat,i,uid=old.uid))
            finally:self.state.add(old)
            for new in sorted(opts,key=lambda t:-t.score)[:3]:
                if self.commit([old],[new],'shift_extend'):return True
        return False
    def exchange(self):
        s=self.state;c=self.cat
        for _ in range(16):
            if not self.alive():return False
            i=self.next_window();a=float(c.start[i]);b=float(c.end[i]);site=int(c.site[i])
            line=s.stations[site];pos=max(0,bisect_left(line,(a,-1))-1)
            anchors=[a,max(a,b-240.)]
            for _,uid in line[pos:pos+6]:
                old=s.tasks[uid]
                if old.start>b:break
                anchors.extend([max(a,old.start),max(a,old.end+30.),max(a,old.start-150.)])
            self.rng.shuffle(anchors)
            for start in anchors[:5]:
                for dur in [240.,120.]:
                    end=min(b,start+dur)
                    if end-start<120.:continue
                    new=c.task(i,start,end,s.next_id);ids=s.conflicts(new)
                    if not ids or len(ids)>4:continue
                    removed=[s.tasks[u] for u in sorted(ids)]
                    if self.commit(removed,[new],'direct_replace'):return True
                    if not self.alive():return False
                    # Eject up to four conflicts and relocate them across sites,
                    # allowing shorter legal durations and shifted observations.
                    for old in removed:s.remove(old.uid)
                    added=[]
                    try:
                        if not s.fits(new) or not self.physical(new):continue
                        s.add(new);added.append(new)
                        for old in sorted(removed,key=lambda t:(t.priority!='high',-t.score)):
                            indices=list(c.by_sat.get(old.sat,[]));self.rng.shuffle(indices)
                            # Prefer the original local opportunity, then other sites.
                            indices.sort(key=lambda j:0 if c.site[j]==old.station and c.start[j]<=old.start<=c.end[j] else 1)
                            options=[]
                            for j in indices[:24]:
                                options.extend(insert_options(s,c,j,uid=old.uid))
                            options.sort(key=lambda t:-t.score)
                            for t in options[:8]:
                                if not self.alive():break
                                if self.physical(t):s.add(t);added.append(t);break
                    finally:
                        for t in reversed(added):s.remove(t.uid)
                        for t in removed:s.add(t)
                    if added and self.commit(removed,added,'ejection_chain'):return True
        return False
    def repack(self):
        s=self.state;c=self.cat;site=self.rng.choice(list(s.stations));line=s.stations[site]
        if not line:return False
        pos=self.rng.randrange(len(line));width=self.rng.choice([6,10,16,24])
        removed=[s.tasks[u] for _,u in line[pos:pos+width]]
        lo=max(0.,removed[0].start-300.);hi=min(518400.,removed[-1].end+300.)
        sites=[site]
        if self.rng.random()<.35:
            other=self.rng.choice([k for k in s.stations if k!=site]);sites.append(other)
            removed.extend(s.tasks[u] for st,u in s.stations[other] if lo<=st<=hi)
        if len(removed)>60:return False
        pool=[]
        for k in sites:
            idx=self.by_site[k];pool.extend(idx[(c.start[idx]<hi)&(c.end[idx]>lo)].tolist())
        # Include remote opportunities for displaced targets; this allows a
        # coordinated reassignment rather than only filling the emptied station.
        for old in removed:
            indices=list(c.by_sat.get(old.sat,[]));self.rng.shuffle(indices);pool.extend(indices[:12])
        pool=list(set(pool));self.rng.shuffle(pool)
        density=self.rng.random()<.55
        pool.sort(key=lambda j:-(float(c.weight[j])*(1.+.12*(s.counts[int(c.sat[j])]==0))))
        for old in removed:s.remove(old.uid)
        added=[]
        try:
            for i in pool[:500]:
                if not self.alive():break
                opts=insert_options(s,c,i)
                if not opts:continue
                t=opts[0]
                if density:
                    # Minimum-duration packing can outperform one full-duration
                    # task. Later iterations can extend the resulting tasks.
                    t=c.task(i,t.start,t.start+120.,s.next_id)
                if self.physical(t):s.add(t);added.append(t)
        finally:
            for t in reversed(added):s.remove(t.uid)
            for old in removed:s.add(old)
        if added:return self.commit(removed,added,'large_repack')
        return False
    def run(self):
        methods={'insert':self.insertion,'exchange':self.exchange,'repack':self.repack,'extend':self.extension}
        attempts=Counter();cost=Counter();gains=Counter()
        while self.alive():
            op=self.rng.choices(list(methods),weights=[self.reward[k] for k in methods])[0]
            tick=time.perf_counter();before=self.state.total
            methods[op]();elapsed=time.perf_counter()-tick;gain=max(0.,self.state.total-before)
            attempts[op]+=1;cost[op]+=elapsed;gains[op]+=gain
            # Smoothed reward with a nonzero exploration floor.
            self.reward[op]=.8*self.reward[op]+.2*(.2+min(15.,gain/max(elapsed,.02)))
        frame=self.state.frame()
        assert abs(float((frame.priority_score*frame.duration_score).sum())-self.state.total)<1e-6
        return frame,{'seed':self.seed,'search_wall_s':time.perf_counter()-self.started,'initial_score':self.initial,'candidate_score':self.state.total,'statistics':dict(self.stats),'operator_attempts':dict(attempts),'operator_time_s':dict(cost),'operator_gain':dict(gains),'trace':self.trace}

def search(plan,windows,meta,*,budget_s,seed,physical):
    return Engine(plan,windows,budget_s=budget_s,seed=seed,physical=physical).run()
