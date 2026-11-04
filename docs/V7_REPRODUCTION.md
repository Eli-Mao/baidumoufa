# V7_REPRODUCTION：A/B/C三层复现

V7最佳31952.281862分是冻结模型成绩，不是官方最终成绩。入口scripts/v7_delivery.py不修改评分或算法。算法冻结f39561d；文档和包装提交可能更新，算法及计划SHA不变。

## 获取代码和环境

远程发布成功后：

```powershell
git -c core.autocrlf=false clone --branch codex/v7-hybrid-optimization https://github.com/Eli-Mao/baidumoufa.git D:\SatelliteTeam\v7
Set-Location D:\SatelliteTeam\v7
git config core.autocrlf false
```

若尚未发布，改用交付的v7_stable_complete.bundle离线克隆，不假定GitHub分支已存在。依赖为Windows x64 CPython3.12（验收3.12.10），requirements-v6.lock保持冻结，无新增第三方包。

```powershell
$basePython='C:\Python312\python.exe' # 换成本机已安装的3.12
$offline='D:\TeamTransfer\v6_stable\dependencies'
& $basePython -m venv .venv
$py=Join-Path $PWD '.venv\Scripts\python.exe'
& $py scripts/bootstrap_v6_environment.py --archive "$offline\windows_cp312_packages.zip" --manifest "$offline\offline_manifest.json" --receipt data/out/environment.json
if ($LASTEXITCODE -ne 0) { throw 'offline dependency SHA/import validation failed' }
& $py -m pip check
$env:PYTHONPATH=Join-Path $PWD 'src'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:PYTHONDONTWRITEBYTECODE='1'
```

离线依赖由组内授权渠道提供，已实际在独立环境验证。它是逐文件SHA核对的发行包复制，并非pip wheel重新构建。公共索引`pip install -r requirements-v6.lock`此前联网安装未验证成功，不作为已验证路径。

## A：只验算交付计划，不进行全量优化或轨道传播

仓库包含最佳计划、10000目标元数据及8713行原始缓存支撑窗口。支撑窗口均逐行来自531432窗口缓存，仅足以检查这份交付计划，不能代替B的完整窗口。无需原始TLE、星历或完整缓存即可调用同一冻结Evaluator。

```powershell
& $py scripts/v7_delivery.py evaluate --out data/out/v7_level_A.json
& $py -m satplan.optimize --plan accepted/v7_round2/best_accepted_plan.csv --windows accepted/v7_delivery/plan_support_windows.csv --sat-meta accepted/v7_delivery/selected_targets.csv --coverage-weight 0
```

预期31952.28186187333、8713任务、4508覆盖、高/中/低2024/2020/464、0调度违规。A同时核对证书文件SHA，但不重新执行物理采样；不应称为完整算法/轨道复现。

## B：完整缓存和同预算重跑优化

另需：完整10000目标缓存（windows.csv、selected_targets.csv、experiment_report.json、final_plan.csv）、授权raw五文件、de421.bsp。搜索本身调用物理谓词，因此B同样需要TLE/站点/星历；只给窗口CSV不够。完整69项测试另需5000目标windows.csv fixture。

```powershell
$cache='D:\CompetitionData\real_aug2026_10000'
$cache5k='D:\CompetitionData\real_aug2026_5000'
& $py scripts/prepare_v6_authorized_data.py --release accepted/v6 --raw D:\CompetitionData\raw --ephemeris D:\CompetitionData\de421.bsp --cache $cache --test-cache-5000 $cache5k --receipt data/out/authorized_inputs.json
if ($LASTEXITCODE -ne 0) { throw 'input identity mismatch; preserve existing files' }
& $py -m unittest discover -s tests
& $py scripts/v7_delivery.py search --cache $cache --budget 600 --seed 44 --out data/out/v7_seed44
```

该搜索从固定第一轮V7计划31426.365分开始，与历史600秒试验起点相同；不会把最终最佳作为更有利的起点。全量同预算对照：

```powershell
& $py scripts/run_v7_round2_comparison.py --cache $cache --out data/out/v7_fair --budgets 300 600 --seeds 11 22 33 44 55 --cpus 2 6 10
```

CPU编号需在本机可用集合内，选择不同物理核；不足时改`--cpus 0`顺序运行。每种子V6/V7绑定同一CPU并轮换先后顺序，全部搜索后再验收。600秒阶段以300秒V7均分高且至少4/5胜出为进入门槛。程序预算为墙钟，另记录CPU秒、RSS和缺页；跨机器逐行相同计划不保证。

当前轮仅核对既有20份结果，没有重新执行B的大规模搜索。历史已验收trial可在相同路径/参数/代码/输入/CPU下复用；provisional候选可用相同参数`--phase validate`继续验收。搜索中断未实现迭代级检查点，应保留原目录，换新输出重跑，不能改旧身份来冒充恢复。详见V7_ROUND2_REPRODUCTION.md。

## C：真实输入重新生成全目录窗口及独立物理复核

另需授权orbits.tle、stations.txt、priority_high.txt、priority_medium.txt、priority_low.txt与de421.bsp。各文件SHA见accepted/v7_delivery/external_files_manifest.json，数据格式见docs/data_contract.md。当前交付不执行全目录传播。

未来仅在新的独立克隆、准备好上述raw/星历、明确决定重建时运行以下命令。它们生成data/interim中的全目录窗口，会有明显计算开销；本轮未重跑此路径，跨版本生成的窗口SHA不保证相同。

```powershell
& $py -m satplan.pipeline --stage meta
& $py -m satplan.pipeline --stage windows --force
```

pipeline是旧兼容编排，`--stage plan`并不是V7优化器；要运行V7请使用B入口。只重建窗口也不表示优化结果或物理精度得到认证。原始输入准备后，重新物理复核交付计划：

```powershell
& $py scripts/v7_delivery.py audit --out data/out/v7_independent_physics.json
```

完整1秒采样包含精确非整数起止时刻及仰角、暗夜、受照、SGP4状态检查；不是连续时间严格认证。赛事待确认项保持docs/V6_FROZEN_RULES.md，未改变任何阈值。
