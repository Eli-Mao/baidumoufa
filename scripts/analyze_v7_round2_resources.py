"""Fixed round-one incumbent station and target opportunities; no propagation."""
from pathlib import Path
import collections,json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import psutil,pandas as pd
from satplan import io_schema
from satplan.v5 import State
from satplan.v6 import Catalog
from audit_v7_baseline import union,subtract,length
def run(cache,out):
    psutil.Process().cpu_affinity([12]);out.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    plan=io_schema.load_plan(ROOT/'accepted/v7/plans/score_priority.csv');w=io_schema.load_windows(cache/'windows.csv');s=State(plan);c=Catalog(w)
    sites=[]
    for site,g in w.groupby('station_id'):
        available=union(g[['t_start_s','t_end_s']].itertuples(index=False,name=None));p=plan[plan.station_id==site]
        blocked=union([(a-30.,b+30.) for a,b in p[['t_start_s','t_end_s']].itertuples(index=False,name=None)])
        gaps=subtract(available,blocked);obs=float(p.dur_s.sum())
        sites.append(dict(station_id=int(site),tasks=len(p),observation_s=obs,candidate_union_s=length(available),
            observation_fraction=obs/length(available),calendar_busy_fraction=(obs+30.*(len(p)-1))/518400.,
            candidate_idle_after_padding_s=length(gaps),min120_gaps=sum(b-a>=120. for a,b in gaps),max_gap_s=max((b-a for a,b in gaps),default=0.)))
    counts=collections.Counter();targets=collections.defaultdict(collections.Counter)
    for i in range(len(w)):
        site,sat=int(c.site[i]),int(c.sat[i]);a,b=float(c.start[i]),float(c.end[i]);priority=str(c.priority[i])
        station=s.free_intervals(site,-1,a,b);free=s.free_intervals(site,sat,a,b) if station else []
        if free:
            counts['coarse_free_'+priority]+=1;targets[sat]['coarse_free']+=1
        if station:targets[sat]['station_free']+=1
        targets[sat]['windows']+=1
    meta=pd.read_csv(cache/'selected_targets.csv');rows=[]
    for r in meta.itertuples(index=False):rows.append(dict(sat_id=int(r.sat_id),priority=r.priority,observations=s.counts[int(r.sat_id)],**targets[int(r.sat_id)]))
    pd.DataFrame(rows).fillna(0).to_csv(out/'target_resources.csv',index=False)
    pd.DataFrame(sites).to_csv(out/'station_resources.csv',index=False)
    result=dict(plan='frozen round-one 31426.365',stations=sites,window_counts=dict(counts),runtime_s=time.perf_counter()-started,
        caveat='Candidate-union gaps and fixed-plan time feasibility only; not physically certified additions or simultaneous coverage promises')
    (out/'resources.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
