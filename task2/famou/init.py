"""伐谋演化的初始程序（赛题二：面向全球覆盖与区域重访的星座构型设计）。

调用契约（famou/evaluator.py 按此运行；EVOLVE-BLOCK 之外的部分不要改）：
    python init.py --n N --budget 秒 --out 星座.csv
在 --budget 秒内为 N 颗星设计太阳同步圆轨道星座，写出每颗星一行：sat_id, h_km, inc_deg, raan_deg, u_deg
（历元 2027-01-01 00:00:00 UTCG，J2000 平均根数，h 相对平均半径 6371 km，u 为纬度幅角）。
硬约束：恰好 N 颗星；500 ≤ h ≤ 700 km；倾角 = sso_inclination(h)（太阳同步）；e = 0。
超出预算太多、报错或违反硬约束，候选即判为非法。

designs / fasteval / score / sso / constellation 是固定模块（物理模型与评分口径），由评估器通过
PYTHONPATH 提供。EVOLVE-BLOCK 里是可演化的设计策略，基线取自 task2/optimizer.py（10-23 长三角整体
重访口径版）：构型初选（Walker + 回归轨道）→ 整体旋转 → 逐星坐标下降。与 optimizer.py 不同的是
初选也按预算截停，保证在预算内交出结果。
"""
import argparse
import time

import numpy as np
import pandas as pd

import designs as D
import score as S
from constellation import epoch_jd
from fasteval import FastEvaluator

COLS = ['alt_km', 'inc_deg', 'raan_deg', 'u_deg']

# EVOLVE-BLOCK-START
GOLD = 0.6180339887498949


class Candidate:
    """一个构型：同一高度 h 上各星的轨迹经度平移 c（度）与时间提前 dt（秒），外加整体旋转 rot。"""

    def __init__(self, name, kind, h, c, dt, Q=None, walker=None):
        self.name, self.kind, self.h = name, kind, float(h)
        self.c, self.dt, self.Q = np.asarray(c, float), np.asarray(dt, float), Q
        self.walker = walker              # Walker 构型的 (P, F, 升交点赤经跨度)
        self.flat, self.official, self.rot = None, None, 0.0

    def elements(self, c=None, dt=None, rot=None):
        c = self.c if c is None else c
        dt = self.dt if dt is None else dt
        rot = self.rot if rot is None else rot
        return D.from_track_offsets(self.h, np.asarray(c) + rot, dt)

    def els(self, **kw):
        return self.elements(**kw)[COLS].to_numpy()


def _period(h):
    return 2 * np.pi / D.rates(h)[2]


def _walker_name(P, F, span):
    return f'Walker P={P} F={F}' + ('' if span == 360.0 else f' span={span:.0f}')


