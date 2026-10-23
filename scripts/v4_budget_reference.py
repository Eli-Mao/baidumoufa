"""Frozen V4 proposal/acceptance logic with an explicit wall-clock search cap."""
import random,time
import pandas as pd
from satplan import rules,scheduler,config

def search(plan,windows,meta,*,budget_s,seed):
    t0=time.perf_counter();deadline=t0+budget_s;best=plan.copy(deep=True).reset_index(drop=True)
    rng=random.Random(seed);candidates=scheduler._prepare_candidates(windows)
    best_value=rules.objective(best,windows,meta,coverage_weight=.25);iterations=accepted=0;reserve=1.5
    while time.perf_counter()+reserve<deadline:
        tick=time.perf_counter();iterations+=1;proposal=best.copy(deep=True)
        if rng.random()<.25:
            covered=set(proposal.sat_id.astype(int));pool=candidates[~candidates.sat_id.isin(covered)]
            if pool.empty:continue
            proposal=pd.concat([proposal,pd.DataFrame([scheduler._task_from_candidate(pool.iloc[rng.randrange(len(pool))])])],ignore_index=True)
        else:
            idx=rng.randrange(len(proposal));task=proposal.iloc[idx].copy();matches=candidates[candidates.sat_id.astype(int)==int(task.sat_id)]
            if matches.empty:continue
            window=matches.iloc[rng.randrange(len(matches))];duration=float(task.dur_s)
            if rng.random()<.5:duration=min(config.MAX_DUR_S,max(config.MIN_DUR_S,duration+rng.choice((-30.,30.))))
            span=float(window.t_end_s)-float(window.t_start_s)-duration
            if span<0:continue
            start=float(window.t_start_s)+rng.random()*span
            task['station_id']=int(window.station_id);task['t_start_s'],task['t_end_s']=start,start+duration;task['dur_s']=duration;task['duration_score']=rules.duration_score(duration);proposal.iloc[idx]=task
        proposal=scheduler._finish_plan(proposal.to_dict(orient='records'))
        if rules.plan_is_feasible(proposal,windows):
            value=rules.objective(proposal,windows,meta,coverage_weight=.25)
            if value>best_value+1e-9:best,best_value=proposal,value;accepted+=1
        reserve=max(reserve,time.perf_counter()-tick+.1)
    return best,{'seed':seed,'budget_s':budget_s,'search_wall_s':time.perf_counter()-t0,'iterations':iterations,'accepted':accepted,'objective_coverage_weight':.25,'logic':'V4 frozen local_search proposal and acceptance; clock cap only'}
