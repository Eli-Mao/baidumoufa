"""Concrete fixed-plan opportunity/blocker analysis on the existing real cache."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd,numpy as np
from satplan import rules,config
from satplan.v5 import State,Catalog,insert_options
from satplan.v5_physics import PhysicalOracle
BASE=Path('D:/SatelliteProject_GitHub/data/out/real_aug2026_10000')
OUT=ROOT/'data/out/v5_analysis';OUT.mkdir(parents=True,exist_ok=True)

def run():
    p=pd.read_csv(BASE/'final_plan.csv');w=pd.read_csv(BASE/'windows.csv');meta=pd.read_csv(BASE/'selected_targets.csv')
    state=State(p);cat=Catalog(w);oracle=PhysicalOracle();rows=[];replacements=[];totals={'windows_with_free_120s_slot':0,'uncovered_windows_with_free_120s_slot':0};t=time.perf_counter()
    missing=meta[~meta.sat_id.isin(p.sat_id)].sort_values(['priority_score','sat_id'],ascending=[False,True])
    for n,r in enumerate(missing.itertuples(index=False),1):
        indexes=cat.by_sat.get(int(r.sat_id),[]);free_count=0;best_span=0.;direct=None;invalid=0;minimum_loss=float('inf');best_replacement=None
        for i in indexes:
            intervals=state.free_intervals(int(cat.site[i]),int(r.sat_id),float(cat.start[i]),float(cat.end[i]))
            if intervals:
                free_count+=1;best_span=max(best_span,max(b-a for a,b in intervals))
                if direct is None:
                    for candidate in insert_options(state,cat,i):
                        if oracle(candidate):direct=candidate;break
                        invalid+=1
            if r.priority=='high' or best_replacement is None:
                for a in [float(cat.start[i]),max(float(cat.start[i]),float(cat.end[i])-240.)]:
                    candidate=cat.task(i,a,min(float(cat.end[i]),a+240.),state.next_id)
                    blockers=state.conflicts(candidate);loss=sum(state.tasks[u].score for u in blockers)
                    if loss<minimum_loss:minimum_loss=loss
                    gain=candidate.score-loss
                    if gain>1e-8 and len(blockers)<=3 and (best_replacement is None or gain>best_replacement['gain']):
                        removed=[state.tasks[u] for u in blockers]
                        for old in removed:state.remove(old.uid)
                        fits=state.fits(candidate)
                        for old in removed:state.add(old)
                        if fits and oracle(candidate):
                            best_replacement={'sat_id':int(r.sat_id),'priority':r.priority,'station_id':candidate.station,'start':candidate.start,'end':candidate.end,'gain':gain,'blocked_score':loss,'blocking_task_ids':','.join(str(x) for x in sorted(blockers)),'blocking_priorities':','.join(state.tasks[x].priority for x in sorted(blockers))}
        reason='direct_physical_insertion_available' if direct else ('coarse_free_slots_failed_physics' if free_count else ('all_windows_blocked_by_station_tasks' if len(indexes) else 'no_candidate_windows'))
        row={'sat_id':int(r.sat_id),'priority':r.priority,'window_count':len(indexes),'stations':len(set(cat.site[indexes])),'free_windows':free_count,'max_free_span_s':best_span,'direct_physical_insert':direct is not None,'reason':reason,'failed_physical_candidates':invalid,'min_anchor_blocking_score':minimum_loss if np.isfinite(minimum_loss) else None,'best_anchor_replacement_gain':best_replacement['gain'] if best_replacement else 0.}
        if direct:row.update(example_station=direct.station,example_start=direct.start,example_end=direct.end,example_gain=direct.score)
        if best_replacement:replacements.append(best_replacement)
        rows.append(row)
        if n%500==0:print('[analysis]',n,'/',len(missing),flush=True)
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'uncovered_opportunities.csv',index=False)
    frame[frame.priority=='high'].to_csv(OUT/'uncovered_high_30.csv',index=False)
    pd.DataFrame(replacements).to_csv(OUT/'replacement_opportunities.csv',index=False)
    # Count all individually insertable windows, including repeat observations.
    for i in range(len(w)):
        if state.free_intervals(int(cat.site[i]),int(cat.sat[i]),float(cat.start[i]),float(cat.end[i])):
            totals['windows_with_free_120s_slot']+=1
            if not state.counts[int(cat.sat[i])]:totals['uncovered_windows_with_free_120s_slot']+=1
    sites=[]
    for site,g in w.groupby('station_id'):
        union=0.;lo=hi=None
        for a,b in g[['t_start_s','t_end_s']].sort_values('t_start_s').itertuples(index=False,name=None):
            if lo is None:lo,hi=a,b
            elif a<=hi:hi=max(hi,b)
            else:union+=hi-lo;lo,hi=a,b
        if lo is not None:union+=hi-lo
        tasks=p[p.station_id==site];obs=float(tasks.dur_s.sum());switch=30*max(0,len(tasks)-1)
        sites.append({'station_id':int(site),'tasks':len(tasks),'targets':tasks.sat_id.nunique(),'score':float((tasks.priority_score*tasks.duration_score).sum()),'observation_s':obs,'switch_overhead_s':switch,'calendar_utilization':(obs+switch)/518400,'candidate_union_s':union,'observation_fraction_of_candidate_union':obs/union})
    pd.DataFrame(sites).to_csv(OUT/'station_utilization.csv',index=False)
    summary={'uncovered_targets':len(frame),'uncovered_high':len(frame[frame.priority=='high']),'reason_by_priority':frame.groupby(['priority','reason']).size().to_dict().__str__(),'direct_physically_insertable_by_priority':frame.groupby('priority').direct_physical_insert.sum().to_dict(),'high_details':frame[frame.priority=='high'].to_dict('records'),'positive_replacement_targets':len(replacements),'best_replacements':sorted(replacements,key=lambda r:-r['gain'])[:30],'independent_window_opportunities':totals,'warning':'Individual free-window opportunities can conflict with each other; counts are not a jointly schedulable promise. Blocking classification is relative to the fixed V4 plan, not proof of global infeasibility.','runtime_s':time.perf_counter()-t}
    (OUT/'analysis.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in summary.items() if k not in ['high_details','best_replacements']},ensure_ascii=False),flush=True)
if __name__=='__main__':run()
