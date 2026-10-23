"""Sequential, resumable equal-budget comparison; pilot must pass first."""
import os,sys,json,subprocess,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from run_v6_trial import save
def main():
    p=argparse.ArgumentParser();p.add_argument('--budgets',type=float,nargs='+',default=[12,36]);p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33]);p.add_argument('--out',type=Path,default=ROOT/'data/out/v6_comparison');args=p.parse_args()
    pilot=json.loads((args.out/'pilot_b12_v6/trial.json').read_text(encoding='utf-8'))
    assert pilot['status']=='accepted' and pilot['gain_vs_v5']>0 and pilot['full_interval_pass'],'Validated pilot improvement required'
    # Guard against concurrent comparisons sharing the same output directory.
    args.out.mkdir(parents=True,exist_ok=True);lock=args.out/'comparison.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise RuntimeError('Comparison lock exists; inspect recorded PID before removing a stale lock')
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    progress={'status':'running','budgets':args.budgets,'seeds':args.seeds,'common_start':'sealed accepted V5, 30682.990429546662','completed':[]}
    try:
        for budget in args.budgets:
            for seed in args.seeds:
                for alg in ['v4','v5','v6']:
                    name=f'formal_b{budget:g}_s{seed}_{alg}';folder=args.out/name
                    cmd=[sys.executable,str(ROOT/'scripts/run_v6_trial.py'),'--algorithm',alg,'--seed',str(seed),'--budget',str(budget),'--out',str(folder)]
                    with (args.out/(name+'.stdout.log')).open('a',encoding='utf-8') as log:
                        subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
                    r=json.loads((folder/'trial.json').read_text(encoding='utf-8'));assert r['status']=='accepted'
                    progress['completed'].append({'name':name,'score':r['final_score']['total_score'],'gain':r['gain_vs_v5']})
                    save(args.out/'comparison_progress.json',progress);print(progress['completed'][-1],flush=True)
        progress['status']='completed';save(args.out/'comparison_progress.json',progress)
    finally:lock.unlink(missing_ok=True)
if __name__=='__main__':main()
