"""评估器区分度验证用的弱候选：不做任何搜索的普通 Walker（P ≈ √N 面，F = 1，700 km）。

与 init.py 同一调用契约：python walker_baseline.py --n N --budget 秒 --out 星座.csv
"""
import argparse

import numpy as np
import pandas as pd

import designs as D


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--n', type=int, required=True)
    p.add_argument('--budget', type=float, required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args(argv)
    df = D.walker(args.n, max(3, int(round(np.sqrt(args.n)))), 1, D.H_MAX)
    pd.DataFrame(dict(sat_id=np.arange(1, len(df) + 1), h_km=df['alt_km'], inc_deg=df['inc_deg'],
                      raan_deg=df['raan_deg'], u_deg=df['u_deg'])).to_csv(args.out, index=False)


if __name__ == '__main__':
    main()
