"""Sequential, resumable pilot and multi-seed equal-budget comparisons."""
from pathlib import Path
import json,sys,subprocess,time,os,argparse
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/out/v5_comparison'
def save(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(path)
def run():
    OUT.mkdir(parents=True,exist_ok=True)
    sequence=[('pilot',10,20261023,'v5'),('pilot',10,20261023,'v4')]+[('formal',budget,seed,algorithm) for budget in [20,60] for seed in [11,22,33] for algorithm in ['v4','v5']]
    records=[];best=29443.647526046665;pilot_gain=None
    for phase,budget,seed,algorithm in sequence:
        trial=OUT/f'{phase}_b{budget}_s{seed}_{algorithm}';path=trial/'trial.json'
        state={'status':'running','current':{'phase':phase,'budget':budget,'seed':seed,'algorithm':algorithm},'completed_trials':records,'best_validated_score':best}
        save(OUT/'comparison_progress.json',state)
        if not path.exists() or json.loads(path.read_text(encoding='utf-8')).get('status')!='accepted':
            trial.mkdir(exist_ok=True)
            command=[sys.executable,'-u',str(ROOT/'scripts/run_v5_trial.py'),'--algorithm',algorithm,'--seed',str(seed),'--budget',str(budget),'--out',str(trial)]
            print('[comparison]',phase,budget,seed,algorithm,flush=True)
            with (trial/'run.log').open('w',encoding='utf-8') as log,(trial/'run.err.log').open('w',encoding='utf-8') as err:
                done=subprocess.run(command,cwd=ROOT,stdout=log,stderr=err)
            if done.returncode:
                state.update(status='failed',failed_trial=str(trial));save(OUT/'comparison_progress.json',state);raise RuntimeError(f'Trial failed: {trial}')
        result=json.loads(path.read_text(encoding='utf-8'))
        assert result['status']=='accepted' and result['full_interval_pass'] and not result['hard_violations']
        score=result['final_score']['total_score'];best=max(best,score)
        records.append({'phase':phase,'budget':budget,'seed':seed,'algorithm':algorithm,'score':score,'covered':result['final_score']['n_covered'],'tasks':result['final_score']['n_tasks'],'gain':result['gain_vs_v4'],'trial':str(trial)})
        if phase=='pilot' and algorithm=='v5':
            pilot_gain=result['gain_vs_v4']
            if pilot_gain<=0:
                state.update(status='pilot_no_improvement',completed_trials=records);save(OUT/'comparison_progress.json',state);return
    save(OUT/'comparison_progress.json',{'status':'completed','completed_trials':records,'best_validated_score':best,'pilot_gain':pilot_gain})
    print(json.dumps({'status':'completed','trials':len(records),'best_validated_score':best}),flush=True)
if __name__=='__main__':run()
