"""One isolated budgeted trial, followed by complete independent acceptance."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
import sys,argparse,time,json,hashlib,threading,shutil,traceback,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import psutil,pandas as pd,numpy as np
from satplan import io_schema,rules,config,v5
from satplan.v5_physics import PhysicalOracle
import audit_plan_physics,repair_plan_physics,v4_budget_reference
BASE=Path('D:/SatelliteProject_GitHub/data/out/real_aug2026_10000')
def save(p,o):
    q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(o,indent=2,ensure_ascii=False),encoding='utf-8');q.replace(p)
def fingerprint(p):
    cols=['station_id','sat_id','priority','priority_score','t_start_s','t_end_s','dur_s']
    return hashlib.sha256(p[cols].sort_values(['station_id','t_start_s','sat_id']).to_csv(index=False,float_format='%.9f').encode()).hexdigest()
def main(args):
    out=args.out;out.mkdir(parents=True,exist_ok=True);report={'status':'running','algorithm':args.algorithm,'seed':args.seed,'budget_s':args.budget,'stages_s':{}};save(out/'trial.json',report)
    proc=psutil.Process();peak=[proc.memory_info().rss];stop=threading.Event();started=time.perf_counter()
    def monitor():
        while not stop.wait(.1):peak[0]=max(peak[0],proc.memory_info().rss)
    threading.Thread(target=monitor,daemon=True).start()
    def stage(name,fn):
        report['stage']=name;save(out/'trial.json',report);print('[trial]',args.algorithm,args.seed,args.budget,name,flush=True);t=time.perf_counter();value=fn();report['stages_s'][name]=time.perf_counter()-t;return value
    try:
        def sha(path):
            h=hashlib.sha256()
            with Path(path).open('rb') as f:
                for block in iter(lambda:f.read(1048576),b''):h.update(block)
            return h.hexdigest()
        frozen=json.loads((BASE/'experiment_report.json').read_text())
        report['input_sha256']={name:sha(ROOT/name) for name in frozen['identity']['inputs_sha256']}
        assert report['input_sha256']==frozen['identity']['inputs_sha256']
        report['planning_start_utc']=config.PLAN_T0_UTC;report['planning_days']=config.PLAN_DAYS
        report['windows_sha256']=sha(BASE/'windows.csv');report['baseline_plan_sha256']=sha(BASE/'final_plan.csv')
        report['code_sha256']={str(p.relative_to(ROOT)):sha(p) for folder in ['src','scripts','tests'] for p in (ROOT/folder).rglob('*.py')}
        report['git_parent']=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        report['timing_scope']='Same allocated optimizer wall budget including in-search preparation and V5 move physics; shared input parsing and final acceptance measured separately. Identical baseline physics certificates may be reused; every changed plan is fully resampled.'
        base=io_schema.load_plan(BASE/'final_plan.csv');w=io_schema.load_windows(BASE/'windows.csv');meta=pd.read_csv(BASE/'selected_targets.csv')
        assert len(w)==531432 and len(base)==6849 and meta.sat_id.nunique()==10000
        oracle=PhysicalOracle() if args.algorithm=='v5' else None
        if args.algorithm=='v5':candidate,stats=stage('search',lambda:v5.search(base,w,meta,budget_s=args.budget,seed=args.seed,physical=oracle))
        else:candidate,stats=stage('search',lambda:v4_budget_reference.search(base,w,meta,budget_s=args.budget,seed=args.seed))
        if 'trace' in stats:save(out/'move_trace.json',stats.pop('trace'))
        report['search']=stats
        if oracle:report['oracle']={'evaluations':oracle.calls,'cache_hits':oracle.hits,'samples':oracle.samples}
        report['candidate_score']=rules.score_plan(candidate,w,meta)
        candidate_path=out/'candidate_plan.csv';io_schema.save_plan(candidate,candidate_path)
        issues=stage('complete_hard_check',lambda:rules.plan_violations(candidate,w,max_report=1000000))
        if issues:save(out/'hard_failures.json',issues);raise RuntimeError('Search produced hard-invalid plan')
        same=fingerprint(candidate)==fingerprint(base)
        if same:
            candidate=base.copy();io_schema.save_plan(candidate,candidate_path)
            shutil.copy2(BASE/'final_physics_audit.csv',out/'physics_audit.csv')
            audit=json.loads((BASE/'final_physics_audit.json').read_text());audit['reused_identical_v4_baseline']=True
            audit['semantic_plan_sha256']=fingerprint(candidate);save(out/'physics_audit.json',audit)
            report['physics_reuse']='Exact same task geometry as sealed V4; original full all-task audit retained. No improved candidate was skipped.'
        else:
            audit=stage('independent_full_interval_audit',lambda:audit_plan_physics.run(candidate_path,out/'physics_audit.json'))
        if not audit['all_pass']:
            stage('physical_repair',lambda:repair_plan_physics.run(candidate_path,BASE/'windows.csv',out/'repair.json'))
            candidate=io_schema.load_plan(out/'repair.csv');io_schema.save_plan(candidate,candidate_path)
            audit=stage('repeat_full_interval_audit',lambda:audit_plan_physics.run(candidate_path,out/'physics_audit.json'))
            if not audit['all_pass']:
                bad=pd.read_csv(out/'physics_audit.csv');reject=bad.loc[~bad['pass'],'task_id'];candidate=candidate[~candidate.task_id.isin(reject)].copy();candidate.to_csv(out/'after_physical_rejection.csv',index=False);io_schema.save_plan(candidate,candidate_path)
                audit=stage('final_full_interval_audit',lambda:audit_plan_physics.run(candidate_path,out/'physics_audit.json'))
        score=rules.score_plan(candidate,w,meta);baseline_score=rules.score_plan(base,w,meta)
        if score['total_score']<baseline_score['total_score']-1e-8:
            candidate=base.copy();score=baseline_score;report['fallback_to_sealed_v4']=True
            io_schema.save_plan(candidate,candidate_path);audit=stage('fallback_full_audit',lambda:audit_plan_physics.run(candidate_path,out/'physics_audit.json'))
        assert audit['all_pass'] and audit['tasks']==len(candidate) and not rules.plan_violations(candidate,w)
        truth=candidate.merge(meta[['sat_id','priority','priority_score']],on='sat_id',suffixes=('','_truth'),validate='many_to_one')
        assert (truth.priority==truth.priority_truth).all() and (truth.priority_score==truth.priority_score_truth).all()
        assert np.isfinite(candidate[['t_start_s','t_end_s','dur_s']]).all().all()
        io_schema.save_plan(candidate,out/'final_plan.csv');save(out/'final_score.json',score)
        report.update(status='accepted',stage='completed',final_score=score,gain_vs_v4=score['total_score']-baseline_score['total_score'],full_interval_pass=True,hard_violations=0,plan_fingerprint=fingerprint(candidate),baseline_fingerprint=fingerprint(base))
        print(json.dumps({'status':'accepted','algorithm':args.algorithm,'seed':args.seed,'budget':args.budget,'score':score['total_score'],'coverage':score['n_covered'],'gain':report['gain_vs_v4']},ensure_ascii=False),flush=True)
    except BaseException as e:
        report.update(status='failed',error=repr(e));traceback.print_exc();raise
    finally:
        stop.set();report['runtime_total_s']=time.perf_counter()-started;report['peak_rss_mib']=max(peak[0],proc.memory_info().rss)/1048576;save(out/'trial.json',report)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--algorithm',choices=['v4','v5'],required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--budget',type=float,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
