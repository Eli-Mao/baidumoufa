# V7本地研发版：Windows复现及继续开发

V7以V6稳定提交401d59d为基础，在codex/v7-hybrid-optimization独立分支开发。原仓库D:/SatelliteProject_GitHub有未提交修改和Git对象目录ACL限制，未改权限、未写入原仓库。V6分支、main和V4/V5/V6封存结果保留。未经用户确认，不推送V7或合并main。

## 获取本地开发版

目前以交付目录的v7_complete.bundle获取，不能假定GitHub上已有V7分支。目标目录应选择不存在的路径。

```powershell
$delivery='D:\Downloads\v7_results'
git -c core.autocrlf=false clone --branch codex/v7-hybrid-optimization "$delivery\v7_complete.bundle" D:\SatelliteTeam\v7
Set-Location D:\SatelliteTeam\v7
git config core.autocrlf false
git status --short
git branch --show-current
```

## Python及授权数据

沿用冻结的requirements-v6.lock，无新增第三方依赖。验收解释器Windows x64 CPython3.12.10，离线依赖文件及manifest由V6稳定交付包提供，不上传原始数据或依赖归档。联网pip路径此前未验证成功，不作为已验证部署路径。

```powershell
$basePython='C:\Python312\python.exe' # 换成本机已安装的CPython3.12
$v6Release='D:\Downloads\v6_stable'
& $basePython -m venv .venv
$py=Join-Path $PWD '.venv\Scripts\python.exe'
& $py scripts/bootstrap_v6_environment.py --archive "$v6Release\dependencies\windows_cp312_packages.zip" --manifest "$v6Release\dependencies\offline_manifest.json" --receipt data/out/environment.json
if ($LASTEXITCODE -ne 0) { throw 'offline environment verification failed' }
& $py -m pip check
$env:PYTHONPATH=Join-Path $PWD 'src'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$cache='D:\CompetitionData\real_aug2026_10000'
$cache5k='D:\CompetitionData\real_aug2026_5000'
& $py scripts/prepare_v6_authorized_data.py --release accepted/v6 --raw D:\CompetitionData\raw --ephemeris D:\CompetitionData\de421.bsp --cache $cache --test-cache-5000 $cache5k --receipt data/out/inputs.json
if ($LASTEXITCODE -ne 0) { throw 'authorized input SHA mismatch' }
```

数据准备脚本检查原始输入、目标清单、531432窗口的冻结SHA，不下载、不传播轨道。首次复制测试fixture到本地忽略目录需要磁盘空间；不修改源缓存。5000目标缓存用于既有测试。

## 测试与重算已验收CSV

```powershell
& $py -m unittest discover -s tests
& $py scripts/verify_v6_csv.py --plan accepted/v7/plans/score_priority.csv --targets "$cache\selected_targets.csv" --windows "$cache\windows.csv"
& $py -m satplan.optimize --plan accepted/v7/plans/score_priority.csv --windows "$cache\windows.csv" --sat-meta "$cache\selected_targets.csv" --coverage-weight 0
& $py scripts/audit_v6_physics.py accepted/v7/plans/score_priority.csv --out data/out/v7_independent_physics.json --step 1
```

预期60项测试通过。精确得分和覆盖以accepted/v7/validation/score.json及summary.json为准。V7调用的是本地冻结Evaluator，不调用外部AI平台。完整1秒离散检查含非整数精确起止时间，不是连续时间严格认证。

## 瓶颈审计、短试验和公平比较

```powershell
& $py scripts/audit_v7_baseline.py --plan accepted/v6/plans/score_priority.csv --cache $cache --out data/out/v7_baseline_audit
& $py scripts/run_v7_trial.py --algorithm v7 --seed 11 --budget 12 --phase all --cache $cache --out data/out/v7_pilot
& $py scripts/run_v7_comparison.py --cache $cache --budget 36 --seeds 11 22 33 --validation-workers 2 --out data/out/v7_formal
```

每个正式试验从同一V6计划出发。搜索预算包含索引构建及搜索中的区间物理调用，不含读入、最后独立验算。V6/V7搜索顺序交替，单进程顺序执行；全部搜索完成后，最多两个进程并行复核。均值/标准差仅使用同预算同种子的已验收结果，标准差为样本标准差ddof=1。12秒试运行和120秒扩展实验单独保存。

candidate_plan.csv始终是候选。只有trial.json的status=accepted、硬约束为0、完整区间及精确端点物理复核通过后，才生成final_plan.csv。失败结果保留，不覆盖V6或最佳验收计划。

## 中断恢复与继续优化

搜索完成且status=provisional时可继续独立验收：

```powershell
& $py scripts/run_v7_trial.py --algorithm v7 --seed 11 --budget 12 --phase validate --cache $cache --out data/out/v7_pilot
```

身份包括代码、输入、种子、预算及原绝对路径。仅在同一位置、同一版本恢复；已验收trial重复运行会验证身份及CSV SHA后复用。跨机器直接验算保存的CSV，不声称能继续原绝对路径trial。搜索中断/失败trial保留并换新--out；当前尚无搜索迭代级检查点。

同一墙钟预算在不同机器或系统负载下可能产生不同任务集；精确恢复已验收成绩应使用交付CSV及SHA。不要将重复运行的浮点差异误当作规则变更。

```powershell
git switch -c team/member-v7-experiment
# 可控扩展实验；不混入36秒公平统计。
& $py scripts/run_v7_trial.py --algorithm v7 --seed 11 --budget 120 --phase all --cache $cache --out data/out/v7_extended
```

只在新模块改进搜索，禁止修改config/rules/Evaluator、放宽冷却或物理阈值。保留accepted/v6与accepted/v7基准。任何更高候选必须重新完成全计划调度检查和独立物理复核后再晋级。

## 已验证与待验证范围

V7独立离线环境、pip check、60项测试、真实窗口审计与正式比较由本轮实际运行生成记录。完整结果见V7研发报告及accepted/v7。新机器安装Python、公共PyPI联网安装、未来GitHub V7推送均不属于本轮已执行事项。官方尚未确认的模型参数沿用docs/V6_FROZEN_RULES.md，未擅自改变。
