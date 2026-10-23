# 10000目标真实数据V4交接

更新：2026-10-23（Asia/Shanghai）。以当前本地文件为准；未使用旧聊天记忆。

## 工程和数据

项目 `D:\SatelliteProject_GitHub`；分支 `codex/v4-scale-engine`；HEAD `0413e83`。工作树和暂存区均已有他人/先前修改，保留全部修改；修改前备份在 `data/out/handoff_backup_20261023/`。仓库Git身份仍未全局配置；本次用户已明确授权作者 Iceswing <755875603@qq.com>，验收后用该身份创建独立本地提交，不推送。

真实输入：`data/raw/orbits.tle`（10000唯一目标、20000条TLE行），`stations.txt`（10站），`priority_high/medium/low.txt`（2024/3990/3986）。星历 `de421.bsp`。原始数据不上传。当前仓库没有 `.venv`；已验证历史项目环境 Python 3.12.10、NumPy 2.5.4、pandas 3.0.6、Skyfield 1.55、SGP4 2.27、psutil 7.2.2，直接复用，不安装依赖。

## 模块

`src/satplan/io_schema.py` 数据契约和Alpha-5编号；`config.py` 冻结参数；`propagate.py` Skyfield/SGP4分块传播和带签名的按目标检查点；`windows.py` 窗口组装；`scheduler.py` 有序站点/卫星时间线贪心和V4局部搜索；`rules.py` 约束及计分；`scripts/repair_plan_physics.py` 物理修复；`scripts/audit_plan_physics.py` 独立逐任务重算；`scripts/run_real_10000.py` 可恢复验收流水线。

## 冻结口径

UTC规划期2026-08-01 00:00至2026-08-07 00:00，共518400秒。10至85度仰角；太阳高度严格小于-6度；卫星受照；120至240秒观测；同站间隔30秒；同星跨站距上次结束48小时冷却。优先级权重5/3/2，时长系数在120秒0.6和240秒1.0之间线性插值。局部搜索使用既有coverage_weight=0.25、250次、seed=20261021。算法不承诺全局最优。上述未获官方确认的规则保持当前模型，不称官方成绩。

## 已有证据

3000目标：160435窗口、最终5418任务、覆盖2304、模型18630.095（历史文件证据）。5000目标：265503窗口；修复计划6324任务、覆盖2891、模型23629.67496089333；最终精确终点审计未完成，不能称已验收。保留5000缓存和所有历史文件。10000目标开始时无目录或缓存。

## 本次修复和运行

已备份原修改，修正独立审计器和修复器的非整数秒精确终点漏检，显式检查SGP4返回消息，传播照明缓存每目标释放，低于200MiB可用RAM或2GiB磁盘在目标边界停止并保留检查点。36项原测试通过；附加真实窗口终点回归测试见tests。初始可用RAM约1.3GiB，D盘空闲约85GiB。每次运行监控峰值RSS，所有任务逐目标处理，避免重复大型进程。

## 启动及恢复（PowerShell）

```powershell
Set-Location D:\SatelliteProject_GitHub
$env:PYTHONPATH='D:\SatelliteProject_GitHub\src'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OPENBLAS_NUM_THREADS='1'
& 'D:\SatelliteProject\Task4_Phase0_DataCheck\.venv\Scripts\python.exe' -u scripts/run_real_10000.py
```

同一命令恢复。输入/代码改变会拒绝复用，须单独新目录。`run.lock.json`阻止重复进程；`experiment_report.json`记录阶段、失败和每次耗时。5000缓存仅在原输入、时间、物理参数、星历及目标签名一致时复制到10000检查点，不修改原缓存；按目标CSV原子写入，完整目标完成才登记，最后CSV合并。`propagation_checkpoint.csv.meta.json`及同名`.chunks`目录不可分离。异常中断后最多重新计算最后未提交目标。总耗时包含本次实际计算；复用窗口的历史耗时单列，不能当成全部重新计算耗时。

## 验收和产物

