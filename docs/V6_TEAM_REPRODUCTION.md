# V6稳定版：四人团队复现与继续开发说明

本轮只做封存、工程交接与短冒烟验证，不开发V7，不重做10000颗轨道传播。V6算法冻结提交a40b3eb590bd33861b25063fb4e4bc6eca4e7d79；稳定分支在它之后合入最新main并补充交付入口，算法、Evaluator、规则和物理判定未修改。具体稳定提交、bundle哈希见交付包engineering/release_git.json。

## 1. 两套成果与目录

|用途|来源|任务|覆盖|高/中/低覆盖|当前模型分数|
|---|---|---:|---:|---|---:|
|得分优先|V6，36秒，seed11|7877|3987|2024/1705/258|31015.978086|
|覆盖优先|同轮V5延续搜索，36秒，seed11|7919|4100|2024/1976/100|30961.386198|

覆盖优先方案是本轮保留的V5非支配方案，不是虚构的另一轮V6算法成绩。两套均经过本轮新隔离环境的完整1秒物理复核。最终计划在accepted/v6/plans；不要覆盖它们。

```text
项目根目录/
  src/satplan/             V4、V5、V6、统一rules与本地Evaluator
  scripts/v6_team.py       verify / select / audit / optimize统一入口
  scripts/prepare_v6_authorized_data.py  校验授权数据，不下载、不传播
  scripts/bootstrap_v6_environment.py   带SHA的离线依赖导入
  scripts/run_v6_trial.py  冻结试验与验收流程
  scripts/analyze_v6_remaining.py       当前V6剩余机会分析
  accepted/v6/            3.6MB左右的计划、V5起点、证书、输入身份与公平表
  docs/                   交接、技术报告、规则和PR草稿
  requirements-v6.lock    验收环境的精确版本
  data/raw/               本地授权TLE、站址、优先级，不入Git
  data/out/               本地缓存、试验与检查点，不入Git
  de421.bsp               本地星历，不入Git
完整交付包（项目外）/
  engineering/            完整Git bundle、代码ZIP、提交身份
  dependencies/           Windows CPython3.12离线依赖与校验清单
  plans/ validation/      两方案及本轮独立验收记录
  reports/                技术、公平、潜力、复现报告及图表
  history/                原V4/V5/V6完整实验ZIP与a40b3eb原bundle
```

历史V4 ZIP包含既有windows.csv，但无原始.tle/.bsp。历史包只保留在本地完整交付中，不加入GitHub分支。原始TLE及星历本轮不打入新工程ZIP、不提交Git。必要输入须由有授权的队员通过组内渠道提供。

## 2. 获取代码

以下PowerShell直接调用python.exe，不用Activate.ps1，不改执行策略。路径变量按本人机器修改；在命令返回非零时先处理错误，不继续当作通过。

本轮已实际验证：从完整bundle独立克隆、历史恢复、隔离离线环境、数据校验、本地Evaluator、51项测试、两方案全物理复核、1秒优化冒烟、同路径已验收检查点复用。远程推送/PR、设备登录及联网pip安装尚未验证。

```powershell
$handoff = 'D:\Downloads\v6_stable'     # 解压完整交付包后的目录
$repo = 'D:\SatelliteTeam\v6_stable'   # 必须是尚不存在的新目录
git -c core.autocrlf=false clone --branch codex/v6-deep-optimization "$handoff\engineering\v6_stable_complete.bundle" $repo
if ($LASTEXITCODE -ne 0) { throw 'bundle clone failed' }
Set-Location $repo
git config core.autocrlf false
git remote rename origin archive
git remote add team https://github.com/Eli-Mao/baidumoufa.git
git config http.sslBackend openssl
git fsck --full
$release = Join-Path $repo 'accepted\v6'
```

待维护者获得确认、成功推送后，队员才可使用以下远程命令。本轮该V6远程分支尚不存在，不要声称已可在线克隆：

```powershell
git -c http.sslBackend=openssl -c core.autocrlf=false clone --branch codex/v6-deep-optimization https://github.com/Eli-Mao/baidumoufa.git D:\SatelliteTeam\v6_from_github
```

