# V5团队交接（2026-10-23）

V4验收提交001b05b8481f9281ad36a76df6a5a7fa74a67147保持不变。当前独立克隆在 `D:\Codex\2026-10-23\files-pasted-by-the-user-10000\work\v5_project`，分支codex/v5-score-engine；原项目Git ACL没有修改。

V5正式最佳：30682.990429547分，较V4增加1239.342903500分（4.209%），7658项合法任务、覆盖3822/10000，高优先级2024/2024。20秒和60秒各3种子全部提高有效得分，全部通过硬约束及独立全任务1秒采样，含精确起止点。45项测试通过。

冻结V4模块未修改。新增satplan/v5.py、v5_physics.py及试验/分析脚本。V5使用站点与同星有序时间线、增量得分和冲突检查，支持短时长插入、换站位移、冲突替换、时长调整和2至3任务的局部破坏修复；不是大规模全局最优求解器。每个改变后的对外候选均执行完整独立验收；临时邻域动作不作为有效成绩发布。

默认真实缓存路径 `D:\SatelliteProject_GitHub\data\out\real_aug2026_10000`，不传播卫星。新机器须获取受限原始输入、DE421并配置Python依赖，原始数据、星历和缓存不入Git。所有脚本目前明确使用该本地缓存路径；不同目录须先统一修改BASE并使用新实验目录，不能混用既有验收记录。对照以同一V4合法计划暖启动；相同优化器墙钟预算包括V5动作物理预检，输入解析和最终验收另外计时。未改变的V4几何计划可复用精确相同的封存证书。

复核/恢复既有比较（完整结果会跳过）：
```powershell
Set-Location 'D:\Codex\2026-10-23\files-pasted-by-the-user-10000\work\v5_project'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OPENBLAS_NUM_THREADS='1'
& 'D:\SatelliteProject\Task4_Phase0_DataCheck\.venv\Scripts\python.exe' -u scripts/run_v5_comparison.py
```

推荐通过 `scripts/resume_v5_comparison.ps1` 恢复，它会先核对已验收试验的源码/输入SHA-256并拒绝重复进程；不同版本应新开实验目录。

继续较大预算的独立试验（V4对照请用相同seed和budget另设--out目录）：
```powershell
& 'D:\SatelliteProject\Task4_Phase0_DataCheck\.venv\Scripts\python.exe' -u scripts/run_v5_trial.py --algorithm v5 --seed 44 --budget 180 --out data/out/v5_extra_b180_s44
```

恢复只适用于代码和输入均未改变。改算法必须建立新的实验目录，不得让run_v5_comparison.py跳过旧结果后混合新版本。每个trial.json记录完整源码和输入SHA-256。正式比较在执行时冻结核心文件，报告核对所有试验核心hash一致。首次开发试跑因CSV时长浮点往返被完整硬检查拦截，失败数据保留不计入统计；新增回归保证保留已验收时长字段并遵循既有1e-6秒自洽容差。

team远端已设为https://github.com/Eli-Mao/baidumoufa.git。没有验证GitHub写权限，没有推送。交付增量bundle要求V4父提交，先恢复V4 bundle再恢复V5 bundle；不覆盖main，不强推。

1秒离散采样不是连续时间数学认证，分数不是赛事官方成绩。暗夜-6度、30秒切换、48小时冷却及线性时长评分等待官方确认参数保持冻结。
