"""Aggregate raw Sensor->AreaTarget intervals, union components per satellite only.

Requires the STK package manifest and completeness status from run_stk.ps1.
Keeps different satellites separate for the project's unmerged interpretation.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fasteval import region_revisit
from stk_evidence import native_region_sampling,native_eop_binding


def check_package_binding(package, evidence):
    expected={'manifest.json','build_scenario.txt','build_coverage.txt',
              'GlobalAll.pnt','GlobalReachable.pnt','YRD_GridDiagnostic.pnt'}
    if not expected.issubset(evidence):
        raise ValueError('missing scene package evidence')
    manifest=json.loads((Path(package)/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('eop_file'):
        name=manifest['eop_file']
        if Path(name).name!=name or '/' in name or '\\' in name:
            raise ValueError('invalid EOP package filename')
        expected.add(name)
    if set(evidence)!=expected:
        raise ValueError('missing or unexpected scene package evidence')
    for name in expected:
        actual=hashlib.sha256((Path(package)/name).read_bytes()).hexdigest()
        if actual!=evidence[name]:
            raise ValueError(f'STK run belongs to a different or modified scene package: {name}')
    return True


def aggregate(raw, status, manifest):
    duration=float(manifest['duration_s'])
    expected={(int(s),str(c)) for s in manifest['satellite_ids'] for c in manifest['region_area_targets']}
    pairs=[(int(x['sat_id']),str(x['component_id'])) for x in status]
    if len(set(pairs)) != len(pairs) or set(pairs)!=expected or not all(x['computed'] is True for x in status):
        raise ValueError('incomplete STK satellite/component computation evidence')
    required=['sat_id','component_id','start_s','stop_s']
    if not set(required).issubset(raw): raise ValueError('missing CSV columns')
    if not np.isfinite(raw[['sat_id','start_s','stop_s']].to_numpy(float)).all():
        raise ValueError('non-finite intervals')
    if not ((raw.start_s>=0)&(raw.stop_s>=raw.start_s)&(raw.stop_s<=duration)).all():
        raise ValueError('invalid interval range')
    if not set(zip(raw.sat_id,raw.component_id)).issubset(expected):
        raise ValueError('unknown satellite/component')
    for item in status:
        group=raw[(raw.sat_id==int(item['sat_id']))&(raw.component_id==str(item['component_id']))]
        if len(group)!=int(item['intervals']): raise ValueError('interval count differs from run status')
    merged=[]
    for sid, group in raw.groupby('sat_id'):
        windows=[]
        for a,b in group.sort_values(['start_s','stop_s'])[['start_s','stop_s']].to_numpy(float):
            if windows and a<=windows[-1][1]+1e-9: windows[-1][1]=max(windows[-1][1],b)
            else: windows.append([a,b])
        merged.extend(dict(sat_id=int(sid),start_s=a,stop_s=b) for a,b in windows)
    s=[r['start_s'] for r in merged]; e=[r['stop_s'] for r in merged]
    metrics=region_revisit(s,e,duration)
    metrics['merged']=region_revisit(s,e,duration,merge=True)
    return dict(region_revisit=metrics,access_intervals=merged,
                rule='Union simultaneous area components per satellite; no positive-gap bridging.',
                overlap_interpretation='Unmerged uses adjacent start-sorted windows; merged gives physical outage gaps.',
                stk_execution_evidence_complete=True,stk_verified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--package',required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args(); run=Path(a.run)
    evidence=json.loads((run/'package_evidence.json').read_text(encoding='utf-8-sig'))
    check_package_binding(a.package,evidence)
    status=json.loads((run/'region_access_status.json').read_text(encoding='utf-8-sig'))
    manifest=json.loads((Path(a.package)/'manifest.json').read_text(encoding='utf-8'))
    execution=json.loads((run/'run_status.json').read_text(encoding='utf-8-sig'))
    if execution.get('status')=='failed' or not execution['coverage_computed'] or execution['skip_region']:
        raise ValueError('missing successful regional execution evidence')
    native=native_region_sampling(run/'Task2_Constellation.sca',manifest,execution['region_step_s'])
    result=aggregate(pd.read_csv(run/'region_access_raw.csv'),status,manifest)
    result['package_binding_verified']=True
    result['package_sha256']=evidence
    result['native_sampling']=native
    result['native_eop']=native_eop_binding(run,a.package,manifest)
    result['execution_settings']=execution
    result['source_sha256']=hashlib.sha256((run/'region_access_raw.csv').read_bytes()).hexdigest()
    Path(a.out).write_text(json.dumps(result,indent=2),encoding='utf-8')
    # The unified workflow compares the actual per-satellite windows, not only
    # aggregate JSON metrics. Preserve a header even for a valid empty result.
    pd.DataFrame(result['access_intervals'],columns=['sat_id','start_s','stop_s']).to_csv(
        Path(a.out).with_suffix('.csv'),index=False)
