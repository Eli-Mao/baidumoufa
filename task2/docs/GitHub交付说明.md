# 赛题二 GitHub 交付说明

更新日期：2026-11-10。交付对应太阳同步/J2 模型、轨道传播、独立访问几何，以及当前 28 星的 STK 工程验证。入口和结果解释见 [工程验证报告](轨道与STK工程验证.md)；每个交付文件的路径、大小和 SHA-256 见 [交付清单](GitHub交付清单.json)。

## 仓库包含的成果

- [可视化任务看板](../dashboard/index.html)：下载项目后可直接离线打开，查看职责、已完成工作、覆盖时间轴、区域窗口与下一步任务；支持汇报摘要复制、下载和打印。更新与检查方法见 [看板说明](../dashboard/README.md)。

- Python 与 PowerShell 实现、68 项单元及原生数据回归测试、独立 STK 测试样本。
- 正式长三角边界、原始区域对象、答疑标注版 Excel，以及固定的 EOP 预测数据。
- `out/engineering_verified_20261110_final/`：当前 28 星的最终验收、逐格点与逐窗口结果、采样精化证据和运行日志。可重新导出的诊断星历不入库。
- `out/stk_validation_eop2026/`：复用原生全量基线所需的全部已登记证据、建场景输入、指标摘要和可携带的 STK 场景压缩包。
- `out/engineering_entry_fresh_smoke_20261110/`：不复用原生基线的单星七天实机入口检查。
- `out/model_alignment/`：重力常数、独立轨迹样本和全窗口对照等必要证明；历史 EOP 与旧球面结果仅保留摘要，重复试算和缓存留在本机。

当前结果为有效区覆盖 58775/59040 点、仍有 265 个未覆盖点，长三角整体访问 169 次。模型核对通过不代表已经全覆盖；优化目标、评分参考值和构型重新优化属于后续工作。

## 在其他电脑复现

安装 Python 3.11+，在 `task2/` 下安装依赖并运行本地回归：

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

实际 STK 计算还需要 Windows、STK 11.6 Engine 与可用的 Coverage 许可。复核已交付的 28 星输入时：

```powershell
python engineering_run.py --reuse-stk out/stk_validation_eop2026 --out out/engineering_recheck
```

该命令会核对原生基线的输入和证据，重新计算 Python、短时访问精化和太阳同步检查。输出目录必须新建或为空。要从头计算原生全量场景，省略 `--reuse-stk`；修改构型后应走从头计算流程。

运行清单中的绝对路径记录原始执行环境；上述命令使用当前检出目录，不要求复制原机器目录。仓库设置了 `task2/** -text`，保留原始文件字节，避免 Git 的自动换行转换破坏证据哈希。不要批量更改已冻结数据的换行或编码。

## 打开 28 星场景

下载 [STK 场景包](../out/stk_validation_eop2026/scene/Task2_Constellation_STK116.zip)，解压全部内容到英文路径，例如 `C:\STK_Task2`，在 STK 11.6 打开 `Task2_Constellation.sc`。该包已验证可重新打开，包含 28 星、28 个传感器及正式区域对象。

场景包保存的是全量原生基线；最新短时窗口精化在最终验收目录中独立保存。引用结果时使用最新报告及 `verification_summary.json`，不要把历史缓存或旧球面近似指标当作当前结果。
