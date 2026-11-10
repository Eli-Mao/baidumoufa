"""Select all discrepant native/Python grid points for independent fine access."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def prepare(python_csv,native_csv,native_raw,out,tolerance_s=.02):
    py=pd.read_csv(python_csv);stk=pd.read_csv(native_csv)
    for frame in (py,stk):
        frame['lat_deg']=frame.lat_deg.round(7)
        frame['lon_deg']=((frame.lon_deg+180)%360-180).round(7)
    m=py.merge(stk,on=['lat_deg','lon_deg'],suffixes=('_py','_stk'),validate='one_to_one')
    bad=m[(m.n_accesses_py!=m.n_accesses_stk)|
          (m.first_access_s_py.isna()!=m.first_access_s_stk.isna())|
          (abs(m.first_access_s_py-m.first_access_s_stk)>tolerance_s)]
    wanted=set(bad.point_id_stk);rows=[]
    lines=iter(Path(native_raw).read_text(encoding='utf-8-sig').splitlines());pid=None;assets={}
    for line in lines:
        s=line.split()
        if not s:continue
        if len(s)==2 and s[1].startswith('Satellite/SAT_'):
            assets[int(s[0])]=int(s[1].split('/')[1][4:])
        if s[0].rstrip(':')=='PointNumber':pid=int(s[1])
        elif s[0].rstrip(':')=='NumberOfAccesses':
            for _ in range(int(s[1])):
                v=next(lines).split()
                if pid in wanted:rows.append([pid,assets[int(v[0])],float(v[1]),float(v[2])])
    windows=pd.DataFrame(rows,columns=['point_id_stk','sat_id','start_s','stop_s'])
    pp=Path(python_csv)
    pw=pd.read_csv(pp.with_name(pp.stem+'_intervals.csv'))
    cases=[]
    for row in bad.itertuples():
        a=windows[windows.point_id_stk==row.point_id_stk][['sat_id','start_s','stop_s']]
        b=pw[pw.point_id==row.point_id_py][['sat_id','start_s','stop_s']]
        for sid,g in pd.concat([a,b]).groupby('sat_id'):
            intervals=[]
            for q in g.sort_values('start_s').itertuples():
                start,stop=max(0,q.start_s-2),min(604800,q.stop_s+2)
                if intervals and start<=intervals[-1][1]:intervals[-1][1]=max(stop,intervals[-1][1])
                else:intervals.append([start,stop])
            for start,stop in intervals:
                cases.append(dict(case_id=len(cases),point_id_stk=row.point_id_stk,point_id_py=row.point_id_py,
                                  lat_deg=row.lat_deg,lon_deg=row.lon_deg,sat_id=int(sid),start_s=start,stop_s=stop))
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(cases,columns=['case_id','point_id_stk','point_id_py','lat_deg','lon_deg','sat_id','start_s','stop_s']).to_csv(out,index=False)
    return dict(discrepant_points=len(bad),cases=len(cases),all_discrepancies_included=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('python-csv','native-csv','native-raw','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.python_csv,a.native_csv,a.native_raw,a.out)))
