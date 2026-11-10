# STK 11.6 安装数据基线（2019 EOP）

本页保留安装数据下的历史实测结果。原 EOP 文件更新于 2019-03-21，表内预测止于 2019-09-18；不含 2027 年目标时段。最新交付使用固定的 2026-11-04 预测数据，见 [最新实机验证记录](STK实机验证记录.md)。

GitHub 保留本页引用的历史指标摘要；旧 EOP 的原始运行目录和旧场景压缩包留在本机归档。当前可复现的完整证据与场景包见 [工程验证说明](轨道与STK工程验证.md)。

本机已实际运行 **STK 11.6.0 与 Coverage**，完成同一份 28 星输入的独立 J2 轨道、全球格点覆盖、长三角整体访问和两档采样复核。可携带场景已经重新打开检查。**当前构型在 STK 中的有效区覆盖率为 99.541%，未达到 100%；不能沿用 Python 近似模型的 100% 结论。**

总证据为 [`validation_summary.json`](../out/stk_validation_n28/validation_summary.json)。它区分“原生指标已做工程收敛验证”“构型达到全覆盖”“Python 完整模型与 STK 等价”，后两项均为 false。工程门限不是赛事官方容差；有限采样收敛也不是任意短事件都不遗漏的数学证明。

## 输入与软件

- 输入：`out/n28/constellation.csv`，28 星，700 km，a=6371+700 km，e=0；保持原构型做独立对照。
- 时段：2027-01-01 00:00:00 至 2027-01-08 00:00:00 UTC，共 604800 s。
- 轨道：原生 J2Perturbation，初始平均根数按 J2000 输入；不是将 Python 星历导回 STK 后自证。
- 载荷：NadirECFVel，Offset 0，矩形两轴半视场角均为 0.81°，零安装偏差，启用视场与视线约束。
- 区域：原资料包的三个正式多边形，建立 YRD_000～YRD_002，`Any` 部分可见；直接 Sensor→AreaTarget，区域不划评价网格。
- 全球：使用明确的 1° 格心点表。全地球 64800 点；按构型剔除不可达高纬后的有效区为 59040 点。点数等权统计，不使用默认面积百分比。
- 环境：`E:\Program Files\AGI\STK 11`。Coverage 对象创建、390635 条逐资产访问导出和全量计算均已实际执行；没有将“存在许可文件”当作授权可用的证据。

## 最终结果

| 指标 | STK 实机结果 |
|---|---:|
| 独立轨道采样 | 28 × 10081 = 282268 条，60 s 间隔，完整 7 天 |
| STK 速率约定下最大 J2000 位置差 | 1.969170 m，低于本次 2 m 工程比较门限 |
| 有效区覆盖 | 58769 / 59040 = 99.540989% |
| 未覆盖有效格点 | 271 |
| 有效区 T90 | 242867.323299 s = 67.463145 h |
| 有效区 T100 | 7 天内未达到 |
| 长三角整体访问 | 169 次 |
| 平均重访间隔，含首尾 | 3499.789843 s = 58.329831 min |
| 最大重访间隔，含首尾 | 10027.224187 s = 167.120403 min |

区域仅合并同一卫星访问不同区域分量时重叠或相接的窗口，不填补正长度间断；跨星按项目对“不合并”的解释排序统计。本构型没有跨星重叠，因此不合并和并集统计相同。

全球使用自适应采样，最小步长 0.001 s、最大步长分别为 60 s 和 30 s，事件时间容差 0.01 s。两次的 59040 个点覆盖状态和每点访问次数全部一致，逐点首次访问最大差 **0.009673351 s**。两次都是 390635 条逐资产访问。见 [`global_native_convergence.json`](../out/stk_validation_n28/global_native_convergence.json)。

区域使用固定步长 0.125 s 和 0.0625 s，事件时间容差 0.01 s。两次都是 169 次访问，逐星逐窗口最大端点差 **0.007625 s**，平均重访差 **0.000114338 s**，最大重访差 0 s。84 个星/区域对的计算与原生保存采样均完整。见 [`region_native_convergence.json`](../out/stk_validation_n28/region_native_convergence.json)。

## 与本地模型的差异

| 指标 | Python 球面近似 | STK 原生 |
|---|---:|---:|
| 有效区覆盖率 | 100% | 99.540989% |
| T90 | 215225 s | 242867.323299 s |
| T100 | 502155 s | 未达到 |
| 区域访问次数 | 177 | 169 |
| 平均重访 | 3342.096032 s | 3499.789843 s |
| 最大重访 | 10031.820313 s | 10027.224187 s |

原一阶长期项的轨道最大位置差为约 1.827 km。新增 `rate_model='stk'` 对照选项，在节点和近地点速率中使用摄动后的平均运动，即乘以 `M_dot/n`；此选项在本次圆轨道数据上将最大差降至 1.97 m。默认 `first_order` 保留，因此旧优化结果没有被静默改写。STK 将输入 J2000 根数转换到内部惯性传播系，仍有米级残差；本次只验证了这组输入和时段。

