"""Explain actual low-target losses and station resources from sealed plans."""
import sys,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from satplan.v5 import State,Task
BASE=Path(os.environ.get('V6_CACHE_DIR','D:/SatelliteProject_GitHub/data/out/real_aug2026_10000'))
SEALED=Path(os.environ.get('V6_BASELINE_DIR',str(ROOT.parents[1]/'outputs/v5_sealed')))
OUT=Path(os.environ.get('V6_ANALYSIS_DIR',str(ROOT/'data/out/v6_analysis')))
def run():
    p=pd.read_csv(SEALED/'best_v5_plan.csv');old=pd.read_csv(BASE/'final_plan.csv');state=State(p)
    before=set(old.loc[old.priority=='low','sat_id']);after=set(p.loc[p.priority=='low','sat_id'])
    lost=before-after;gained=after-before;retained=before&after
    pd.DataFrame({'sat_id':sorted(gained)}).to_csv(OUT/'new_low_targets.csv',index=False)
    opportunity=pd.read_csv(OUT/'uncovered_opportunities.csv').set_index('sat_id')
    rows=[]
    for row in old[old.sat_id.isin(lost)].itertuples(index=False):
        t=Task(0,int(row.station_id),int(row.sat_id),str(row.priority),int(row.priority_score),float(row.t_start_s),float(row.t_end_s),float(row.dur_s))
        blockers=[state.tasks[u] for u in state.conflicts(t)]
        rows.append({'sat_id':t.sat,'old_task_id':row.task_id,'old_station':t.station,'old_start':t.start,'old_end':t.end,'old_score':t.score,'blocking_tasks':','.join(str(x.uid) for x in blockers),'blocking_priorities':','.join(x.priority for x in blockers),'blocking_score':sum(x.score for x in blockers),'direct_physical_insertion_available_elsewhere':bool(opportunity.loc[t.sat,'direct_physical_insert']),'original_interval_free':not blockers})
    f=pd.DataFrame(rows);f.to_csv(OUT/'lost_low_task_blockers.csv',index=False)
    lostopp=opportunity.loc[sorted(lost)]
    reps=pd.read_csv(OUT/'replacement_opportunities.csv');real=reps[(reps.blocking_task_ids.notna())&(reps.blocked_score>0)]
    real.to_csv(OUT/'profitable_conflict_replacements.csv',index=False)
    # Site gaps include true switching margins; report only intersections of
    # resource gaps with the cached candidate union, not raw daytime idle time.
    w=pd.read_csv(BASE/'windows.csv');stations=pd.read_csv(OUT/'station_utilization.csv');spare=[]
    for site,g in w.groupby('station_id'):
        union=[]
        for a,b in g[['t_start_s','t_end_s']].sort_values('t_start_s').itertuples(index=False,name=None):
            if union and a<=union[-1][1]:union[-1]=(union[-1][0],max(b,union[-1][1]))
            else:union.append((a,b))
        line=state.stations[int(site)];cursor=0.;gaps=[]
        for st,uid in line:
            t=state.tasks[uid]
            if t.start-30>cursor:gaps.append((cursor,t.start-30))
            cursor=t.end+30
        if cursor<518400:gaps.append((cursor,518400.))
        free=sum(max(0.,min(b,y)-max(a,x)) for a,b in union for x,y in gaps if x<b and y>a)
        usable=[(max(a,x),min(b,y)) for a,b in union for x,y in gaps if min(b,y)-max(a,x)>=120.]
        spare.append({'station_id':int(site),'candidate_union_unoccupied_s':free,'union_free_gaps_ge120':len(usable),'union_free_gap_s_ge120':sum(b-a for a,b in usable),'max_union_free_gap_s':max([b-a for a,b in usable],default=0)})
    stations=stations.merge(pd.DataFrame(spare),on='station_id');stations.to_csv(OUT/'station_resources.csv',index=False)
    summary={'low_v4':len(before),'low_v5':len(after),'low_retained':len(retained),'low_lost':len(lost),'low_new':len(gained),'lost_low_old_tasks':len(f),'lost_low_old_tasks_blocked_by_current_high_or_mid':int(f.blocking_priorities.str.contains('high|mid').sum()),'lost_low_targets_with_direct_physical_opportunity_elsewhere':int(lostopp.direct_physical_insert.sum()),'uncovered_all_have_windows':bool((opportunity.window_count>0).all()),'uncovered_windows_by_priority':opportunity.groupby('priority').window_count.sum().to_dict(),'positive_real_replacements':len(real),'replacement_examples':real.sort_values('gain',ascending=False).head(10).to_dict('records'),'station_resources':stations.to_dict('records'),'caveat':'Resource intersections are geometric cache unions. A 120-second union gap can consist of different targets and is not itself a physical single-target insertion certificate. Individual insertion certificates appear in uncovered_opportunities.csv.'}
    (OUT/'resources.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':run()