## 3. Python与依赖

已验证Windows x64、CPython3.12.10。核心版本：numpy2.5.4、pandas3.0.6、Skyfield1.55、sgp4 2.27、psutil7.2.2，其余精确依赖见requirements-v6.lock。缓存执行路径不需要SciPy/matplotlib；历史requirements.txt为整个项目的宽版本集合，不用于本轮精确环境。

本机实际用D:/Software/Python312/python.exe创建干净venv，未使用system-site-packages。10个分发包均从新venv加载，pip check通过。离线方法是复制验收环境的完整分发文件及dist-info/许可证，不是重新构建wheel，也不含原venv路径注入；仅支持Windows x64 CPython3.12。

```powershell
$basePython = 'C:\Python312\python.exe' # 换成本机已有的Python3.12 x64路径
& $basePython -c "import sys,platform; assert sys.version_info[:2]==(3,12) and platform.architecture()[0]=='64bit'"
& $basePython -m venv .venv
$py = Join-Path $repo '.venv\Scripts\python.exe'
& $py scripts/bootstrap_v6_environment.py --archive "$handoff\dependencies\windows_cp312_packages.zip" --manifest "$handoff\dependencies\offline_manifest.json" --receipt data/out/environment_setup.json
if ($LASTEXITCODE -ne 0) { throw 'offline environment setup failed' }
& $py -m pip check
$env:PYTHONPATH = Join-Path $repo 'src'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
```

联网安装替代命令如下，但本轮PyPI连接超时，**没有完成联网安装验证**；不能声称已验证公共索引可获得所有锁定版本。离线导入是实际通过的路径。

```powershell
& $py -m pip install --disable-pip-version-check --timeout 15 --retries 1 --index-url https://pypi.org/simple -r requirements-v6.lock
```

## 4. 准备授权数据及缓存

所需raw文件：orbits.tle、stations.txt、priority_high.txt、priority_medium.txt、priority_low.txt；还需de421.bsp。缓存目录须含531432行windows.csv、10000行selected_targets.csv、原V4 experiment_report.json、final_plan.csv；后两项分别用于冻结runner输入检查与本地测试fixture。执行51项完整测试还需原5000目标缓存windows.csv；没有该fixture会跳过对应测试，不能报告51项全通过。以上都复用现有文件，不运行pipeline.py/propagate.py。

```powershell
$raw = 'D:\CompetitionData\raw'
$eph = 'D:\CompetitionData\de421.bsp'
$cache = 'D:\CompetitionData\real_aug2026_10000'
$testCache = 'D:\CompetitionData\real_aug2026_5000'
& $py scripts/prepare_v6_authorized_data.py --release $release --raw $raw --ephemeris $eph --cache $cache --test-cache-5000 $testCache --receipt data/out/data_setup.json
if ($LASTEXITCODE -ne 0) { throw 'wrong or missing authorized input; existing different files were preserved' }
```

脚本对原始数据、星历、窗口与目标列表验证SHA，再复制缺少的本地文件；若已有不同文件直接报错，不覆盖队友修改。窗口留在$cache，只有测试所需fixture复制到被gitignore的data/out。完整输入SHA与冻结规则位于accepted/v6/provenance。

## 5. Evaluator与独立算分

```powershell
& $py scripts/v6_team.py verify --release $release --cache $cache --mode score --out data/out/check_score
& $py scripts/v6_team.py verify --release $release --cache $cache --mode coverage --out data/out/check_coverage
& $py -m satplan.optimize --plan "$release\plans\score_priority.csv" --windows "$cache\windows.csv" --sat-meta "$cache\selected_targets.csv" --coverage-weight 0 --verbose
```

预期裸分数分别31015.978086、30961.386198。统一Evaluator在本地复用satplan.rules；文件的历史文档提及FAMOU，但此命令不连接百度伐谋或其他AI。正式当前模型必须coverage-weight=0；其他值是搜索辅助目标，不能作为本轮最终成绩。Evaluator检查调度硬约束和模型得分，不代替物理复核。v6_team verify还验证目标元数据、最终CSV独立算术和冻结输入身份。

