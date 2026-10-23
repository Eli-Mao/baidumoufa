"""300s five-seed frozen comparison; 600s stage gated on validated advantage."""
import argparse,json,os,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,obj):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n');t.replace(p)

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cpu',type=int,default=6);p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33,44,55]);p.add_argument('--budgets',type=int,nargs='+',default=[300,600])
    a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    assert len(a.seeds)>=5 and len(set(a.seeds))==len(a.seeds)
    protocol=dict(algorithms=['v6','v7'],budgets_s=a.budgets,seeds=a.seeds,cpu_affinity=[a.cpu],concurrency=1,
        baseline_commit='42eabbfe1739be22fbe3550986aef97b6fd38303',baseline_score=31426.364999713333,
        baseline_plan_sha256='3e2b0265c95df472a7c55bb84a848930fa7541663ea886e3b5ff2e0ca4e91426',
        gate='600s only if accepted 300s V7 mean beats V6 and at least 4/5 paired seeds improve',
        budget_definition='Wall time including engine construction and candidate physics; CPU seconds, page faults and memory pressure also recorded.',
        scheduling='One search process at a time pinned to same logical CPU; algorithms alternate first position by seed. No concurrent audit during searches.',
        std='sample, ddof=1',raw_orbit_propagation=False,push=False)
    protocol_path=a.out/'protocol.json'
    if protocol_path.exists():assert read(protocol_path)==protocol
    else:save(protocol_path,protocol)
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    def launch(algorithm,seed,budget,phase):
        directory=a.out/f'b{budget}_s{seed}_{algorithm}';receipt=directory/'trial.json'
        if receipt.exists():
            old=read(receipt)
            if old['status']=='accepted' or (phase=='search' and old['status']=='provisional'):return old
        save(a.out/'pipeline_status.json',dict(status='running',algorithm=algorithm,seed=seed,budget_s=budget,phase=phase,trial=str(directory)))
        args=[sys.executable,'-u',str(ROOT/'scripts/run_v7_round2_trial.py'),'--algorithm',algorithm,'--seed',str(seed),'--budget',str(budget),
            '--cache',str(a.cache.resolve()),'--out',str(directory),'--phase',phase,'--cpu',str(a.cpu)]
        with (a.out/f'{directory.name}_{phase}.log').open('a',encoding='utf-8') as log:
            subprocess.run(args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        result=read(receipt);print(phase,directory.name,result['status'],result.get('evaluator_score',result.get('search',{}).get('candidate_score')),flush=True)
        return result
    previous=None
    for budget in a.budgets:
        if budget>300 and previous is not None and not previous['advance_gate_pass']:
            save(a.out/'pipeline_status.json',dict(status='600s_skipped_gate_not_met',previous=previous));return
        order=[(alg,seed) for k,seed in enumerate(a.seeds) for alg in (['v6','v7'] if k%2==0 else ['v7','v6'])]
        for alg,seed in order:launch(alg,seed,budget,'search')
        records=[launch(alg,seed,budget,'validate') for alg,seed in order]
        assert all(r['status']=='accepted' for r in records)
        summary=[]
        for alg in ['v6','v7']:
            group=[r for r in records if r['algorithm']==alg];scores=[r['evaluator_score'] for r in group]
            summary.append(dict(algorithm=alg,n=len(group),budget_s=budget,score_mean=statistics.mean(scores),score_std_sample=statistics.stdev(scores),
                score_best=max(scores),score_worst=min(scores),coverage_mean=statistics.mean(r['final_score']['n_covered'] for r in group),
                coverage_rate_mean=statistics.mean(r['final_score']['coverage_rate'] for r in group),
                search_wall_s_mean=statistics.mean(r['search_wall_s_measured'] for r in group),search_cpu_s_mean=statistics.mean(r['search_cpu_s'] for r in group),
                peak_rss_mib=max(r['search_peak_rss_mib'] for r in group),tasks_mean=statistics.mean(r['final_score']['n_tasks'] for r in group)))
        pairs=[]
        for seed in a.seeds:
            r={x['algorithm']:x for x in records if x['seed']==seed}
            pairs.append(dict(seed=seed,score_gain=r['v7']['evaluator_score']-r['v6']['evaluator_score'],
                coverage_gain=r['v7']['final_score']['n_covered']-r['v6']['final_score']['n_covered'],
                cpu_s_v6=r['v6']['search_cpu_s'],cpu_s_v7=r['v7']['search_cpu_s']))
        passed=summary[1]['score_mean']>summary[0]['score_mean']+1e-7 and sum(r['score_gain']>1e-7 for r in pairs)>=4
        previous=dict(budget_s=budget,summary=summary,paired=pairs,advance_gate_pass=passed,
            accepted_trials=[dict(algorithm=r['algorithm'],seed=r['seed'],final_score=r['final_score'],csv_sha256=r['final_csv_sha256'],
                search_cpu_s=r['search_cpu_s'],search_wall_s=r['search_wall_s_measured'],peak_rss_mib=r['search_peak_rss_mib'],hard_violations=0,full_interval_pass=True) for r in records])
        save(a.out/f'comparison_b{budget}.json',previous);print(json.dumps(previous['summary']),flush=True)
    save(a.out/'pipeline_status.json',dict(status='completed',budgets=a.budgets))

if __name__=='__main__':main()
