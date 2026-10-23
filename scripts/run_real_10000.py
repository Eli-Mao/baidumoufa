"""Resumable real-data V4 acceptance run. Does not change scoring rules."""
from __future__ import annotations
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import sys, json, hashlib, shutil, time, threading, traceback, argparse
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
import numpy as np
import pandas as pd
import psutil
from sgp4.api import Satrec, SGP4_ERRORS, jday
from satplan import config, io_schema, propagate, windows, rules, scheduler
import audit_plan_physics, repair_plan_physics

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def save(path, value):
    path=Path(path); tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(path)

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    lock=out/'run.lock.json'; me=psutil.Process()
    if lock.exists():
        old=json.loads(lock.read_text())
        try:
            other=psutil.Process(old['pid'])
            if abs(other.create_time()-old['create_time'])<0.01: raise RuntimeError(f'Experiment already running: {old}')
        except psutil.NoSuchProcess: pass
    save(lock,{'pid':me.pid,'create_time':me.create_time()})
    started=time.perf_counter(); peak=[me.memory_info().rss]; stop=threading.Event()
    def monitor():
        while not stop.wait(.2): peak[0]=max(peak[0],me.memory_info().rss)
    threading.Thread(target=monitor,daemon=True).start()
    statepath=out/'experiment_report.json'
    state=json.loads(statepath.read_text(encoding='utf-8')) if statepath.exists() else {'attempts':[]}
    attempt={'started_utc':datetime.now(timezone.utc).isoformat(),'stages_s':{}}
    state.setdefault('attempts',[]).append(attempt)
    def stage(name, fn):
        state['status']='running';state['stage']=name;save(statepath,state)
        print(f'[stage] {name}',flush=True);t=time.perf_counter()
        result=fn();attempt['stages_s'][name]=time.perf_counter()-t;save(statepath,state)
        return result
    try:
        assert config.PLAN_T0_UTC=='2026-08-01T00:00:00Z' and config.PLAN_DAYS==6
        tle=io_schema.read_tle_raw(); sites=io_schema.read_stations_raw()
        meta=io_schema.build_sat_meta(tle,io_schema.read_priority_raw())
        assert len(tle)==tle.sat_id.nunique()==10000 and len(sites)==10
        assert meta.priority.value_counts().to_dict()=={'mid':3990,'low':3986,'high':2024}
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in [config.RAW_TLE_FILE,config.RAW_STATION_FILE,*config.RAW_PRIORITY_FILES.values(),config.EPHEMERIS_FILE]}
        source={str(p.relative_to(ROOT)):sha(p) for base in ['src','scripts','tests'] for p in (ROOT/base).rglob('*.py')}
        identity={'inputs_sha256':inputs,'code_sha256':source,'planning_start_utc':config.PLAN_T0_UTC,'planning_days':6,'step_s':30.,'seed':20261021,'local_search_iters':250}
        if state.get('identity') and state['identity']!=identity: raise RuntimeError('Inputs/code changed; use separate output directory')
        state['identity']=identity
        state['git_head']=(ROOT/'data/out/handoff_backup_20261023/git_head.txt').read_text(encoding='utf-8-sig').strip()
        state['git_dirty']=True
        state['rules']={k:getattr(config,k) for k in ['MIN_ELEV_DEG','MAX_ELEV_DEG','SUN_ELEV_MAX_DEG','REQUIRE_SAT_SUNLIT','MIN_DUR_S','MAX_DUR_S','SWITCH_TIME_S','REPEAT_COOLDOWN_S','PRIORITY_SCORE','DUR_SCORE_AT_MIN','DUR_SCORE_AT_MAX','WINDOW_BOUNDARY_TOLERANCE_S']}
        state['warnings']=['Model scores are not official competition results. Darkness threshold, switching, repeat cooldown and duration interpolation require organizer confirmation.','One-second discrete sampling including exact endpoints is not a continuous-time mathematical certification.','30-second coarse candidate detection may miss narrow invalid gaps or short windows. Final tasks are independently sampled.','TLE epochs Aug 2-4: backward propagation about 1-3 days and forward about 3-5 days. No official orbit accuracy certification.']
        meta.to_csv(out/'selected_targets.csv',index=False);sites.to_csv(out/'stations_used.csv',index=False)
        for n in ['src','scripts','tests']:
            for p in (ROOT/n).rglob('*.py'):
                dest=out/'code_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
                if not dest.exists(): shutil.copy2(p,dest)
        # Audit native SGP4 status on the entire coarse grid, including cached targets.
        # Native numeric arrays have bounded per-target memory; no fabricated orbit data.
        def sgp4_check():
            offsets=np.arange(0.,6*86400.+1.,30.)
            jd,fr=jday(2026,8,1,0,0,0.);jds=np.full(len(offsets),jd);frs=fr+offsets/86400.
            summary=[]; errors=out/'sgp4_errors.csv'
            import csv
            with errors.open('w',newline='',encoding='utf-8') as f:
                writer=csv.writer(f);writer.writerow(['sat_id','offset_s','utc','error_code','error_type','handling'])
                for i,r in enumerate(tle.itertuples(index=False),1):
                    sat=Satrec.twoline2rv(r.line1,r.line2);e,position,velocity=sat.sgp4_array(jds,frs)
                    invalid=(e!=0)|(~np.isfinite(position).all(axis=1))|(~np.isfinite(velocity).all(axis=1))
                    for k in np.flatnonzero(invalid):
                        writer.writerow([r.sat_id,offsets[k],io_schema.offset_to_utc(offsets[k]),int(e[k]),SGP4_ERRORS.get(int(e[k]),'nonfinite_state'),'invalid sample excluded; exact task samples checked independently'])
                    summary.append({'sat_id':int(r.sat_id),'samples':len(offsets),'invalid_samples':int(invalid.sum())})
                    if i%1000==0: print(f'[sgp4] {i}/10000',flush=True)
            frame=pd.DataFrame(summary);frame.to_csv(out/'sgp4_target_summary.csv',index=False)
            save(out/'sgp4_report.json',{'targets':len(frame),'samples':int(frame.samples.sum()),'invalid_samples':int(frame.invalid_samples.sum()),'step_s':30.,'start_utc':config.PLAN_T0_UTC,'days':6})
        if not (out/'sgp4_report.json').exists(): stage('sgp4_all_targets',sgp4_check)
        sgp4=json.loads((out/'sgp4_report.json').read_text());state['sgp4']=sgp4
        state['sgp4_handling']='SGP4 error samples explicitly excluded in coarse visibility and refined edges; exact final task samples independently checked'
        invalid_ids=set(pd.read_csv(out/'sgp4_target_summary.csv').query('invalid_samples > 0').sat_id.astype(int))
        cp=out/'propagation_checkpoint.csv'; cpmeta=cp.with_suffix('.csv.meta.json')
        signature=propagate._checkpoint_signature(tle,sites,io_schema.parse_utc(config.PLAN_T0_UTC),6,30.,config.EPHEMERIS_FILE)
        def reuse():
            old=ROOT/'data/out/real_aug2026_5000'; report=json.loads((old/'profile_report.json').read_text())
            selected=pd.read_csv(old/'selected_targets.csv');subset=tle[tle.sat_id.isin(selected.sat_id)].copy()
            info=json.loads((old/'propagation_checkpoint.csv.meta.json').read_text())
            expected=propagate._checkpoint_signature(subset,sites,io_schema.parse_utc(config.PLAN_T0_UTC),6,30.,config.EPHEMERIS_FILE)
            assert info['signature']==expected and info['status']=='completed'
            assert set(info['completed_satellites'])==set(selected.sat_id.astype(int))
            assert not (set(info['completed_satellites']) & invalid_ids), 'Cached target has SGP4 errors: do not reuse its windows'
            assert report['tle_sha256']==inputs['data/raw/orbits.tle'] and report['stations_sha256']==inputs['data/raw/stations.txt']
            assert report['planning_start_utc']==config.PLAN_T0_UTC and report['planning_days']==6 and report['coarse_step_s']==30.
            chunks=cp.with_name(cp.name+'.chunks');chunks.mkdir(exist_ok=True)
            total=0;manifest={}
            for sid in info['completed_satellites']:
                p=old/'propagation_checkpoint.csv.chunks'/f'sat_{sid}.csv';frame=pd.read_csv(p)
                assert frame.empty or set(frame.sat_id.astype(int))=={sid}
                total+=len(frame);shutil.copy2(p,chunks/p.name);manifest[p.name]=sha(p)
            assert total==info['row_count']==265503
            save(out/'cache_reuse_manifest.json',{'source':str(old),'targets':5000,'windows':total,'signature_verified':True,'historical_propagation_s':report['stages_s']['orbit_and_visibility_propagation_s'],'chunk_sha256':manifest})
            save(cpmeta,{'format':'target_chunks_v1','status':'running','signature':signature,'completed_satellites':info['completed_satellites'],'row_count':total})
        if not cpmeta.exists(): stage('verified_cache_reuse',reuse)
        if not (out/'windows.csv').exists():
            raw=stage('remaining_real_propagation',lambda:propagate.propagate_windows(tle,sites,days=6,step_s=30.,checkpoint_path=cp))
            assembled=stage('assemble_windows',lambda:windows.assemble_windows(raw,meta));del raw
            io_schema.save_windows(assembled,out/'windows.csv')
        else: assembled=io_schema.load_windows(out/'windows.csv')
        state['window_count']=len(assembled)
        info=json.loads(cpmeta.read_text());assert len(info['completed_satellites'])==10000 and info['status']=='completed'
        initial=out/'v4_plan.csv'
        if not initial.exists():
            baseline=stage('greedy_schedule',lambda:scheduler.greedy_schedule(assembled,meta))
            baseline.to_csv(out/'greedy_plan.csv',index=False)
            plan=stage('v4_local_search',lambda:scheduler.local_search(baseline,assembled,meta,iters=250,seed=20261021))
            io_schema.save_plan(plan,initial)
        plan=io_schema.load_plan(initial);state['initial_candidate_score']=rules.score_plan(plan,assembled,meta)
        if not (out/'initial_physics_audit.json').exists(): stage('initial_full_interval_audit',lambda:audit_plan_physics.run(initial,out/'initial_physics_audit.json'))
        repaired=out/'repair_report.json'
        if not repaired.exists(): stage('physical_repair',lambda:repair_plan_physics.run(initial,out/'windows.csv',repaired))
        final=out/'final_plan.csv'
        if not final.exists(): shutil.copy2(repaired.with_suffix('.csv'),final)
        audit=stage('final_full_interval_audit',lambda:audit_plan_physics.run(final,out/'final_physics_audit.json'))
        if not audit['all_pass']:
            details=pd.read_csv(out/'final_physics_audit.csv');bad=details.loc[~details['pass'],'task_id']
            p=io_schema.load_plan(final);removed=p[p.task_id.isin(bad)];removed.to_csv(out/'post_repair_endpoint_rejections.csv',index=False)
            p=p[~p.task_id.isin(bad)].copy();io_schema.save_plan(p,final)
            audit=stage('final_audit_after_rejection',lambda:audit_plan_physics.run(final,out/'final_physics_audit.json'))
        plan=io_schema.load_plan(final);violations=rules.plan_violations(plan,assembled,max_report=1000000)
        # Independently verify input identities and scoring columns, including fractional durations.
        joined=plan.merge(meta[['sat_id','priority','priority_score']],on='sat_id',suffixes=('','_truth'),validate='many_to_one')
        assert len(joined)==len(plan) and (joined.priority==joined.priority_truth).all() and (joined.priority_score==joined.priority_score_truth).all()
        assert np.isfinite(plan[['t_start_s','t_end_s','dur_s']].to_numpy()).all()
        assert plan.task_id.is_unique and set(plan.station_id)<=set(sites.station_id)
        assert np.allclose(plan.duration_score,rules.duration_score_series(plan.dur_s),rtol=0,atol=1e-10)
        score=rules.score_plan(plan,assembled,meta);save(out/'final_score.json',score)
        save(out/'hard_constraints.json',{'all_pass':not violations,'n_violations':len(violations),'violations':violations,'tasks':len(plan)})
        counts=plan.groupby('sat_id').size().rename('n_observations')
        stats=meta.merge(counts,on='sat_id',how='left').fillna({'n_observations':0});stats['n_observations']=stats.n_observations.astype(int)
        stats.to_csv(out/'target_observation_counts.csv',index=False);stats[stats.n_observations==0].to_csv(out/'uncovered_targets.csv',index=False)
        pd.DataFrame(score['by_priority']).T.to_csv(out/'priority_coverage.csv',index_label='priority')
        assert not violations and audit['all_pass'] and audit['tasks']==score['n_tasks']==len(plan)
        assert int((stats.n_observations>0).sum())==score['n_covered'] and int(stats.n_observations.sum())==len(plan)
        # Keep original pending reports untouched. This is the new acceptance report.
        state.update(status='completed',stage='accepted',actual_targets=10000,station_count=10,final_effective_score=score,final_physics_audit=audit,repair=json.loads(repaired.read_text()))
        manifest={str(p.relative_to(out)):sha(p) for p in out.glob('*') if p.is_file() and p.name not in ['experiment_report.json','run.lock.json','artifact_manifest.json','run.log','run.err.log']}
        save(out/'artifact_manifest.json',manifest)
        text=f'\n## 10000-target August acceptance (2026-10-23)\n\n- Completed real-data V4 run: {len(assembled)} windows; {len(plan)} final tasks; {score["n_covered"]}/10000 targets; model score {score["total_score"]:.9f}.\n- Zero hard-constraint violations; all tasks passed independent one-second interval sampling including exact fractional endpoints and SGP4 status. Discrete sampling is not continuous-time certification.\n- Full evidence: `data/out/real_aug2026_10000/experiment_report.json`. Official-rule and orbit-accuracy questions remain open.\n'
        status=ROOT/'PROJECT_STATUS.md'
        if '## 10000-target August acceptance' not in status.read_text(encoding='utf-8'): status.write_text(status.read_text(encoding='utf-8')+text,encoding='utf-8')
        handoff=ROOT/'docs/PROJECT_HANDOFF_10000.md';handoff.write_text(handoff.read_text(encoding='utf-8')+text,encoding='utf-8')
        print(json.dumps({'status':'completed','final_score':score},ensure_ascii=False),flush=True)
    except BaseException as exc:
        state['status']='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed'
        state['error']=repr(exc);traceback.print_exc();raise
    finally:
        stop.set();attempt['runtime_s']=time.perf_counter()-started;attempt['peak_rss_mb']=max(peak[0],me.memory_info().rss)/1024**2
        attempt['ended_utc']=datetime.now(timezone.utc).isoformat();save(statepath,state)
        lock.unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'data/out/real_aug2026_10000');args=p.parse_args();main(args.out.resolve())
