"""Recoverable V6/V7 warm-start comparison: search, then independent acceptance.

No candidate is accepted until its exact saved CSV passes frozen arithmetic,
Evaluator, all hard constraints and the unchanged independent 1s/endpoints audit.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse,hashlib,json,shutil,sys,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import psutil
import pandas as pd
from satplan import io_schema, rules, optimize, v6, v7
from satplan.v5_physics import PhysicalOracle
from audit_v7_baseline import sha
from verify_v6_csv import verify
import audit_v6_physics

def save(path,obj):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(path)

def identity(cache):
    paths=[cache/'windows.csv',cache/'selected_targets.csv',ROOT/'accepted/v6/plans/score_priority.csv',ROOT/'de421.bsp',
        *sorted((ROOT/'data/raw').glob('*')),*sorted((ROOT/'src/satplan').glob('*.py')),
        ROOT/'scripts/run_v7_trial.py',ROOT/'scripts/audit_v6_physics.py',ROOT/'scripts/verify_v6_csv.py']
    return {str(p.resolve()):sha(p) for p in paths if p.is_file()}

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);receipt=a.out/'trial.json'
    signature=identity(a.cache)
    if receipt.exists():
        r=json.loads(receipt.read_text(encoding='utf-8'))
        assert r['identity']==signature and r['algorithm']==a.algorithm and r['seed']==a.seed and r['budget_s']==a.budget,'Resume identity mismatch'
        if r['status']=='accepted':
            assert sha(a.out/'final_plan.csv')==r['final_csv_sha256'];print('resume accepted',a.out,flush=True);return
        assert a.phase=='validate' and r['status']=='provisional','Preserve incomplete or rejected trial; choose new --out'
    else:
        assert a.phase!='validate','No provisional trial to validate'
        r=dict(status='initializing',algorithm=a.algorithm,seed=a.seed,budget_s=a.budget,identity=signature)
    start=time.perf_counter();proc=psutil.Process();peak=[proc.memory_info().rss];stop=threading.Event()
    def monitor():
        while not stop.wait(.05):peak[0]=max(peak[0],proc.memory_info().rss)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        w=io_schema.load_windows(a.cache/'windows.csv');meta=pd.read_csv(a.cache/'selected_targets.csv')
        base=io_schema.load_plan(ROOT/'accepted/v6/plans/score_priority.csv')
        assert len(w)==531432 and len(meta)==10000 and len(base)==7877
        expected={Path(k).name:v for k,v in json.loads((ROOT/'accepted/v6/provenance/historical_identity.json').read_text(encoding='utf-8')).items()}
        for name in ('windows.csv','selected_targets.csv'):assert sha(a.cache/name)==expected[name]
        for name in ('orbits.tle','stations.txt','priority_high.txt','priority_medium.txt','priority_low.txt'):
            assert sha(ROOT/'data/raw'/name)==expected[name]
        assert sha(ROOT/'de421.bsp')==expected['de421.bsp']
        if a.phase in ('search','all'):
            oracle=PhysicalOracle();r['status']='searching';save(receipt,r)
            candidate,stats={'v6':v6.search,'v7':v7.search}[a.algorithm](base,w,meta,budget_s=a.budget,seed=a.seed,physical=oracle)
            save(a.out/'move_trace.json',stats.pop('trace'));r['search']=stats
            r['oracle']=dict(calls=oracle.calls,hits=oracle.hits,samples=oracle.samples)
            io_schema.save_plan(candidate,a.out/'candidate_plan.csv')
            r.update(status='provisional',candidate_csv_sha256=sha(a.out/'candidate_plan.csv'),search_peak_rss_mib=max(peak[0],proc.memory_info().rss)/1048576,
                search_process_s=time.perf_counter()-start)
            save(receipt,r)
            print(json.dumps(dict(status='provisional',algorithm=a.algorithm,seed=a.seed,score=stats['candidate_score'],search_s=stats['search_wall_s'])),flush=True)
        if a.phase in ('validate','all'):
            assert sha(a.out/'candidate_plan.csv')==r['candidate_csv_sha256']
            candidate=io_schema.load_plan(a.out/'candidate_plan.csv')
            issues=rules.plan_violations(candidate,w,max_report=1000000)
            save(a.out/'hard_check.json',dict(count=len(issues),violations=issues))
            assert not issues,issues[:5]
            arithmetic=verify(a.out/'candidate_plan.csv',a.cache/'selected_targets.csv',a.cache/'windows.csv')
            evaluator=optimize.evaluate(a.out/'candidate_plan.csv',windows_path=a.cache/'windows.csv',sat_meta_path=a.cache/'selected_targets.csv',coverage_weight=0.)
            score=rules.score_plan(candidate,w,meta)
            assert abs(evaluator-arithmetic['independent_csv_score'])<1e-7
            assert abs(score['total_score']-evaluator)<1e-7
            assert score['hi_covered']==2024 and evaluator>=31015.978085736664-1e-7
            r['stage']='independent_physics';save(receipt,r)
            audit_start=time.perf_counter()
            audit=audit_v6_physics.run(a.out/'candidate_plan.csv',a.out/'physics_audit.json',step_s=1.)
            assert audit['all_pass'] and audit['exact_endpoints_included'] and audit['bad_sgp4_samples']==0 and audit['tasks']==len(candidate)
            # Exact serialized bytes are the accepted artifact, not a regenerated frame.
            shutil.copy2(a.out/'candidate_plan.csv',a.out/'final_plan.csv')
            save(a.out/'final_score.json',score);save(a.out/'independent_score.json',arithmetic)
            r.update(status='accepted',stage='completed',final_score=score,evaluator_score=evaluator,hard_violations=0,
                final_csv_sha256=sha(a.out/'final_plan.csv'),physics_s=time.perf_counter()-audit_start,full_interval_pass=True,
                validation_peak_rss_mib=max(peak[0],proc.memory_info().rss)/1048576,gain_vs_v6=evaluator-31015.978085736664)
            print(json.dumps(dict(status='accepted',algorithm=a.algorithm,seed=a.seed,score=evaluator,tasks=len(candidate),covered=score['n_covered'])),flush=True)
    except BaseException as exc:
        r.update(status='rejected_or_failed',error=repr(exc));traceback.print_exc();raise
    finally:
        stop.set();thread.join(timeout=1.)
        r['last_phase']=a.phase;r['last_phase_wall_s']=time.perf_counter()-start;save(receipt,r)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--algorithm',choices=['v6','v7'],required=True)
    p.add_argument('--cache',type=Path,required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--budget',type=float,required=True)
    p.add_argument('--phase',choices=['search','validate','all'],default='all');p.add_argument('--out',type=Path,required=True)
    run(p.parse_args())
