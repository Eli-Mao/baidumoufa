"""Bounded exact selection on a finite interval pool, with explicit proof status.

This solves a discrete neighborhood, not the full continuous scheduling problem.
No duration/score quantization, external solver, or rule relaxation is used.
"""
from __future__ import annotations
import time
from . import config

def conflict(a,b):
    for same,pad in ((a.station==b.station,config.SWITCH_TIME_S),(a.sat==b.sat,config.REPEAT_COOLDOWN_S)):
        if same and a.end+pad>b.start+1e-9 and a.start<b.end+pad-1e-9:return True
    return False

def select_intervals(pool,initial,*,required_sats=(),outside_counts=None,deadline=None,max_nodes=12000):
    n=len(pool)
    if n>64:raise ValueError('Discrete neighborhood limited to 64 intervals')
    if len({t.uid for t in pool})!=n:raise ValueError('Candidate identities must be unique')
    outside_counts={} if outside_counts is None else outside_counts
    deadline=time.perf_counter()+1. if deadline is None else deadline
    weights=[t.score for t in pool];neighbors=[0]*n
    for i in range(n):
        for j in range(i):
            if conflict(pool[i],pool[j]):neighbors[i]|=1<<j;neighbors[j]|=1<<i
    sats=sorted({t.sat for t in pool});bits={sat:1<<i for i,sat in enumerate(sats)}
    satbits=[bits[t.sat] for t in pool]
    required=set(required_sats)
    if not required<=bits.keys():raise ValueError('Required target absent from candidate pool')
    required_mask=sum(bits[sat] for sat in required)
    coverage_eligible=sum(bits[sat] for sat in sats if outside_counts.get(sat,0)==0)
    initial=list(initial);selected=0;satmask=0
    for i in initial:
        if i<0 or i>=n or selected&(1<<i) or neighbors[i]&selected:raise ValueError('Invalid incumbent selection')
        selected|=1<<i;satmask|=satbits[i]
    if satmask&required_mask!=required_mask:raise ValueError('Incumbent loses mandatory coverage')
    best_score=sum(weights[i] for i in initial);best_mask=selected
    best_cov=(satmask&coverage_eligible).bit_count();nodes=0;stopped=False;bound_cache={}
    def indices(mask):
        while mask:
            bit=mask&-mask;yield bit.bit_length()-1;mask^=bit
    def upper(mask):
        # A partition into conflict cliques gives a valid weighted upper bound.
        if mask in bound_cache:return bound_cache[mask]
        original=mask;bound=0.
        while mask:
            v=max(indices(mask),key=lambda i:(neighbors[i]&mask).bit_count())
            clique=1<<v;maximum=weights[v];candidates=mask&neighbors[v]
            while candidates:
                u=max(indices(candidates),key=lambda i:weights[i])
                clique|=1<<u;maximum=max(maximum,weights[u]);candidates&=neighbors[u]
            bound+=maximum;mask&=~clique
        if len(bound_cache)<8192:bound_cache[original]=bound
        return bound
    def visit(available,chosen,value,covered):
        nonlocal best_score,best_mask,best_cov,nodes,stopped
        nodes+=1
        if nodes>max_nodes or (nodes%32==0 and time.perf_counter()>=deadline):stopped=True;return
        missing=required_mask&~covered
        if missing:
            possible=0
            for i in indices(available):possible|=satbits[i]
            if missing&~possible:return
        if not missing:
            cov=(covered&coverage_eligible).bit_count()
            if value>best_score+1e-9 or (abs(value-best_score)<=1e-9 and cov>best_cov):
                best_score=value;best_mask=chosen;best_cov=cov
        if not available or value+upper(available)<best_score-1e-9:return
        v=max(indices(available),key=lambda i:(weights[i]*(1+(neighbors[i]&available).bit_count()),weights[i]))
        bit=1<<v
        visit(available&~(neighbors[v]|bit),chosen|bit,value+weights[v],covered|satbits[v])
        if not stopped:visit(available&~bit,chosen,value,covered)
    root_bound=upper((1<<n)-1) if n else 0.
    if time.perf_counter()<deadline:visit((1<<n)-1,0,0.,0)
    else:stopped=True
    return [pool[i] for i in indices(best_mask)],dict(nodes=nodes,pool_intervals=n,score=best_score,
        coverage_from_pool=best_cov,optimal_for_finite_pool=not stopped,upper_bound=best_score if not stopped else root_bound,
        warning='Finite generated interval pool only; time/node cutoff returns a feasible incumbent, not an optimality proof')
