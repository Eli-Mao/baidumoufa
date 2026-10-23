"""给伐谋评估器生成固定参考值 famou/refs.json（按当前评分口径）。

参考值（"当届最优"的替身）= 同一 N 下构型初选与整体旋转扫描里各指标的最优值，
与 generate.py 写进 metrics.json 的 refs 是同一套算法（optimizer.Optimizer.screen / rotate），
但不做坐标下降、不写 out/。演化期间参考值必须固定，候选之间的分数才可比；
评分口径变了（如 10-23 答疑把重访改为长三角整体口径）就重跑一次：

    python famou/make_refs.py                 # 默认 N = 28 37 60 100（task2 目录下）
    python famou/make_refs.py --n 28 60
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from constellation import epoch_jd  # noqa: E402
from optimizer import Optimizer  # noqa: E402

DEFAULT_NS = (28, 37, 60, 100)


def refs_for(n):
    """返回 (refs，单位 天 / 小时, 初选与旋转用时 s)。"""
    opt = Optimizer(n, epoch_jd(), budget_s=1e9, log=lambda *_: None)
    opt.t0 = time.perf_counter()
    opt.rotate(opt.screen())
    r = opt.refs
    return (dict(T90_d=r['T90'] / 86400.0, T100_d=r['T100'] / 86400.0,
                 Tavg_h=r['Tavg'] / 3600.0, Tmax_h=r['Tmax'] / 3600.0),
            time.perf_counter() - opt.t0)


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='生成伐谋评估器的固定参考值 refs.json')
    p.add_argument('--n', type=int, nargs='+', default=list(DEFAULT_NS))
    p.add_argument('--out', default=str(HERE / 'refs.json'))
    args = p.parse_args(argv)

    out = Path(args.out)
    data = json.loads(out.read_text(encoding='utf-8')) if out.exists() else {}
    refs = data.get('refs', {})
    for n in args.n:
        refs[str(n)], sec = refs_for(n)
        print(f'N={n}: ' + ', '.join(f'{k}={v:.4f}' for k, v in refs[str(n)].items()) + f'（{sec:.1f} s）')
    data = dict(
        generated=datetime.now().isoformat(timespec='seconds'),
        rule='长三角整体、不合并、计入首尾的重访口径（答疑 #45-3 / #28 / #49-1）；全球覆盖按 reachable 有效区',
        method='optimizer.Optimizer 初选 + 整体旋转扫描中各指标的最优值（不含坐标下降）',
        refs=dict(sorted(refs.items(), key=lambda kv: int(kv[0]))))
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'写入 {out}')


if __name__ == '__main__':
    main()
