"""Reconcile the completed local experiments and create portable V5 deliverables."""
from pathlib import Path
import argparse,json,hashlib,shutil,subprocess,zipfile,sys
import pandas as pd,numpy as np
SESSION=Path('D:/Codex/2026-10-23/files-pasted-by-the-user-10000')
p=argparse.ArgumentParser();p.add_argument('--project',type=Path,default=SESSION/'work/v5_project');p.add_argument('--baseline',type=Path,default=Path('D:/SatelliteProject_GitHub/data/out/real_aug2026_10000'));p.add_argument('--output',type=Path,default=SESSION/'outputs/v5_results');args=p.parse_args()
ROOT=args.project;BASE=args.baseline;OUT=args.output;COMP=ROOT/'data/out/v5_comparison';ANALYSIS=ROOT/'data/out/v5_analysis'
sys.path.insert(0,str(ROOT/'src'))
from satplan import rules,config
from satplan.v5 import State,Catalog
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def write_json(path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
def table(frame):
    columns=list(frame.columns);lines=['| '+' | '.join(map(str,columns))+' |','|'+'|'.join(['---']*len(columns))+'|']
    for row in frame.itertuples(index=False,name=None):lines.append('| '+' | '.join(str(v) for v in row)+' |')
    return '\n'.join(lines)
def git(*parts):return subprocess.check_output(['git','-C',str(ROOT),*parts],text=True,encoding='utf-8').strip()

def main():
    progress=json.loads((COMP/'comparison_progress.json').read_text(encoding='utf-8'));assert progress['status']=='completed'
    OUT.mkdir(parents=True,exist_ok=True);baseline=pd.read_csv(BASE/'final_plan.csv');meta=pd.read_csv(BASE/'selected_targets.csv');windows=pd.read_csv(BASE/'windows.csv')
    baseline_score=json.loads((BASE/'final_score.json').read_text());seal=json.loads((SESSION/'outputs/v4_sealed/seal_manifest.json').read_text())
    for name,digest in seal['complete_original_tree_sha256'].items():assert sha(BASE/name)==digest,('V4 changed',name)
    records=[];trials={};core_hashes={}
    for record in progress['completed_trials']:
        folder=Path(record['trial']);r=json.loads((folder/'trial.json').read_text());plan=pd.read_csv(folder/'final_plan.csv');s=r['final_score']
        assert r['status']=='accepted' and r['full_interval_pass'] and r['hard_violations']==0
        assert len(plan)==s['n_tasks'] and plan.sat_id.nunique()==s['n_covered']
        truthful=plan.merge(meta[['sat_id','priority','priority_score']],on='sat_id',suffixes=('','_truth'),validate='many_to_one')
        assert (truthful.priority==truthful.priority_truth).all() and (truthful.priority_score==truthful.priority_score_truth).all()
        independent=float((truthful.priority_truth.map(config.PRIORITY_SCORE)*(.6+.4*(truthful.dur_s-120.)/120.)).sum())
        assert abs(independent-s['total_score'])<1e-7
        audit=pd.read_csv(folder/'physics_audit.csv');assert audit['pass'].all() and len(audit)==len(plan) and audit.exact_end_included.all() and audit.bad_sgp4_samples.sum()==0
        assert set(audit.task_id)==set(plan.task_id)
        for path,digest in r['code_sha256'].items():
            if Path(path).name in ['v5.py','v5_physics.py','v4_budget_reference.py','rules.py','config.py','audit_plan_physics.py','repair_plan_physics.py']:
                if path in core_hashes:assert core_hashes[path]==digest,('mixed algorithms',path)
                core_hashes[path]=digest
                assert sha(ROOT/path)==digest
        for path,digest in r['input_sha256'].items():assert sha(ROOT/path)==digest
        assert r['windows_sha256']==seal['complete_original_tree_sha256']['windows.csv']
        assert r['baseline_plan_sha256']==seal['complete_original_tree_sha256']['final_plan.csv']
        search=r['search']['search_wall_s']
        records.append({'phase':record['phase'],'budget_s':record['budget'],'seed':record['seed'],'algorithm':record['algorithm'],'valid_score':s['total_score'],'gain_vs_v4':r['gain_vs_v4'],'gain_pct':r['gain_vs_v4']/baseline_score['total_score']*100,'n_tasks':s['n_tasks'],'n_covered':s['n_covered'],'coverage_rate':s['coverage_rate'],'high_covered':s['by_priority']['high']['n_covered'],'mid_covered':s['by_priority']['mid']['n_covered'],'low_covered':s['by_priority']['low']['n_covered'],'search_wall_s':search,'total_wall_s':r['runtime_total_s'],'additional_reaudit_s':r.get('additional_full_reaudit_s',0.),'peak_rss_mib':r['peak_rss_mib'],'hard_violations':r['hard_violations'],'all_physical_pass':True,'baseline_audit_reused':bool(r.get('physics_reuse')),'trial':str(folder)})
        trials[str(folder)]=r
    frame=pd.DataFrame(records);formal=frame[frame.phase=='formal'].copy();assert len(formal)==12
    paired=formal.pivot(index=['budget_s','seed'],columns='algorithm',values='valid_score');assert (paired.v5>paired.v4).all()
    assert formal[formal.algorithm=='v5'].groupby('budget_s').size().to_dict()=={20:3,60:3}
    bestrow=formal[formal.algorithm=='v5'].sort_values('valid_score',ascending=False).iloc[0];bestfolder=Path(bestrow.trial);best=pd.read_csv(bestfolder/'final_plan.csv');bestreport=trials[str(bestfolder)];bestscore=bestreport['final_score']
    assert not rules.plan_violations(best,windows,max_report=1000000)
    testlog=(ROOT/'data/out/v5_tests.log').read_text(encoding='utf-8-sig');assert 'Ran 45 tests' in testlog and '\nOK' in testlog
    frame.to_csv(OUT/'all_trials.csv',index=False);formal.to_csv(OUT/'fair_comparison.csv',index=False)
    shutil.copy2(SESSION/'outputs/v4_sealed/seal_manifest.json',OUT/'v4_seal_manifest.json')
    shutil.copy2(SESSION/'outputs/v4_sealed/v4_10000_acceptance.bundle',OUT/'v4_baseline.bundle')
    summary=formal.groupby(['budget_s','algorithm']).agg(mean_score=('valid_score','mean'),std_score=('valid_score','std'),min_score=('valid_score','min'),max_score=('valid_score','max'),mean_covered=('n_covered','mean'),mean_search_s=('search_wall_s','mean'),mean_total_s=('total_wall_s','mean'),max_peak_mib=('peak_rss_mib','max')).reset_index()
    summary.to_csv(OUT/'budget_summary.csv',index=False)
    for src,dst in [('final_plan.csv','best_v5_plan.csv'),('final_score.json','best_v5_score.json'),('physics_audit.csv','best_v5_physics_audit.csv'),('physics_audit.json','best_v5_physics_audit.json'),('trial.json','best_v5_trial.json'),('move_trace.json','best_v5_move_trace.json')]:
        if (bestfolder/src).exists():shutil.copy2(bestfolder/src,OUT/dst)
    counts=meta.copy();oldcounts=baseline.groupby('sat_id').size();newcounts=best.groupby('sat_id').size();counts['v4_observations']=counts.sat_id.map(oldcounts).fillna(0).astype(int);counts['v5_observations']=counts.sat_id.map(newcounts).fillna(0).astype(int);counts.to_csv(OUT/'target_observation_counts.csv',index=False)
    newly=counts[(counts.v4_observations==0)&(counts.v5_observations>0)];lost=counts[(counts.v4_observations>0)&(counts.v5_observations==0)]
    newly.to_csv(OUT/'newly_covered_targets.csv',index=False);lost.to_csv(OUT/'lost_covered_targets.csv',index=False)
    high=pd.read_csv(ANALYSIS/'uncovered_high_30.csv');state_initial=State(pd.read_csv(BASE/'v4_plan.csv'));catalog=Catalog(windows)
    high['initial_max_free_span_s']=[max([b-a for wi in catalog.by_sat[sid] for a,b in state_initial.free_intervals(int(catalog.site[wi]),int(sid),float(catalog.start[wi]),float(catalog.end[wi]))],default=0.) for sid in high.sat_id]
    high['cause_detail']=['repair_created_or_enlarged_gap' if a<120 and b>=120 else ('fixed_240s_duration_misses_short_gap' if 120<=a<240 else ('all_cached_windows_station_blocked' if b<120 else 'candidate_order_or_repair_changed_opportunities')) for a,b in zip(high.initial_max_free_span_s,high.max_free_span_s)]
    high['covered_in_best_v5']=high.sat_id.isin(best.sat_id);high.to_csv(OUT/'high_priority_30_diagnosis.csv',index=False)
    priority=[]
    for key,label in [('high','高'),('mid','中'),('low','低')]:
        a,b=baseline_score['by_priority'][key],bestscore['by_priority'][key];total=int((meta.priority==key).sum());priority.append({'优先级':label,'目标数':total,'V4覆盖':a['n_covered'],'V5覆盖':b['n_covered'],'V4覆盖率':f'{a["coverage_rate"]:.2%}','V5覆盖率':f'{b["coverage_rate"]:.2%}','V4得分':f'{a["score"]:.6f}','V5得分':f'{b["score"]:.6f}'})
    pd.DataFrame(priority).to_csv(OUT/'priority_comparison.csv',index=False)
    stations=pd.read_csv(ANALYSIS/'station_utilization.csv');stations['v5_tasks']=stations.station_id.map(best.groupby('station_id').size());stations['v5_observation_s']=stations.station_id.map(best.groupby('station_id').dur_s.sum());stations['v5_calendar_utilization']=(stations.v5_observation_s+30*(stations.v5_tasks-1))/518400;stations['v5_observation_fraction_of_candidate_union']=stations.v5_observation_s/stations.candidate_union_s;stations.to_csv(OUT/'station_comparison.csv',index=False)
    replacements=pd.read_csv(ANALYSIS/'replacement_opportunities.csv');actual=replacements[replacements.blocking_task_ids.notna()&(replacements.blocked_score>0)].copy();actual.to_csv(OUT/'profitable_conflict_replacements.csv',index=False)
    state=State(best);remaining=counts[(counts.priority=='high')&(counts.v5_observations==0)].copy()
    remaining['max_remaining_free_span_s']=[max([b-a for wi in catalog.by_sat[sid] for a,b in state.free_intervals(int(catalog.site[wi]),int(sid),float(catalog.start[wi]),float(catalog.end[wi]))],default=0.) for sid in remaining.sat_id];remaining.to_csv(OUT/'remaining_high_priority.csv',index=False)
    for name in ['uncovered_opportunities.csv','analysis.json','station_utilization.csv']:
        shutil.copy2(ANALYSIS/name,OUT/name)
    shutil.copy2(ROOT/'data/out/v5_tests.log',OUT/'tests.log')
    write_json(OUT/'optimization_record.json',{'operators':bestreport['search'].get('statistics',{}),'successful_trial_count':len(frame),'formal_trial_count':len(formal),'paired_improvements':[{'budget_s':int(index[0]),'seed':int(index[1]),'gain':float(value)} for index,value in (paired.v5-paired.v4).items()],'best_trial':str(bestfolder),'failed_pilot_not_counted':'CSV round-trip could make end-start slightly above 240; V5 now preserves the validated duration field in the frozen 1e-6 consistency tolerance. Failed candidate was rejected, preserved, and never published as valid.','lns_scope':'Bounded local ruin/recreate of 2-3 station tasks; larger neighborhoods remain future work.','high_priority_protection':'No move may remove the last observation of an already-covered high-priority satellite.','timing_scope':bestreport['timing_scope']})
    # Standard scientific plots, exported as standalone PNGs.
    try:
        import matplotlib
    except ModuleNotFoundError:
        import os
        framework=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319'
        chartdll=next((Path(os.environ['WINDIR'])/'Microsoft.NET/assembly/GAC_MSIL/System.Windows.Forms.DataVisualization').glob('*/System.Windows.Forms.DataVisualization.dll'))
        executable=ROOT/'data/out/RenderV5Charts.exe'
        subprocess.run([str(framework/'csc.exe'),'/nologo','/target:exe','/out:'+str(executable),'/reference:System.Drawing.dll','/reference:System.Windows.Forms.dll','/reference:System.Core.dll','/reference:'+str(chartdll),str(ROOT/'scripts/RenderV5Charts.cs')],check=True)
        subprocess.run([str(executable),str(OUT)],check=True)
    else:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        colors={'v4':'#83909c','v5':'#157f93'}
        fig,ax=plt.subplots(figsize=(8.6,4.8))
        for alg in ['v4','v5']:
            g=formal[formal.algorithm==alg]
            for seed,sub in g.groupby('seed'):ax.plot(sub.budget_s,sub.gain_pct,'o-',color=colors[alg],alpha=.65,label=alg.upper() if seed==11 else None)
        ax.axhline(0,color='#66717e',lw=.8);ax.set(xlabel='Optimizer wall-clock budget (seconds)',ylabel='Validated score gain over sealed V4 (%)',title='Equal-budget, three-seed comparison');ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(OUT/'score_gain_by_budget.png',dpi=180);plt.close(fig)
        fig,ax=plt.subplots(figsize=(8.6,4.8));x=np.arange(3)
        ax.bar(x-.18,[baseline_score['by_priority'][k]['coverage_rate']*100 for k in ['high','mid','low']],width=.36,label='V4',color=colors['v4']);ax.bar(x+.18,[bestscore['by_priority'][k]['coverage_rate']*100 for k in ['high','mid','low']],width=.36,label='Best validated V5',color=colors['v5']);ax.set_xticks(x,['High','Medium','Low']);ax.set(ylabel='Unique target coverage (%)',title='Coverage under unchanged 5 / 3 / 2 scoring weights');ax.legend();ax.grid(axis='y',alpha=.2);fig.tight_layout();fig.savefig(OUT/'priority_coverage.png',dpi=180);plt.close(fig)
        fig,ax=plt.subplots(figsize=(10,4.8));x=stations.station_id.to_numpy();ax.bar(x-.18,stations.calendar_utilization*100,width=.36,label='V4',color=colors['v4']);ax.bar(x+.18,stations.v5_calendar_utilization*100,width=.36,label='Best V5',color=colors['v5']);ax.set_xticks(x);ax.set(xlabel='Ground station',ylabel='Calendar utilization incl. switches (%)',title='Six-day station utilization');ax.legend();ax.grid(axis='y',alpha=.2);fig.tight_layout();fig.savefig(OUT/'station_utilization.png',dpi=180);plt.close(fig)
    gain=bestscore['total_score']-baseline_score['total_score'];pct=gain/baseline_score['total_score']*100
    compact=formal[['budget_s','seed','algorithm','valid_score','n_covered','high_covered','n_tasks','search_wall_s','total_wall_s','additional_reaudit_s','peak_rss_mib']].copy()
    for c in ['valid_score','search_wall_s','total_wall_s','additional_reaudit_s','peak_rss_mib']:compact[c]=compact[c].map(lambda x:f'{x:.3f}')
    overview={'status':'accepted','v4_seal_verified_unchanged':True,'v4_score':baseline_score['total_score'],'v5_best_score':bestscore['total_score'],'absolute_gain':gain,'gain_percent':pct,'v4_covered':3117,'v5_covered':bestscore['n_covered'],'high_covered':bestscore['hi_covered'],'tasks':bestscore['n_tasks'],'best_seed':int(bestrow.seed),'best_budget_s':int(bestrow.budget_s),'all_formal_v5_trials_improved':True,'formal_seed_count':3,'formal_budgets_s':[20,60],'all_formal_checks_pass':True,'tests_passed':45,'remaining_high_ids':remaining.sat_id.astype(int).tolist(),'audit_endpoint_metadata_code_sha256':sha(ROOT/'scripts/reconcile_v5_audit.py'),'core_code_sha256':core_hashes,'input_sha256':seal['inputs_sha256'],'windows_sha256':seal['complete_original_tree_sha256']['windows.csv'],'baseline_plan_sha256':seal['complete_original_tree_sha256']['final_plan.csv'],'github_write_permission':'not verified; no GitHub connector or gh CLI available; no push performed'}
    # Make the team handoff concrete before committing only source and docs.
    handoff=f'''# V5团队交接（2026-10-23）

V4验收提交001b05b8481f9281ad36a76df6a5a7fa74a67147保持不变。当前独立克隆在 `{ROOT}`，分支codex/v5-score-engine；原项目Git ACL没有修改。

V5正式最佳：{bestscore['total_score']:.9f}分，较V4增加{gain:.9f}分（{pct:.3f}%），{bestscore['n_tasks']}项合法任务、覆盖{bestscore['n_covered']}/10000，高优先级{bestscore['hi_covered']}/2024。20秒和60秒各3种子全部提高有效得分，全部通过硬约束及独立全任务1秒采样，含精确起止点。45项测试通过。

冻结V4模块未修改。新增satplan/v5.py、v5_physics.py及试验/分析脚本。V5使用站点与同星有序时间线、增量得分和冲突检查，支持短时长插入、换站位移、冲突替换、时长调整和2至3任务的局部破坏修复；不是大规模全局最优求解器。每个改变后的对外候选均执行完整独立验收；临时邻域动作不作为有效成绩发布。

默认真实缓存路径 `{BASE}`，不传播卫星。新机器须获取受限原始输入、DE421并配置Python依赖，原始数据、星历和缓存不入Git。所有脚本目前明确使用该本地缓存路径；不同目录须先统一修改BASE并使用新实验目录，不能混用既有验收记录。对照以同一V4合法计划暖启动；相同优化器墙钟预算包括V5动作物理预检，输入解析和最终验收另外计时。未改变的V4几何计划可复用精确相同的封存证书。

复核/恢复既有比较（完整结果会跳过）：
```powershell
Set-Location '{ROOT}'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OPENBLAS_NUM_THREADS='1'
& 'D:\\SatelliteProject\\Task4_Phase0_DataCheck\\.venv\\Scripts\\python.exe' -u scripts/run_v5_comparison.py
```

推荐通过 `scripts/resume_v5_comparison.ps1` 恢复，它会先核对已验收试验的源码/输入SHA-256并拒绝重复进程；不同版本应新开实验目录。

继续较大预算的独立试验（V4对照请用相同seed和budget另设--out目录）：
```powershell
& 'D:\\SatelliteProject\\Task4_Phase0_DataCheck\\.venv\\Scripts\\python.exe' -u scripts/run_v5_trial.py --algorithm v5 --seed 44 --budget 180 --out data/out/v5_extra_b180_s44
```

恢复只适用于代码和输入均未改变。改算法必须建立新的实验目录，不得让run_v5_comparison.py跳过旧结果后混合新版本。每个trial.json记录完整源码和输入SHA-256。正式比较在执行时冻结核心文件，报告核对所有试验核心hash一致。首次开发试跑因CSV时长浮点往返被完整硬检查拦截，失败数据保留不计入统计；新增回归保证保留已验收时长字段并遵循既有1e-6秒自洽容差。

team远端已设为https://github.com/Eli-Mao/baidumoufa.git。没有验证GitHub写权限，没有推送。交付增量bundle要求V4父提交，先恢复V4 bundle再恢复V5 bundle；不覆盖main，不强推。

1秒离散采样不是连续时间数学认证，分数不是赛事官方成绩。暗夜-6度、30秒切换、48小时冷却及线性时长评分等待官方确认参数保持冻结。
'''
    (ROOT/'docs/V5_HANDOFF.md').write_text(handoff,encoding='utf-8')
    status=ROOT/'PROJECT_STATUS.md';old=status.read_text(encoding='utf-8')
    marker='\n## V5 equal-budget accepted optimization (2026-10-23)\n'
    if marker in old:old=old.split(marker)[0]
    status.write_text(old+marker+f'\n- Frozen V4: 29443.647526046665 points, 6849 tasks, 3117 targets. Original source/data/results unchanged.\n- V5 best: {bestscore["total_score"]:.9f} points (+{pct:.3f}%), {bestscore["n_tasks"]} tasks, {bestscore["n_covered"]} targets, high {bestscore["hi_covered"]}/2024.\n- Same V4 start, 531432 cached windows, three seeds (11/22/33), 20/60-second optimizer caps. Every formal V5 run improved. Full hard/physical acceptance passed; 45 tests passed.\n- Isolated branch codex/v5-score-engine; GitHub push not attempted. See docs/V5_HANDOFF.md and outputs/v5_results.\n',encoding='utf-8')
    destination=ROOT/'scripts/finalize_v5_results.py'
    if Path(__file__).resolve()!=destination.resolve():shutil.copy2(Path(__file__),destination)
    paths=['src/satplan/v5.py','src/satplan/v5_physics.py','tests/test_v5.py','scripts/analyze_v4_opportunities.py','scripts/v4_budget_reference.py','scripts/run_v5_trial.py','scripts/run_v5_comparison.py','scripts/resume_v5_comparison.ps1','scripts/RenderV5Charts.cs','scripts/reconcile_v5_audit.py','tests/test_v5_audit_metadata.py','scripts/finalize_v5_results.py','docs/V5_HANDOFF.md','PROJECT_STATUS.md']
    git('add','--',*paths)
    if subprocess.run(['git','-C',str(ROOT),'diff','--cached','--quiet']).returncode!=0:
        message=ROOT/'data/out/v5_commit_message.txt';message.write_text(f'feat: add validated V5 incremental scheduling optimizer\n\nFreeze V4 and reuse all 531432 real windows. Equal-budget three-seed\ncomparisons at 20 and 60 seconds all improve effective score.\nBest accepted score {bestscore["total_score"]:.9f}, coverage {bestscore["n_covered"]},\nhigh {bestscore["hi_covered"]}/2024, tasks {bestscore["n_tasks"]}.\nEvery final plan passes complete one-second interval physics and frozen\nhard constraints; 45 tests pass. Include explicit timing and rule limits.\nNo raw inputs, ephemeris, caches, or virtual environments committed.\n',encoding='utf-8')
        git('-c','user.name=Iceswing','-c','user.email=755875603@qq.com','commit','--file',str(message))
    commit=git('rev-parse','HEAD');overview['v5_commit']=commit;overview['branch']=git('branch','--show-current')
    git('bundle','create',str(OUT/'v5_optimization.bundle'),'codex/v5-score-engine','^001b05b8481f9281ad36a76df6a5a7fa74a67147')
    git('bundle','verify',str(OUT/'v5_optimization.bundle'));git('format-patch','-1',commit,'--output-directory',str(OUT))
    restore=SESSION/'work'/f'v5_bundle_restore_{commit[:10]}.git'
    original=BASE.parents[2]
    if not restore.exists():
        subprocess.run(['git','-c',f'safe.directory={original.as_posix()}/.git','-c',f'safe.directory={original.as_posix()}','clone','--bare','--no-hardlinks',str(original),str(restore)],check=True)
    for bundle,branch in [(SESSION/'outputs/v4_sealed/v4_10000_acceptance.bundle','codex/v4-10000-accepted'),(OUT/'v5_optimization.bundle','codex/v5-score-engine')]:
        subprocess.run(['git','--git-dir',str(restore),'fetch',str(bundle),f'refs/heads/{branch}:refs/heads/{branch}'],check=True)
    restored=subprocess.check_output(['git','--git-dir',str(restore),'rev-parse','refs/heads/codex/v5-score-engine'],text=True).strip()
    assert restored==commit
    overview['bundle_roundtrip_verified']=True
    write_json(OUT/'bundle_roundtrip.json',{'verified':True,'restored_commit':restored,'restored_repository':str(restore),'original_repo_acl_unchanged':True,'method':'Clone original pre-V4-acceptance repository, import V4 incremental bundle, then V5 incremental bundle.'})
    write_json(OUT/'comparison_report.json',overview)
    md=f'''# V4/V5真实10000目标公平比较报告

V4基准已封存且未改变。V5在相同10000颗真实卫星、10站、2026-08-01至08-07 UTC、531432段真实窗口下，正式最佳有效得分 **{bestscore['total_score']:.6f}**，比V4的29443.647526提高 **{gain:.6f}分（{pct:.3f}%）**。最终{bestscore['n_tasks']}项任务，覆盖{bestscore['n_covered']}/10000，高优先级{bestscore['hi_covered']}/2024。全部硬约束与独立全区间1秒审计通过，精确起止点包含在内；45项测试通过。

## 公平比较方法与全部正式结果

两算法均从同一份合法V4计划开始，以相同20秒/60秒标称优化器墙钟预算、相同种子11/22/33运行；V4保留其原邻域与coverage_weight=0.25接受逻辑，仅增加预算停止条件，V5以有效分优先、覆盖增益破同分，并保护已覆盖高优目标。预算包括各自搜索准备和V5动作物理预检。输入解析及最终独立验收不在搜索预算内，另列总耗时；V4完全未改变的计划复用同一几何的封存物理证书，任何改变后的候选均全量重新采样。搜索在动作边界停止，标称预算与实际耗时分别保留；内存为0.1秒间隔采样RSS峰值。试验串行执行，BLAS线程数设为1。不比较旧版250轮V4整条轨道流水线耗时。

10秒小预算先确认通过验收的增益，才执行正式20秒与60秒矩阵。正式6组配对均为V5得分更高；这支持本次3种子条件下的稳定改善，不代表所有种子或全局最优保证。

{table(compact)}

![各预算下三个种子的有效得分增益](score_gain_by_budget.png)

## 优先级和站点

{table(pd.DataFrame(priority))}

![优先级覆盖率](priority_coverage.png)

V4站点日历利用率含站间任务切换开销，分别约为35.33%、41.00%、44.67%、20.69%、30.38%、33.92%、42.81%、49.74%、25.08%、25.41%。对缓存窗口时间并集的观测占用约71.16%至80.22%；夜间与白天没有混为同一分母。逐站的观测秒数、切换秒数和缓存窗口并集容量见station_comparison.csv。

![六天站点日历利用率](station_utilization.png)

## 未覆盖目标的具体诊断

原30颗高优先级未覆盖中，27颗受V4固定240秒候选长度限制，已有120至239秒空隙；68837在V4物理修复后出现新空隙；58821和66205在V4固定计划下的全部缓存窗口被站点占用挡住。V5当前补回{int(high.covered_in_best_v5.sum())}颗；最佳计划仍未覆盖的高优目标为{remaining.sat_id.astype(int).tolist()}。这只是相对固定计划的可用性分析，没有将其宣布为全局不可覆盖。逐颗窗口数、站点数、空隙上限、示例时段和最终覆盖状态见high_priority_30_diagnosis.csv。

原计划下，直接独立物理可行的未覆盖中/低优目标分别2841和3590颗；存在72073个满足调度几何空隙条件、单独可插入至少120秒的缓存窗口，其中67987个属于原未覆盖目标。这些窗口数量没有逐个作物理认证；上述目标的具体示例已独立物理检查。它们可能相互冲突，不能相加当成可联合安排任务数。另发现{len(actual)}个正收益冲突替换实例：例如67863在站5替换任务3072，单独净增2.471680；59258等在站9替换低优任务5884，单独净增1.748438。完整示例及阻塞任务编号见profitable_conflict_replacements.csv。

## 实现、验证及限制

V5独立模块使用站点/同星有序索引与增量计分，尝试短时长空隙插入、冲突任务替换、跨站重定位、合法时长调整，以及2至3任务的有界破坏修复。未实现大规模全局大邻域求解，不将局部搜索称为全局最优。搜索状态需经过独立验收才对外记为有效成绩。最佳结果的动作统计和逐步净收益见optimization_record.json与best_v5_move_trace.json；所有试验目录保留原候选、最终计划、物理报告和日志。

最终核对发现两份报告用最后数组元素判定终点包含关系，在arange多出相邻浮点值时会误标false；终点实际上已经加入并检查。已用同一未修改的物理审计器追加两份计划的全量复核，再按终点集合成员关系修正元数据，旧报告保留。采样数组和物理阈值均未改变；追加耗时列为additional_reaudit_s，total_wall_s为原次流水线耗时。

首次开发试跑因浮点读写使重算时长略大于240秒而被整表硬检查拦截，已保留失败证据、不计入成绩；修复采用原合法时长字段，并遵循原1e-6秒自洽容差，没有放宽规则。正式所有源码核心、原始输入、缓存和基准SHA-256逐项一致，最终CSV重新核算得分与覆盖。

1秒离散检查不是连续时间数学认证，结果不是官方赛事成绩。10至85度仰角、暗夜太阳高度严格低于-6度、受照、120至240秒、30秒站点间隔、跨站48小时冷却、5/3/2权重及线性时长系数均保持冻结。TLE历元与官方待确认规则风险沿用V4。

## 代码和复现

独立项目：`{ROOT}`；分支codex/v5-score-engine；V5提交 `{commit}`，作者Iceswing <755875603@qq.com>。V4父提交001b05b保持。未改原仓库ACL、未覆盖main、未强推；team远端已配置，未核实GitHub写权限，因此没有推送。

复现与继续优化命令见V5_HANDOFF.md。v5_optimization.bundle是相对V4提交的增量，先恢复V4 bundle，再导入V5分支；输入原始TLE、DE421及窗口缓存均不在Git bundle中。本次没有重新传播10000颗卫星，也没有依赖外部AI生成成果。
'''
    (OUT/'V4_V5比较报告.md').write_text(md,encoding='utf-8');shutil.copy2(ROOT/'docs/V5_HANDOFF.md',OUT/'V5_HANDOFF.md');shutil.copy2(ROOT/'PROJECT_STATUS.md',OUT/'PROJECT_STATUS.md')
    snapshot=OUT/'code_snapshot'
    for directory in ['src','scripts','tests','docs']:
        for path in (ROOT/directory).rglob('*'):
            if path.is_file() and path.suffix in ['.py','.md','.ps1','.cs']:
                dest=snapshot/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    manifest={str(path.relative_to(OUT)):sha(path) for path in OUT.rglob('*') if path.is_file() and path.name not in ['artifact_manifest.json','v5_results.zip','SHA256SUMS.txt']}
    write_json(OUT/'artifact_manifest.json',manifest)
    archive=OUT/'v5_results.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in OUT.rglob('*'):
            if path.is_file() and path!=archive and path.name!='SHA256SUMS.txt':z.write(path,path.relative_to(OUT))
        for directory in [COMP,ANALYSIS]:
            for path in directory.rglob('*'):
                if path.is_file():z.write(path,Path('experiments')/path.relative_to(ROOT/'data/out'))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(path)}  {path.name}' for path in sorted(OUT.iterdir()) if path.is_file() and path.name!='SHA256SUMS.txt')+'\n',encoding='utf-8')
    print(json.dumps(overview,ensure_ascii=False));print('ARCHIVE',archive.stat().st_size)
if __name__=='__main__':main()
