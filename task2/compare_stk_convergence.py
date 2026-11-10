"""Compare two independently computed native STK runs after strict aggregation."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def compare(coarse_path,fine_path,kind,tolerance_s=.02):
    a=json.loads(Path(coarse_path).read_text(encoding='utf-8'))
    b=json.loads(Path(fine_path).read_text(encoding='utf-8'))
    if a['package_sha256']!=b['package_sha256']:
        raise ValueError('different scene packages')
    if not all(x.get('native_sampling',{}).get('verified') for x in [a,b]):
        raise ValueError('native saved sampling was not verified')
    result=dict(kind=kind,coarse=str(coarse_path),fine=str(fine_path),
                native_sampling_verified=True,tolerance_s=tolerance_s)
    if kind=='region':
        def intervals(d):
            return np.array(sorted((r['sat_id'],r['start_s'],r['stop_s']) for r in d['access_intervals']))
        x,y=intervals(a),intervals(b)
        same=x.shape==y.shape and np.array_equal(x[:,0],y[:,0])
        error=float(np.max(np.abs(x[:,1:]-y[:,1:]))) if same else None
        result.update(coarse_visits=len(x),fine_visits=len(y),same_interval_assignment=same,
                      max_endpoint_difference_s=error,
                      ok=bool(same and error<=tolerance_s))
        for key in ['Tavg_s','Tmax_s']:
            result[key+'_difference']=abs(a['region_revisit'][key]-b['region_revisit'][key])
        result['step_sizes_s']=[a['native_sampling']['fixed_step_s'],b['native_sampling']['fixed_step_s']]
    else:
        def points(path):
            d=pd.read_csv(Path(path).with_suffix('.csv'))
            d['lat_deg']=d.lat_deg.round(7);d['lon_deg']=d.lon_deg.round(7)
            return d.set_index(['lat_deg','lon_deg']).sort_index()
        x,y=points(coarse_path),points(fine_path)
        if not x.index.equals(y.index):raise ValueError('global point coordinates differ')
        fx,fy=x.first_access_s.to_numpy(),y.first_access_s.to_numpy()
        hit_change=int(np.count_nonzero(np.isfinite(fx)!=np.isfinite(fy)))
        count_change=int(np.count_nonzero(x.n_accesses.to_numpy()!=y.n_accesses.to_numpy()))
        both=np.isfinite(fx)&np.isfinite(fy)
        error=float(np.max(np.abs(fx[both]-fy[both]))) if both.any() else 0.
        result.update(points=len(x),covered_state_changes=hit_change,access_count_changes=count_change,
                      max_first_access_difference_s=error,
                      ok=bool(hit_change==0 and count_change==0 and error<=tolerance_s),
                      adaptive_max_steps_s=[a['execution_settings']['global_max_step_s'],b['execution_settings']['global_max_step_s']])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--coarse',required=True);p.add_argument('--fine',required=True)
    p.add_argument('--kind',choices=['region','global'],required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args();r=compare(a.coarse,a.fine,a.kind)
    Path(a.out).write_text(json.dumps(r,indent=2),encoding='utf-8')
    print(json.dumps(r,indent=2));raise SystemExit(0 if r['ok'] else 1)
