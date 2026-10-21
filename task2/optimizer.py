"""星座构型优化：输入卫星数 N，输出 (h, i, Ω, u)。

四个阶段（都用 fasteval 的解析评估，单次全量评估 0.1–0.5 s、改一颗星 5–20 ms）：

1. 构型初选：Walker（多种面数 P、相位因子 F，N 不整除时前几个面多放一颗）与
   回归轨道交错构型（赛题高度范围内所有 D ≤ 8 天的回归周期，"成簇"/"分散"两种排布），
   全部评估，各指标的最优值作为参考值 refs（相当于"当届最优"），按赛题评分公式打分。
2. 整体旋转：把所有卫星的升交点赤经同时加一个角度，全球覆盖不变（地面轨迹整体东移），
   但哪几条轨迹扫过长三角会变——对回归轨道构型，Tavg 可相差 30% 以上。
   对得分最高的几个构型做 0–360° 粗扫 + 细扫（只算区域重访）。
3. 坐标下降：逐颗卫星做一维穷举，保留使目标函数上升的移动，直到一轮没有改进或用完时间：
   - 回归轨道构型：轨迹平移整数个格距 360°/Q（D 天内的全球覆盖集合不变，只改时序），
     以及一圈内的时间提前量；
   - 其他构型：轨迹平移量与时间提前量各做"粗网格 → 细网格"三级搜索。
4. 取赛题分最高的构型输出。

目标函数见 score.py：赛题分（28·T90*/T90 + 12·T100*/T100 + 42·Tavg*/Tavg + 18·Tmax*/Tmax，
未达 90% / 100% 覆盖或有格点不足两次访问时按赛题规则置零）+ 少量平滑辅助项。
"""
import time

import numpy as np

import designs as D
import score as S
from fasteval import FastEvaluator

COLS = ['alt_km', 'inc_deg', 'raan_deg', 'u_deg']
GOLD = 0.6180339887498949


class Candidate:
    def __init__(self, name, kind, h, c, dt, Q=None):
        self.name, self.kind, self.h = name, kind, float(h)
        self.c, self.dt, self.Q = np.asarray(c, float), np.asarray(dt, float), Q
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


