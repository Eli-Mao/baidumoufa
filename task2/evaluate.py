"""伐谋（FAMOU）Evaluator 入口：把一个星座文件折算成赛题分。

伐谋按"生成 → 评估 → 迭代"演化：让它改写构型生成策略（designs.py / optimizer.py 里的构型族、
移动方式、预算分配），每生成一个星座就用本脚本打分。评分与 generate.py 同一套口径（score.py），
参考值（"当届最优"）固定取自某次 generate.py 的输出，保证不同候选之间可比。

用法（task2 目录下）：
    python evaluate.py --elements out/n28/constellation.csv --refs out/n28/metrics.json
    python evaluate.py --elements cand.csv --refs out/n28/metrics.json --exact   # 逐步长仿真打分

约定：最后一行打印裸分数，便于平台解析；星座不合法（数量不对、高度越界、倾角不满足太阳同步）时打印 -inf。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import score as S
from constellation import epoch_jd
from fasteval import FastEvaluator
from sso import design_inclination
from model_convention import element_model, using_rate_model

COLS = ['alt_km', 'inc_deg', 'raan_deg', 'u_deg']


def load(path):
    df = pd.read_csv(path)
    return df.rename(columns={'h_km': 'alt_km'})


def legal(df, n=None, rate_model='auto'):
    """赛题"轨道构型非法"判据：数量、高度范围、太阳同步倾角、e = 0。"""
    if n is not None and len(df) != n:
        return False, f'卫星数 {len(df)} ≠ {n}'
    if not df['alt_km'].between(500.0, 700.0).all():
        return False, '高度超出 500–700 km'
    try:
        selected=element_model(df,rate_model)
    except ValueError as exc:
        return False,str(exc)
    i_sso = design_inclination(df.alt_km.to_numpy(),df.raan_deg.to_numpy(),rate_model=selected)
    if not np.isfinite(df[COLS].to_numpy(float)).all() or np.abs(df['inc_deg'] - i_sso).max() > 1e-5:
        return False, '倾角不满足太阳同步条件'
    if 'ecc' in df and (df['ecc'].abs() > 1e-9).any():
        return False, '偏心率不为 0'
    return True, ''


def refs_from(path):
    r = json.loads(open(path, encoding='utf-8').read())['refs']
    return dict(T90=r['T90_d'] * 86400, T100=r['T100_d'] * 86400, Tavg=r['Tavg_h'] * 3600, Tmax=r['Tmax_h'] * 3600)


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='伐谋 Evaluator：星座文件 -> 赛题分')
    p.add_argument('--elements', required=True)
    p.add_argument('--refs', required=True, help='含 refs 的 metrics.json（generate.py 的输出）')
    p.add_argument('--n', type=int, default=None, help='期望的卫星数')
    p.add_argument('--exact', action='store_true', help='用逐步长仿真打分（慢）')
    p.add_argument('--rate-model',choices=['auto','stk','first_order'],default='auto')
    p.add_argument('--lenient', action='store_true', help='不按"长三角整体不足两次访问则重访 0 分"从严处理')
    args = p.parse_args(argv)

    df = load(args.elements)
    ok, why = legal(df, args.n,args.rate_model)
    if not ok:
        print(f'ILLEGAL: {why}')
        print('-inf')
        return 1
    selected=element_model(df,args.rate_model)
    reference_meta=json.loads(Path(args.refs).read_text(encoding='utf-8'))
    reference_model=reference_meta.get('rate_model','first_order')
    if reference_model!=selected:
        p.error(f'input uses {selected}, references use {reference_model}; recompute references before scoring')
    refs = refs_from(args.refs)
    jd0 = epoch_jd()
    fe = FastEvaluator(jd0,rate_model=selected)
    fe.set_constellation(df[COLS].to_numpy())
    m = fe.flat()
    if args.exact:
        from exactsim import simulate
        with using_rate_model(selected):
            ex = simulate(df, jd0)
        g, r = ex['global_coverage']['reachable'], ex['region_revisit']
        m.update(T90=g['T90_s'], T100=g['T100_s'], Tavg=r['Tavg_s'], Tmax=r['Tmax_s'], n_visits=r['n_visits'])
    total, parts = S.official(m, refs, not args.lenient)
    print(json.dumps(dict(score=round(total, 4),rate_model=selected,regional_model='legacy_grid_proxy', parts={k: round(v, 3) for k, v in parts.items()},
                          T90_d=m['T90'] and m['T90'] / 86400, T100_d=m['T100'] and m['T100'] / 86400,
                          Tavg_h=m['Tavg'] / 3600, Tmax_h=m['Tmax'] / 3600, region_visits=m['n_visits']),
                     ensure_ascii=False, indent=2))
    print(f'{total:.6f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
