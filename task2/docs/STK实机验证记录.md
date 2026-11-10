# STK 11.6 实机验证记录（2026-11-05，固定 EOP 预测数据版）

**历史基线说明：**本页保存 2026-11-05 当时的原生全量结果与模型差异，未覆盖 2026-11-10 的坐标/椭球对齐及短时访问精化。
当前入口、默认模型和最新结论见 [轨道与 STK 工程验证](轨道与STK工程验证.md)。下文“完整模型未对齐”、旧默认值及旧误差只描述本页日期的状态。

本机 **STK 11.6.0 与 Coverage 已实际运行**。28 星独立轨道、全球覆盖、长三角整体访问、采样精化和便携场景重新打开检查均已完成。当前构型的有效区覆盖率为 **99.551152%**，7 天内还有 **265 个有效格点未覆盖**，不能引用 Python 近似结果的 100% 作为 STK 结论。

最终证据为 [`validation_summary.json`](../out/stk_validation_eop2026/validation_summary.json)。这里的“通过”指所述输入、数据与工程容差下的计算及收敛检查；完整 Python 模型等价和构型达到全覆盖两项仍为 false，也不是赛事官方成绩。

## 数据与场景

输入为 `out/n28/constellation.csv`，28 星、700 km、a=6371+700 km、e=0；时段为 2027-01-01 至 01-08 UTC。原生 J2Perturbation 按 J2000 平均根数初始化。相机为 NadirECFVel、Offset 0、零安装偏差，两轴半视场角均为 0.81°。

