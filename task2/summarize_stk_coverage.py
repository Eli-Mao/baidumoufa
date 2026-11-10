"""Strict parser for native STK 11.6 COV 6.0 exports; count-weighted first access.

Geodetic coordinates in the export are radians, longitude may be in [0, 2pi).
Every point, asset and declared access row is checked before reporting coverage.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd
from summarize_stk_region import check_package_binding
from stk_evidence import native_global_sampling,native_eop_binding


def parse_cvaa(path, satellite_ids, duration_s, epoch='2027-01-01T00:00:00'):
    with Path(path).open(encoding='utf-8-sig') as stream:
        lines=iter(line.strip() for line in stream if line.strip())
        def take():
            try: return next(lines)
            except StopIteration: raise ValueError('truncated COV export') from None
        def field(name, convert=str):
            row=take().split(maxsplit=1)
            if len(row)!=2 or row[0].rstrip(':')!=name:
                raise ValueError(f'expected {name}, got {row}')
            return convert(row[1])
        if take()!='COV 6.0': raise ValueError('unsupported STK coverage export version')
        stamp=field('EpochTime')
        parsed=datetime.strptime(' '.join(stamp.split()).split('.')[0],'%d %b %Y %H:%M:%S')
        if parsed.isoformat()!=epoch: raise ValueError('coverage epoch differs')
        asset_count=field('NumberOfAssets',int)
        assets={}
        for _ in range(asset_count):
            row=take()
            m=re.fullmatch(r'(\d+)\s+Satellite/SAT_(\d+)/Sensor/Cam',row)
            if not m: raise ValueError('unexpected coverage asset: '+row)
            index,sid=map(int,m.groups())
            if index in assets: raise ValueError('duplicate asset index')
            assets[index]=sid
        if sorted(assets.values())!=sorted(satellite_ids): raise ValueError('coverage asset set differs')
        regions=field('NumberOfRegions',int)
        if regions<=0: raise ValueError('empty coverage region list')
        point_ids=set(); rows=[]; access_rows=0
        for region_index in range(regions):
            rid=field('RegionNumber',int)
            # Native STK 11.6 may reuse RegionNumber (e.g. both polar bands).
            # PointNumber and the final coordinate set identify grid points.
            count=field('NumPtsInRegion',int)
            if count<0: raise ValueError('negative point count')
            for _ in range(count):
                pid=field('PointNumber',int)
                if pid in point_ids: raise ValueError('duplicate point ID')
                point_ids.add(pid)
                lat,lon,alt=field('Lat',float),field('Lon',float),field('Alt',float)
                if not np.isfinite([lat,lon,alt]).all() or abs(lat)>math.pi/2+1e-10:
                    raise ValueError('invalid ground coordinates')
                n=field('NumberOfAccesses',int)
                if n<0: raise ValueError('negative access count')
                first=math.inf
                for _ in range(n):
                    values=take().split()
                    if len(values)!=3: raise ValueError('invalid access row')
                    asset=int(values[0]); start,stop=map(float,values[1:])
                    if asset not in assets or not np.isfinite([start,stop]).all() or not (
                            -1e-6<=start<=stop<=duration_s+1e-6):
                        raise ValueError('invalid access asset or time')
                    first=min(first,max(start,0.)); access_rows+=1
                rows.append(dict(point_id=pid,region_id=rid,region_index=region_index,lat_deg=math.degrees(lat),
                                 lon_deg=(math.degrees(lon)+180)%360-180,altitude=alt,
                                 first_access_s=first,n_accesses=n))
        if next(lines,None) is not None: raise ValueError('unparsed coverage export tail')
    return pd.DataFrame(rows),dict(regions=regions,assets=asset_count,access_rows=access_rows)


def summarize(points, expected_points):
    if len(points)==0 or len(points)!=len(expected_points): raise ValueError('incomplete grid point count')
    def keys(lat,lon):
        return list(zip(np.round(np.asarray(lat),7),np.round((np.asarray(lon)+180)%360-180,7)))
    actual=keys(points.lat_deg,points.lon_deg)
    expected=keys(expected_points[:,0],expected_points[:,1])
    if len(set(actual))!=len(actual) or len(set(expected))!=len(expected):
        raise ValueError('duplicate grid coordinates')
    if set(actual)!=set(expected): raise ValueError('exported coordinates differ from the supplied grid')
    if not np.allclose(points.altitude,0,atol=1e-8): raise ValueError('nonzero grid altitude')
    first=np.sort(points.first_access_s.to_numpy())
    hit=int(np.isfinite(first).sum()); n=len(first)
    threshold=int(math.ceil(.9*n))-1
    return dict(n_valid=n,n_covered=hit,coverage=hit/n,
                T90_s=float(first[threshold]) if np.isfinite(first[threshold]) else None,
                T100_s=float(first[-1]) if np.isfinite(first[-1]) else None)


def read_points(path):
    text=Path(path).read_text(encoding='ascii').splitlines()
    if text[1].strip().upper()!='BEGIN POINTLIST' or text[-1].strip().upper()!='END POINTLIST':
        raise ValueError('unexpected point list structure')
    return np.array([list(map(float,line.split())) for line in text[2:-1] if line.strip()])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--package',required=True)
    p.add_argument('--definition',default='GlobalReachable')
    p.add_argument('--out',required=True)
    args=p.parse_args(); run=Path(args.run); package=Path(args.package); out=Path(args.out)
    status=json.loads((run/'run_status.json').read_text(encoding='utf-8-sig'))
    evidence=json.loads((run/'package_evidence.json').read_text(encoding='utf-8-sig'))
    check_package_binding(package,evidence)
    if status.get('status')=='failed' or not status['coverage_computed'] or status.get('skip_global') or args.definition not in status['global_definitions']:
        raise ValueError('missing successful coverage execution evidence')
    manifest=json.loads((package/'manifest.json').read_text())
    raw=run/(args.definition+'_accesses.txt')
    points,meta=parse_cvaa(raw,manifest['satellite_ids'],manifest['duration_s'])
    expected=read_points(package/(args.definition+'.pnt'))
    if len(expected)!=manifest['grid_counts'][args.definition]: raise ValueError('grid manifest count differs')
    metrics=summarize(points,expected)
    sampling=native_global_sampling(run/(args.definition+'.cv'),status)
    out.parent.mkdir(parents=True,exist_ok=True)
    points.replace([np.inf,-np.inf],np.nan).to_csv(out.with_suffix('.csv'),index=False)
    result=dict(global_coverage={args.definition:metrics},native_export=meta,
                package_binding_verified=True,grid_coordinates_verified=True,
                source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                package_sha256=evidence,execution_settings=status,
                native_sampling=sampling,
                native_eop=native_eop_binding(run,package,manifest),
                evaluation='equal point count; earliest access over all satellites',
                convergence_verified=False,local_model_equivalence_verified=False)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(metrics,indent=2))


if __name__=='__main__': main()
