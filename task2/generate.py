"""赛题二主程序：输入卫星总数 N，自动生成太阳同步星座构型并输出每颗星的轨道初始参数。

用法（task2 目录下）：
    python generate.py --n 28                        # 结果写到 out/n28/（默认搜索 600 s）
    python generate.py --n 60 --budget 900 --exact   # 加长搜索时间，并做逐步长仿真复核
    python generate.py --n 28 --stk                  # 另外导出 STK 星历与建场景脚本

输出（--out 目录，默认 out/n{N}）：
    constellation.csv   每颗星一行：sat_id, h_km, inc_deg, raan_deg, u_deg, a_km, ecc, argp_deg
                        （历元 2027-01-01 00:00:00 UTCG，J2000，平均根数；h 相对平均半径 6371 km，
                        a = 6371 + h；e = 0、ω = 0，u 为纬度幅角 = ω + 真近点角）
    constellation.json  同上，外加生成参数与评估指标
    metrics.json        快速评估（与 --exact 时的逐步长仿真）结果：Tavg_h / Tmax_h 为长三角整体、
                        不合并口径（答疑 #45-3 / #28），merged 为合并口径，per_cell_old 为旧的逐格点口径
    stk/                （--stk）STK 星历 *.e 与 Connect 建场景脚本
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from constellation import epoch_jd
from optimizer import Optimizer
from region import load_geojson
from sso import R_EARTH

EPOCH = '2027-01-01T00:00:00 UTCG'


def output_table(df):
    t = pd.DataFrame({
        'sat_id': np.arange(1, len(df) + 1),
        'h_km': df['alt_km'].round(6),
        'inc_deg': df['inc_deg'].round(6),
        'raan_deg': (df['raan_deg'] % 360.0).round(6),
        'u_deg': (df['u_deg'] % 360.0).round(6),
        'a_km': (df['alt_km'] + R_EARTH).round(6),
        'ecc': 0.0,
        'argp_deg': 0.0,
    })
    return t


def _days(x):
    return None if x is None else round(x / 86400.0, 4)


def _hours(x):
    return None if x is None else round(x / 3600.0, 3)


def summarize(m):
    """Tavg_h / Tmax_h / region_visits 为计分口径（长三角整体、不合并）；merged 为合并口径，
    per_cell_old 为 10-23 答疑前的逐格点口径（仅作参考）。"""
    g, r, c = m['global_coverage'], m['region_revisit'], m['region_revisit_cell']
    return dict(
        T90_d=_days(g['reachable']['T90_s']), T100_d=_days(g['reachable']['T100_s']),
        coverage_7d=round(g['reachable']['coverage'], 6),
        T90_all_grid_d=_days(g['all']['T90_s']), T100_all_grid_d=_days(g['all']['T100_s']),
        coverage_all_grid_7d=round(g['all']['coverage'], 6),
        Tavg_h=_hours(r['Tavg_s']), Tmax_h=_hours(r['Tmax_s']), region_visits=r['n_visits'],
        region_two_visits_ok=r['valid'],
        merged=dict(Tavg_h=_hours(r['merged']['Tavg_s']), Tmax_h=_hours(r['merged']['Tmax_s']),
                    region_visits=r['merged']['n_visits']),
        per_cell_old=dict(Tavg_h=_hours(c['Tavg_s']), Tmax_h=_hours(c['Tmax_s']),
                          region_cells=c['n_cells'], cells_lt2_visits=c['n_cells_0'] + c['n_cells_1'],
                          visits_per_cell_min=c['visits_min'], visits_per_cell_mean=round(c['visits_mean'], 3)))


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='赛题二：按卫星总数 N 生成太阳同步星座构型')
    p.add_argument('--n', type=int, required=True, help='卫星总数 N')
    p.add_argument('--out', default=None, help='输出目录（默认 out/n{N}）')
    p.add_argument('--budget', type=float, default=600.0, help='搜索时间上限（秒），N 大时适当加长')
    p.add_argument('--region', default=None, help='长三角边界 GeoJSON（默认内置简化轮廓）')
    p.add_argument('--lenient', action='store_true',
                   help='不把"长三角整体不足两次访问"按重访项 0 分处理（默认按赛题规则从严）')
    p.add_argument('--exact', action='store_true', help='生成后用逐步长仿真（10 s / 1 s）复核指标')
    p.add_argument('--stk', action='store_true', help='导出 STK 星历与建场景脚本')
    p.add_argument('--seed', type=int, default=0, help='随机种子（坐标下降的卫星顺序）')
    args = p.parse_args(argv)
    if args.n < 1:
        p.error('N 必须为正整数')

    out = Path(args.out or f'out/n{args.n}')
    out.mkdir(parents=True, exist_ok=True)
    jd0 = epoch_jd()
    polys = load_geojson(args.region) if args.region else None
    tic = time.perf_counter()
    opt = Optimizer(args.n, jd0, region_polys=polys, budget_s=args.budget,
                    strict_two_visits=not args.lenient, seed=args.seed)
    df, info = opt.run()

    table = output_table(df)
    table.to_csv(out / 'constellation.csv', index=False)
    metrics = dict(fast=summarize(info['metrics']), design=info['design'],
                   rotation_deg=round(info['rotation_deg'], 4),
                   proxy_score=round(info['official_proxy'], 3),
                   refs=dict(T90_d=_days(info['refs']['T90']), T100_d=_days(info['refs']['T100']),
                             Tavg_h=_hours(info['refs']['Tavg']), Tmax_h=_hours(info['refs']['Tmax'])),
                   search_s=info['elapsed_s'])
    if args.exact:
        from exactsim import simulate
        metrics['exact'] = summarize(simulate(df, jd0, region_polys=polys))
    meta = dict(N=args.n, epoch=EPOCH, frame='J2000', elements='mean (J2 secular)',
                altitude_reference='mean Earth radius 6371 km (a = 6371 + h)',
                design=info['design'], h_km=round(info['h_km'], 4), metrics=metrics,
                satellites=table.to_dict(orient='records'))
    (out / 'constellation.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.stk:
        from stk_export import export
        export(df.assign(sat_id=np.arange(1, len(df) + 1)), out / 'stk')
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f'输出：{out.resolve()}（用时 {time.perf_counter() - tic:.0f} s）')


if __name__ == '__main__':
    main()