本机原 EOP 表更新于 2019-03-21，预测止于 2019-09-18，不含目标时段。最终场景采用 [CelesTrak EOP 数据](https://celestrak.org/SpaceData/EOP-All.txt)的固定快照：**2026-11-04 15:11:01 UTC 更新，数据至 2027-05-04**。2027 年记录是预测值，不能当作未来实测真值。下载来源、日期与 SHA-256 见 [`provenance.json`](../data/earth_orientation/provenance.json)。快照同时存入输入包、每次原始运行和便携场景；汇总会检查整个仿真时段有逐日数据，并核对实际 `.sc` 使用的文件与哈希。系统安装数据保持原样。

全球使用明确的 1° 格心点表，按点数等权统计。全地球 64800 点，按构型剔除不可达高纬后的有效区 59040 点。长三角使用原资料包的三个正式多边形，直接计算 Sensor→AreaTarget 的 `Any` 部分可见，不划区域评价网格。3270 点的旧区域网格仅保留作诊断。

## 最终结果

| 指标 | STK 实机结果 |
|---|---:|
| 独立轨道采样 | 282268 条，28 星完整 7 天，每 60 s 一点 |
| STK 速率约定下最大位置差 | 1.962980 m，工程门限 2 m |
| 有效区覆盖 | 58775 / 59040 = 99.551152% |
| T90 | 242805.429524 s = 67.445953 h |
| T100 | 7 天内未达到 |
| 长三角整体访问 | 169 次 |
| 平均重访，含首尾 | 3499.792507 s = 58.329875 min |
| 最大重访，含首尾 | 10027.219187 s = 167.120320 min |

同星仅合并各区域组成部分重叠或相接的窗口，不填补正长度间断；跨星按项目对“不合并”的解释排序统计。本构型无跨星重叠，因此不合并与并集统计相同。

全球自适应采样的最小步长为 0.001 s，最大步长分别为 60 s、30 s；事件时间容差 0.01 s。两轮 59040 点的覆盖状态和每点访问次数一致，各有 **390643 条逐资产访问**，逐点首次访问最大差为 **0.009793217 s**。[全球收敛证据](../out/stk_validation_eop2026/global_native_convergence.json)

区域 0.125 s 与 0.0625 s 曾得到 168、169 次，未通过收敛。差异定位到第 6 颗星约 **0.09375 s** 的离开区域间断，不能填成连续访问。[诊断记录](../out/stk_validation_eop2026/region_sampling_diagnostic.json)

最终用 **0.0625 s 与 0.03125 s** 复核，均为 169 次，逐星逐窗口最大端点差 **0.007000000 s**；平均重访差 **0.000184926 s**，最大重访差 **0.002812500 s**。细采样分为四组各七颗星并行计算，场景命令、点表、EOP 与其他元数据完全相同；分组仅选择工作清单。汇总拒绝重复、遗漏或修改输入的分组，核对全部 84 个星/区域对的原生保存采样后再组合。[最终区域收敛证据](../out/stk_validation_eop2026/region_native_refined_convergence.json)

有限步长收敛不是任意短事件绝不遗漏的数学证明。2 m、0.02 s 等门限是项目工程选择，资料没有给出对应的赛事官方容差。

## J2、太阳同步与模型差异

默认一阶长期项轨道对照的最大位置差约 1.827 km。新增 `rate_model='stk'`，在节点和近地点速率中乘入摄动平均运动与两体平均运动的比值 `M_dot/n`；本次独立原生轨迹对照最大差降至 1.963 m。该结论限于本次圆轨道输入与时段，不能据此认为地固变换或完整访问几何也等价。

已补充相同速率约定下的太阳同步倾角及高度反解。`sso_inclination(700, rate_model='stk')` 得到 **98.164026494°**；另建单星 STK 场景实测 7 天节点进动率为 **0.985647211099°/d**，与太阳同步目标的差为 **1.21e-07°/d**。[独立单星证据](../out/stk_validation_eop2026/sso_native_check.json)

本次 28 星输入仍为原有一阶解 98.158925°，没有把辅助设计试验混入当前构型。默认函数约定和旧优化结果保留原含义；下一轮构型若采用新约定，需同步选择相应校验和评估口径后重新优化。

| 指标 | Python 球面近似 | 本次 STK |
|---|---:|---:|
| 有效区覆盖率 | 100% | 99.551152% |
| T90 | 215225 s | 242805.429524 s |
| T100 | 502155 s | 未达到 |
| 区域访问次数 | 177 | 169 |
| 平均重访 | 3342.096032 s | 3499.792507 s |
| 最大重访 | 10031.820313 s | 10027.219187 s |

Python 地表仍为 6371 km 球面和地心纬度，地固变换为简化 GMST 旋转；STK 使用椭球大地纬度及更完整的变换。这些差异与区域边界处理共同影响窗口，目前没有逐项隔离误差贡献。旧优化器、固定参考值尚未按原生指标重新搜索，不能宣称当前 28 星在新口径下最优。安装数据下的历史结果另见 [旧 EOP 基线](STK实机验证记录_旧EOP基线.md)，不与本次数字混用。

## 已修复与验证

- 修正 STK 11.6 姿态命令缺少 `Offset 0`，并以英文临时目录解决 Connect 点表路径问题。
- 区域采样通过原生 `Access` 命令传入，保留相关 COM 对象至保存，并核验 `.sca`。仅有 COM 读回值不能证明采样生效；早期 151 次结果已排除。
- 原生 COV 6.0 使用弧度，RegionNumber 可重复。解析器核对唯一点编号、完整经纬度集合、全部资产及访问行；未覆盖点不被丢弃。
- 场景输入绑定现在包含冻结的 EOP。日期缺失、数据替换、错误原生采样或不完整分组均拒绝。
- 按官方接口调用 `STKX.Application.Terminate()` 结束引擎。最终全量运行和四组细化运行均正常退出；旧流程结束时退出码异常已修复。

**57 项单元测试通过**，另完成分组重复/遗漏两项负向检查、真实 STK 全量收敛、单星太阳同步对照及场景重新打开检查。[测试日志](../out/stk_validation_eop2026/unit_tests.log)

## 交付与复现

- [原生场景包](../out/stk_validation_eop2026/scene/Task2_Constellation_STK116.zip)：解压所有文件到英文路径，例如 `C:\STK_Task2`，在 STK 11.6 打开 `Task2_Constellation.sc`。包含全球访问缓存、正式区域对象、相对路径点表和固定 EOP。
- [场景验收记录](../out/stk_validation_eop2026/scene/scene_validation.json)：重新打开后验证 28 星、28 个传感器、3 个 AreaTarget、3 个 CoverageDefinition、全部点表，并重新加载固定 EOP。
- [全量格点首次访问](../out/stk_validation_eop2026/global_native_30.csv)、[265 个未覆盖点](../out/stk_validation_eop2026/global_uncovered_points.csv)、[169 条区域窗口](../out/stk_validation_eop2026/region_access_intervals.csv)。区域最终结果以窗口表和各组原始分量输出为准。
- [总验收 JSON](../out/stk_validation_eop2026/validation_summary.json)：运行目录、原始结果、冻结输入和当前校验代码的 SHA-256；完整模型等价与全覆盖状态分别记录。

在 `task2` 目录，用本机 Python 或 `../../.venv-task2/Scripts/python.exe` 准备新的输入包：

```powershell
python stk_export.py --elements out/n28/constellation.csv --out out/stk_new --region data/official_region/yangtze_river_delta_boundary.geojson --eop data/earth_orientation/EOP-20261105.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_stk.ps1 -Package .\out\stk_new -Engine -ComputeCoverage -GlobalAdaptive -GlobalMaxStep 30 -ParallelCores 8 -RegionStep 0.03125
```

Bypass 只作用于该进程。新的输出写入独立时间戳目录。单独区域复核加 `-SkipOrbit -SkipGlobal`，单独全球复核加 `-SkipOrbit -SkipRegion`；另用全球最大步长 60 s、区域固定步长 0.0625 s 作对照。把下面占位路径替换为真实目录：

```powershell
python compare_stk.py --elements out/n28/constellation.csv --states <运行目录>/stk_positions.csv --rate-model stk --tolerance-km 0.002 --out <运行目录>/orbit.json
python summarize_stk_coverage.py --run <运行目录> --package out/stk_new --out <运行目录>/global.json
python summarize_stk_region.py --run <运行目录> --package out/stk_new --out <运行目录>/region.json
python compare_stk_convergence.py --kind region --coarse <粗汇总.json> --fine <细汇总.json> --out <收敛.json>
```

完整单次区域运行用 `summarize_stk_region.py`。分组运行用 `summarize_stk_region_grouped.py --package <完整输入包> --runs <各组运行目录> --out <汇总.json>`，必须使用完全一致的场景和数据，并覆盖每颗星一次；不得拼接不同构型的结果。全球比较将 `--kind` 改为 `global`。未来仿真日期超出固定 EOP 范围时，应重新准备明确版本的数据并重算。
