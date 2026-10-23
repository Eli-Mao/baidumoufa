# V6稳定版团队入口

最高合法模型得分31015.978086；7877任务、3987覆盖。另保留4100覆盖备选。

请先阅读[团队复现说明](docs/V6_TEAM_REPRODUCTION.md)，计划与证书位于[accepted/v6](accepted/v6)。技术报告、官方待确认参数和未推送GitHub状态均有独立记录。

---

# 赛题四 · 万级空间目标多站观测任务规划

> 百度伐谋杯 · 开运联合命题方向（万级空间目标条件下的多站资源协同调度与全局优化）

10 个地面站、10000 颗空间目标、6 天规划期，在观测时长、切换开销、站点独占等硬约束下，
**最大化观测得分并覆盖尽可能多的目标**。

---

## 一、5 分钟快速开始

```powershell
cd sat-planning

# 1) 依赖（Python 3.11 / 3.12）
pip install -r requirements.txt

# 2) 把原始数据从压缩包解到 data/raw（文件名是 GBK，必须用这个脚本解，否则会乱码）
py -3 scripts/prepare_raw_data.py

# 3) 契约层自检：解析 10 个站址 + 10000 颗卫星 + 优先级，并校验 1:1 对齐
py -3 -m satplan.pipeline --stage meta

# 4) 跑测试（34 条，含真实数据校验）
py -3 tests/run_tests.py

# 5) 全链路（需楼心荡的模块已实现，或已有 windows.csv）
py -3 -m satplan.pipeline
```

也可以直接用 `run.ps1`：`.\run.ps1 -Stage meta` / `.\run.ps1 -Test` / `.\run.ps1 -WithReport`。

---

## 二、分区与所有权（**重要**）

四人各占一段，**改别人文件前先在群里说一声**。跨区只能通过函数调用，不能改对方内部实现。

| 区 | 负责人 | 文件 | 职责 |
|---|---|---|---|
| **契约层 / 总控** | 川谷 | `src/satplan/config.py`<br>`src/satplan/io_schema.py`<br>`src/satplan/pipeline.py`<br>`src/satplan/optimize.py`<br>`src/satplan/report.py` | 统一口径常量、**全项目唯一的数据读写入口**、端到端编排、伐谋 Evaluator、图表与展示 |
| **轨道与窗口** | 楼心荡 | `src/satplan/propagate.py`<br>`src/satplan/windows.py` | TLE 解析、SGP4 传播、地面站可见性、生成 `windows.csv` |
| **调度算法** | Iceswing | `src/satplan/scheduler.py` | 贪心 → 局部搜索 / 伐谋自演化，产出 `plan.csv` |
| **评分与约束** | Priime | `src/satplan/rules.py`<br>`src/satplan/scoring.py` | 硬约束判定内核、计分公式、约束报告、算法对比实验 |

**冻结接口（改这些要四个人同意）**
- `io_schema.SCHEMAS` 里的列名与类型
- `rules` 里的判定与计分函数签名
- `scheduler.greedy_schedule` / `scheduler.local_search` 的入参出参
- `propagate.propagate_windows` 的入参出参

每人对应的开工提示词见 [`prompts/`](prompts/)。

---

## 三、数据流

```
轨道.txt / 站址.txt / 优先级*.txt        （原始数据，scripts/prepare_raw_data.py 解出）
            │
            ├─► 契约层 io_schema ──► data/interim/sat_meta.csv   (10000 颗，含优先级与权重)
            │                      ──► data/interim/stations.csv  (10 个站)
            ▼
   propagate.py + windows.py（楼心荡）
            │
            ▼
   data/interim/windows.csv   ★ 全队唯一数据源
            │
            ▼
   scheduler.py（Iceswing）──► data/out/plan.csv
            │
            ▼
   rules.py + scoring.py（Priime）──► data/out/score.json
            │
            ▼
   report.py（川谷）──► reports/*.png
```

---

## 四、当前状态

| 模块 | 状态 |
|---|---|
| 契约层（config / io_schema） | ✅ 完成，含 34 条测试覆盖 |
| 原始数据解析与 1:1 对齐校验 | ✅ 完成（10000 颗星 ↔ 10000 个优先级编号，零缺失零重叠） |
| 硬约束判定内核 `rules.py` | ✅ 参考实现可用（Priime 待按最终口径校准） |
| 参考基线贪心 `scheduler.greedy_schedule` | ✅ 可跑，作为 Iceswing 的对比基线 |
| `scheduler.local_search` | ⬜ 待 Iceswing 实现 |
| `propagate.py` / `windows.py` | ⬜ 待楼心荡实现 |
| `scoring.compare_algorithms` | ⬜ 待 Priime 实现 |
| `report.make_figures` | ⬜ 待川谷实现 |
| `optimize.py`（伐谋 Evaluator） | ✅ 接口可用（依赖 plan.csv 与 windows.csv） |

---

## 五、必须尽快确认的口径（会决定谁能开工）

详见 [`docs/open_questions.md`](docs/open_questions.md)，其中最关键的两条：

1. **规划期到底是哪 6 天？** 实测所有 TLE 历元集中在 **2026-08-02 ~ 08-04 UTC**；
   若按 `10.1~10.7` 规划，SGP4 要外推约 58 天，误差巨大。`config.PLAN_T0_UTC` 目前是占位值。
2. **评分用哪一套？** 母版是 `25/25/25/15/10`，`说明.docx` 是 `计算结果40% + 产品体验30% + 算法效率30% + 加分10%`。

---

## 六、协作规约

1. **数据只走 `io_schema`**。不要在各模块里自己 `pd.read_csv`，否则列名一改就全线崩。
2. **判分只走 `rules`**。Iceswing 的搜索判据和 Priime 的最终评分必须同源，避免"搜出来可行、提交判违规"。
3. **口径只改 `config.py`**。不要在业务代码里写死 120 / 240 / 30 / 5 / 3 / 2 这些数字。
4. **提交前跑 `py -3 tests/run_tests.py`**，红了不要提交。
5. 每天 20:00 群里报进度，格式：`已完成 / 卡在哪 / 明日目标`。
