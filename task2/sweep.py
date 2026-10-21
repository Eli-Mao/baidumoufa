"""赛题二：Walker / 回归轨道构型对比扫点（快速评估）。

对若干 (面数 P, 相位因子 F, 高度 h) 的 Walker 构型和赛题高度范围内的回归轨道构型，
输出 T90 / T100 / 覆盖率 / Tavg / Tmax，用来说明构型参数对各指标的影响，也是 optimizer 初选的展开版。

用法（task2 目录下）：python sweep.py --n 28 --planes 7 14 28 --h 600 700 --out out/sweep_28.csv
"""
import argparse
import sys
import time

import numpy as np
import pandas as pd

import designs as D
from constellation import epoch_jd
from fasteval import FastEvaluator

COLS = ['alt_km', 'inc_deg', 'raan_deg', 'u_deg']


def row(name, fe, df):
    fe.set_constellation(df[COLS].to_numpy())
    m = fe.flat()
    d = lambda x: np.nan if x is None else x / 86400
    return dict(design=name, h_km=round(float(df.alt_km.iloc[0]), 2), T90_d=d(m['T90']), T100_d=d(m['T100']),
                coverage=m['cov'], Tavg_h=m['Tavg'] / 3600, Tmax_h=m['Tmax'] / 3600, cells_lt2=m['n_lt2'])


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser()
    p.add_argument('--n', type=int, default=28)
    p.add_argument('--planes', type=int, nargs='+', default=None)
    p.add_argument('--h', type=float, nargs='+', default=[700.0])
    p.add_argument('--phasing', type=int, nargs='+', default=None, help='默认每个 P 取 0、1、P/4、P/2、3P/4、P−1')
    p.add_argument('--no-rgt', action='store_true', help='不扫回归轨道构型')
    p.add_argument('--out', default='sweep.csv')
    args = p.parse_args()

    fe = FastEvaluator(epoch_jd())
    planes = args.planes or [q for q in (7, 14, 28) if args.n % q == 0] or [args.n]
    rows, tic = [], time.perf_counter()
    for P in planes:
        Fs = args.phasing or sorted({0, 1, P // 4, P // 2, (3 * P) // 4, P - 1})
        for h in args.h:
            for F in Fs:
                rows.append(row(f'Walker P={P} F={F}', fe, D.walker(args.n, P, F, h)))
    if not args.no_rgt:
        for Q, Dd, h in D.rgt_options(max_days=8):
            rows.append(row(f'RGT {Q}/{Dd}', fe, D.rgt_interleaved(args.n, Q, Dd)))
    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    pd.set_option('display.width', 200)
    print(df.round(3).to_string(index=False))
    print(f'{len(df)} 个构型，用时 {time.perf_counter() - tic:.0f} s -> {args.out}')


if __name__ == '__main__':
    main()
