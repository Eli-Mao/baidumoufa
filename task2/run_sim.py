"""赛题二：按赛题仿真条件对一个星座做逐步长仿真（"精确"评估）。

用法（task2 目录下）：
    python run_sim.py --elements out/n28/constellation.csv         # 评估生成器输出的星座
    python run_sim.py --walker 28 14 3 --h 700                    # 评估一个 Walker 构型（N P F）

输出 JSON：全球覆盖（reachable / all 两种有效区的 T90、T100、覆盖率）、
长三角整体重访 region_revisit（计分口径：不合并、计入首尾；merged 为合并口径）、
逐格点重访 region_revisit_cell（10-23 答疑前的旧口径，仅作参考）。
全球 10 s 步长、区域 1 s 步长，与赛题推荐的分析步长一致。
"""
import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

import designs
from constellation import epoch_jd
from exactsim import simulate
from region import load_geojson


def load_elements(path):
    df = pd.read_csv(path)
    if 'h_km' in df and 'alt_km' not in df:
        df = df.rename(columns={'h_km': 'alt_km'})
    return df


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='星座逐步长仿真（赛题二评估口径）')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--elements', help='星座文件（generate.py 输出的 constellation.csv）')
    g.add_argument('--walker', nargs=3, type=int, metavar=('N', 'P', 'F'), help='Walker 构型')
    p.add_argument('--h', type=float, default=700.0, help='Walker 构型的高度 km')
    p.add_argument('--step', type=float, default=10.0, help='全球覆盖步长 s')
    p.add_argument('--step-region', type=float, default=1.0, help='区域重访步长 s')
    p.add_argument('--region', default=None, help='长三角边界 GeoJSON（默认用内置简化轮廓）')
    p.add_argument('--out', default=None, help='把结果写到这个 JSON 文件')
    args = p.parse_args(argv)

    jd0 = epoch_jd()
    if args.elements:
        el = load_elements(args.elements)
    else:
        n, pl, f = args.walker
        el = designs.walker(n, pl, f, args.h, jd0=jd0)
    polys = load_geojson(args.region) if args.region else None
    tic = time.perf_counter()
    m = simulate(el, jd0, step=args.step, step_region=args.step_region, region_polys=polys)
    m['N'] = int(len(el))
    m['timing_s'] = round(time.perf_counter() - tic, 1)
    text = json.dumps(m, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
