"""STK 交付文件：每颗星的 .e 星历 + 一份建场景用的 Connect 命令脚本。

本机没有 STK，下面两类文件都没有在 STK 里实测过，在装有 STK 11.6 的机器上导入后请先核对：
1. `ephem/SAT_xxx.e`：J2000 位置速度，30 s 步长，由与评估相同的 J2 长期项模型生成，
   Satellite → Propagator 选 StkExternal 指向该文件即可复现我们评估用的轨迹；
2. `build_scenario.txt`：Connect 命令（STK 菜单 Utilities → Connect Command，或
   AgStkObjectRoot.ExecuteCommand 逐行执行）。按赛题条件建场景：J2 传播器、30 s 步长、
   J2000、平均根数、2027-01-01 ~ 01-08 UTCG，每颗星挂一个矩形视场传感器
   （交叉迹、沿迹半角都是 0.81°，答疑 #46；原文档沿迹为 0.001622°）。选矩形而不是
   Simple Conic 0.81°：两者幅宽相同，矩形与我们仿真用的方形视场判据（exactsim / coverage._hits）一致。
   覆盖分析（1° 全球网格、0.1° 长三角网格、10 s / 1 s 步长）的设置步骤写在 README 里，需在 STK 界面里完成。
"""
from pathlib import Path

import numpy as np

from coverage import ETA_DEG, ETA_ALONG_DEG
from propagate import propagate_j2_secular
from sso import R_EARTH

SCEN_START = '1 Jan 2027 00:00:00.000'
SCEN_STOP = '8 Jan 2027 00:00:00.000'


def write_ephemeris(path, times_s, r_km, v_kms, scenario_epoch=SCEN_START):
    lines = ['stk.v.11.0', 'BEGIN Ephemeris',
             f'NumberOfEphemerisPoints {len(times_s)}',
             f'ScenarioEpoch {scenario_epoch}',
             'InterpolationMethod Lagrange', 'InterpolationSamplesM1 5',
             'CentralBody Earth', 'CoordinateSystem J2000', 'DistanceUnit Kilometers',
             'EphemerisTimePosVel']
    for t, p, v in zip(times_s, r_km, v_kms):
        lines.append(f'{t:.3f} ' + ' '.join(f'{x:.6f}' for x in p) + ' ' + ' '.join(f'{x:.9f}' for x in v))
    lines.append('END Ephemeris')
    Path(path).write_text('\n'.join(lines) + '\n', encoding='ascii')


def connect_script(elems, scenario='Task2_Constellation'):
    """Connect 命令：建场景、按经典根数建卫星（J2 传播器）、挂矩形传感器（沿迹 × 交叉迹半角）。单位：米、度。"""
    out = [f'New / Scenario {scenario}',
           f'SetAnalysisTimePeriod * "{SCEN_START}" "{SCEN_STOP}"',
           'SetUnits / km sec deg UTCG']
    for r in elems.itertuples():
        name = f'SAT_{int(r.sat_id):03d}'
        a_m = (R_EARTH + r.alt_km) * 1000.0
        out += [f'New / */Satellite {name}',
                f'SetState */Satellite/{name} Classical J2Perturbation "{SCEN_START}" "{SCEN_STOP}" 30 '
                f'J2000 "{SCEN_START}" {a_m:.3f} 0.0 {r.inc_deg:.6f} 0.0 {r.raan_deg:.6f} {r.u_deg:.6f}',
                f'New / */Satellite/{name}/Sensor Cam',
                f'Define */Satellite/{name}/Sensor/Cam Rectangular {ETA_ALONG_DEG} {ETA_DEG}']
    return '\n'.join(out) + '\n'


def export(elems, out_dir, days=7.0, step=30.0):
    """写 ephem/*.e 与 build_scenario.txt，返回写出的文件数。"""
    out = Path(out_dir)
    (out / 'ephem').mkdir(parents=True, exist_ok=True)
    t = np.arange(0.0, days * 86400.0 + step / 2, step)
    for r in elems.itertuples():
        rr, vv = propagate_j2_secular(R_EARTH + r.alt_km, r.inc_deg, r.raan_deg, r.u_deg, t)
        write_ephemeris(out / 'ephem' / f'SAT_{int(r.sat_id):03d}.e', t, rr[0], vv[0])
    (out / 'build_scenario.txt').write_text(connect_script(elems), encoding='utf-8')
    return len(elems) + 1
