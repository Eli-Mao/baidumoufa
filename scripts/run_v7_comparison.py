"""Sequential equal-budget searches; independent audits in a separate phase."""
import argparse,concurrent.futures,hashlib,json,os,shutil,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,obj):
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8');temp.replace(p)

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--budget',type=float,default=36.);p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33])
    p.add_argument('--validation-workers',type=int,choices=[1,2],default=2);p.add_argument('--wait-for',type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if a.wait_for:
        deadline=time.monotonic()+600.
        while True:
            r=read(a.wait_for)
            if r['status']=='accepted':break
            if r['status']=='rejected_or_failed':raise RuntimeError('Pilot failed; preserve all evidence and fix before scaling')
            if time.monotonic()>deadline:raise TimeoutError('Pilot not accepted within ten minutes')
            time.sleep(3.)
    protocol=dict(initial_plan_sha256=hashlib.sha256((ROOT/'accepted/v6/plans/score_priority.csv').read_bytes()).hexdigest(),
        budget_s=a.budget,seeds=a.seeds,algorithms=['v6','v7'],baseline_score=31015.978085736664,
        search_processes=1,validation_workers=a.validation_workers,pilot_included=False,
        code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        budget_definition='Search includes state/catalog/index construction and proposed-task physical queries. Input loading and final validation are outside the identical search allocation.',
        ordering='Algorithms alternate by seed. All searches finish before any formal independent audit starts.',
        std_definition='sample standard deviation, ddof=1')
    path=a.out/'protocol.json'
    if path.exists():assert read(path)==protocol,'Comparison protocol changed'
    else:save(path,protocol)
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    trials=[]
    for k,seed in enumerate(a.seeds):
        for alg in (['v6','v7'] if k%2==0 else ['v7','v6']):
            out=a.out/f'b{a.budget:g}_s{seed}_{alg}';trials.append((alg,seed,out))
    def launch(item,phase):
        alg,seed,out=item
        args=[sys.executable,'-u',str(ROOT/'scripts/run_v7_trial.py'),'--algorithm',alg,'--seed',str(seed),
            '--budget',str(a.budget),'--phase',phase,'--cache',str(a.cache.resolve()),'--out',str(out.resolve())]
        with (a.out/f'{out.name}_{phase}.log').open('a',encoding='utf-8') as log:
            subprocess.run(args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        result=read(out/'trial.json');print(phase,out.name,result['status'],flush=True);return result
    for trial in trials:
        receipt=trial[2]/'trial.json'
        if receipt.exists() and read(receipt)['status'] in ('provisional','accepted'):
            print('search exists',trial[2].name,flush=True);continue
        launch(trial,'search')
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.validation_workers) as executor:
        futures=[executor.submit(launch,t,'validate') for t in trials]
        for future in concurrent.futures.as_completed(futures):future.result()
    records=[read(t[2]/'trial.json') for t in trials];assert all(r['status']=='accepted' for r in records)
    summary=[]
    for alg in ('v6','v7'):
        rows=[r for r in records if r['algorithm']==alg]
        summary.append(dict(algorithm=alg,budget_s=a.budget,n=len(rows),
            score_mean=statistics.mean(r['final_score']['total_score'] for r in rows),
            score_std_sample=statistics.stdev(r['final_score']['total_score'] for r in rows) if len(rows)>1 else None,
            coverage_mean=statistics.mean(r['final_score']['n_covered'] for r in rows),
            score_max=max(r['final_score']['total_score'] for r in rows),
            search_s_mean=statistics.mean(r['search']['search_wall_s'] for r in rows),
            search_peak_rss_mib_max=max(r['search_peak_rss_mib'] for r in rows)))
    paired=[]
    for seed in a.seeds:
        v={r['algorithm']:r['final_score'] for r in records if r['seed']==seed}
        paired.append(dict(seed=seed,score_gain_v7_minus_v6=v['v7']['total_score']-v['v6']['total_score'],
            coverage_gain_v7_minus_v6=v['v7']['n_covered']-v['v6']['n_covered']))
    best=max((t for t in trials if t[0]=='v7'),key=lambda t:read(t[2]/'trial.json')['final_score']['total_score'])
    for src,dst in [('final_plan.csv','best_v7_plan.csv'),('final_score.json','best_v7_score.json'),
        ('physics_audit.json','best_v7_physics.json'),('physics_audit.csv','best_v7_physics.csv')]:shutil.copy2(best[2]/src,a.out/dst)
    save(a.out/'comparison.json',dict(protocol=protocol,summary=summary,paired=paired,best_v7_trial=str(best[2].resolve()),
        accepted_trials=[dict(algorithm=r['algorithm'],seed=r['seed'],score=r['final_score'],
            search_s=r['search']['search_wall_s'],search_peak_rss_mib=r['search_peak_rss_mib'],
            physics_s=r['physics_s'],final_csv_sha256=r['final_csv_sha256'],hard_violations=0,full_interval_pass=True) for r in records]))
    print(json.dumps(dict(summary=summary,paired=paired)),flush=True)

if __name__=='__main__':main()