输出 `data/out/real_aug2026_10000/`。SGP4对10000目标完整30秒网格独立原生检查，保存逐目标样本数和异常时间；发现26702在规划后段有5303个code 6衰减错误采样点；该目标不在5000缓存，现传播与边界细化显式屏蔽SGP4错误，只保留有效区间。错误不冒充正常窗口。首次预检安全停止证据保存于preflight_report_failed.json，修复后复用已完成预检。窗口、初始V4、修复报告和最终计划分别保存。初始及最终物理审计均重新计算真实轨道，精确起止点及从起点每1秒检查仰角、暗夜、照明、SGP4；修复后仍不合法的任务记录并剔除，再全量重审。硬约束独立报告；最终以10000完整元数据重计分，保存优先级覆盖、每目标次数及未覆盖清单。输入SHA-256、完整源码SHA-256、脏工作树标识、源码快照、Git HEAD、资源和各阶段耗时均保存。只有全部验收通过才标completed。`artifact_manifest.json`保存主要产物SHA-256。

## 已知限制和待办

30秒粗网格可能跨过短暂无效区间；0.1秒边界细化不等于完整区间有效，因此最终全任务1秒审计必须完成。1秒离散检查不是连续时间数学认证。8月2至4日TLE相对规划期向前约1至3天、向后约3至5天传播，轨道精度需官方确认。切换、冷却、暗夜、时长插值和重复计分等详见 `docs/open_questions.md`。现有V4并未实现完整大邻域/局部多任务交换；先完成冻结V4基准，不能声称具备未实现算子。后续新算法应独立版本公平对比。

## 新机器 / 全新克隆的准备

本次恢复命令依赖现有工程中的原始数据、DE421、历史环境和 `data/out/handoff_backup_20261023/git_head.txt`，这些不全部在Git里。当前机上已具备。新机器应先按README配置依赖并授权获取原始输入，在项目根目录执行以下元数据初始化（仅当该文件不存在时），再用独立 `--out` 目录开始新实验：

```powershell
New-Item -ItemType Directory -Path data/out/handoff_backup_20261023 -Force | Out-Null
if (-not (Test-Path data/out/handoff_backup_20261023/git_head.txt)) {
    git rev-parse HEAD | Set-Content data/out/handoff_backup_20261023/git_head.txt -Encoding utf8
}
```

此文件保存本次运行的代码父版本；完整实际源码由实验报告的SHA-256与code_snapshot确定。切换到其他代码版本开展新实验时应单独管理新的版本证据，不可将旧报告当作新计算证明。


## 修复阶段性能修正

全量规则检查实测每候选1.20秒，历史5000目标修复前后文件相差约49分钟。当前万级运行在修复阶段受控停止一次，保留全部轨道、V4、初始审计；仅优化修复器：在原完整计划硬可行的前提下，一次只改变一个任务，其受影响约束限于自身窗口/时长/规划期及站点、同星的前后相邻任务。调用相同rules内核检查这些相邻任务（实测平均0.014秒），最后仍执行全量规则检查和独立物理审计。不改变规则或V4搜索预算。新增真实计划修改与整表检查的等价性测试，以及冷却/切换临界值回归；39项测试全部通过。中断前源码、日志和阶段证据保留于code_snapshot_before_repair_optimization、repair_optimization_checkpoint.json等；experiment_report的identity_history记录版本演化，不将已完成轨道重算。

## 10000-target August acceptance (2026-10-23)

- Completed real-data V4 run: 531432 windows; 6849 final tasks; 3117/10000 targets; model score 29443.647526047.
- Zero hard-constraint violations; all tasks passed independent one-second interval sampling including exact fractional endpoints and SGP4 status. Discrete sampling is not continuous-time certification.
- Full evidence: `data/out/real_aug2026_10000/experiment_report.json`. Official-rule and orbit-accuracy questions remain open.

- Acceptance reconciliation passed: task counts, coverage, scoring weights, fractional durations, 30-second station gaps, global 48-hour cooldown, all input/source/artifact hashes. 39/39 tests passed.
- Total actual processing time across all attempts (including controlled repair restart): 3368.657 s; peak process RSS: 805.203 MiB. Preserved cache historical propagation time is separate.
- Local acceptance author: Iceswing <755875603@qq.com>; acceptance branch `codex/v4-10000-accepted`. Active branch and original index are retained; no remote push.

## 本地Git交付位置说明

原仓库 `.git/objects` 存在Windows显式拒绝ACL，授予目录写权限后仍不能写入。没有修改ACL，也没有改动原暂存区；计算前后暂存差异SHA-256一致。验收提交改在当前任务可写目录中的独立bare仓库创建，使用用户指定 Iceswing <755875603@qq.com>；分支codex/v4-10000-accepted在该独立仓库中。交付Git bundle仅包含本次验收提交相对0413e83父版本的增量，不推送远端。原项目代码、结果、交接文档和检查点仍保留于原位置。
