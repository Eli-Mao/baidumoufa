"""V5: incremental, score-monotone insertion, displacement and local repacking.

V4 and the frozen scoring/constraint modules are intentionally unchanged.
Search states are provisional until independent whole-plan acceptance.
"""
from __future__ import annotations
from bisect import bisect_left, insort
from dataclasses import dataclass, replace
import random, time
from collections import Counter
import numpy as np
import pandas as pd
from . import config, rules, scheduler

@dataclass(frozen=True)
class Task:
    uid: int
    station: int
    sat: int
    priority: str
    weight: int
    start: float
    end: float
    declared_duration: float | None = None
    @property
    def duration(self): return self.end-self.start if self.declared_duration is None else self.declared_duration
    @property
    def score(self): return rules.task_score(self.weight, self.duration)

class Catalog:
    def __init__(self, windows):
        self.windows=windows
        self.site=windows.station_id.to_numpy(dtype=int)
        self.sat=windows.sat_id.to_numpy(dtype=int)
        self.start=windows.t_start_s.to_numpy(dtype=float)
        self.end=windows.t_end_s.to_numpy(dtype=float)
        self.weight=windows.priority_score.to_numpy(dtype=int)
        self.priority=windows.priority.to_numpy()
        self.by_sat={int(sid):np.asarray(idx,dtype=int) for sid,idx in windows.groupby('sat_id',sort=False).indices.items()}
    def task(self,i,start,end,uid):
        return Task(uid,int(self.site[i]),int(self.sat[i]),str(self.priority[i]),int(self.weight[i]),float(start),float(end))

class State:
    def __init__(self,plan):
        self.tasks={};self.stations={int(s):[] for s in config.STATION_IDS};self.sats={};self.counts=Counter();self.total=0.;self.next_id=1
        for row in plan.itertuples(index=False):
            self.add(Task(int(row.task_id),int(row.station_id),int(row.sat_id),str(row.priority),int(row.priority_score),float(row.t_start_s),float(row.t_end_s),float(row.dur_s)))
    def add(self,t):
        assert t.uid not in self.tasks
        self.tasks[t.uid]=t;insort(self.stations.setdefault(t.station,[]),(t.start,t.uid));insort(self.sats.setdefault(t.sat,[]),(t.start,t.uid))
        self.counts[t.sat]+=1;self.total+=t.score;self.next_id=max(self.next_id,t.uid+1)
    def remove(self,uid):
        t=self.tasks.pop(uid)
        for timeline in (self.stations[t.station],self.sats[t.sat]):timeline.pop(bisect_left(timeline,(t.start,t.uid)))
        self.counts[t.sat]-=1;self.total-=t.score;return t
    def conflicts(self,t):
        found=set()
        for line,pad in [(self.stations.get(t.station,[]),config.SWITCH_TIME_S),(self.sats.get(t.sat,[]),config.REPEAT_COOLDOWN_S)]:
            a=max(0,bisect_left(line,(t.start-pad,-1))-1)
            b=bisect_left(line,(t.end+pad-1e-9,-1))
            for _,uid in line[a:b]:
                old=self.tasks[uid]
                if old.end+pad>t.start+1e-9 and old.start<t.end+pad-1e-9:found.add(uid)
        return found
    def free_intervals(self,site,sat,start,end):
        blocked=[]
        for line,pad in [(self.stations.get(site,[]),config.SWITCH_TIME_S),(self.sats.get(sat,[]),config.REPEAT_COOLDOWN_S)]:
            a=max(0,bisect_left(line,(start-pad,-1))-1)
            b=bisect_left(line,(end+pad,-1))
            for _,uid in line[a:b]:
                old=self.tasks[uid]
                lo,hi=old.start-pad,old.end+pad
                if hi>start and lo<end:blocked.append((lo,hi))
        cursor=start;free=[]
        for lo,hi in sorted(blocked):
            if lo>cursor:free.append((cursor,min(lo,end)))
            cursor=max(cursor,hi)
            if cursor>=end:break
        if cursor<end:free.append((cursor,end))
        return [(a,b) for a,b in free if b-a>=config.MIN_DUR_S]
    def fits(self,t):
        return (0<=t.start<t.end<=rules.plan_period_s() and config.MIN_DUR_S<=t.duration<=config.MAX_DUR_S and abs(t.duration-(t.end-t.start))<=1e-6 and not self.conflicts(t))
    def frame(self):
        rows=[{'station_id':t.station,'sat_id':t.sat,'priority':t.priority,'priority_score':t.weight,'t_start_s':t.start,'t_end_s':t.end,'dur_s':t.duration,'duration_score':rules.duration_score(t.duration)} for t in self.tasks.values()]
        return scheduler._finish_plan(rows)

