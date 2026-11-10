"""STK 11.6 engineering handoff: ephemerides, J2 scene and custom coverage grids.

Connect distances are explicitly kilometers. Generated files are locally checked,
but are not STK runtime evidence. See the engineering guide in docs/ for model differences.
"""
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import json
import re
import hashlib
import shutil

import numpy as np

from coverage import ETA_DEG, ETA_ALONG_DEG
from propagate import propagate_j2_secular
from sso import R_EARTH
from coverage import Grid, max_reachable_lat
from region import rings, bbox, points_in_polygon, load_geojson

SCEN_START = '1 Jan 2027 00:00:00.000'
SCEN_STOP = '8 Jan 2027 00:00:00.000'


def write_ephemeris(path, times_s, r_km, v_kms, scenario_epoch=SCEN_START):
    times_s, r_km, v_kms = (np.asarray(x, float) for x in (times_s, r_km, v_kms))
    if (times_s.ndim != 1 or len(times_s) < 2 or np.any(np.diff(times_s) <= 0)
            or r_km.shape != (len(times_s), 3) or v_kms.shape != r_km.shape
            or not all(np.isfinite(x).all() for x in (times_s, r_km, v_kms))):
        raise ValueError('invalid ephemeris samples')
    lines = ['stk.v.11.0', 'BEGIN Ephemeris',
             f'NumberOfEphemerisPoints {len(times_s)}',
             f'ScenarioEpoch {scenario_epoch}',
             'InterpolationMethod Lagrange', 'InterpolationSamplesM1 5',
             'CentralBody Earth', 'CoordinateSystem J2000', 'DistanceUnit Kilometers',
             'EphemerisTimePosVel']
    for t, p, v in zip(times_s, r_km, v_kms):
        lines.append(f'{t:.3f} ' + ' '.join(f'{x:.6f}' for x in p) + ' ' + ' '.join(f'{x:.9f}' for x in v))
    lines.append('END Ephemeris')
    Path(path).write_text('\n'.join(lines) + '\n', encoding='ascii')


def connect_script(elems, scenario='Task2_Constellation', stop=SCEN_STOP, step=30.0):
    """Connect 建场景命令，距离统一 km，角度 deg；不关闭已有场景。"""
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', scenario):
        raise ValueError('scenario must be an ASCII identifier')
    out = ['Units_SetConnect / Distance Kilometer Time Second Date GregorianUTC',
           f'New / Scenario {scenario}',
           f'SetAnalysisTimePeriod * "{SCEN_START}" "{stop}"',
           f'SetEpoch * "{SCEN_START}"']
    for r in elems.itertuples():
        name = f'SAT_{int(r.sat_id):03d}'
        a_km = R_EARTH + r.alt_km
        out += [f'New / */Satellite {name}',
                f'SetState */Satellite/{name} Classical J2Perturbation "{SCEN_START}" "{stop}" {step:g} '
                f'J2000 "{SCEN_START}" {a_km:.9f} 0.0 {r.inc_deg:.9f} 0.0 {r.raan_deg:.9f} {r.u_deg:.9f}',
                f'SetAttitude */Satellite/{name} Profile NadirECFVel Offset 0',
                f'New / */Satellite/{name}/Sensor Cam',
                f'Define */Satellite/{name}/Sensor/Cam Rectangular {ETA_ALONG_DEG} {ETA_DEG}',
                f'Point */Satellite/{name}/Sensor/Cam Fixed Quaternion 0 0 0 1',
                f'SetConstraint */Satellite/{name}/Sensor/Cam FieldOfView On',
                f'SetConstraint */Satellite/{name}/Sensor/Cam LineOfSight On']
    return '\n'.join(out) + '\n'


