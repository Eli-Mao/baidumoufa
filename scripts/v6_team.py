"""Portable V6 handoff entry point; frozen algorithms and score remain unchanged."""
from pathlib import Path
import argparse,hashlib,json,os,sys,shutil,subprocess,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['verify','select','optimize','audit']);p.add_argument('--release',type=Path,required=True);p.add_argument('--cache',type=Path);p.add_argument('--mode',choices=['score','coverage'],default='score');p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=11);p.add_argument('--budget',type=float,default=36);a=p.parse_args()
    release=a.release.resolve();plan=release/'plans'/f'{a.mode}_priority.csv'
    if a.action=='optimize' and a.mode!='score':p.error('Frozen V6 optimize uses score acceptance; use select --mode coverage for the accepted coverage alternative')
    assert plan.exists()
    expected=json.loads((release/'provenance/initial_seal.json').read_text(encoding='utf-8'))
    assert sha(plan)==expected['core_artifact_sha256'][f'plans/{a.mode}_priority.csv'],'Plan SHA differs from sealed accepted result'
    if a.action=='select':
        if a.out.exists():raise FileExistsError('Choose a new output path; existing files are preserved')
        a.out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(plan,a.out);print(json.dumps({'selected':a.mode,'sha256':sha(a.out),'file':str(a.out)}));return
    a.out.mkdir(parents=True,exist_ok=True)
    if a.action=='audit':
        import audit_v6_physics
        started=time.perf_counter();r=audit_v6_physics.run(plan,a.out/'physics.json');r['elapsed_s']=time.perf_counter()-started
        assert r['all_pass'] and r['exact_endpoints_included'] and r['bad_sgp4_samples']==0
        (a.out/'physics.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r));return
    if a.cache is None:p.error('--cache is required for verify/optimize')
    cache=a.cache.resolve()
    identity=json.loads((release/'provenance/historical_identity.json').read_text(encoding='utf-8'))
    for name in ['windows.csv','selected_targets.csv']:
        digests={v for k,v in identity.items() if Path(k).name==name}
        assert len(digests)==1 and sha(cache/name) in digests,'Wrong cached input: '+name
    if a.action=='verify':
        from satplan import optimize
        from verify_v6_csv import verify
        r=verify(plan,cache/'selected_targets.csv',cache/'windows.csv')
        value=optimize.evaluate(plan,windows_path=cache/'windows.csv',sat_meta_path=cache/'selected_targets.csv',coverage_weight=0.)
        assert abs(value-r['independent_csv_score'])<1e-8
        r.update(evaluator_score=value,plan_sha256=sha(plan),coverage_weight=0.,physical_status='Run audit separately, or use hashed historical certificate; Evaluator itself checks scheduling only')
        (a.out/'evaluation.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r));return
    # Always refine the same frozen V5 baseline for comparable experiments.
    env=os.environ.copy();env['V6_CACHE_DIR']=str(cache);env['V6_BASELINE_DIR']=str(release/'baselines/v5');env['OPENBLAS_NUM_THREADS']='1';env['OMP_NUM_THREADS']='1';env['PYTHONDONTWRITEBYTECODE']='1'
    subprocess.run([sys.executable,str(ROOT/'scripts/run_v6_trial.py'),'--algorithm','v6','--seed',str(a.seed),'--budget',str(a.budget),'--out',str(a.out.resolve())],cwd=ROOT,env=env,check=True)
if __name__=='__main__':main()
