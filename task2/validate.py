"""赛题二：模型与仿真的自校验，输出 <目录>/validation.json。

七项检查：
1. 太阳同步条件：按 i(h) 建的轨道，J2 解析节点进动率是否等于 0.985647°/天；
2. 传播器交叉校验：解析 J2 长期项 vs RK4 数值积分的节点周期（用数值轨道自身的
   平均半长轴评估，避开平均/瞬时根数转换带来的 9 km 偏差）；
3. β 角稳定性：输出星座 7 天内 β 角应基本不变；
4. 步长无关性：10 s 与 5 s 步长的全球覆盖率差异；
5. 输出格式：constellation.csv 的字段、取值域、卫星数、倾角是否满足太阳同步条件；
6. 重访口径：构造已知访问时刻的格点，核对首尾间隔、未访问格点的计算；
7. 快速评估（解析穿越法）与逐步长仿真的一致性。

用法（task2 目录下）：python validate.py --const out/n28
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import designs
from constellation import epoch_jd
from coverage import Grid, global_coverage, ground_half_width
from exactsim import ecef_track, simulate
from fasteval import FastEvaluator, revisit_stats
from propagate import propagate_j2_secular, propagate_rk4
from sso import R_EARTH, DAY, SSO_RATE_DEG_DAY, j2_rates, sso_inclination, beta_angle_deg

COLS = ['alt_km', 'inc_deg', 'raan_deg', 'u_deg']


def load(const_dir):
    e = pd.read_csv(Path(const_dir) / 'constellation.csv')
    return e.rename(columns={'h_km': 'alt_km'})


def check_sso(h=700.0):
    inc = sso_inclination(h)
    rd, _, _ = j2_rates(R_EARTH + h, 0.0, np.radians(inc))
    rate = np.degrees(rd) * DAY
    return dict(h_km=h, inc_deg=round(float(inc), 4), raan_rate_deg_day=round(float(rate), 6),
                target_deg_day=round(SSO_RATE_DEG_DAY, 6),
                error_pct=round(abs(rate / SSO_RATE_DEG_DAY - 1) * 100, 6))


def check_propagator(h=700.0, days=3.0):
    """解析长期项 vs RK4：节点周期一致性（按数值轨道自身的平均半长轴评估）。"""
    inc = float(sso_inclination(h))
    a = R_EARTH + h
    r0, v0 = propagate_j2_secular(a, np.array([inc]), np.array([30.0]), np.array([0.0]), 0.0)
    t = np.arange(0.0, days * 86400.0, 2.0)
    rr, vv = propagate_rk4(r0, v0, t, dt=2.0, use_j2=True)
    r = np.linalg.norm(rr[0], axis=-1)
    v = np.linalg.norm(vv[0], axis=-1)
    a_osc = 1.0 / (2.0 / r - v ** 2 / 398600.4418)
    z, vz = rr[0, :, 2], vv[0, :, 2]
    idx = np.nonzero((z[:-1] < 0) & (z[1:] >= 0) & (vz[:-1] > 0))[0]
    tc = t[idx] + 2.0 * (-z[idx]) / (z[idx + 1] - z[idx])
    T_num = float(np.diff(tc).mean())
    _, argp, mdot = j2_rates(a_osc.mean(), 0.0, np.radians(inc))
    T_ana = float(2 * np.pi / (argp + mdot))
    return dict(h_km=h, init_a_km=a, mean_osc_a_km=round(float(a_osc.mean()), 3),
                nodal_period_numeric_s=round(T_num, 3), nodal_period_analytic_s=round(T_ana, 3),
                error_s=round(abs(T_num - T_ana), 3), error_pct=round(abs(T_num / T_ana - 1) * 100, 6),
                note='数值积分用平均根数 a 作初始半径会得到偏小约 9 km 的平均瞬时半长轴')


def check_beta(e, days=7.0):
    jd0 = epoch_jd()
    inc = e['inc_deg'].to_numpy()
    om = j2_rates(R_EARTH + e['alt_km'].to_numpy(), 0.0, np.radians(inc))[0]
    raan0 = e['raan_deg'].to_numpy()
    b0 = beta_angle_deg(inc, raan0, jd0)
    b1 = beta_angle_deg(inc, raan0 + np.degrees(om) * days * DAY, jd0 + days)
    return dict(days=days, beta_drift_max_deg=round(float(np.abs(b1 - b0).max()), 4),
                beta_range_deg=[round(float(b0.min()), 3), round(float(b0.max()), 3)],
                note='β 漂移来自太阳赤经速率在年内的变化，不是节点进动误差')


def check_step(n=28, planes=14, h=700.0, days=1.0):
    el = designs.walker(n, planes, 3, h)
    jd0 = epoch_jd()
    g = Grid(-90.0, 90.0, 1.0)
    out = {}
    for st in (10.0, 5.0):
        t = np.arange(0.0, days * 86400.0 + st / 2, st)
        first = global_coverage(ecef_track(el, t, jd0), t, g, ground_half_width(h))
        out[st] = round(float(np.isfinite(first).mean()), 5)
    return dict(days=days, coverage_step10=out[10.0], coverage_step5=out[5.0],
                abs_diff=round(abs(out[10.0] - out[5.0]), 5))


def check_output(e, n_expected=None):
    need = {'sat_id', 'alt_km', 'a_km', 'inc_deg', 'raan_deg', 'u_deg'}
    i_sso = np.array([sso_inclination(h) for h in e['alt_km']])
    res = dict(n=int(e.shape[0]), columns_ok=need.issubset(set(e.columns)),
               alt_range_km=[float(e.alt_km.min()), float(e.alt_km.max())],
               alt_in_500_700=bool(e.alt_km.between(500, 700).all()),
               a_consistent=bool(np.allclose(e.a_km, e.alt_km + R_EARTH, atol=1e-5)),
               sso_inclination_max_err_deg=float(np.abs(e.inc_deg - i_sso).max()),
               angles_in_0_360=bool(e.raan_deg.between(0, 360).all() and e.u_deg.between(0, 360).all()),
               duplicate_sat=bool(e.sat_id.duplicated().any()))
    if n_expected is not None:
        res['n_matches_input'] = res['n'] == n_expected
    res['ok'] = bool(res['columns_ok'] and res['alt_in_500_700'] and res['a_consistent']
                     and res['sso_inclination_max_err_deg'] < 1e-5 and res['angles_in_0_360']
                     and not res['duplicate_sat'] and res.get('n_matches_input', True))
    return res


def check_revisit():
    """重访口径自测：仿真 100 s，三个格点，访问时刻已知。"""
    pos = np.array([0, 0, 1])
    t = np.array([10.0, 50.0, 30.0])
    out = {}
    # 格点0：0→10、10→50、50→100；格点1：0→30、30→100；格点2（从未访问）：100
    for name, kw, exp in (('计入未访问格点', dict(never_visited=True), [10, 40, 50, 30, 70, 100]),
                          ('不计未访问格点', dict(never_visited=False), [10, 40, 50, 30, 70])):
        m = revisit_stats(pos, t, 3, 100.0, **kw)
        out[name] = dict(Tavg_s=m['Tavg_s'], Tmax_s=m['Tmax_s'], expected=[float(np.mean(exp)), float(max(exp))],
                         ok=bool(m['n_intervals'] == len(exp) and abs(m['Tavg_s'] - np.mean(exp)) < 1e-9
                                 and abs(m['Tmax_s'] - max(exp)) < 1e-9))
    m = revisit_stats(pos, t, 3, 100.0)
    out['cell_counts_ok'] = (m['n_cells_0'], m['n_cells_1'], m['n_cells_2plus']) == (1, 1, 1)
    out['ok'] = bool(out['cell_counts_ok'] and all(v['ok'] for v in out.values() if isinstance(v, dict)))
    return out


def _cmp(fast, exact):
    gf, ge = fast['global_coverage'], exact['global_coverage']
    rf, re = fast['region_revisit'], exact['region_revisit']
    d = lambda a, b: None if a is None or b is None else round(abs(a - b), 3)
    res = dict(
        T90_diff_s={k: d(gf[k]['T90_s'], ge[k]['T90_s']) for k in gf},
        T100_diff_s={k: d(gf[k]['T100_s'], ge[k]['T100_s']) for k in gf},
        coverage_diff={k: round(abs(gf[k]['coverage'] - ge[k]['coverage']), 6) for k in gf},
        Tavg_h=[round(rf['Tavg_s'] / 3600, 3), round(re['Tavg_s'] / 3600, 3)],
        Tmax_h=[round(rf['Tmax_s'] / 3600, 3), round(re['Tmax_s'] / 3600, 3)],
        cells_lt2=[rf['n_cells_0'] + rf['n_cells_1'], re['n_cells_0'] + re['n_cells_1']])
    t90 = [v for v in res['T90_diff_s'].values() if v is not None]
    res['ok'] = bool(max(t90, default=0) <= 600 and abs(res['Tavg_h'][0] - res['Tavg_h'][1]) <= 0.01 * res['Tavg_h'][1]
                     and abs(res['Tmax_h'][0] - res['Tmax_h'][1]) <= 1.0)
    return res


def check_fast_vs_exact(e=None):
    jd0 = epoch_jd()
    cases = {'Walker 14/3 700km': designs.walker(28, 14, 3, 700.0)}
    if e is not None:
        cases['输出星座'] = e
    out = {}
    for name, el in cases.items():
        fe = FastEvaluator(jd0)
        fe.set_constellation(el[COLS].to_numpy())
        out[name] = _cmp(fe.metrics(), simulate(el, jd0))
    out['ok'] = all(v['ok'] for v in out.values() if isinstance(v, dict))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--const', default='out/n28', help='constellation.csv 所在目录')
    p.add_argument('--n', type=int, default=None, help='期望的卫星数（核对输出数量）')
    args = p.parse_args()
    e = load(args.const)
    rep = dict(sso=check_sso(), propagator=check_propagator(), beta=check_beta(e), step=check_step(),
               output=check_output(e, args.n), revisit=check_revisit(), fast_vs_exact=check_fast_vs_exact(e))
    (Path(args.const) / 'validation.json').write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