def export(elems, out_dir, days=7.0, step=30.0, region_polys=None, eop_path=None,rate_model='auto'):
    """写 ephem/*.e 与 build_scenario.txt，返回写出的文件数。"""
    if not np.isfinite(days) or not np.isfinite(step) or days <= 0 or step <= 0:
        raise ValueError('days and step must be positive and finite')
    elems = elems.copy()
    if 'alt_km' not in elems and 'h_km' in elems:
        elems = elems.rename(columns={'h_km': 'alt_km'})
    from validate import check_output
    checked = elems.assign(a_km=R_EARTH + elems.alt_km) if 'a_km' not in elems else elems.copy()
    for col in ('ecc', 'argp_deg'):
        if col not in checked:
            checked[col] = 0.0
    checked_result=check_output(checked,rate_model=rate_model)
    if not checked_result['ok']:
        raise ValueError('invalid constellation')
    from earth_frames import DEFAULT_EOP
    eop_path=Path(eop_path) if eop_path else DEFAULT_EOP
    out = Path(out_dir)
    (out / 'ephem').mkdir(parents=True, exist_ok=True)
    dur = days * 86400.0
    t = np.r_[np.arange(0.0, dur, step), dur]
    end = datetime(2027, 1, 1) + timedelta(seconds=dur)
    months = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
    stop = f'{end.day} {months[end.month-1]} {end.year} {end:%H:%M:%S}.{end.microsecond // 1000:03d}'
    for r in elems.itertuples():
        rr, vv = propagate_j2_secular(R_EARTH + r.alt_km, r.inc_deg, r.raan_deg, r.u_deg, t,
                                      rate_model='stk',eop_path=eop_path)
        write_ephemeris(out / 'ephem' / f'SAT_{int(r.sat_id):03d}.e', t, rr[0], vv[0])
    scenario_commands=connect_script(elems, stop=stop, step=step)
    eop_metadata=None
    if eop_path is not None:
        source=Path(eop_path);raw=source.read_bytes();content=raw.decode('ascii')
        dates={datetime(*map(int,m)).date() for m in re.findall(r'^(\d{4}) (\d{2}) (\d{2}) ',content,re.M)}
        required={(datetime(2027,1,1)+timedelta(days=d)).date() for d in range((end.date()-datetime(2027,1,1).date()).days+1)}
        if not required.issubset(dates):raise ValueError('EOP data does not cover the scenario dates')
        name='EarthOrientation.txt'
        shutil.copyfile(source,out/name)
        scenario_commands=scenario_commands.replace('New / Scenario Task2_Constellation\n',
            'New / Scenario Task2_Constellation\nEarthData * EOPFile "@PACKAGE@/'+name+'"\n')
        predicted=content.split('BEGIN PREDICTED',1)[-1] if 'BEGIN PREDICTED' in content else ''
        predicted_dates={datetime(*map(int,m)).date() for m in re.findall(r'^(\d{4}) (\d{2}) (\d{2}) ',predicted,re.M)}
        eop_metadata=dict(updated=content.splitlines()[1],sha256=hashlib.sha256(raw).hexdigest(),
                          first_date=str(min(dates)),last_date=str(max(dates)),
                          scenario_dates_are_predictions=bool(required & predicted_dates))
    (out / 'build_scenario.txt').write_text(scenario_commands, encoding='utf-8')
    polys = rings() if region_polys is None else region_polys
    from fasteval import DEFAULT_BBOX
    la0, la1, lo0, lo1 = DEFAULT_BBOX if region_polys is None else bbox(polys)
    gg, rg = Grid(-90, 90, 1), Grid(la0, la1, .1, lo0, lo1, .1)
    reach = max_reachable_lat(elems.inc_deg.to_numpy(), elems.alt_km.to_numpy())
    grids = {'GlobalAll': (gg, np.ones(gg.size, bool)),
             'GlobalReachable': (gg, np.abs(gg.lat_c) <= reach),
             'YRD_GridDiagnostic': (rg, points_in_polygon(rg.lat_c, rg.lon_c, polys))}
    commands = []
    for k, poly in enumerate(polys):
        name = f'YRD_{k:03d}'
        commands += [f'New / */AreaTarget {name}',
                     f'SetBoundary */AreaTarget/{name} Pattern LatLon {len(poly)} ' +
                     ' '.join(f'{lat:.9f} {lon:.9f}' for lon, lat in poly),
                     f'SetAccessOption */AreaTarget/{name} Any',
                     f'SetConstraint */AreaTarget/{name} LineOfSight On']
    for name, (grid, mask) in grids.items():
        lines = ['stk.v.4.2.1', 'BEGIN PointList']
        lines += [f'{a:.9f} {b:.9f} 0' for a, b in zip(grid.lat_c[mask], grid.lon_c[mask])]
        lines += ['END PointList']
        (out / f'{name}.pnt').write_text('\n'.join(lines) + '\n', encoding='ascii')
        cov = f'*/CoverageDefinition/{name}'
        commands += [f'New / */CoverageDefinition {name}', f'Cov {cov} Access AutoRecompute Off',
                     f'Cov {cov} Grid AreaOfInterest Global',
                     f'Cov {cov} Grid PointLocation Custom "@PACKAGE@/{name}.pnt"',
                     f'Cov {cov} Grid PointAltitude Altitude 0']
        commands += [f'Cov {cov} Asset */Satellite/SAT_{int(s):03d}/Sensor/Cam Assign' for s in elems.sat_id]
    (out / 'build_coverage.txt').write_text('\n'.join(commands) + '\n', encoding='utf-8')
    manifest = dict(epoch_utc=SCEN_START, stop_utc=stop, duration_s=dur, step_s=step,
                    satellite_ids=[int(s) for s in elems.sat_id],
                    grid_counts={k: int(m.sum()) for k, (_, m) in grids.items()},
                    region_area_targets=[f'YRD_{k:03d}' for k in range(len(polys))],
                    region_metric='continuous Sensor-to-AreaTarget access, QA E41/E45/E49',
                    global_metric='design-dependent reachable grid, QA G41/E55',
                    region_grid_role='diagnostic_only_not_scoring',
                    region_source='supplied_geojson' if region_polys is not None else 'simplified_builtin',
                    stk_verified=False, position_frame='J2000', velocity='analytic_position_derivative',
                    design_rate_model=checked_result['rate_model'],propagation_rate_model='stk',
                    ground_model='WGS84 ellipsoid; geodetic points; frozen EOP and ICRF propagation',
                    caveat='Python ephemerides are diagnostic only; native validation uses independent SetState J2Perturbation.')
    if eop_metadata is not None:
        manifest.update(eop_file='EarthOrientation.txt',eop_provenance=eop_metadata)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return len(elems) + 6 + int(eop_metadata is not None)


if __name__ == '__main__':
    import pandas as pd
    p = argparse.ArgumentParser(description='Export existing constellation without rerunning optimization')
    p.add_argument('--elements', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--days', type=float, default=7)
    p.add_argument('--step', type=float, default=30)
    p.add_argument('--region')
    p.add_argument('--eop',help='Freeze an EOP file that contains every scenario date')
    p.add_argument('--rate-model',choices=['auto','stk','first_order'],default='auto')
    args = p.parse_args()
    print(export(pd.read_csv(args.elements), args.out, args.days, args.step,
                 load_geojson(args.region) if args.region else None,args.eop,args.rate_model))
