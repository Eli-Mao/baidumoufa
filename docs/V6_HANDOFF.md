# V6团队交接

最佳增强版合法得分31015.978086，任务7877，覆盖3987；基准V5始终封存。独立分支codex/v6-deep-optimization，尚未远程推送。原main、原仓库权限和队友修改没有改动。

## 环境与数据

Python3.12，numpy/pandas/skyfield/sgp4/psutil版本见runtime_environment.json；不新增第三方依赖。原始TLE、站点、优先级、de421.bsp需在本地就位，均不提交。现有窗口、selected_targets.csv和V4 experiment_report.json放到缓存目录。用V6_CACHE_DIR指定该目录；V6_BASELINE_DIR指向v5_sealed，含验收V5计划、物理报告与seal.json。冻结配置、输入和算法SHA见frozen_identity.json。

## 直接命令（在项目根目录，PowerShell）

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:PYTHONPATH=(Join-Path $PWD 'src')
$env:V6_CACHE_DIR='D:/SatelliteProject_GitHub/data/out/real_aug2026_10000'
$env:V6_BASELINE_DIR='D:/Codex/2026-10-23/files-pasted-by-the-user-10000/outputs/v5_sealed'
$py='D:/SatelliteProject/Task4_Phase0_DataCheck/.venv/Scripts/python.exe'
& $py -m unittest discover -s tests
& $py scripts/analyze_v5_opportunities.py
& $py scripts/summarize_v5_resources.py
& $py scripts/refine_v5_opportunities.py
& $py scripts/verify_v6_csv.py --plan 'D:/Codex/2026-10-23/files-pasted-by-the-user-10000/outputs/v6_results/best_v6_plan.csv' --targets "$env:V6_CACHE_DIR/selected_targets.csv" --windows "$env:V6_CACHE_DIR/windows.csv"
& $py scripts/run_v6_trial.py --algorithm v6 --seed 44 --budget 36 --out data/out/v6_extra_s44
if (-not (Test-Path data/out/v6_comparison/pilot_b12_v6/trial.json)) { & $py scripts/run_v6_trial.py --algorithm v6 --seed 20261023 --budget 12 --out data/out/v6_comparison/pilot_b12_v6 }
& $py scripts/run_v6_comparison.py --budgets 12 36 --seeds 11 22 33
```

完整比较命令需要data/out/v6_comparison下的已验收pilot；实验ZIP保留该pilot。每个正式trial以原子JSON检查点和CSV保存。重跑比较会校验算法/输入身份和计划SHA再跳过已完成trial。未完成试验不会被静默覆盖；保留其目录，使用新输出目录重新运行该trial。comparison.lock记录PID，进程异常退出后先确认PID已不存在，再只删除该锁文件；不要并行运行相同输出目录。源代码或输入改变时使用新实验目录，不复用旧检查点。

新预算和种子可直接调用trial；批量比较默认要求同目录内已有通过验收且优于V5的12秒pilot。继续优化时V6_BASELINE_DIR必须仍指向封存V5以保持公平。本轮无必须达到的预设分数。

图表使用Windows自带.NET绘图库，无需安装matplotlib。当前18次试验的表格由scripts/finalize_v6_results.py生成；RenderV6Charts.cs读取这些CSV。可在Windows执行：

```powershell
$chartDll=(Get-ChildItem "$env:WINDIR/Microsoft.NET/assembly/GAC_MSIL/System.Windows.Forms.DataVisualization" -Recurse -Filter System.Windows.Forms.DataVisualization.dll | Select-Object -First 1).FullName
& "$env:WINDIR/Microsoft.NET/Framework64/v4.0.30319/csc.exe" /nologo /target:exe /out:data/out/RenderV6Charts.exe /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Core.dll "/reference:$chartDll" scripts/RenderV6Charts.cs
& ./data/out/RenderV6Charts.exe 'D:/Codex/2026-10-23/files-pasted-by-the-user-10000/outputs/v6_results'
```

## 合并与恢复

只合并独立新增v6.py、审计/实验/分析/绘图脚本、测试及文档；V4/V5与冻结rules/config不改变。最终交付bundle及源代码快照用于本地恢复，具体提交与验证记录见bundle_restore.json。远程team为https://github.com/Eli-Mao/baidumoufa.git；推送前须由用户确认，禁止force或覆盖main。确认后仅执行git push team codex/v6-deep-optimization。未验证远程写权限，不声称已发布。

不提交data/raw、de421、窗口缓存、实验大文件、密钥或本地环境。交付ZIP只含代码、脱敏路径身份记录及实验产物；实际路径只是复现线索，没有密钥。完整本地输入不随Git提交。原V5增量bundle需要V4前置提交；增强版最终提供完整bundle，可独立克隆。
