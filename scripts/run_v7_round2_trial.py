"""Round two: immutable V7 warm start, frozen V6/V7, separate full acceptance."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import argparse,gc,hashlib,json,shutil,sys,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import psutil,pandas as pd
from satplan import io_schema,rules,optimize,v6,v7
from satplan.v5_physics import PhysicalOracle
from audit_v7_baseline import sha
from verify_v6_csv import verify
import audit_v6_physics
BASE_SCORE=31426.364999713333
BASE_SHA='3e2b0265c95df472a7c55bb84a848930fa7541663ea886e3b5ff2e0ca4e91426'

def save(p,obj):
    temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n');temp.replace(p)

def signature(a):
    files=[a.cache/'windows.csv',a.cache/'selected_targets.csv',ROOT/'accepted/v7/plans/score_priority.csv',ROOT/'de421.bsp',*sorted((ROOT/'data/raw').glob('*'))]
    frozen=['config','io_schema','rules','optimize','scheduler','v5','v5_physics','v6','v7']
    files.extend(ROOT/'src/satplan'/f'{n}.py' for n in frozen)
    if a.algorithm=='v7a':files.extend(ROOT/'src/satplan'/f'{n}.py' for n in ['v7_adaptive','v7_exact'])
    files.extend(ROOT/'scripts'/n for n in ['run_v7_round2_trial.py','verify_v6_csv.py','audit_v6_physics.py'])
    return {str(p.resolve()):sha(p) for p in files}

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);path=a.out/'trial.json';proc=psutil.Process()
    if a.cpu is not None:proc.cpu_affinity([a.cpu])
    identity=signature(a)
    if path.exists():
        r=json.loads(path.read_text(encoding='utf-8'))
        assert r['identity']==identity and (r['algorithm'],r['seed'],r['budget_s'],r['cpu_affinity'])==(a.algorithm,a.seed,a.budget,proc.cpu_affinity()),'Trial identity mismatch'
        if r['status']=='accepted':
            assert sha(a.out/'final_plan.csv')==r['final_csv_sha256'];print('accepted trial reused',flush=True);return
        assert a.phase=='validate' and r['status']=='provisional','Retain incomplete trial and choose new directory'
    else:
        assert a.phase!='validate'
        assert not any(a.out.iterdir()),'Refuse nonempty unidentified output directory'
        r=dict(status='initializing',algorithm=a.algorithm,seed=a.seed,budget_s=a.budget,identity=identity,
            cpu_affinity=proc.cpu_affinity(),baseline_score=BASE_SCORE,baseline_plan_sha256=BASE_SHA)
    started=time.perf_counter();peak=[proc.memory_info().rss];stop=threading.Event();holder={};pressure=[]
    def cpu_seconds():
        t=proc.cpu_times();return t.user+t.system
    def monitor():
        last=0.
        while not stop.wait(.2):
            mem=proc.memory_info();peak[0]=max(peak[0],mem.rss)
            now=time.perf_counter()
            if now-last>=15.:
                last=now;available=psutil.virtual_memory().available/1048576
                pressure.append(dict(elapsed_s=now-started,available_mib=available,rss_mib=mem.rss/1048576))
                engine=holder.get('engine')
                progress=dict(phase=r.get('stage',r['status']),elapsed_s=now-started,available_mib=available,
                    rss_mib=mem.rss/1048576,cpu_s=cpu_seconds())
                if engine is not None:
                    trace=engine.trace
                    progress.update(search_elapsed_s=now-engine.started,provisional_committed_score=trace[-1]['total_score'] if trace else BASE_SCORE,
                        accepted_search_transactions=len(trace))
                save(a.out/'progress.json',progress)
                engine=None
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        base_path=ROOT/'accepted/v7/plans/score_priority.csv';assert sha(base_path)==BASE_SHA
        expected={Path(k).name:v for k,v in json.loads((ROOT/'accepted/v6/provenance/historical_identity.json').read_text(encoding='utf-8')).items()}
        for name in ['windows.csv','selected_targets.csv']:assert sha(a.cache/name)==expected[name]
        for name in ['orbits.tle','stations.txt','priority_high.txt','priority_medium.txt','priority_low.txt']:assert sha(ROOT/'data/raw'/name)==expected[name]
        assert sha(ROOT/'de421.bsp')==expected['de421.bsp']
        w=io_schema.load_windows(a.cache/'windows.csv');meta=pd.read_csv(a.cache/'selected_targets.csv');base=io_schema.load_plan(base_path)
        assert len(w)==531432 and len(meta)==10000 and len(base)==8193
        if a.phase in ('search','all'):
            oracle=PhysicalOracle();r.update(status='searching',stage='search');save(path,r)
            engine_type={'v6':v6.Engine,'v7':v7.Engine}.get(a.algorithm)
            if a.algorithm=='v7a':
                from satplan.v7_adaptive import Engine
                engine_type=Engine
            tick=time.perf_counter();cpu0=cpu_seconds();fault0=getattr(proc.memory_info(),'num_page_faults',None)
            engine=engine_type(base,w,budget_s=a.budget,seed=a.seed,physical=oracle);holder['engine']=engine
            candidate,stats=engine.run();r['search_cpu_s']=cpu_seconds()-cpu0;r['search_wall_s_measured']=time.perf_counter()-tick
            fault1=getattr(proc.memory_info(),'num_page_faults',None)
            r['search_page_faults']=fault1-fault0 if fault0 is not None else None
            save(a.out/'move_trace.json',stats.pop('trace'));r['search']=stats
            r['oracle']=dict(calls=oracle.calls,hits=oracle.hits,samples=oracle.samples)
            io_schema.save_plan(candidate,a.out/'candidate_plan.csv')
            r.update(status='provisional',stage='search_complete',candidate_csv_sha256=sha(a.out/'candidate_plan.csv'),
                search_peak_rss_mib=max(peak[0],proc.memory_info().rss)/1048576,search_process_s=time.perf_counter()-started)
            save(path,r);print(json.dumps(dict(status='provisional',algorithm=a.algorithm,seed=a.seed,score=stats['candidate_score'])),flush=True)
            holder.clear()
            oracle.eph.close()
            del engine,oracle,candidate
            gc.collect()
        if a.phase in ('validate','all'):
            assert sha(a.out/'candidate_plan.csv')==r['candidate_csv_sha256']
            plan=io_schema.load_plan(a.out/'candidate_plan.csv')
            issues=rules.plan_violations(plan,w,max_report=1000000);save(a.out/'hard_check.json',dict(count=len(issues),violations=issues));assert not issues,issues[:3]
            independent=verify(a.out/'candidate_plan.csv',a.cache/'selected_targets.csv',a.cache/'windows.csv')
            value=optimize.evaluate(a.out/'candidate_plan.csv',windows_path=a.cache/'windows.csv',sat_meta_path=a.cache/'selected_targets.csv',coverage_weight=0.)
            score=rules.score_plan(plan,w,meta)
            assert abs(value-independent['independent_csv_score'])<1e-7 and abs(value-score['total_score'])<1e-7
            assert value>=BASE_SCORE-1e-7 and score['hi_covered']==2024
            r['stage']='independent_physics';save(path,r);tick=time.perf_counter()
            audit=audit_v6_physics.run(a.out/'candidate_plan.csv',a.out/'physics_audit.json',step_s=1.)
            assert audit['all_pass'] and audit['exact_endpoints_included'] and audit['bad_sgp4_samples']==0 and audit['tasks']==len(plan)
            assert identity==signature(a),'Code or input changed during trial'
            shutil.copy2(a.out/'candidate_plan.csv',a.out/'final_plan.csv');save(a.out/'final_score.json',score);save(a.out/'independent_score.json',independent)
            r.update(status='accepted',stage='completed',final_score=score,evaluator_score=value,hard_violations=0,full_interval_pass=True,
                final_csv_sha256=sha(a.out/'final_plan.csv'),physics_s=time.perf_counter()-tick,gain_vs_round1=value-BASE_SCORE,
                validation_peak_rss_mib=max(peak[0],proc.memory_info().rss)/1048576)
            print(json.dumps(dict(status='accepted',algorithm=a.algorithm,seed=a.seed,score=value,tasks=len(plan),covered=score['n_covered'])),flush=True)
    except BaseException as e:r.update(status='rejected_or_failed',error=repr(e));traceback.print_exc();raise
    finally:
        stop.set();thread.join(timeout=1.);r.update(last_phase=a.phase,last_phase_wall_s=time.perf_counter()-started)
        save(path,r);save(a.out/'resource_samples_'+a.phase+'.json',pressure)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--algorithm',choices=['v6','v7','v7a'],required=True);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--budget',type=float,required=True);p.add_argument('--cpu',type=int);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--phase',choices=['search','validate','all'],default='all');run(p.parse_args())