def walker_candidates(N, h=D.H_MAX):
    Ps = {p for p in range(2, N + 1) if N % p == 0 and p >= 3}
    Ps |= {max(3, int(round(N / k))) for k in range(1, 7)}
    Ps |= {p for p in (7, 8, 10, 12, 14, 16, 20) if p <= N}
    out = []
    for P in sorted(Ps):
        for F in sorted({0, 1, P // 4, P // 2, (3 * P) // 4, P - 1}):
            df = D.walker(N, P, F, h)
            hh, c, dt = D.to_track_offsets(df)
            out.append(Candidate(f'Walker P={P} F={F}', 'walker', hh, c, dt))
    return out


def rgt_candidates(N, max_days=8, walker_seeds=()):
    """回归轨道构型：N 颗星在一个格距内等分子位置；"格子号"只改各星时序、不改 D 天内的覆盖集合。"""
    out = []
    j = np.arange(N)
    for Q, Dd, h in D.rgt_options(max_days=max_days):
        s = 360.0 / Q
        per = _period(h)
        sub = j * s / N                                  # 每个格子里的子位置，N 颗星铺满一个格距
        dt = np.mod(j * GOLD, 1.0) * per
        cells = {'成簇': np.zeros(N),                    # 全在同一格
                 '分散': np.floor(j * Q / N),             # 均匀分到各格
                 '黄金': np.floor(np.mod(j * GOLD, 1.0) * Q)}   # 按黄金分割跳格
        for name, cell in cells.items():
            out.append(Candidate(f'RGT {Q}/{Dd} {name}', 'rgt', h, sub + cell * s, dt, Q))
        for P, F in walker_seeds:                        # Walker 结构放到回归高度上
            _, c, dtw = D.to_track_offsets(D.walker(N, P, F, h))
            out.append(Candidate(f'RGT {Q}/{Dd} Walker P={P} F={F}', 'rgt', h, c, dtw, Q))
    return out


class Optimizer:
    def __init__(self, N, jd0, region_polys=None, budget_s=300.0, strict_two_visits=True,
                 log=print, seed=0):
        self.N, self.jd0, self.budget = N, jd0, float(budget_s)
        self.strict = strict_two_visits
        self.fe = FastEvaluator(jd0, region_polys=region_polys)
        self.fr = FastEvaluator(jd0, region_polys=region_polys, region_only=True)
        self.log, self.rng = log, np.random.default_rng(seed)
        self.t0 = None
        self.history = []          # 所有评估过的 (名称, 扁平指标)，用于 refs

    def _left(self):
        return self.budget - (time.perf_counter() - self.t0)

    def _eval(self, cand, **kw):
        self.fe.set_constellation(cand.els(**kw))
        return self.fe.flat()

    def _region(self, cand, rot):
        self.fr.set_constellation(cand.els(rot=rot))
        return self.fr.region_metrics()

    def _region_value(self, r, refs):
        """区域重访得分；有格点不足两次访问时为负（这类格点越少越好），保证合规的旋转角总是优先。"""
        if r['Tavg_s'] is None:
            return -1.0
        if self.strict and r['visits_min'] < 2:
            return -(r['n_cells_0'] + r['n_cells_1']) / max(r['n_cells'], 1)
        return S.W['Tavg'] * refs['Tavg'] / r['Tavg_s'] + S.W['Tmax'] * refs['Tmax'] / r['Tmax_s']

    # ------------------------------------------------------------ 阶段 1
    def screen(self):
        walkers = walker_candidates(self.N)
        for c in walkers:
            c.flat = self._eval(c)
            self.history.append(c.flat)
        self.refs = S.make_refs(self.history)
        walkers.sort(key=lambda c: -S.official(c.flat, self.refs, self.strict)[0])
        seeds = []
        for c in walkers[:3]:
            P, F = (int(x.split('=')[1]) for x in c.name.split()[1:3])
            seeds.append((P, F))
        rgts = rgt_candidates(self.N, walker_seeds=seeds)
        for c in rgts:
            c.flat = self._eval(c)
            self.history.append(c.flat)
        cands = walkers + rgts
        self.refs = S.make_refs(self.history)
        for c in cands:
            c.official = S.official(c.flat, self.refs, self.strict)[0]
        cands.sort(key=lambda c: -c.official)
        self.log(f'[1/4] 初选 {len(cands)} 个构型，最好：' +
                 '；'.join(f'{c.name} {c.official:.1f}' for c in cands[:3]))
        return cands

    # ------------------------------------------------------------ 阶段 2
    def rotate(self, cands, top=6):
        regions = []
        for c in cands[:top]:
            if self._left() < 0.4 * self.budget:
                break
            coarse = [(rot, self._region(c, rot)) for rot in np.arange(0.0, 360.0, 3.0)]
            regions += [r for _, r in coarse]
            best = max(coarse, key=lambda x: self._region_value(x[1], self.refs))
            fine = [(rot, self._region(c, rot)) for rot in best[0] + np.arange(-2.75, 3.0, 0.25)]
            regions += [r for _, r in fine]
            rot, _ = max(fine + [best], key=lambda x: self._region_value(x[1], self.refs))
            c.rot = float(rot % 360.0)
            c.flat = self._eval(c)
            self.history.append(c.flat)
        # 旋转扫描里出现过的区域指标也算进参考值（只更新 Tavg / Tmax / Tq99）
        for r in regions:
            self.history.append(dict(Tavg=r['Tavg_s'], Tmax=r['Tmax_s'], Tq99=r['Tq99_s']))
        self.refs = S.make_refs(self.history)
        for c in cands:
            c.official = S.official(c.flat, self.refs, self.strict)[0]
        cands.sort(key=lambda c: -c.official)
        self.log(f'[2/4] 整体旋转后最好：' + '；'.join(
            f'{c.name}（旋转 {c.rot:.2f}°）{c.official:.1f}' for c in cands[:3]))
        return cands

    # ------------------------------------------------------------ 阶段 3
    def descend(self, cand, budget):
        fe, refs, N = self.fe, self.refs, self.N
        fe.set_constellation(cand.els())
        cur = S.objective(fe.flat(), refs, self.strict)
        c, dt = cand.c.copy(), cand.dt.copy()
        per = _period(cand.h)
        t_end = time.perf_counter() + budget
        rnd = 0

        def trial(j, cj, dtj):
            el = D.from_track_offsets(cand.h, [cj + cand.rot], [dtj])[COLS].to_numpy()[0]
            old = fe.update_sat(j, el)
            v = S.objective(fe.flat(), refs, self.strict)
            fe.revert_sat(j, old)
            return v

        while time.perf_counter() < t_end:
            rnd += 1
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
        cand.official = S.official(cand.flat, refs, self.strict)[0]
        return rnd

    # ------------------------------------------------------------ 总流程
    def run(self):
        self.t0 = time.perf_counter()
        cands = self.screen()
        cands = self.rotate(cands)
        top = cands[:2]
        for i, c in enumerate(top):
            share = self._left() / (len(top) - i)
            if share < 5:
                break
            before = c.official
            rounds = self.descend(c, share)
            self.log(f'[3/4] 坐标下降 {c.name}：{before:.2f} → {c.official:.2f}（{rounds} 轮）')
        # 赛题分相同（如 N 很小、所有构型都是 0 分）时，按含平滑项的目标函数挑
        best = max(cands, key=lambda c: (round(c.official, 6), S.objective(c.flat, self.refs, self.strict)))
        df = best.elements()
        self.fe.set_constellation(df[COLS].to_numpy())
        info = dict(design=best.name, rotation_deg=best.rot, h_km=best.h,
                    official_proxy=best.official, refs=self.refs, metrics=self.fe.metrics(),
                    flat=best.flat, elapsed_s=round(time.perf_counter() - self.t0, 1))
        self.log(f'[4/4] 选用 {best.name}（旋转 {best.rot:.2f}°），赛题分（相对参考值）{best.official:.2f}')
        return df, info
