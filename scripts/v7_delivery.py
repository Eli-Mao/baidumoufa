"""Frozen V7 handoff entry point. A evaluates; B searches; audit needs raw inputs."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    e=sub.add_parser('evaluate');e.add_argument('--out',type=Path,required=True)
    e=sub.add_parser('audit');e.add_argument('--out',type=Path,required=True)
    e=sub.add_parser('search');e.add_argument('--cache',type=Path,required=True);e.add_argument('--out',type=Path,required=True)
    e.add_argument('--budget',type=float,default=600);e.add_argument('--seed',type=int,default=44);e.add_argument('--cpu',type=int)
    a=p.parse_args();plan=ROOT/'accepted/v7_round2/best_accepted_plan.csv';release=ROOT/'accepted/v7_delivery'
    manifest=json.loads((release/'delivery_manifest.json').read_text(encoding='utf-8'))
    for rel,digest in manifest['files'].items():
        if sha(ROOT/rel)!=digest:raise ValueError('Frozen delivery identity differs: '+rel)
    if a.action=='search':
        cmd=[sys.executable,str(ROOT/'scripts/run_v7_round2_trial.py'),'--algorithm','v7','--budget',str(a.budget),'--seed',str(a.seed),
            '--cache',str(a.cache.resolve()),'--out',str(a.out.resolve()),'--phase','all']
        if a.cpu is not None:cmd+=['--cpu',str(a.cpu)]
        subprocess.run(cmd,cwd=ROOT,check=True);return
    if a.out.exists():raise FileExistsError('Choose a new output path; existing evidence is preserved')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    if a.action=='audit':
        import audit_v6_physics
        r=audit_v6_physics.run(plan,a.out,step_s=1.)
        if not r['all_pass'] or not r['exact_endpoints_included'] or r['bad_sgp4_samples']:raise RuntimeError('Independent physical audit failed')
        print(json.dumps(r));return
    from satplan import optimize
    from verify_v6_csv import verify
    windows=release/'plan_support_windows.csv';targets=release/'selected_targets.csv'
    r=verify(plan,targets,windows);score=optimize.evaluate(plan,windows_path=windows,sat_meta_path=targets,coverage_weight=0.)
    if abs(score-manifest['accepted_score'])>1e-7 or abs(score-r['independent_csv_score'])>1e-7:raise ValueError('Score differs from accepted result')
    r.update(evaluator_score=score,level='A',plan_sha256=sha(plan),window_scope='original-cache support subset for this exact delivered plan only',
        physical_status='Historical certificate hash checked. No new physical sampling in level A. Use audit with authorized TLE/stations/ephemeris.',
        full_search_reproduced=False,full_orbit_propagation=False)
    a.out.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(r))
if __name__=='__main__':main()
