# V7第二轮复现与中断恢复

本轮不推送GitHub、不合并main。V6、第一轮V7均为冻结基准；第二轮共同起点是42eabbf的8193任务计划，31426.364999713333分。

先按V7_TEAM_REPRODUCTION.md建立Windows x64 CPython3.12离线环境、准备有授权原始数据及冻结窗口缓存。无需重新传播轨道。变量示例：

```powershell
Set-Location D:\SatelliteTeam\v7_round2
$py=Join-Path $PWD '.venv\Scripts\python.exe'
$cache='D:\CompetitionData\real_aug2026_10000'
$env:PYTHONPATH=Join-Path $PWD 'src'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& $py -m unittest discover -s tests
```

300秒五种子对照及有条件600秒实验：

```powershell
& $py scripts/run_v7_round2_comparison.py --cache $cache --out data/out/round2 --seeds 11 22 33 44 55 --budgets 300 600 --cpus 2 6 10
```

CPU编号必须在本机可用集合内。选择不同物理核；资源不足时用`--cpus 0`顺序运行。每个种子的一对算法始终绑定同一CPU，轮换先后顺序；搜索阶段结束后才进入独立验收。预算包含构造索引和候选区间物理查询，另记实际CPU秒、内存及缺页。不要拿不同机器或CPU配置的绝对墙钟结果当作严格配对实验。

600秒进入门槛事前确定为：300秒V7已验收均分高于V6，且至少4/5种子配对增分。未过门槛则保留真实300秒结果，不自动延长预算。

`trial.json`状态为provisional时只表示搜索结束；只有accepted及完整证据才生成final_plan.csv。已完成试验在相同位置、代码、输入、参数和CPU下可复用。未完成搜索的目录必须保留，换新输出位置重跑；没有搜索迭代级检查点。不修改旧试验的代码身份来强行复用。

单独恢复候选验收（示例）：

```powershell
& $py scripts/run_v7_round2_trial.py --algorithm v7 --seed 11 --budget 300 --cpu 2 --cache $cache --out data/out/round2/b300_s11_v7 --phase validate
```

自适应增强版单独试验，不混入冻结V6/V7统计：

```powershell
& $py scripts/run_v7_round2_trial.py --algorithm v7a --seed 11 --budget 60 --cpu 2 --cache $cache --out data/out/adaptive_pilot --phase all
```

完成交付后，直接重算及复核已保存最佳计划：

```powershell
& $py scripts/verify_v6_csv.py --plan accepted/v7_round2/best_accepted_plan.csv --targets "$cache\selected_targets.csv" --windows "$cache\windows.csv"
& $py -m satplan.optimize --plan accepted/v7_round2/best_accepted_plan.csv --windows "$cache\windows.csv" --sat-meta "$cache\selected_targets.csv" --coverage-weight 0
& $py scripts/audit_v6_physics.py accepted/v7_round2/best_accepted_plan.csv --out data/out/round2_reaudit.json --step 1
```

以上入口已由当前工程实际使用；新机器安装Python和公共PyPI联网安装不属于已验证步骤。不同墙钟运行可产生不同计划，精确复现验收得分以保存CSV及SHA为准。1秒离散加精确端点不是连续时间严格认证；待官方确认的模型参数沿用V6冻结规则。
