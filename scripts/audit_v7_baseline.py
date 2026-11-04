"""Read-only frozen-plan bottleneck audit. No full-catalog orbit propagation."""
from __future__ import annotations
import argparse, hashlib, json, sys, time
from bisect import bisect_left
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
import numpy as np
import pandas as pd
from satplan import config, io_schema, rules, optimize
from satplan.v5 import State, insert_options
from satplan.v6 import Catalog
from satplan.v5_physics import PhysicalOracle

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''): h.update(block)
    return h.hexdigest()

def union(intervals):
    result = []
    for a, b in sorted(intervals):
        if result and a <= result[-1][1]: result[-1] = (result[-1][0], max(b, result[-1][1]))
        else: result.append((a, b))
    return result

def subtract(available, blocked):
    result = []; j = 0
    for a, b in available:
        while j < len(blocked) and blocked[j][1] <= a: j += 1
        cursor = a; k = j
        while k < len(blocked) and blocked[k][0] < b:
            lo, hi = blocked[k]
            if lo > cursor: result.append((cursor, min(lo, b)))
            cursor = max(cursor, hi); k += 1
        if cursor < b: result.append((cursor, b))
    return result

def length(intervals): return sum(b-a for a, b in intervals)

def run(args):
    started = time.perf_counter(); out = args.out; out.mkdir(parents=True, exist_ok=False)
    plan = io_schema.load_plan(args.plan); windows = io_schema.load_windows(args.cache/'windows.csv')
    meta = pd.read_csv(args.cache/'selected_targets.csv')
    assert len(plan) == 7877 and len(windows) == 531432 and len(meta) == 10000
    identity = json.loads((ROOT/'accepted/v6/provenance/historical_identity.json').read_text(encoding='utf-8'))
    expected = {Path(k).name:v for k,v in identity.items()}
    for name in ('windows.csv','selected_targets.csv'): assert sha(args.cache/name) == expected[name]
    seal = json.loads((ROOT/'accepted/v6/provenance/initial_seal.json').read_text(encoding='utf-8'))
    assert sha(args.plan) == seal['core_artifact_sha256']['plans/score_priority.csv']
    score = rules.score_plan(plan, windows, meta)
    evaluator = optimize.evaluate(args.plan, windows_path=args.cache/'windows.csv', sat_meta_path=args.cache/'selected_targets.csv', coverage_weight=0.)
    assert score['n_violations'] == 0 and abs(evaluator-31015.978085736664) < 1e-7
    (out/'baseline_score.json').write_text(json.dumps(score,indent=2),encoding='utf-8')
    state = State(plan); cat = Catalog(windows); oracle = PhysicalOracle()
    task_rows=[]
    for t in state.tasks.values():
        task_rows.append(dict(task_id=t.uid,sat_id=t.sat,station_id=t.station,priority=t.priority,
            duration_s=t.duration,score=t.score,removal_score_loss=t.score,coverage_loss=int(state.counts[t.sat]==1),
            extra_score_above_120s=t.score-rules.task_score(t.weight,120.),
            extension_score_per_s=(t.weight/300. if t.duration<240.-1e-7 else 0.),
            score_per_occupied_s=t.score/(t.duration+config.SWITCH_TIME_S)))
    pd.DataFrame(task_rows).to_csv(out/'task_marginal_scores.csv',index=False)
    station_rows=[]; idle_rows=[]; hour_rows=[]
    for site, g in windows.groupby('station_id'):
        legal = union(g[['t_start_s','t_end_s']].itertuples(index=False,name=None))
        tasks = sorted((state.tasks[u] for _,u in state.stations[int(site)]),key=lambda t:t.start)
        occupied = [(t.start,t.end) for t in tasks]
        padded = union([(max(0.,t.start-30.),min(518400.,t.end+30.)) for t in tasks])
        legal_idle = subtract(legal, occupied); usable = subtract(legal,padded)
        calendar_idle = subtract([(0.,518400.)],occupied)
        for kind, intervals in [('calendar',calendar_idle),('candidate_union',legal_idle),('candidate_union_with_switch_padding',usable)]:
            for a,b in intervals: idle_rows.append(dict(station_id=int(site),kind=kind,start_s=a,end_s=b,duration_s=b-a))
        for day in range(6):
            for hour in range(24):
                a=day*86400.+hour*3600.;b=a+3600.
                obs=sum(max(0.,min(b,t.end)-max(a,t.start)) for t in tasks)
                opportunity=sum(max(0.,min(b,y)-max(a,x)) for x,y in legal)
                hour_rows.append(dict(station_id=int(site),day=day+1,hour_utc=hour,observation_s=obs,candidate_union_s=opportunity))
        obs=sum(t.duration for t in tasks); switch=30.*max(0,len(tasks)-1)
        station_rows.append(dict(station_id=int(site),tasks=len(tasks),targets=len({t.sat for t in tasks}),
            observation_s=obs,mandatory_switch_s=switch,calendar_idle_s=length(calendar_idle),
            calendar_busy_fraction=(obs+switch)/518400.,candidate_union_s=length(legal),
            observation_fraction_of_candidate_union=obs/length(legal),candidate_idle_s=length(legal_idle),
            candidate_idle_with_switch_padding_s=length(usable),candidate_idle_runs_120s=sum(b-a>=120 for a,b in usable),
            max_candidate_idle_s=max((b-a for a,b in usable),default=0.)))
    pd.DataFrame(station_rows).to_csv(out/'station_utilization.csv',index=False)
    pd.DataFrame(idle_rows).to_csv(out/'idle_intervals.csv',index=False)
    pd.DataFrame(hour_rows).to_csv(out/'station_hourly.csv',index=False)
    per_sat={int(r.sat_id):dict(sat_id=int(r.sat_id),priority=r.priority,observations=state.counts[int(r.sat_id)],
        windows=0,assigned_windows=0,station_only_free=0,cooldown_only_free=0,both_free=0) for r in meta.itertuples(index=False)}
    assigned={}
    for t in state.tasks.values(): assigned.setdefault((t.station,t.sat),[]).append(t)
    counts=Counter(); window_rows=[]; direct=[]; replacements=[]
    for i in range(len(windows)):
        site=int(cat.site[i]);sat=int(cat.sat[i]);a=float(cat.start[i]);b=float(cat.end[i]);r=per_sat[sat];r['windows']+=1
        used=any(a<=t.start and t.end<=b for t in assigned.get((site,sat),[]))
        if used:r['assigned_windows']+=1;counts['assigned_windows']+=1
        station=state.free_intervals(site,-1,a,b)
        cooldown=state.free_intervals(-1,sat,a,b)
        both=state.free_intervals(site,sat,a,b) if station and cooldown else []
        for key,value in [('station_only_free',station),('cooldown_only_free',cooldown),('both_free',both)]:
            if value:r[key]+=1;counts[key]+=1
        if b-a<120.:reason='window_shorter_than_120s'
        elif both:reason='coarse_insertion_slot'
        elif station and not cooldown:reason='cooldown_only'
        elif cooldown and not station:reason='station_only'
        elif station and cooldown:reason='station_cooldown_intersection'
        else:reason='station_and_cooldown'
        counts[reason]+=1
        if not used:counts['unassigned_windows']+=1
        if both:
            for t in insert_options(state,cat,i)[:2]:
                direct.append((t.score,i,t.start,t.end))
        # Exact anchor losses are a fixed-plan diagnostic, not an infeasibility proof.
        if not used and b-a>=120.:
            for start in (a,max(a,b-120.)):
                new=cat.task(i,start,start+120.,state.next_id)
                ids=state.conflicts(new)
                if len(ids)<=3:
                    loss=sum(state.tasks[u].score for u in ids);gain=new.score-loss
                    if gain>1e-7:replacements.append(dict(window_index=i,sat_id=sat,station_id=site,priority=new.priority,
                        start_s=new.start,end_s=new.end,gross_score=new.score,blocking_score=loss,gain=gain,
                        blocker_ids=','.join(str(u) for u in sorted(ids))))
        window_rows.append((i,site,sat,int(used),reason))
        if (i+1)%100000==0: print('window audit',i+1,flush=True)
    pd.DataFrame(window_rows,columns=['window_index','station_id','sat_id','assigned','fixed_plan_status']).to_csv(out/'window_status.csv',index=False)
    targets=pd.DataFrame(per_sat.values())
    targets['fixed_plan_reason']=np.select([targets.windows==0,targets.both_free>0,targets.station_only_free==0,targets.cooldown_only_free==0],
        ['no_cached_windows','coarse_insertion_slot','station_blocks_all_windows','cooldown_blocks_all_windows'],default='joint_station_cooldown_block')
    targets.to_csv(out/'target_opportunities.csv',index=False)
    targets[targets.observations==0].to_csv(out/'uncovered_targets.csv',index=False)
    probes=[]; tick=time.perf_counter()
    for _,i,a,b in sorted(direct,reverse=True):
        if len(probes)>=args.max_probes or time.perf_counter()-tick>=args.probe_seconds:break
        for shift in (0.,.1):
            end=min(b, b-shift);start=a+shift
            if end-start<120.:continue
            t=cat.task(i,start,end,state.next_id)
            ok=state.fits(t) and oracle(t)
            probes.append(dict(window_index=i,sat_id=t.sat,station_id=t.station,start_s=t.start,end_s=t.end,score=t.score,physical_pass=ok))
            if ok:break
    pd.DataFrame(probes).to_csv(out/'direct_physical_probes.csv',index=False)
    pd.DataFrame(sorted(replacements,key=lambda r:-r['gain'])).to_csv(out/'anchor_replacement_candidates.csv',index=False)
    extension=[]
    for old in list(state.tasks.values()):
        if old.duration>=239.999999:continue
        state.remove(old.uid)
        try:
            opts=[]
            for i in cat.by_sat.get(old.sat,[]):
                if cat.site[i]==old.station and cat.start[i]<=old.start and cat.end[i]>=old.end:
                    opts.extend(insert_options(state,cat,i,uid=old.uid))
            best=max(opts,key=lambda t:t.score,default=old)
        finally: state.add(old)
        if best.score>old.score+1e-7:
            extension.append(dict(task_id=old.uid,sat_id=old.sat,station_id=old.station,old_start=old.start,old_end=old.end,
                new_start=best.start,new_end=best.end,coarse_gain=best.score-old.score,physical_pass=bool(oracle(best))))
    pd.DataFrame(extension).to_csv(out/'shift_extension_candidates.csv',index=False)
    by_priority=[]
    for priority in config.PRIORITY_ORDER:
        t=targets[targets.priority==priority];tasks=pd.DataFrame(task_rows);q=tasks[tasks.priority==priority]
        by_priority.append(dict(priority=priority,targets=len(t),covered=int((t.observations>0).sum()),
            observations=int(t.observations.sum()),uncovered_with_windows=int(((t.observations==0)&(t.windows>0)).sum()),
            uncovered_without_windows=int(((t.observations==0)&(t.windows==0)).sum()),
            uncovered_with_station_slot=int(((t.observations==0)&(t.station_only_free>0)).sum()),
            observed_cooldown_blocks_all_windows=int(((t.observations>0)&(t.cooldown_only_free==0)&(t.windows>0)).sum()),
            score=float(q.score.sum()),min_duration_tasks=int((q.duration_s<=120.+1e-6).sum()),max_duration_tasks=int((q.duration_s>=240.-1e-6).sum())))
    summary=dict(baseline_score=score,evaluator_score=evaluator,plan_sha256=sha(args.plan),windows_sha256=sha(args.cache/'windows.csv'),
        by_priority=by_priority,window_counts=dict(counts),direct_probe_count=len(probes),direct_physical_passes=sum(r['physical_pass'] for r in probes),
        direct_probe_exhaustive=len(probes)>=len(direct),positive_anchor_candidates=len(replacements),
        legal_shift_extensions=sum(r['physical_pass'] for r in extension),shift_extension_gain=sum(r['coarse_gain'] for r in extension if r['physical_pass']),
        station_statistics=station_rows,runtime_s=time.perf_counter()-started,
        caveats=['Candidate union is the union of cached target windows, not exact station dark time.',
                 'Coarse insertion counts and anchor gains are not physical certificates or jointly schedulable totals.',
                 'Block classifications are relative to the frozen plan, not global impossibility.',
                 'No full target-catalog propagation; physical calls sample only proposed intervals.'])
    (out/'audit.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['station_statistics','baseline_score']},ensure_ascii=True),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--max-probes',type=int,default=1000);p.add_argument('--probe-seconds',type=float,default=30.)
    run(p.parse_args())