def walker_candidates(N, h=D.H_MAX):
    Ps = {p for p in range(2, N + 1) if N % p == 0 and p >= 3}
    Ps |= {max(3, int(round(N / k))) for k in range(1, 7)}
    Ps |= {p for p in (7, 8, 10, 12, 14, 16, 20) if p <= N}
    out = []
    for P in sorted(Ps):
        for span, Fs in ((360.0, {0, 1, P // 4, P // 2, (3 * P) // 4, P - 1}),
                         (180.0, {0, 1, P // 2})):      # 跨 180°：升、降段过境时刻交错
            for F in sorted(Fs):
                hh, c, dt = D.to_track_offsets(D.walker(N, P, F, h, raan_span=span))
                out.append(Candidate(_walker_name(P, F, span), 'walker', hh, c, dt, walker=(P, F, span)))
    return out


def rgt_candidates(N, max_days=8, walker_seeds=()):
    """回归轨道构型：N 颗星在一个格距内等分子位置；"格子号"只改各星时序、不改 D 天内的覆盖集合。"""
    out = []
    j = np.arange(N)
    for Q, Dd, h in D.rgt_options(max_days=max_days):
        s = 360.0 / Q
        per = _period(h)
        sub = j * s / N
        dt = np.mod(j * GOLD, 1.0) * per
        cells = {'cluster': np.zeros(N), 'spread': np.floor(j * Q / N),
                 'golden': np.floor(np.mod(j * GOLD, 1.0) * Q)}
        for name, cell in cells.items():
            out.append(Candidate(f'RGT {Q}/{Dd} {name}', 'rgt', h, sub + cell * s, dt, Q))
        for span in (360.0, 180.0):                      # 升交点赤经均布，过境地方时错开
            c, dtu = D.rgt_uniform_raan(N, Q, h, span)
            out.append(Candidate(f'RGT {Q}/{Dd} uniform-raan {span:.0f}', 'rgt', h, c, dtu, Q))
        for P, F, span in walker_seeds:                  # Walker 结构放到回归高度上
            _, c, dtw = D.to_track_offsets(D.walker(N, P, F, h, raan_span=span))
            out.append(Candidate(f'RGT {Q}/{Dd} {_walker_name(P, F, span)}', 'rgt', h, c, dtw, Q))
    return out


class Designer:
    # 各阶段截止时刻（占预算的比例）：Walker 初选、回归轨道初选、整体旋转；剩下的给坐标下降
    STOP_WALKER, STOP_RGT, STOP_ROTATE, RESERVE = 0.20, 0.45, 0.65, 0.05

    def __init__(self, N, jd0, budget_s, seed=0):
        self.N, self.budget = N, float(budget_s)
        self.fe = FastEvaluator(jd0)
        self.fr = FastEvaluator(jd0, region_only=True)
        self.rng = np.random.default_rng(seed)
        self.history = []          # 评估过的扁平指标，用来估参考值 refs（搜索目标里的"当届最优"）
        self.t0 = time.perf_counter()

    def _elapsed(self):
        return time.perf_counter() - self.t0

    def _before(self, frac):
        return self._elapsed() < frac * self.budget

    def _eval(self, cand, **kw):
        self.fe.set_constellation(cand.els(**kw))
        return self.fe.flat()

    def _region(self, cand, rot):
        self.fr.set_constellation(cand.els(rot=rot))
        return self.fr.region_metrics()

    def _region_value(self, r, refs):
        """区域重访得分（长三角整体）+ 间隔均方根平滑项；整体不足两次访问时为负。"""
        if not r['valid']:
            return r['n_visits'] - 2.0
        return (S.W['Tavg'] * refs['Tavg'] / r['Tavg_s'] + S.W['Tmax'] * refs['Tmax'] / r['Tmax_s']
                + S.SOFT['Trms'] * refs['Trms'] / r['Trms_s'])

    def _score_all(self, cands):
        self.refs = S.make_refs(self.history)
        for c in cands:
            c.official = S.official(c.flat, self.refs)[0]
        cands.sort(key=lambda c: -c.official)
        return cands

    def screen(self):
        walkers = []
        for c in walker_candidates(self.N):
            if walkers and not self._before(self.STOP_WALKER):
                break
            c.flat = self._eval(c)
            self.history.append(c.flat)
            walkers.append(c)
        walkers = self._score_all(walkers)
        rgts = []
        for c in rgt_candidates(self.N, walker_seeds=[c.walker for c in walkers[:3]]):
            if not self._before(self.STOP_RGT):
                break
            c.flat = self._eval(c)
            self.history.append(c.flat)
            rgts.append(c)
        return self._score_all(walkers + rgts)

    def rotate(self, cands, top=6):
        """整体旋转：全球覆盖不变，只改哪几条轨迹、在一天里什么时刻扫过长三角。"""
        for c in cands[:top]:
            if not self._before(self.STOP_ROTATE):
                break
            coarse = [(rot, self._region(c, rot)) for rot in np.arange(0.0, 360.0, 3.0)]
            best = max(coarse, key=lambda x: self._region_value(x[1], self.refs))
            fine = [(rot, self._region(c, rot)) for rot in best[0] + np.arange(-2.75, 3.0, 0.25)]
            rot, _ = max(fine + [best], key=lambda x: self._region_value(x[1], self.refs))
            c.rot = float(rot % 360.0)
            c.flat = self._eval(c)
            self.history.append(c.flat)
            for _, r in coarse + fine:
                if r['valid']:
                    self.history.append(dict(Tavg=r['Tavg_s'], Tmax=r['Tmax_s'], Trms=r['Trms_s']))
        return self._score_all(cands)

    def descend(self, cand, budget):
        """逐星一维穷举，保留使目标函数上升的移动，直到一轮无改进或用完 budget 秒。"""
        fe, refs, N = self.fe, self.refs, self.N
        fe.set_constellation(cand.els())
        cur = S.objective(fe.flat(), refs)
        c, dt = cand.c.copy(), cand.dt.copy()
        per = _period(cand.h)
        t_end = time.perf_counter() + budget

        def trial(j, cj, dtj):
            el = D.from_track_offsets(cand.h, [cj + cand.rot], [dtj])[COLS].to_numpy()[0]
            old = fe.update_sat(j, el)
            v = S.objective(fe.flat(), refs)
            fe.revert_sat(j, old)
            return v

        while time.perf_counter() < t_end:
            improved = 0
            for j in self.rng.permutation(N):
                if time.perf_counter() > t_end:
                    break
                best_v, best = cur, None
                if cand.kind == 'rgt':
                    s = 360.0 / cand.Q
                    for a in range(1, cand.Q):
                        v = trial(j, c[j] + a * s, dt[j])
                        if v > best_v + 1e-9:
                            best_v, best = v, (c[j] + a * s, dt[j])
                    for x in np.linspace(0.0, per, 37)[:-1]:
                        v = trial(j, c[j], x)
                        if v > best_v + 1e-9:
                            best_v, best = v, (c[j], x)
                else:
                    for var, span in (('c', 360.0), ('dt', per)):
                        base = c[j] if var == 'c' else dt[j]
                        grid = base + np.linspace(-span / 2, span / 2, 73)[:-1]
                        bx = None
                        for _ in range(3):
                            for x in grid:
                                x = x % span
                                v = trial(j, x, dt[j]) if var == 'c' else trial(j, c[j], x)
                                if v > best_v + 1e-9:
                                    best_v, bx = v, x
                            step = grid[1] - grid[0]
                            grid = (bx if bx is not None else base) + np.linspace(-step, step, 9)
                        if bx is not None:
                            best = (bx, dt[j]) if var == 'c' else (c[j], bx)
                            if var == 'c':
                                c[j] = bx
                            else:
                                dt[j] = bx
                if best is not None:
                    c[j], dt[j] = best
                    fe.update_sat(j, D.from_track_offsets(cand.h, [c[j] + cand.rot], [dt[j]])[COLS].to_numpy()[0])
                    cur = best_v
                    improved += 1
            if improved == 0:
                break
        cand.c, cand.dt = c, dt
        cand.flat = self._eval(cand)
        cand.official = S.official(cand.flat, refs)[0]

    def run(self):
        cands = self.rotate(self.screen())
        top = cands[:2]
        for i, c in enumerate(top):
            share = ((1.0 - self.RESERVE) * self.budget - self._elapsed()) / (len(top) - i)
            if share < 2.0:
                break
            self.descend(c, share)
        # 赛题分相同（如所有构型都是 0 分）时，按含平滑项的目标函数挑
        best = max(cands, key=lambda c: (round(c.official, 6), S.objective(c.flat, self.refs)))
        return best.elements()


def design(N, jd0, budget_s):
    """入口：在 budget_s 秒内设计 N 颗星的星座，返回含 alt_km, inc_deg, raan_deg, u_deg 的 DataFrame。"""
    return Designer(N, jd0, budget_s).run()
# EVOLVE-BLOCK-END


def main(argv=None):
    p = argparse.ArgumentParser(description='赛题二星座构型设计（伐谋演化候选）')
    p.add_argument('--n', type=int, required=True, help='卫星总数 N')
    p.add_argument('--budget', type=float, required=True, help='时间预算（秒）')
    p.add_argument('--out', required=True, help='输出星座 CSV')
    args = p.parse_args(argv)
    df = design(args.n, epoch_jd(), args.budget)
    pd.DataFrame(dict(sat_id=np.arange(1, len(df) + 1), h_km=df['alt_km'].to_numpy(float),
                      inc_deg=df['inc_deg'].to_numpy(float), raan_deg=df['raan_deg'].to_numpy(float) % 360.0,
                      u_deg=df['u_deg'].to_numpy(float) % 360.0)).to_csv(args.out, index=False)


if __name__ == '__main__':
    main()