## 6. 全部测试与独立物理复核

```powershell
& $py -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw 'tests failed' }
& $py scripts/v6_team.py audit --release $release --mode score --out data/out/audit_score
& $py scripts/v6_team.py audit --release $release --mode coverage --out data/out/audit_coverage
```

实际验收51项、0跳过；7877/7877与7919/7919全部通过。审计从原TLE逐任务计算精确起止与区间内1秒网格，检查仰角、太阳高度、卫星日照及SGP4错误；只计算任务区间，不是重做10000颗全规划期传播。1秒离散复核不能称为连续时间严格认证。调度冷却与站点切换由verify/冻结runner检查，物理audit单独不承担全计划冲突判断。

## 7. 精确重现成果与切换方案

```powershell
& $py scripts/v6_team.py select --release $release --mode score --out data/out/score_priority_submission.csv
& $py scripts/v6_team.py select --release $release --mode coverage --out data/out/coverage_priority_submission.csv
Get-FileHash data/out/score_priority_submission.csv -Algorithm SHA256
Get-FileHash data/out/coverage_priority_submission.csv -Algorithm SHA256
```

得分计划SHA：144b4738b04f837a0fa34470fc0fd29e65627dff92e34f46bf2513338f37adbf。
覆盖计划SHA：359fa8b480d4d04146b6149bf47e2218f8dc208c0d9633cafb3a3e02d13b12a4。
select拒绝覆盖已存在输出。这里重现的是相同字节的已验收成果，可独立重新算分和复核。

## 8. 启动算法与恢复

```powershell
# 本轮实际验证的是1秒工具链冒烟；它仍会做约百秒的最终全计划物理检查。
& $py scripts/v6_team.py optimize --release $release --cache $cache --seed 20261023 --budget 1 --out data/out/v6_smoke
# 相同根目录、源码、输入和参数下重复这一行：已验收trial校验SHA后跳过。
& $py scripts/v6_team.py optimize --release $release --cache $cache --seed 20261023 --budget 1 --out data/out/v6_smoke

# 下一阶段由团队决定执行；本轮未在新环境重跑36秒搜索。
& $py scripts/v6_team.py optimize --release $release --cache $cache --seed 11 --budget 36 --out data/out/v6_seed11_b36
```

36秒seed11是原正式最佳试验配置；所有可比试验统一从封存V5开始。墙钟截止在不同机器上会改变迭代数，因此重新搜索不保证字节级复现最佳CSV；不能把这件事与上面精确成果恢复混为一谈。score/coverage切换用于选择两份已验收计划；当前V6搜索仍按冻结模型收益接受，不是另外实现的覆盖优化器。

恢复粒度为**完整trial**，没有持久化每个LNS迭代状态。中断在搜索或审计中：保留不完整目录，换新--out重跑该trial；无需重算窗口。已完成trial原路径可安全跳过；更换源码、输入、项目根目录或输出身份时不要复用旧检查点。批量比较的comparison.lock含PID，只有确认原进程已结束才能删除陈旧锁。历史18次试验在history/v6_original_results.zip中封存，不能把跨路径复制来的旧检查点伪装成当前代码的续跑结果。

## 9. 工作分工与Git协作

轨道/数据同学维护授权输入与缓存身份；算法同学维护独立模块与预算实验；Evaluator同学维护冻结计分与验收；集成同学审核证书、结果与PR。修改规则应新建规则版本并重评，不能覆盖本轮基准。各自用独立分支，不在main开发。依赖包、缓存、venv、密钥和历史ZIP都不提交；accepted/v6只包含最终派生计划、证书及小型身份/实验表。

推送与PR步骤见V6_GITHUB_HANDOFF.md。本轮尚未推送，真实账户写权限未验证。禁止force、修改原ACL或覆盖D:/SatelliteProject_GitHub的未提交文件。
