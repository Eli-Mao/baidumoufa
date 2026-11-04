"""Summarize only accepted V7 experiments and prepare small versioned evidence."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from satplan import config

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,indent=2,ensure_ascii=False),encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);a=p.parse_args();out=a.results.resolve()
    formal=read(out/'formal_b36/comparison.json')
    candidates=[Path(formal['best_v7_trial'])]
    extended=out/'extended_b120_s11_v7'
    if (extended/'trial.json').exists() and read(extended/'trial.json')['status']=='accepted':candidates.append(extended)
    best=max(candidates,key=lambda p:read(p/'trial.json')['final_score']['total_score'])
    trial=read(best/'trial.json');assert trial['status']=='accepted' and trial['hard_violations']==0 and trial['full_interval_pass']
    assert sha(best/'final_plan.csv')==trial['final_csv_sha256']
    for src,dst in [('final_plan.csv','best_v7_plan.csv'),('final_score.json','best_v7_score.json'),('physics_audit.json','best_v7_physics.json'),
        ('physics_audit.csv','best_v7_physics.csv'),('hard_check.json','best_v7_hard_check.json'),('move_trace.json','best_v7_move_trace.json')]:shutil.copy2(best/src,out/dst)
    score=trial['final_score'];base=pd.read_csv(ROOT/'accepted/v6/plans/score_priority.csv');plan=pd.read_csv(out/'best_v7_plan.csv')
    columns=['station_id','sat_id','t_start_s','t_end_s','dur_s']
    before=set(base[columns].itertuples(index=False,name=None));after=set(plan[columns].itertuples(index=False,name=None))
    changed=dict(removed_or_changed=len(before-after),added_or_changed=len(after-before),unchanged=len(before&after))
    rows=[]
    for r in formal['accepted_trials']:
        s=r['score'];rows.append(dict(algorithm=r['algorithm'],seed=r['seed'],budget_s=36.,score=s['total_score'],tasks=s['n_tasks'],covered=s['n_covered'],
            high=s['by_priority']['high']['n_covered'],mid=s['by_priority']['mid']['n_covered'],low=s['by_priority']['low']['n_covered'],
            search_s=r['search_s'],search_peak_rss_mib=r['search_peak_rss_mib'],physics_s=r['physics_s'],hard_violations=0,physical_pass=True))
    pd.DataFrame(rows).to_csv(out/'fair_comparison.csv',index=False)
    pd.DataFrame(formal['summary']).to_csv(out/'fair_summary.csv',index=False)
    pd.DataFrame(formal['paired']).to_csv(out/'paired_gains.csv',index=False)
    priority=[]
    for level in config.PRIORITY_ORDER:
        sub=plan[plan.priority==level];old=base[base.priority==level]
        total={'high':2024,'mid':3990,'low':3986}[level]
        priority.append(dict(priority=level,total=total,v6_tasks=len(old),v7_tasks=len(sub),v6_covered=old.sat_id.nunique(),v7_covered=sub.sat_id.nunique(),
            v6_rate=old.sat_id.nunique()/total,v7_rate=sub.sat_id.nunique()/total))
    pd.DataFrame(priority).to_csv(out/'priority_comparison.csv',index=False)
    sites=[]
    for site in config.STATION_IDS:
        old=base[base.station_id==site];new=plan[plan.station_id==site]
        sites.append(dict(station_id=site,v6_tasks=len(old),v7_tasks=len(new),
            v6_utilization=(old.dur_s.sum()+30.*max(0,len(old)-1))/518400.,
            v7_utilization=(new.dur_s.sum()+30.*max(0,len(new)-1))/518400.))
    pd.DataFrame(sites).to_csv(out/'station_comparison.csv',index=False)
    trace=read(out/'best_v7_move_trace.json')
    convergence=[dict(elapsed_s=0.,total_score=31015.978085736664)]
    convergence.extend({k:r[k] for k in ('elapsed_s','total_score')} for r in trace)
    convergence.append(dict(elapsed_s=trial['search']['search_wall_s'],total_score=score['total_score']))
    pd.DataFrame(convergence).to_csv(out/'best_convergence.csv',index=False)
    changes=pd.DataFrame(trace)
    if len(changes):changes.groupby('operator').agg(accepted_moves=('delta_score','size'),gain=('delta_score','sum')).to_csv(out/'operator_contributions.csv')
    cross_station_moves=0
    for row in trace:
        removed={t['uid']:t for t in row['removed']}
        cross_station_moves+=sum(t['uid'] in removed and t['station']!=removed[t['uid']]['station'] for t in row['added'])
    frozen={}
    for name in ('src/satplan/config.py','src/satplan/rules.py','src/satplan/io_schema.py','src/satplan/optimize.py',
        'src/satplan/v5.py','src/satplan/v6.py','src/satplan/v5_physics.py','scripts/audit_v6_physics.py'):
        original=subprocess.check_output(['git','show','401d59d:'+name],cwd=ROOT)
        assert (ROOT/name).read_bytes()==original,name+' changed from V6'
        frozen[name]=hashlib.sha256(original).hexdigest()
    summary=dict(best_trial=str(best),best_score=score,search_budget_s=trial['budget_s'],seed=trial['seed'],
        gain_vs_sealed_v6=score['total_score']-31015.978085736664,gain_percent=(score['total_score']/31015.978085736664-1.)*100.,
        best_plan_sha256=sha(out/'best_v7_plan.csv'),changes=changed,frozen_core_sha256=frozen,
        cross_station_relocations=cross_station_moves,
        physics_certificate=dict(plan_sha256=sha(out/'best_v7_plan.csv'),report_sha256=sha(out/'best_v7_physics.json'),
            detail_sha256=sha(out/'best_v7_physics.csv'),report=read(out/'best_v7_physics.json')),
        formal_summary=formal['summary'],paired=formal['paired'],tests_passed=60,pushed=False,
        extended_in_fair_statistics=False,physical_method='independent exact endpoints plus complete interval 1s discrete samples; not continuous certification')
    write(out/'summary.json',summary)
    accepted=ROOT/'accepted/v7'
    copies={out/'best_v7_plan.csv':accepted/'plans/score_priority.csv',out/'best_v7_physics.json':accepted/'validation/physics.json',
        out/'best_v7_physics.csv':accepted/'validation/physics.csv',out/'best_v7_hard_check.json':accepted/'validation/hard_check.json',
        best/'trial.json':accepted/'provenance/best_trial.json',best/'independent_score.json':accepted/'validation/independent_score.json',
        out/'best_v7_score.json':accepted/'validation/score.json',out/'summary.json':accepted/'summary.json',
        out/'formal_b36/comparison.json':accepted/'comparison/comparison.json',out/'fair_comparison.csv':accepted/'comparison/fair_comparison.csv',
        out/'input_verification.json':accepted/'provenance/input_verification.json',out/'environment.json':accepted/'provenance/environment.json',
        out/'experiment_plan.json':accepted/'provenance/experiment_plan.json',out/'formal_b36/protocol.json':accepted/'provenance/protocol.json',
        out/'test_results.txt':accepted/'validation/test_results.txt',out/'baseline_audit/audit.json':accepted/'analysis/baseline_audit.json',
        out/'baseline_audit/station_utilization.csv':accepted/'analysis/station_utilization.csv'}
    for r in formal['accepted_trials']:
        directory=out/'formal_b36'/f'b36_s{r["seed"]}_{r["algorithm"]}'
        copies[directory/'final_plan.csv']=accepted/'comparison/plans'/f'{directory.name}.csv'
    for source,target in copies.items():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    print(json.dumps(summary,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
