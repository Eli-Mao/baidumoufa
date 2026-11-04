# V7_TEAM_HANDOFF：阶段冻结与团队接手

赛题四当前算法研发阶段结束，V7已冻结，等待团队独立复现、正式赛事规则核查和最终提交准备。

当前最佳模型分31952.281862、8713任务、4508覆盖，高/中/低2024/2020/464。算法冻结f39561d，交付工程提交可能仅因文档、支持数据和封装变更而更新。发布前状态为待发布，实际状态以本次publication_result.json及远程SHA/新PR查询为准。不得把旧V6文档的封存时发布状态当成当前状态。

## 背景、边界和目录

10000颗真实卫星，10站，2026-08-01至08-07 UTC共6天，531432窗口。原D:/SatelliteProject_GitHub有ACL与队友修改，本轮使用独立克隆，不改权限、不写原仓库或V6分支。原V4/V5/V6/V7成果保留，不开发V8、不追加搜索。

- src/satplan/v7.py：本轮最佳使用的冻结V7；v7_adaptive.py与v7_exact.py为单独验证的备选，不等于最佳算法。
- v5.py、v6.py、scheduler.py：基准接口和兼容实现；rules.py/config.py/optimize.py：冻结规则与Evaluator。
- propagate.py/windows.py：真实轨道与窗口模块；scripts/audit_v6_physics.py：独立区间物理审计。
- scripts/v7_delivery.py：交付入口；run_v7_round2_trial.py/comparison.py：同预算实验。
- accepted/v7_round2：最佳CSV、模型结果和实验汇总；accepted/v7_delivery：A层支撑数据、20个正式CSV/JSON、新审计及哈希。
- accepted/v6：两套V6合法计划；accepted/v7：第一轮V7；accepted/v7_delivery/historical_baselines：V4/V5 CSV。
- docs/V7_REPRODUCTION.md：Windows复制命令及A/B/C界限；V7_EXPERIMENT_REPORT.md：核算、性能、实验局限。
- tests：69项自动化测试；requirements-v6.lock：沿用依赖冻结，无新增第三方包。

工程中历史trial身份的绝对路径属于原始证据，不是当前运行必需路径；不要修改它们伪造新机器可续算。新入口及文档显式传入本机缓存位置。运行环境为独立Windows x64 CPython3.12.10；离线安装实际验证，公共PyPI路径未验证。

## 三位组员分工与验收清单

建议一位负责A层算分/测试，一位负责B层同预算重跑，一位负责C层原始数据身份与物理审计；共同核查正式规则。保存各人的环境、输入SHA、命令、结果、差异，不覆写accepted历史文件。B/C如缺授权输入，明确标记缺失，不能仅凭A宣布完整复现。当前阶段不要求再次长搜；须团队自行安排计算时间。

GitHub只发布独立codex/v7-hybrid-optimization，目标main的新PR供审核，不强推、不合并、不修改V6 PR #1。组员继续开发时创建自己的team分支；不得在main或稳定V6上直接改实验。

## 不入Git的大文件和授权输入

以下仅提供清单和SHA，文件通过团队已有受控、限组员访问的内部文件渠道交接；确认赛事授权允许再传递，禁止在公开Issue/PR附原始TLE或公开分享链接。接收后用Get-FileHash -Algorithm SHA256逐项核对。缓存与依赖ZIP不属于GitHub代码包。完整路径定位清单另在本地交付external_files_manifest.json，仓库版本只保存文件名/用途/大小/哈希。

|用途|文件|字节|SHA-256|
|---|---|---:|---|
|B_C_authorized_inputs|orbits.tle|1585118|d3347ed5926ed70b9f7dd008fb17a707b210a7fbe4754e59de4e8d92c4ff729a|
|B_C_authorized_inputs|priority_high.txt|11997|1c147fef33897e417a085dc546f1709eb30d0b59fdf412b306c204512fc78dee|
|B_C_authorized_inputs|priority_low.txt|23663|9748c59a28f50f1ead9fad58c718b7d6a78c49c720d937346583cc02f5fbe43a|
|B_C_authorized_inputs|priority_medium.txt|23684|714b94c954270f6b04c21e7bee274f344cc5fae9296b370f761fb25ea44370a8|
|B_C_authorized_inputs|stations.txt|416|f34dcb2d3f1932ad37c5030df430ac0e5ed4c7e1ee93d3d0d7198a0efda095e6|
|B_C_authorized_inputs|de421.bsp|16788480|a20a7139da04cbc462454634918e9a9ca69127044e2cc9d4f9c16e238d2deedc|
|B_C_authorized_inputs|windows.csv|97104769|ccc3a0d614709d4dde203a7d237f51cfa3a2406a934c1d5cbddc2736ea2957f3|
|B_C_authorized_inputs|selected_targets.csv|516540|83224013f42959e9e6ffbea57d637bfd165580ef1df1f987b197fcc65c875fe3|
|B_C_authorized_inputs|experiment_report.json|29894|e0c9c13475cf9d3502c45c2a26159f0fe3b473dc24c222e6652a1460319ea28c|
|B_C_authorized_inputs|final_plan.csv|402896|3036bb91dcc77389ac2276b8482110e4795551c101709f08c1ddcf052d7be71c|
|test_fixture|windows.csv|48492793|adffe7157a6dca8a699497c7159dedb91bc4bf2ad7c78cf6c0c5c2c369f2a764|
|offline_environment|windows_cp312_packages.zip|23647404|5c2fbf64f447423165c7e54a168dfa2c4b595755512a8c1becca339d3d74058f|
|offline_environment|offline_manifest.json|379892|edb56cadfc5f08d1225cea68e5d5f57bd7a7e9f2e7ec2dc3f8ffd94f8c3f01aa|
|local_historical_archives|real_aug2026_10000_results.zip|43209771|f002c0c8df23356442a801e047092fd735ffc482e22d9ab4b04f094c426a04f2|
|local_historical_archives|v5_results.zip|9508650|03af51b8613b10671c31ca132371cc7331a868a0e5ac55308815e576f306bb9e|
|local_historical_archives|V6_STABLE_RELEASE.zip|95363428|8f949db7a43c281ec962e3ffbb558a6e146b4d24b0512decb12feb4ed1c9f205|
|local_historical_archives|V7_RESULTS.zip|14398370|c45daa7db502267d48c2bf11aa5db17134c4cff25bd3b3e136dd5eab3a595877|
|local_historical_archives|V7_ROUND2_RESULTS.zip|22908718|d5ba876d1d1b535afad043248f451b54724df4604b8d7155d7a6382976fbbf60|

例如校验：

```powershell
Get-FileHash -LiteralPath 'D:\CompetitionData\real_aug2026_10000\windows.csv' -Algorithm SHA256
```

目标元数据已入库，不含原始TLE行。A层支撑窗口仅8713条，已记录原97MB全量缓存SHA；用于验算固定计划，不是全量窗口缓存。测试5000窗口与优化10000窗口同名，必须按用途放入不同目录，禁止相互覆盖。

## 尚需团队完成

独立记录A、B、C各级复现状态；核实赛事规则和原始数据传播授权、TLE适用性与物理精度；审核新PR并决定何时合并及准备官方提交。GitHub发布前再次检查最新main/V6快照，原V6 PR #1保持原状。任何后续得分改进均须另开阶段，不属本次冻结交付。
