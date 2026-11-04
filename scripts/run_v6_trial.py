"""Comparable warm-start refinement trial with immutable input identities."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
import sys,time,json,argparse,hashlib,threading,shutil,traceback,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import psutil,pandas as pd,numpy as np
from satplan import io_schema,rules,config,v5,v6
from satplan.v5_physics import PhysicalOracle
import v4_budget_reference,audit_v6_physics
BASE=Path(os.environ.get('V6_CACHE_DIR','D:/SatelliteProject_GitHub/data/out/real_aug2026_10000'))
SEALED=Path(os.environ.get('V6_BASELINE_DIR',str(ROOT.parents[1]/'outputs/v5_sealed')))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def save(p,o):
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(o,indent=2,ensure_ascii=False),encoding='utf-8');t.replace(p)
def identity():
    files=[BASE/'windows.csv',BASE/'selected_targets.csv',SEALED/'best_v5_plan.csv',ROOT/'de421.bsp',*sorted((ROOT/'data/raw').glob('*'))]
    files.extend(sorted((ROOT/'src').rglob('*.py')))
    files.extend(ROOT/'scripts'/n for n in ['run_v6_trial.py','audit_v6_physics.py','v4_budget_reference.py'])
    return {str(p):sha(p) for p in files if p.is_file()}
def run(args):
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    signature=identity()
    if (out/'trial.json').exists():
        old=json.loads((out/'trial.json').read_text(encoding='utf-8'))
        if old.get('status')=='accepted':
            assert old['identity']==signature and old['algorithm']==args.algorithm and old['seed']==args.seed and old['budget_s']==args.budget,'Resume identity mismatch'
            assert old['final_csv_sha256']==sha(out/'final_plan.csv')
            print('resume accepted',out.name,flush=True);return old
        raise RuntimeError('Incomplete trial exists: retain it and use a new output folder')
    started=time.perf_counter();proc=psutil.Process();peak=[proc.memory_info().rss];stop=threading.Event()
    def monitor():
        while not stop.wait(.1):peak[0]=max(peak[0],proc.memory_info().rss)
    threading.Thread(target=monitor,daemon=True).start()
    report={'status':'running','algorithm':args.algorithm,'seed':args.seed,'budget_s':args.budget,'identity':signature,'stages_s':{}}
    def stage(name,fn):
        report['stage']=name;save(out/'trial.json',report);print(args.algorithm,args.seed,args.budget,name,flush=True)
        t=time.perf_counter();value=fn();report['stages_s'][name]=time.perf_counter()-t;return value
    try:
        w=io_schema.load_windows(BASE/'windows.csv');meta=pd.read_csv(BASE/'selected_targets.csv');base=io_schema.load_plan(SEALED/'best_v5_plan.csv')
        assert len(w)==531432 and len(base)==7658 and len(meta)==10000
        sealed=json.loads((SEALED/'seal.json').read_text(encoding='utf-8'))
        assert sha(BASE/'windows.csv')==sealed['data_sha256']['windows.csv']
        assert sha(BASE/'selected_targets.csv')==sealed['data_sha256']['selected_targets.csv']
        frozen=json.loads((BASE/'experiment_report.json').read_text(encoding='utf-8'))
        assert all(sha(ROOT/name)==digest for name,digest in frozen['identity']['inputs_sha256'].items())
        oracle=PhysicalOracle() if args.algorithm!='v4' else None
        method={'v4':v4_budget_reference.search,'v5':v5.search,'v6':v6.search}[args.algorithm]
        kwargs=dict(budget_s=args.budget,seed=args.seed)
        if oracle:kwargs['physical']=oracle
        candidate,stats=stage('search',lambda:method(base,w,meta,**kwargs))
        save(out/'move_trace.json',stats.pop('trace',[]));report['search']=stats
        if oracle:report['oracle']={'calls':oracle.calls,'hits':oracle.hits,'samples':oracle.samples}
        report['candidate_score']=rules.score_plan(candidate,w,meta)
        io_schema.save_plan(candidate,out/'candidate_plan.csv')
        # Round-trip the deliverable CSV before every acceptance calculation.
        candidate=io_schema.load_plan(out/'candidate_plan.csv')
        issues=stage('complete_hard_check',lambda:rules.plan_violations(candidate,w,max_report=1000000))
        save(out/'hard_check.json',{'violations':issues,'count':len(issues)})
        baseline_score=rules.score_plan(base,w,meta)
        changed=sha(out/'candidate_plan.csv')!=sha(SEALED/'best_v5_plan.csv')
        if changed and not issues:
            audit=stage('independent_full_audit',lambda:audit_v6_physics.run(out/'candidate_plan.csv',out/'physics_audit.json'))
        elif not changed:
            audit=json.loads((SEALED/'best_v5_physics_audit.json').read_text());audit['reused_identical_v5']=True
            shutil.copy2(SEALED/'best_v5_physics_audit.csv',out/'physics_audit.csv');save(out/'physics_audit.json',audit)
        else:audit={'all_pass':False}
        valid=not issues and audit['all_pass'] and audit['exact_endpoints_included']
        score=rules.score_plan(candidate,w,meta)
        if not valid or score['total_score']<baseline_score['total_score']-1e-8:
            report['rejected_candidate']=True;report['rejected_audit']=audit
            candidate=base;score=baseline_score
            # Rejected candidate evidence remains separately available.
            if (out/'physics_audit.json').exists():shutil.copy2(out/'physics_audit.json',out/'rejected_physics_audit.json')
            if (out/'physics_audit.csv').exists():shutil.copy2(out/'physics_audit.csv',out/'rejected_physics_audit.csv')
            audit=json.loads((SEALED/'best_v5_physics_audit.json').read_text());audit['reused_identical_v5']=True
            shutil.copy2(SEALED/'best_v5_physics_audit.csv',out/'physics_audit.csv');save(out/'physics_audit.json',audit)
        truth=candidate.merge(meta[['sat_id','priority','priority_score']],on='sat_id',suffixes=('','_truth'),validate='many_to_one')
        assert (truth.priority==truth.priority_truth).all() and (truth.priority_score==truth.priority_score_truth).all()
        assert np.isfinite(candidate[['t_start_s','t_end_s','dur_s']]).all().all()
        assert audit['all_pass'] and audit['exact_endpoints_included'] and audit['tasks']==len(candidate)
        assert not rules.plan_violations(candidate,w)
        io_schema.save_plan(candidate,out/'final_plan.csv');save(out/'final_score.json',score)
        report.update(status='accepted',stage='completed',final_score=score,hard_violations=0,full_interval_pass=True,gain_vs_v5=score['total_score']-baseline_score['total_score'],final_csv_sha256=sha(out/'final_plan.csv'))
        print(json.dumps({k:report[k] for k in ['algorithm','seed','budget_s','gain_vs_v5','status']}) ,flush=True)
    except BaseException as e:report.update(status='failed',error=repr(e));traceback.print_exc();raise
    finally:
        stop.set();report['runtime_total_s']=time.perf_counter()-started;report['peak_rss_mib']=max(peak[0],proc.memory_info().rss)/1048576;save(out/'trial.json',report)
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--algorithm',choices=['v4','v5','v6'],required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--budget',type=float,required=True);p.add_argument('--out',type=Path,required=True);run(p.parse_args())