原输入倾角 98.158925°由一阶太阳同步条件得到。一阶目标节点率为 0.985647332°/d；采用新增 STK 速率约定计算约为 0.985035547°/d。若下一轮要求按该约定精确满足太阳同步，应重求倾角，并将新输入重新优化、重新仿真。

Python 地表仍采用 6371 km 球面和地心纬度，地固变换为简化 GMST 旋转；STK 使用椭球大地纬度及更完整的坐标变换。这些差异及区域边界处理共同影响访问窗口，目前没有逐项隔离它们的误差贡献。轨道位置通过比较，不能推出完整几何模型等价。旧优化器与固定参考值也未按原生 STK 指标重新搜索，当前构型不宣称为新口径下的最优解。

## 实机中修复的问题

1. STK 11.6 的 `NadirECFVel` 命令必须显式带 `Offset 0`；已修正导出器。
2. 旧版 Connect 点表读取不能可靠处理本项目中文目录。入口自动使用唯一的英文临时目录；结果复制回项目。
3. 区域高级设置的 COM 读回值不能单独证明实际采样生效。早期 151 次结果及其“步长收敛”已作废。最终通过原生 `Access` 命令传入采样参数，保留相关 COM 对象直到保存，再核验 `.sca` 中全部 84 对的固定步长。失败和被否决的原始目录保留作排错记录，不进入最终指标。
4. 原生 COV 6.0 导出使用弧度，且 RegionNumber 可重复。解析器以唯一点编号及完整经纬度集合核对网格，检查所有资产和访问行；未覆盖点不会被丢弃。
5. STK Engine 结束前须调用 `Terminate()`。早期区域全量运行在已完成保存后返回退出码 1；其原生文件已独立核验。入口已加入官方终止接口，并用固定步长实算验证正常退出。不能笼统忽略所有非零退出码。

Python 全套 **54 项测试通过**，含独立 STK 轨道实测基准、错误点表/缺失访问证据拒绝、原生采样配置核查；两轮全量收敛和场景重新打开是另行完成的实机检查。

## 交付文件

- 本机历史场景包 `out/stk_validation_n28/scene/Task2_Constellation_STK116.zip`：保留原生场景、对象、相对路径点表和全球访问缓存；GitHub 交付使用现行 EOP 的场景包。
- [`scene_validation.json`](../out/stk_validation_n28/scene/scene_validation.json)：重新打开后验证 28 星、28 个 Sensor、3 个 AreaTarget、3 个 CoverageDefinition，三个点表分别为 64800、59040、3270 点。3270 点的区域网格只是旧链路诊断。
- [`global_native_30.csv`](../out/stk_validation_n28/global_native_30.csv)：全量格点首次访问和访问次数。
- [`global_uncovered_points.csv`](../out/stk_validation_n28/global_uncovered_points.csv)：271 个未覆盖点的经纬度，可供下一轮构型优化使用。
- [`region_access_intervals.csv`](../out/stk_validation_n28/region_access_intervals.csv)：169 条逐星整体区域访问窗口。区域结果以此表及原始分量输出为准，便携场景中的区域对象可供重新计算。
- [`validation_summary.json`](../out/stk_validation_n28/validation_summary.json)：最终指标、运行目录、采样比较和输入/源码/原始结果 SHA-256。

最终采纳的运行目录均位于 `out/stk_validation_n28/stk/`：轨道 `183142_984`；全球 `193323_060`、`194920_078`；区域 `195511_523`、`200333_309`，共同日期前缀为 `stk_run_20261105_`。轨道目录的后续旧保存步骤曾中断，但独立 CSV 已完成；重新汇总严格检查了全部卫星、首尾时刻及 60 s 最大间隔。

## 复现入口

在 `task2` 目录运行；PowerShell 的 Bypass 仅用于本次进程，不修改系统执行策略：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_stk.ps1 -Package .\out\stk_validation_n28\stk -Engine -ComputeCoverage -GlobalAdaptive -GlobalMaxStep 30 -ParallelCores 8 -RegionStep 0.0625
```

该命令新建独立实例，导出轨道并计算两类访问。单独复核区域可加 `-SkipOrbit -SkipGlobal`；单独复核全球可加 `-SkipOrbit -SkipRegion`。新的输出使用独立时间戳目录。将下面的 `<运行目录>` 替换为真实目录：

```powershell
python compare_stk.py --elements out/n28/constellation.csv --states <运行目录>/stk_positions.csv --rate-model stk --tolerance-km 0.002 --out <运行目录>/orbit_comparison.json
python summarize_stk_coverage.py --run <运行目录> --package out/stk_validation_n28/stk --out <运行目录>/global.json
python summarize_stk_region.py --run <运行目录> --package out/stk_validation_n28/stk --out <运行目录>/region.json
```

另用全球最大步长 60 s、区域固定步长 0.125 s 分别重算，再用 `compare_stk_convergence.py --kind global|region --coarse <粗汇总.json> --fine <细汇总.json> --out <比较.json>` 比较。汇总器会核查点表、84 对区域计算、原生保存的真实采样和六个场景输入文件的绑定；只有模型说明、原始数据和采样复核共同成立，才采用结果。
