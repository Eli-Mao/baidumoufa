"""Fail-closed comparisons of complete grids, windows and native refinements."""
from pathlib import Path
import hashlib
import json
import re
import numpy as np
import pandas as pd


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def points_comparison(a,b,tolerance_s=.02):
    def clean(x):
        x=x.copy()
        cols=['lat_deg','lon_deg','n_accesses','first_access_s']
        if x.empty or not set(cols).issubset(x):raise ValueError('missing grid data')
        x.lat_deg=x.lat_deg.round(7);x.lon_deg=((x.lon_deg+180)%360-180).round(7)
        if x.duplicated(['lat_deg','lon_deg']).any():raise ValueError('duplicate grid coordinates')
        if not np.isfinite(x[['lat_deg','lon_deg','n_accesses']]).all().all():raise ValueError('nonfinite grid')
        if ((x.n_accesses<0)|(x.n_accesses!=np.floor(x.n_accesses))).any():raise ValueError('invalid access count')
        hit=x.n_accesses>0
        if not np.isfinite(x.loc[hit,'first_access_s']).all() or x.loc[~hit,'first_access_s'].notna().any():
            raise ValueError('hit/count/time disagree')
        return x
    a,b=clean(a),clean(b)
    z=a.merge(b,on=['lat_deg','lon_deg'],suffixes=('_a','_b'),validate='one_to_one')
    if len(z)!=len(a) or len(a)!=len(b):raise ValueError('grid coordinate set differs')
    changed=int((z.first_access_s_a.isna()!=z.first_access_s_b.isna()).sum())
    counts=int((z.n_accesses_a!=z.n_accesses_b).sum())
    delta=abs(z.first_access_s_a-z.first_access_s_b)
    max_delta=float(delta.max()) if delta.notna().any() else 0.
    return dict(points=len(z),covered_state_changes=changed,access_count_changes=counts,
                max_first_access_difference_s=max_delta,tolerance_s=tolerance_s,
                ok=changed==0 and counts==0 and max_delta<=tolerance_s)


def windows_comparison(a,b,keys=('sat_id',),tolerance_s=.02):
    columns=[*keys,'start_s','stop_s']
    for table in (a,b):
        if not set(columns).issubset(table) or not np.isfinite(table[columns]).all().all():raise ValueError('invalid window data')
        if (table.start_s>table.stop_s).any():raise ValueError('reversed access window')
        if table.duplicated(columns).any():raise ValueError('duplicate access window')
    x=a.sort_values(columns)[columns].to_numpy(float)
    y=b.sort_values(columns)[columns].to_numpy(float)
    same=x.shape==y.shape and np.array_equal(x[:,:len(keys)],y[:,:len(keys)])
    delta=float(np.max(abs(x[:,-2:]-y[:,-2:]))) if same and len(x) else (0. if same else None)
    return dict(counts=[len(x),len(y)],same_assignment=same,max_endpoint_difference_s=delta,
                tolerance_s=tolerance_s,ok=bool(same and delta<=tolerance_s))


