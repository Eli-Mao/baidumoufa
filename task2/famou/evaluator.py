"""伐谋（FAMOU）评估器：给一个"星座设计程序"候选打分（赛题二）。

平台接口（Famou Skills 的 famou-artifact-generator 规范）：
    evaluate(path_user_py, task_name="default", timeout=3600) -> dict
    返回 validity（1 合法 / 0 非法）、combined_score（越大越好，非法为 0）、cost_time（秒）、
    error_info（合法时为空）、metric（各 N 的分数与指标）。

流程：对任务里的每个 N 并行起一个子进程运行候选程序
    python <path_user_py> --n N --budget B --out <csv>
（工作目录为本文件所在目录，PYTHONPATH 指向 task2，供候选 import designs / fasteval / score / sso），
读回星座，按赛题"轨道构型非法"判据检查（evaluate.legal，另查列齐全、数值有限），再用快速评估按赛题
公式算分（score.official，长三角整体不足两次访问时重访项 0 分），参考值取 famou/refs.json（固定，
由 make_refs.py 按当前口径生成，保证不同候选之间可比）。
combined_score = 各 N 赛题分的平均；单个 N 与参考值持平时约 100 分，优于参考值可超过 100。
任一 N 报错、超时（超过 预算 × 1.25 + 60 s）、输出缺失或构型非法，整个候选判为非法——
赛题要求程序对任意 N 都能给出合法构型。候选若改动了评估依赖的文件（task2/*.py、refs.json、本文件），
也判为非法。

本地自测（task2 目录下）：
    python famou/evaluator.py famou/init.py --task quick
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import evaluate as cli  # noqa: E402  task2/evaluate.py：load / legal 与命令行评估器同源
import score as S  # noqa: E402
from constellation import epoch_jd  # noqa: E402
from fasteval import FastEvaluator  # noqa: E402

REFS_JSON = HERE / 'refs.json'
COLS = ['alt_km', 'inc_deg', 'raan_deg', 'u_deg']

# task_name -> 评估的 N 与每个 N 的时间预算（秒）。37 不能被常见面数整除，防止策略只适配整除的 N。
TASKS = {
    'default': dict(ns=(28, 37, 60, 100), budget=120.0),
    'quick': dict(ns=(28,), budget=30.0),
    'full': dict(ns=(28, 37, 60, 100), budget=600.0),
}
SLACK = (1.25, 60.0)       # 单个 N 的硬超时 = 预算 × 1.25 + 60 s（含解释器启动与模块导入）
LOG_TAIL = 600


def load_refs(path=REFS_JSON):
    """refs.json -> {N: 秒为单位的 refs}。"""
    raw = json.loads(Path(path).read_text(encoding='utf-8'))['refs']
    return {int(n): dict(T90=r['T90_d'] * 86400.0, T100=r['T100_d'] * 86400.0,
                         Tavg=r['Tavg_h'] * 3600.0, Tmax=r['Tmax_h'] * 3600.0) for n, r in raw.items()}


def _fingerprint(skip):
    """评估依赖文件的哈希，用来发现候选程序改动评分口径。"""
    files = sorted(ROOT.glob('*.py')) + [REFS_JSON, Path(__file__).resolve()]
    return {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.resolve() != skip}


def _tail(path):
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    return text[-LOG_TAIL:].strip()


def _run(path_user_py, ns, budget, deadline, workdir):
    """并行运行候选程序；返回 {N: (退出码或 None=超时, 输出 csv, 日志, 用时 s)}。"""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), os.environ.get('PYTHONPATH', '')]).rstrip(os.pathsep),
               PYTHONIOENCODING='utf-8', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    limit = budget * SLACK[0] + SLACK[1]
    procs = {}
    for n in ns:
        out, log = workdir / f'n{n}.csv', workdir / f'n{n}.log'
        fh = open(log, 'wb')
        p = subprocess.Popen([sys.executable, str(path_user_py), '--n', str(n), '--budget', str(budget),
                              '--out', str(out)], cwd=str(HERE), env=env, stdout=fh, stderr=subprocess.STDOUT)
        procs[n] = (p, out, log, fh, time.perf_counter())
    res = {}
    for n, (p, out, log, fh, t0) in procs.items():
        try:
            rc = p.wait(timeout=max(min(t0 + limit, deadline) - time.perf_counter(), 0.1))
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            rc = None
        fh.close()
        res[n] = (rc, out, log, time.perf_counter() - t0)
    return res, limit


def _score(df, n, refs, fe):
    fe.set_constellation(df[COLS].to_numpy(float))
    m = fe.flat()
    total, parts = S.official(m, refs[n])
    d = lambda x: None if x is None else round(x / 86400.0, 4)
    return total, dict(score=round(total, 3), parts={k: round(v, 2) for k, v in parts.items()},
                       T90_d=d(m['T90']), T100_d=d(m['T100']), Tavg_h=round(m['Tavg'] / 3600.0, 3),
                       Tmax_h=round(m['Tmax'] / 3600.0, 3), region_visits=m['n_visits'])


def _check(df, n):
    missing = [c for c in COLS if c not in df]
    if missing:
        return f'缺少列 {missing}（需要 sat_id, h_km, inc_deg, raan_deg, u_deg）'
    if not np.isfinite(df[COLS].to_numpy(float)).all():
        return '含 NaN / inf'
    ok, why = cli.legal(df, n)
    return None if ok else why


def evaluate(path_user_py: str, task_name: str = "default", timeout: int = 3600) -> dict:
    t0 = time.perf_counter()
    cfg = TASKS.get(task_name, TASKS['default'])
    ns, budget = cfg['ns'], float(cfg['budget'])
    result = dict(validity=0.0, combined_score=0.0, cost_time=0.0, error_info='', metric={})

    def fail(msg, metric=None):
        result.update(error_info=msg, metric=metric or {}, cost_time=round(time.perf_counter() - t0, 2))
        return result

    path = Path(path_user_py).resolve()
    if not path.is_file():
        return fail(f'找不到候选程序 {path_user_py}')
    try:
        refs = load_refs()
    except (OSError, KeyError, ValueError) as e:
        return fail(f'读取 refs.json 失败：{e}')
    lacking = [n for n in ns if n not in refs]
    if lacking:
        return fail(f'refs.json 缺少 N = {lacking} 的参考值，先运行 famou/make_refs.py')

    before = _fingerprint(path)
    with tempfile.TemporaryDirectory(prefix='famou_eval_') as tmp:
        runs, limit = _run(path, ns, budget, t0 + float(timeout), Path(tmp))
        if _fingerprint(path) != before:
            return fail('候选程序改动了评估依赖文件（task2/*.py、refs.json 或评估器）')
        fe = FastEvaluator(epoch_jd())
        scores, metric = [], {}
        for n in ns:
            rc, out, log, sec = runs[n]
            if rc is None:
                return fail(f'N={n} 超时（{sec:.0f} s，上限 {limit:.0f} s）。日志尾部：{_tail(log)}', metric)
            if rc != 0:
                return fail(f'N={n} 退出码 {rc}。日志尾部：{_tail(log)}', metric)
            if not out.is_file():
                return fail(f'N={n} 没有写出 --out 文件', metric)
            try:
                df = cli.load(out)
            except Exception as e:  # noqa: BLE001  任何读不了的输出都判非法
                return fail(f'N={n} 输出无法读取：{e}', metric)
            why = _check(df, n)
            if why:
                return fail(f'N={n} 构型非法：{why}', metric)
            total, metric[f'n{n}'] = _score(df, n, refs, fe)
            metric[f'n{n}']['run_s'] = round(sec, 1)
            scores.append(total)

    result.update(validity=1.0, combined_score=float(np.mean(scores)), metric=metric,
                  cost_time=round(time.perf_counter() - t0, 2))
    return result


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='伐谋评估器本地自测：候选程序 -> 赛题分')
    p.add_argument('path_user_py')
    p.add_argument('--task', default='default', choices=sorted(TASKS))
    p.add_argument('--timeout', type=int, default=3600)
    args = p.parse_args(argv)
    r = evaluate(args.path_user_py, args.task, args.timeout)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r['validity'] == 1.0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
