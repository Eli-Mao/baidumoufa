"""Compare independently exported STK J2000 positions with the secular model.

Input CSV: sat_id,t_s,x_km,y_km,z_km. Missing satellites, short time spans,
duplicates and non-finite data fail closed; this is orbit validation only.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from propagate import propagate_j2_secular
from sso import R_EARTH
from run_sim import load_elements


def compare(elements, states, duration_s=604800.0, tolerance_km=1.0, max_step_s=60.0,
            rate_model='stk'):
    required = ['sat_id', 't_s', 'x_km', 'y_km', 'z_km']
    if duration_s <= 0 or tolerance_km <= 0 or max_step_s <= 0:
        raise ValueError('limits must be positive')
    if not set(required).issubset(states.columns) or states.empty:
        raise ValueError('empty or incomplete STK CSV')
    if not np.isfinite(states[required].to_numpy(float)).all():
        raise ValueError('non-finite STK values')
    if states.duplicated(['sat_id', 't_s']).any():
        raise ValueError('duplicate satellite/time rows')
    if elements.sat_id.duplicated().any() or set(elements.sat_id) != set(states.sat_id):
        raise ValueError('satellite ID set differs')
    results = []
    for e in elements.itertuples():
        group = states[states.sat_id == e.sat_id].sort_values('t_s')
        t = group.t_s.to_numpy(float)
        if len(t) < 2 or abs(t[0]) > 1e-6 or abs(t[-1]-duration_s) > 1e-6 or np.diff(t).max() > max_step_s+1e-6:
            raise ValueError(f'satellite {e.sat_id}: incomplete time coverage')
        r, _ = propagate_j2_secular(R_EARTH+e.alt_km, e.inc_deg, e.raan_deg, e.u_deg, t,
                                    rate_model=rate_model)
        delta = np.linalg.norm(group[['x_km','y_km','z_km']].to_numpy()-r[0], axis=1)
        results.append(dict(sat_id=int(e.sat_id), samples=len(t), max_error_km=float(delta.max()),
                            rms_error_km=float(np.sqrt(np.mean(delta**2))),
                            ok=bool(delta.max() <= tolerance_km)))
    return dict(orbit_ok=all(x['ok'] for x in results), tolerance_km=tolerance_km, rate_model=rate_model,
                duration_s=duration_s, satellites=results, coverage_verified=False,
                note='Orbit comparison alone does not validate Earth-fixed frame, sensor, coverage or revisit.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elements', required=True)
    p.add_argument('--states', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--tolerance-km', type=float, default=.002)
    p.add_argument('--days', type=float, default=7.0)
    p.add_argument('--rate-model', choices=['first_order','stk'], default='stk')
    args = p.parse_args()
    result = compare(load_elements(args.elements), pd.read_csv(args.states),
                     duration_s=args.days*86400, tolerance_km=args.tolerance_km, rate_model=args.rate_model)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['orbit_ok'] else 1)