def read_refinement(run,expected_cases=None,expected_eop_sha=None,expected_commands_sha=None):
    run=Path(run);status=load_json(run/'status.json')
    if status.get('status')!='completed':raise ValueError('incomplete native refinement')
    if sha(run/'cases.csv').lower()!=status['cases_sha256'].lower():raise ValueError('refinement case hash differs')
    if expected_cases and sha(expected_cases)!=sha(run/'cases.csv'):raise ValueError('unexpected refinement case list')
    for key,expected in [('eop_sha256',expected_eop_sha),('scene_commands_sha256',expected_commands_sha)]:
        if expected and status[key].lower()!=expected.lower():raise ValueError('refinement input binding differs: '+key)
    cases=pd.read_csv(run/'cases.csv');counts=pd.read_csv(run/'counts.csv');windows=pd.read_csv(run/'intervals.csv')
    if cases.empty or cases.case_id.duplicated().any() or counts.case_id.duplicated().any():raise ValueError('duplicate/empty refinement cases')
    if not np.isfinite(cases.to_numpy(float)).all() or (cases.start_s<0).any() or (cases.stop_s<=cases.start_s).any():raise ValueError('invalid case bounds')
    for _,group in cases.groupby(['point_id_stk','sat_id']):
        group=group.sort_values('start_s')
        if np.any(group.start_s.to_numpy()[1:]<group.stop_s.to_numpy()[:-1]):raise ValueError('overlapping duplicate cases')
    if set(cases.case_id)!=set(counts.case_id) or len(cases)!=status['cases']:raise ValueError('missing refinement cases')
    if not set(windows.case_id).issubset(set(cases.case_id)):raise ValueError('unrequested native window')
    actual=windows.groupby('case_id').size().reindex(counts.case_id,fill_value=0).to_numpy()
    if not np.array_equal(actual,counts.interval_count.to_numpy()) or len(windows)!=status['intervals']:
        raise ValueError('native interval counts differ')
    index=cases.set_index('case_id')
    for w in windows.itertuples():
        c=index.loc[w.case_id]
        if w.sat_id!=c.sat_id or w.point_id_stk!=c.point_id_stk or not c.start_s-1e-6<=w.start_s<=w.stop_s<=c.stop_s+1e-6:
            raise ValueError('native window outside requested encounter')
    scene=(run/'Task2_Constellation.sca').read_text(encoding='utf-8-sig')
    commands=(run/'commands.log').read_text(encoding='utf-8-sig')
    blocks=re.findall(r'^BEGIN Access\s*\n(.*?)^END Access\s*$',scene,re.M|re.S)
    found=[]
    for block in blocks:
        match=re.search(r'/Target/CHECK_(\d+)',block)
        if not match:continue
        cid=int(match[1]);found.append(cid)
        if cid not in index.index:raise ValueError('unexpected saved access')
        sat=re.search(r'/Satellite/SAT_(\d+)/Sensor/Cam',block)
        step=re.search(r'FixedStepSampling\s+(\S+)',block)
        tol=re.search(r'(?m)^\s*TimeConvergence\s+(\S+)',block)
        if not sat or int(sat[1])!=index.loc[cid,'sat_id'] or not step or not tol:
            raise ValueError('incomplete native sampling proof')
        if not np.isfinite([float(step[1]),float(tol[1])]).all() or abs(float(step[1])-status['step_s'])>1e-12 or float(tol[1])>status['time_convergence_s']*1.000001:
            raise ValueError('saved native refinement sampling differs')
        if not re.search(r'UseLightTimeDelay\s+No',block) or not re.search(r'IsComputed\s+Yes',block):
            raise ValueError('native computation settings differ')
        period=re.search(r'BEGINUserList\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+ENDUserList',block)
        expected=index.loc[cid,['start_s','stop_s']].to_numpy(float)
        # STK 11.6 serializes this list's start to 6 decimals but its stop to
        # only 6 significant digits. Bind exact bounds to the executed Connect
        # command as well as checking the native writer's representation.
        logged=re.findall(r'/Target/CHECK_'+str(cid)+r'\s+TimePeriod "([^"]+)" "([^"]+)"',commands)
        if len(logged)!=1 or not np.allclose(list(map(float,logged[0])),expected,atol=1e-8,rtol=0):
            raise ValueError('executed native encounter period differs')
        if not period or abs(float(period[1])-expected[0])>1e-5 or float(period[2])!=float(format(expected[1],'.6g')):
            raise ValueError('saved native encounter period differs')
    if len(found)!=len(set(found)) or set(found)!=set(cases.case_id):raise ValueError('saved native access list incomplete')
    return cases,windows,status


def refined_points(native_points,cases,windows):
    result=native_points.copy().set_index('point_id')
    if not set(cases.point_id_stk).issubset(result.index):raise ValueError('refinement point outside native grid')
    for pid,group in cases.groupby('point_id_stk'):
        original=result.loc[pid]
        if not np.allclose(group.lat_deg,original.lat_deg,atol=1e-7,rtol=0) or not np.allclose(
                (group.lon_deg-original.lon_deg+180)%360-180,0,atol=1e-7,rtol=0):raise ValueError('refinement coordinates differ')
        w=windows[windows.point_id_stk==pid]
        result.loc[pid,'n_accesses']=len(w)
        result.loc[pid,'first_access_s']=w.start_s.min() if len(w) else np.nan
    return result.reset_index()
