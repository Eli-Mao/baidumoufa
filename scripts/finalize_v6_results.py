"""Verify and assemble real experiment evidence; never invent missing trials."""
import sys,json,hashlib,shutil,platform,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import numpy as np,pandas as pd,psutil,skyfield,sgp4
from satplan import config,rules
from verify_v6_csv import verify
HERE=ROOT.parents[1];BASE=Path('D:/SatelliteProject_GitHub/data/out/real_aug2026_10000')
EXP=ROOT/'data/out/v6_comparison';OUT=HERE/'outputs/v6_results';SEALED=HERE/'outputs/v5_sealed'
def save(p,o):p.write_text(json.dumps(o,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    OUT.mkdir(exist_ok=True)
    progress=json.loads((EXP/'comparison_progress.json').read_text(encoding='utf-8'))
    assert progress['status']=='completed' and len(progress['completed'])==18
    rows=[];records={};identities=[];bindings=[]
    for entry in progress['completed']:
        name=entry['name'];folder=EXP/name;r=json.loads((folder/'trial.json').read_text(encoding='utf-8'))
        assert r['status']=='accepted' and r['hard_violations']==0 and r['full_interval_pass']
        assert sha(folder/'final_plan.csv')==r['final_csv_sha256']
        identities.append(r['identity'])
        recomputed=verify(folder/'final_plan.csv',BASE/'selected_targets.csv')
        s=r['final_score'];assert abs(recomputed['independent_csv_score']-s['total_score'])<1e-6
        assert recomputed['covered']==s['n_covered'] and recomputed['tasks']==s['n_tasks']
        audit=json.loads((folder/'physics_audit.json').read_text(encoding='utf-8'));detail=pd.read_csv(folder/'physics_audit.csv')
        assert audit['all_pass'] and audit['exact_endpoints_included'] and audit['tasks']==len(detail)==s['n_tasks']
        assert detail['pass'].all() and detail.exact_end_included.all() and detail.bad_sgp4_samples.sum()==0
        geom=['task_id','station_id','sat_id','t_start_s','t_end_s']
        assert pd.read_csv(folder/'candidate_plan.csv')[geom].equals(pd.read_csv(folder/'final_plan.csv')[geom]),'Final CSV differs from audited geometry'
        declared_delta=float((pd.read_csv(folder/'candidate_plan.csv').dur_s-pd.read_csv(folder/'final_plan.csv').dur_s).abs().max())
        bindings.append({'trial':name,'exact_parsed_geometry_equal':True,'declared_duration_serialization_max_delta_s':declared_delta,'candidate_sha256':sha(folder/'candidate_plan.csv'),'final_sha256':sha(folder/'final_plan.csv'),'audit_json_sha256':sha(folder/'physics_audit.json'),'audit_csv_sha256':sha(folder/'physics_audit.csv')})
        row={'trial':name,'algorithm':r['algorithm'],'seed':r['seed'],'budget_s':r['budget_s'],'score':s['total_score'],'gain_vs_v5':r['gain_vs_v5'],'covered':s['n_covered'],'tasks':s['n_tasks'],'search_s':r['search']['search_wall_s'],'runtime_total_s':r['runtime_total_s'],'peak_rss_mib':r['peak_rss_mib'],'hard_violations':0,'physical_pass':True,'physical_audit_s':r['stages_s'].get('independent_full_audit',0),'candidate_rejected':r.get('rejected_candidate',False)}
        row.update({f'{k}_covered':s['by_priority'][k]['n_covered'] for k in config.PRIORITY_ORDER})
        rows.append(row);records[name]=r
    assert all(i==identities[0] for i in identities),'Formal trials used different input/code identities'
    assert all(sha(Path(name))==digest for name,digest in identities[0].items()),'Frozen inputs/code changed after experiments'
    frame=pd.DataFrame(rows).sort_values(['budget_s','seed','algorithm']);frame.to_csv(OUT/'fair_comparison.csv',index=False)
    save(OUT/'final_csv_certificate_bindings.json',bindings)
    save(OUT/'experiment_progress.json',{'status':'completed','accepted_formal_trials':18,'expected_formal_trials':18,'in_progress':[],'startup_repeat_completed':True})
    summary=frame.groupby(['budget_s','algorithm']).agg(score_mean=('score','mean'),score_std=('score','std'),score_min=('score','min'),score_max=('score','max'),coverage_mean=('covered','mean'),tasks_mean=('tasks','mean'),search_s_mean=('search_s','mean'),rss_mib_max=('peak_rss_mib','max'),runtime_total_s_mean=('runtime_total_s','mean')).reset_index();summary.to_csv(OUT/'budget_summary.csv',index=False)
    paired=frame.pivot(index=['budget_s','seed'],columns='algorithm',values='score').reset_index();paired['v6_minus_v5']=paired.v6-paired.v5;paired['v6_minus_v4']=paired.v6-paired.v4;paired.to_csv(OUT/'paired_gains.csv',index=False)
    enhanced=frame[frame.algorithm=='v6'];bestrow=enhanced.sort_values(['score','covered'],ascending=False).iloc[0];bestname=bestrow.trial
    bestfolder=EXP/bestname;bestrecord=records[bestname]
    assert bestrow.score>=30682.990429546662
    bestoverall=frame.sort_values(['score','covered'],ascending=False).iloc[0]
    mostcovered=frame.sort_values(['covered','score'],ascending=False).iloc[0]
    for src,dst in [('final_plan.csv','best_coverage_plan.csv'),('final_score.json','best_coverage_score.json'),('physics_audit.csv','best_coverage_physics_audit.csv'),('physics_audit.json','best_coverage_physics_audit.json'),('trial.json','best_coverage_trial.json')]:shutil.copy2(EXP/mostcovered.trial/src,OUT/dst)
    for src,dst in [('final_plan.csv','best_v6_plan.csv'),('final_score.json','best_v6_score.json'),('physics_audit.csv','best_v6_physics_audit.csv'),('physics_audit.json','best_v6_physics_audit.json'),('trial.json','best_v6_trial.json'),('move_trace.json','best_v6_move_trace.json'),('hard_check.json','best_v6_hard_check.json')]:shutil.copy2(bestfolder/src,OUT/dst)
    independent=verify(OUT/'best_v6_plan.csv',BASE/'selected_targets.csv',BASE/'windows.csv');save(OUT/'independent_csv_verification.json',independent)
    trace=json.loads((OUT/'best_v6_move_trace.json').read_text(encoding='utf-8'))
    pd.DataFrame([{'elapsed_s':0.,'total_score':30682.990429546662,'covered':3822,'operator':'baseline','delta_score':0.},*[{k:t[k] for k in ['elapsed_s','total_score','covered','operator','delta_score']} for t in trace]]).to_csv(OUT/'best_convergence.csv',index=False)
    operators=pd.DataFrame(trace).groupby('operator').agg(accepted=('delta_score','size'),score_gain=('delta_score','sum'),coverage_gain=('coverage_change','sum')).reset_index();operators.to_csv(OUT/'best_operator_gains.csv',index=False)
    transitions=[]
    for step,t in enumerate(trace,1):
        added={a['uid']:a for a in t['added']}
        for old in t['removed']:
            if old['uid'] not in added:continue
            new=added[old['uid']]
            transitions.append({'step':step,'operator':t['operator'],'sat_id':old['sat'],'old_station':old['station'],'new_station':new['station'],'old_start':old['start'],'new_start':new['start'],'old_duration':old['end']-old['start'],'new_duration':new['end']-new['start'],'move_net_score_gain':t['delta_score'],'cross_station':old['station']!=new['station']})
    pd.DataFrame(transitions).to_csv(OUT/'best_task_transitions.csv',index=False)
    transition_stats={'uid_preserving_cross_station_moves':sum(r['cross_station'] for r in transitions),'uid_preserving_shortened_tasks':sum(r['new_duration']<r['old_duration']-1e-6 for r in transitions),'uid_preserving_lengthened_tasks':sum(r['new_duration']>r['old_duration']+1e-6 for r in transitions),'largest_accepted_destroyed_neighborhood':max((len(t['removed']) for t in trace if t['operator']=='large_repack'),default=0),'note':'Counts cover UID-preserving exchanges/extensions. Repacked observations get new UIDs and are recorded separately in the complete move trace.'}
    save(OUT/'best_transition_summary.json',transition_stats)
    # Nondominated score/coverage points are archives of independently accepted
    # final plans, not extra terms in the frozen official-model score.
    pareto=[]
    for row in frame.to_dict('records'):
        if not any((z['score']>=row['score'] and z['covered']>=row['covered'] and (z['score']>row['score'] or z['covered']>row['covered'])) for z in frame.to_dict('records')):pareto.append(row)
    pd.DataFrame(pareto).to_csv(OUT/'nondominated_plans.csv',index=False)
    archive=OUT/'nondominated_plans';archive.mkdir(exist_ok=True)
    for row in pareto:shutil.copy2(EXP/row['trial']/'final_plan.csv',archive/(row['trial']+'.csv'))
    v4=pd.read_csv(BASE/'final_plan.csv');v5=pd.read_csv(SEALED/'best_v5_plan.csv');v6p=pd.read_csv(OUT/'best_v6_plan.csv');plans={'v4':v4,'v5':v5,'v6':v6p}
    meta=pd.read_csv(BASE/'selected_targets.csv');priority=[]
    for k in config.PRIORITY_ORDER:
        n=int((meta.priority==k).sum());rr={'priority':k,'targets':n}
        for alg,p in plans.items():
            sub=p[p.priority==k];rr[alg+'_covered']=int(sub.sat_id.nunique());rr[alg+'_rate']=rr[alg+'_covered']/n
            rr[alg+'_tasks']=len(sub);rr[alg+'_score']=float((sub.priority_score*(.6+.4*(sub.dur_s-120)/120)).sum())
        priority.append(rr)
    pd.DataFrame(priority).to_csv(OUT/'priority_comparison.csv',index=False)
    target=meta.copy()
    for alg,p in plans.items():
        target[alg+'_tasks']=target.sat_id.map(p.groupby('sat_id').size()).fillna(0).astype(int)
    target.to_csv(OUT/'target_coverage_comparison.csv',index=False)
    target[(target.v5_tasks==0)&(target.v6_tasks>0)].to_csv(OUT/'newly_covered_vs_v5.csv',index=False)
    target[(target.v5_tasks>0)&(target.v6_tasks==0)].to_csv(OUT/'lost_covered_vs_v5.csv',index=False)
    target[target.v6_tasks==0].to_csv(OUT/'remaining_uncovered_best.csv',index=False)
    stations=[]
    for site in config.STATION_IDS:
        rr={'station_id':site}
        for alg,p in plans.items():
            sub=p[p.station_id==site];rr[alg+'_tasks']=len(sub);rr[alg+'_utilization']=(sub.dur_s.sum()+30*max(0,len(sub)-1))/518400
        stations.append(rr)
    pd.DataFrame(stations).to_csv(OUT/'station_comparison.csv',index=False)
    analysis=ROOT/'data/out/v6_analysis'
    for p in analysis.iterdir():
        if p.is_file():shutil.copy2(p,OUT/p.name)
    a=json.loads((analysis/'analysis.json').read_text(encoding='utf-8'));resources=json.loads((analysis/'resources.json').read_text(encoding='utf-8'));edge=json.loads((analysis/'edge_refinement.json').read_text(encoding='utf-8'))
    refined=pd.read_csv(analysis/'uncovered_opportunities.csv')
    for r in edge:
        if r['shorter_interior_physical_insertion']:
            mask=refined.sat_id==r['sat_id'];refined.loc[mask,'direct_physical_insert']=True
            refined.loc[mask,'reason']='shorter_shifted_physical_insertion_available'
            for dest,source in [('example_station','station'),('example_start','start'),('example_end','end'),('example_gain','score')]:refined.loc[mask,dest]=r[source]
    refined.to_csv(OUT/'uncovered_opportunities_refined.csv',index=False)
    save(OUT/'refined_opportunity_counts.json',refined.groupby('priority').direct_physical_insert.sum().to_dict())
    s=bestrecord['final_score'];gain=s['total_score']-30682.990429546662
    environment={'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'numpy':np.__version__,'pandas':pd.__version__,'skyfield':skyfield.__version__,'sgp4':sgp4.__version__,'psutil':psutil.__version__,'logical_cpus':psutil.cpu_count(),'physical_cpus':psutil.cpu_count(logical=False),'blas_threads':1,'rss_sampling_interval_s':.1}
    save(OUT/'runtime_environment.json',environment);save(OUT/'frozen_identity.json',identities[0])
    rule_names=['PLAN_T0_UTC','PLAN_DAYS','STATION_IDS','MIN_ELEV_DEG','MAX_ELEV_DEG','MIN_DUR_S','MAX_DUR_S','SWITCH_TIME_S','REPEAT_COOLDOWN_S','SUN_ELEV_MAX_DEG','REQUIRE_SAT_SUNLIT','PRIORITY_SCORE','DUR_SCORE_AT_MIN','DUR_SCORE_AT_MAX']
    save(OUT/'frozen_rules.json',{'config':{n:getattr(config,n) for n in rule_names},'score_formula':'priority_weight * (0.6 + 0.4 * (duration_s - 120) / 120), only hard-valid and physically accepted tasks','targets':10000,'cached_windows':531432,'model_confirmation':'Frozen current model; open official-rule questions remain in docs/open_questions.md'})
    report={'best_enhanced_trial':bestname,'best_enhanced_score':s,'gain_vs_accepted_v5':gain,'gain_pct_vs_accepted_v5':100*gain/30682.990429546662,'gain_vs_original_v4':s['total_score']-29443.647526046665,'best_overall_trial':bestoverall.trial,'best_overall_score':float(bestoverall.score),'budget_summary':summary.to_dict('records'),'paired_gains':paired.to_dict('records'),'formal_trials':18,'all_formal_accepted':True,'pilot_excluded':True,'common_warm_start':'same accepted V5 for all three refiners','budgets_s':[12,36],'seeds':[11,22,33],'v6_pair_wins':int((paired.v6_minus_v5>1e-8).sum()),'hard_violations':0,'all_full_interval_physics_pass':True,'independent_csv_verification':independent,'analysis':a,'resource_analysis':resources,'edge_refinement':edge,'nondominated_trials':[r['trial'] for r in pareto]}
    save(OUT/'comparison_report.json',report)
    report['highest_coverage_trial']=mostcovered.trial;report['highest_coverage_count']=int(mostcovered.covered);report['highest_coverage_score']=float(mostcovered.score)
    save(OUT/'comparison_report.json',report)
    table=['|预算秒|优化器|得分均值|样本标准差|覆盖均值|实际搜索秒均值|峰值RSS MiB|','|---:|---|---:|---:|---:|---:|---:|']
    for r in summary.itertuples(index=False):table.append(f'|{r.budget_s:g}|{r.algorithm.upper()}|{r.score_mean:.6f}|{r.score_std:.6f}|{r.coverage_mean:.1f}|{r.search_s_mean:.3f}|{r.rss_mib_max:.1f}|')
    priority_table=['|等级|总数|原V4覆盖|验收V5覆盖|增强版最佳覆盖|','|---|---:|---:|---:|---:|']
    for r in priority:priority_table.append(f"|{r['priority']}|{r['targets']}|{r['v4_covered']}|{r['v5_covered']}|{r['v6_covered']}|")
    station_table=['|站点|V5任务|日历利用率含切换|窗口并集内空闲≥120秒总时长|','|---:|---:|---:|---:|']
    for r in resources['station_resources']:station_table.append(f"|{r['station_id']}|{r['tasks']}|{100*r['calendar_utilization']:.2f}%|{r['union_free_gap_s_ge120']:.1f}秒|")
    operator_table=['|最佳试验算子|接受次数|净得分增加|净覆盖增加|','|---|---:|---:|---:|']
    for r in operators.itertuples(index=False):operator_table.append(f'|{r.operator}|{r.accepted}|{r.score_gain:.6f}|{r.coverage_gain}|')
    text=f'''# 10000目标深度优化：V4 / V5 / V6实际实验

增强版最佳合法成绩 **{s['total_score']:.6f}**，较验收V5增加 **{gain:.6f}（{100*gain/30682.990429546662:.3f}%）**。{s['n_tasks']}项任务，覆盖{s['n_covered']}/10000颗；高优先级{s['hi_covered']}/2024。最佳正式试验 `{bestname}`。全部任务硬约束及独立完整区间1秒物理复核通过，非整数秒起止点包含在采样中。

## 封存与输入

V5提交0337bb2593ea89c05b6778fcc592194279067816、81项交付哈希、ZIP CRC、bundle验证及恢复、独立CSV得分30682.990429546662均已核实；见相邻v5_sealed/seal.json。原V4、V5及原仓库均保留。现有531432段窗口原样复用，未重做10000颗卫星轨道传播。逐任务物理检查仍从真实TLE计算调度区间。

## 公平比较

三种优化器**统一从验收V5计划开始**。这比较的是继续优化能力；原V4的29443.647526与原V5的30682.990430只是历史基准，不能把不同预算的历史最高分当作公平对照。预算12/36秒，固定种子11/22/33，正式18次，试验性pilot不计入均值和标准差。样本标准差ddof=1。V4保留其原提案与score+0.25coverage接受逻辑；V5保留其原实现；V6单独模块。输入加载和初始化物理引擎在搜索预算外，各算法内部准备、增量检查、候选物理检查均计入预算；最终验收耗时另列。V4全计划检查与V5/V6增量检查的效率差异属于算法实现差异。墙钟截止可在最后一次有限事务上略微超时，实际耗时完整记录。

{chr(10).join(table)}

V6相对V5的6组成对试验胜出{report['v6_pair_wins']}/6；逐种子差值见paired_gains.csv。全部算法中最高正式成绩为{bestoverall.score:.6f}（{bestoverall.trial}）。本报告保存增强版最佳；任何算法更优的合法方案同时完整保留在实验归档中。运行耗时、内存、任务和分级覆盖逐次见fair_comparison.csv。RSS每0.1秒采样，可能错过更短尖峰。

## 剩余机会的实际分析（相对固定验收V5）

6178颗未覆盖目标全部存在缓存窗口。2315颗中优先级合计109614段，3863颗低优先级合计203832段。首次最长区间扫描发现中优493、低优1487颗存在可直接插入并经完整区间物理检查的单目标机会；追加较短时长与内部平移搜索又找到中优35532的120秒合法插入（站10，起点445551.638282秒），因此已证实至少**494颗中优、1487颗低优**有直接合法机会。其余3颗有几何空隙但有限候选物理检查未找到合法任务，不能判为全局不可能。中优1820、低优2374颗在当前固定计划下没有120秒站点空隙；也不代表移走任务后不可安排。

全体缓存中14513段窗口有不少于120秒几何空隙，其中13695段属于未覆盖目标。941条正收益冲突替换经过候选物理复核，例如站8原任务6244（低优，得分1.3460937533）可被中优100088的240秒任务替换，增加1.6539062467分；站6任务3926可换成中优49279，增加1.5980468733分。任务编号对应封存V5 CSV。这些都是各自相对固定计划的机会，彼此可能冲突，不能累计收益或覆盖数。任务可行性包含站点切换及全局48小时冷却。

低优覆盖178→123的55颗全部是丢失原V4低优目标，没有新低优加入；这55项旧观测区间均被当前高/中优任务阻塞。其中11颗在别处有经物理检查的直接插入机会。逐目标与阻塞任务见lost_low_task_blockers.csv；其余未覆盖目标逐项见uncovered_opportunities.csv。得分模型按任务累加，覆盖只是另一指标，原V5因此可能接受增加收益、减少低优覆盖的替换。

{chr(10).join(station_table)}

以上利用率分母是6天全部UTC日历时间。窗口并集空闲已扣切换边界，但并集可能由不同目标窗口拼接，不能替代单目标物理证书。站4虽然日历利用率低，其可见窗口并集内已无120秒资源空隙，因此不能凭日历空闲认定还能直接插入。

## 增强算法与实际贡献

独立satplan.v6复用V5的增量站点/目标时间索引，采用48窗口批量按可得收益选择插入、精确起点平移及延长、最多4个阻塞任务的跨站点逐级迁移、单站6/10/16/24项或双站最多60项的破坏重建。重建尝试120秒高密度排列或最长合法时长，并含被移出目标的其他站点窗口。算子按单位耗时真实收益平滑调整概率，保留探索下限。所有接受事务要求正式模型得分不下降，平分时覆盖增加，并保护已覆盖高优目标；物理拒绝、超时、部分插入失败均回滚。内部临时状态只属搜索候选，最终计划独立验收后才计成绩。

最佳试验各算子的实际次数及净得分见best_operator_gains.csv；每笔迁移前后站点、目标和精确时刻见best_v6_move_trace.json。optimization_convergence.png记录搜索中的临时最优曲线，曲线最后计划已独立验收；不把每个中间点标为独立验收成果。不同得分/覆盖权衡的非支配正式方案见nondominated_plans.csv及对应CSV，最终评分未添加覆盖奖励。

{chr(10).join(operator_table)}

{chr(10).join(priority_table)}

## 验收与局限

最终CSV回读后独立计算权重×[0.6+0.4×(时长−120)/120]，复核目标元数据、有限数值、时长120–240秒、窗口包含、站点30秒切换、同星172800秒冷却及6天规划边界；最终最佳再做全计划检查。每份改变的正式候选用独立audit_v6_physics.py逐任务重建Skyfield对象、检查精确起止点及间隔不超过1秒的区间内网格，复核10°–85°仰角、太阳高度严格低于−6°、卫星日照、SGP4错误。该独立模块保留V4审计计算口径，修正其浮点网格可能超出任务尾端不足1e-9秒的端点标记问题；原V4/V5文件未修改。任何失败候选仅留拒绝证据，采用封存V5回退，不覆盖基准。

仍是冻结的当前模型分数，赛题待确认项未宣称已获官方认证。1秒离散检查不是连续时间物理证明；Aug2–4 TLE用于Aug1–7仍有外推误差。多种子实验可比较稳定性，不保证相同墙钟预算在其他机器上逐位重现同一个计划；最终CSV和输入哈希可精确复算。
'''
    text+='\n运行总耗时字段runtime_total_s从输入/代码身份哈希完成后开始，包含数据解析、搜索与验收，不含Python进程启动和之前的身份哈希；search_s是共同预算所约束的计时区间。每次完整物理复核耗时单列，实验并未用搜索时间掩盖验收成本。首次V4启动试验因与单元测试短暂并行，保留为excluded_startup_overlap证据并在批次结束后单独重跑；统计仅采用独立重跑的18次正式结果，详见experiment_protocol.json。\n'
    text+='\n18份最终CSV均与其实际审计candidate CSV逐项比较任务ID、站点、目标、精确起止，解析后全部完全相同，无容差合并。final_csv_certificate_bindings.json记录两份CSV及物理报告的SHA，因此物理报告中candidate路径对应的区间证书可精确绑定最终交付CSV。两份seed33增强版的声明dur_s在第二次序列化后有最多2.84e-14秒末位变化，起止区间完全不变；最终时长一致性、硬约束及分数均按交付CSV重新计算。\n'
    text=text.replace('每份改变的正式候选用独立audit_v6_physics.py','每份通过硬约束的改变候选再用独立audit_v6_physics.py')
    text+=f"\n得分与覆盖的实际取舍：36秒档V5平均覆盖4079颗，V6平均覆盖{float(summary[(summary.budget_s==36)&(summary.algorithm=='v6')].iloc[0].coverage_mean):.2f}颗。V6在此预算下得分更高但平均覆盖更少。正式试验最高覆盖方案为{mostcovered.trial}，覆盖{int(mostcovered.covered)}颗、得分{float(mostcovered.score):.6f}；其计划和独立物理证书另存为best_coverage_plan.csv与best_coverage_physics_audit.*。非支配归档支持两种指标的真实权衡，不宣称V6在所有指标上支配V5。\n"
    text+=f"\n正式试验中触发候选拒绝并回退封存V5的次数：{int(frame.candidate_rejected.sum())}；拒绝原因与原候选证据保留在各trial中。\n"
    (OUT/'V4_V5_V6比较报告.md').write_text(text,encoding='utf-8')
    with (OUT/'V4_V5_V6比较报告.md').open('a',encoding='utf-8') as log:
        log.write(f"\n最佳试验中可直接按任务UID追踪到{transition_stats['uid_preserving_cross_station_moves']}次跨站迁移、{transition_stats['uid_preserving_shortened_tasks']}次缩短和{transition_stats['uid_preserving_lengthened_tasks']}次延长；已接受的最大破坏重建邻域包含{transition_stats['largest_accepted_destroyed_neighborhood']}项旧任务。逐项见best_task_transitions.csv；重建后采用新UID的任务另见完整trace，避免重复统计。\n")
    handoff=f'''# V6团队交接

最佳增强版合法得分{s['total_score']:.6f}，任务{s['n_tasks']}，覆盖{s['n_covered']}；基准V5始终封存。独立分支codex/v6-deep-optimization，尚未远程推送。原main、原仓库权限和队友修改没有改动。

## 环境与数据

Python3.12，numpy/pandas/skyfield/sgp4/psutil版本见runtime_environment.json；不新增第三方依赖。原始TLE、站点、优先级、de421.bsp需在本地就位，均不提交。现有窗口、selected_targets.csv和V4 experiment_report.json放到缓存目录。用V6_CACHE_DIR指定该目录；V6_BASELINE_DIR指向v5_sealed，含验收V5计划、物理报告与seal.json。冻结配置、输入和算法SHA见frozen_identity.json。

## 直接命令（在项目根目录，PowerShell）

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:PYTHONPATH=(Join-Path $PWD 'src')
$env:V6_CACHE_DIR='D:/SatelliteProject_GitHub/data/out/real_aug2026_10000'
$env:V6_BASELINE_DIR='{SEALED.as_posix()}'
$py='D:/SatelliteProject/Task4_Phase0_DataCheck/.venv/Scripts/python.exe'
& $py -m unittest discover -s tests
& $py scripts/analyze_v5_opportunities.py
& $py scripts/summarize_v5_resources.py
& $py scripts/refine_v5_opportunities.py
& $py scripts/verify_v6_csv.py --plan '{(OUT/'best_v6_plan.csv').as_posix()}' --targets "$env:V6_CACHE_DIR/selected_targets.csv" --windows "$env:V6_CACHE_DIR/windows.csv"
& $py scripts/run_v6_trial.py --algorithm v6 --seed 44 --budget 36 --out data/out/v6_extra_s44
if (-not (Test-Path data/out/v6_comparison/pilot_b12_v6/trial.json)) {{ & $py scripts/run_v6_trial.py --algorithm v6 --seed 20261023 --budget 12 --out data/out/v6_comparison/pilot_b12_v6 }}
& $py scripts/run_v6_comparison.py --budgets 12 36 --seeds 11 22 33
```

完整比较命令需要data/out/v6_comparison下的已验收pilot；实验ZIP保留该pilot。每个正式trial以原子JSON检查点和CSV保存。重跑比较会校验算法/输入身份和计划SHA再跳过已完成trial。未完成试验不会被静默覆盖；保留其目录，使用新输出目录重新运行该trial。comparison.lock记录PID，进程异常退出后先确认PID已不存在，再只删除该锁文件；不要并行运行相同输出目录。源代码或输入改变时使用新实验目录，不复用旧检查点。

新预算和种子可直接调用trial；批量比较默认要求同目录内已有通过验收且优于V5的12秒pilot。继续优化时V6_BASELINE_DIR必须仍指向封存V5以保持公平。本轮无必须达到的预设分数。

图表使用Windows自带.NET绘图库，无需安装matplotlib。当前18次试验的表格由scripts/finalize_v6_results.py生成；RenderV6Charts.cs读取这些CSV。可在Windows执行：

```powershell
$chartDll=(Get-ChildItem "$env:WINDIR/Microsoft.NET/assembly/GAC_MSIL/System.Windows.Forms.DataVisualization" -Recurse -Filter System.Windows.Forms.DataVisualization.dll | Select-Object -First 1).FullName
& "$env:WINDIR/Microsoft.NET/Framework64/v4.0.30319/csc.exe" /nologo /target:exe /out:data/out/RenderV6Charts.exe /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Core.dll "/reference:$chartDll" scripts/RenderV6Charts.cs
& ./data/out/RenderV6Charts.exe '{OUT.as_posix()}'
```

## 合并与恢复

只合并独立新增v6.py、审计/实验/分析/绘图脚本、测试及文档；V4/V5与冻结rules/config不改变。最终交付bundle及源代码快照用于本地恢复，具体提交与验证记录见bundle_restore.json。远程team为https://github.com/Eli-Mao/baidumoufa.git；推送前须由用户确认，禁止force或覆盖main。确认后仅执行git push team codex/v6-deep-optimization。未验证远程写权限，不声称已发布。

不提交data/raw、de421、窗口缓存、实验大文件、密钥或本地环境。交付ZIP只含代码、脱敏路径身份记录及实验产物；实际路径只是复现线索，没有密钥。完整本地输入不随Git提交。原V5增量bundle需要V4前置提交；增强版最终提供完整bundle，可独立克隆。
'''
    (OUT/'V6_HANDOFF.md').write_text(handoff,encoding='utf-8')
    status=f'''# PROJECT_STATUS

验收V4：29443.647526，6849任务，3117覆盖；验收V5：30682.990430，7658任务，3822覆盖，均已保留并核验。

增强V6最佳：{s['total_score']:.6f}，{s['n_tasks']}任务，{s['n_covered']}覆盖，高{s['by_priority']['high']['n_covered']}/2024，中{s['by_priority']['mid']['n_covered']}/3990，低{s['by_priority']['low']['n_covered']}/3986。18次正式公平试验及完整1秒物理审核完成；共同V5起点、12/36秒、种子11/22/33。具体对照、均值/标准差、时间内存、拒绝候选记录见交付报告。独立开发分支codex/v6-deep-optimization，尚未推送；不改变原main、ACL和队友修改。测试结果见test_results.txt。当前冻结模型并非连续时间或官方规则认证。
'''
    (OUT/'PROJECT_STATUS.md').write_text(status,encoding='utf-8')
    shutil.copy2(OUT/'PROJECT_STATUS.md',ROOT/'PROJECT_STATUS.md')
    for n in ['V6_HANDOFF.md','V4_V5_V6比较报告.md']:shutil.copy2(OUT/n,ROOT/'docs'/n)
    print(json.dumps({'best':bestname,'score':s['total_score'],'covered':s['n_covered'],'paired_wins':report['v6_pair_wins'],'best_overall':bestoverall.trial},ensure_ascii=False))
if __name__=='__main__':main()