def insert_options(state,catalog,i,uid=None):
    options=[]
    for a,b in state.free_intervals(int(catalog.site[i]),int(catalog.sat[i]),float(catalog.start[i]),float(catalog.end[i])):
        end=min(b,a+config.MAX_DUR_S)
        if end-a>=config.MIN_DUR_S:options.append(catalog.task(i,a,end,state.next_id if uid is None else uid))
        start=max(a,b-config.MAX_DUR_S)
        if b-start>=config.MIN_DUR_S and abs(start-a)>.001:options.append(catalog.task(i,start,b,state.next_id if uid is None else uid))
    return sorted(options,key=lambda t:(-t.score,t.start))

def _protect_high(state,removed,added):
    delta=Counter(t.sat for t in added);delta.subtract(t.sat for t in removed)
    priority={t.sat:t.priority for t in [*removed,*added]}
    return all(not (priority[sat]=='high' and state.counts[sat]>0 and state.counts[sat]+change<=0) for sat,change in delta.items())

def search(plan,windows,meta,*,budget_s,seed,physical=None):
    start=time.perf_counter();deadline=start+budget_s;rng=random.Random(seed)
    state=State(plan);catalog=Catalog(windows);trace=[];stats=Counter();initial=state.total
    if physical is None: raise ValueError('V5 requires an exact-interval physical predicate')
    order=list(range(len(windows)));rng.shuffle(order)
    # First prioritize missing high-priority targets, then randomized high-density
    # opportunities. The random tie order gives independent seeded runs.
    order.sort(key=lambda i:(state.counts[int(catalog.sat[i])]>0,-int(catalog.weight[i])))
    pointer=0
    def accept(removed,added,operator):
        if not _protect_high(state,removed,added):return False
        gain=sum(t.score for t in added)-sum(t.score for t in removed)
        counts=Counter(t.sat for t in added);counts.subtract(t.sat for t in removed)
        coverage=sum((state.counts[s]+v>0)-(state.counts[s]>0) for s,v in counts.items())
        if gain<-1e-8 or (gain<1e-8 and coverage<=0):return False
        if time.perf_counter()>=deadline:return False
        for t in added:
            if not physical(t):stats['physical_rejected']+=1;return False
        for t in removed:state.remove(t.uid)
        inserted=[]
        try:
            for t in added:
                if not state.fits(t):return False
                state.add(t);inserted.append(t)
            trace.append({'step':len(trace)+1,'operator':operator,'delta_score':gain,'total_score':state.total,'coverage_change':coverage,'removed_ids':[t.uid for t in removed],'added':[{'station':t.station,'sat':t.sat,'start':t.start,'end':t.end} for t in added],'elapsed_s':time.perf_counter()-start})
            stats[operator]+=1
            return True
        finally:
            # A failed partial transaction must leave the old state intact.
            if len(inserted)!=len(added):
                for t in reversed(inserted):state.remove(t.uid)
                for t in removed:state.add(t)
    def relocate_conflicts(new,ids):
        removed=[state.tasks[u] for u in sorted(ids)]
        if len(removed)>2:return False
        for old in removed:state.remove(old.uid)
        added=[];success=False
        try:
            if not state.fits(new):return False
            state.add(new);added.append(new)
            for old in sorted(removed,key=lambda t:-t.weight):
                indices=list(catalog.by_sat.get(old.sat,np.array([],dtype=int)));rng.shuffle(indices)
                found=None
                for wi in indices[:20]:
                    if time.perf_counter()>=deadline:return False
                    for option in insert_options(state,catalog,wi,uid=old.uid):
                        if option.score+1e-9<old.score*.55:continue
                        if physical(option):found=option;break
                    if found:break
                if found is None:return False
                state.add(found);added.append(found)
            success=True
        finally:
            for t in reversed(added):state.remove(t.uid)
            for old in removed:state.add(old)
        if success:return accept(removed,added,'cross_station_displacement')
        return False
    while time.perf_counter()<deadline-.025:
        stats['iterations']+=1
        # A small neighborhood jointly relocates or shortens blocking tasks.
        if pointer<len(order):i=order[pointer];pointer+=1
        else:i=rng.randrange(len(windows))
        options=insert_options(state,catalog,i)
        if options:
            best=options[0] if rng.random()<.8 else rng.choice(options[:min(3,len(options))])
            if accept([], [best], 'free_insert'):continue
        # Test bounded conflict replacements at real window and occupied-slot edges.
        if rng.random()<.55:
            a,b=float(catalog.start[i]),float(catalog.end[i]);site=int(catalog.site[i])
            anchors=[a,max(a,b-config.MAX_DUR_S)]
            line=state.stations.get(site,[]);lo=max(0,bisect_left(line,(a-240,-1))-1);hi=bisect_left(line,(b+240,-1))
            for _,uid in line[lo:hi][:12]:
                old=state.tasks[uid];anchors.extend([max(a,old.start),max(a,old.end+config.SWITCH_TIME_S),max(a,old.start-config.SWITCH_TIME_S-config.MIN_DUR_S)])
            rng.shuffle(anchors)
            for pos in anchors[:8]:
                if time.perf_counter()>=deadline:break
                for duration in (config.MAX_DUR_S,config.MIN_DUR_S):
                    end=min(b,pos+duration)
                    if end-pos<config.MIN_DUR_S:continue
                    new=catalog.task(i,pos,end,state.next_id);conflicts=state.conflicts(new)
                    if not conflicts or len(conflicts)>3:continue
                    removed=[state.tasks[u] for u in sorted(conflicts)]
                    if accept(removed,[new],'conflict_replace'):break
                    if len(conflicts)<=2 and rng.random()<.12 and physical(new) and relocate_conflicts(new,conflicts):break
                else:continue
                break
        if stats['iterations']%30==0 and state.tasks and time.perf_counter()<deadline-.03:
            old=state.tasks[rng.choice(list(state.tasks))]
            # Extend a short observation or shift it inside the same target's windows.
            if old.end-old.start<config.MAX_DUR_S-.001:
                state.remove(old.uid)
                try:
                    candidates=[]
                    for wi in catalog.by_sat.get(old.sat,np.array([],dtype=int)):
                        if int(catalog.site[wi])==old.station and catalog.start[wi]<=old.start and catalog.end[wi]>=old.end:
                            candidates.extend(insert_options(state,catalog,int(wi),uid=old.uid))
                finally:state.add(old)
                for new in candidates[:3]:
                    if accept([old],[new],'duration_extend'):break
        if stats['iterations']%100==0 and time.perf_counter()<deadline-.05:
            # Bounded large-neighborhood destruction: remove up to three adjacent
            # low-yield tasks, repack their real opportunities plus uncovered ones.
            site=rng.choice(list(state.stations));line=state.stations[site]
            if not line:continue
            pos=rng.randrange(len(line));removed=[state.tasks[u] for _,u in line[pos:pos+rng.choice((2,3))]]
            for old in removed:state.remove(old.uid)
            added=[]
            try:
                pool=[]
                for old in removed:pool.extend(catalog.by_sat.get(old.sat,np.array([],dtype=int)).tolist())
                pool.extend(order[pointer:min(len(order),pointer+30)])
                rng.shuffle(pool)
                pool.sort(key=lambda wi:-int(catalog.weight[wi]))
                for wi in pool[:60]:
                    if time.perf_counter()>=deadline:break
                    opts=insert_options(state,catalog,wi)
                    if opts and physical(opts[0]):state.add(opts[0]);added.append(opts[0])
            finally:
                for t in reversed(added):state.remove(t.uid)
                for old in removed:state.add(old)
            if added:accept(removed,added,'local_repack')
    output=state.frame()
    assert abs(float((output.priority_score*output.duration_score).sum())-state.total)<1e-6
    return output,{'seed':seed,'budget_s':budget_s,'search_wall_s':time.perf_counter()-start,'initial_score':initial,'candidate_score':state.total,'statistics':dict(stats),'trace':trace}
