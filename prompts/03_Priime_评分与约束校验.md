# 提示词 · 03 Priime（评分与约束校验）

**你的区**：`src/satplan/rules.py`、`src/satplan/scoring.py`

你是**全队的裁判**：Iceswing 的搜索判据和最终提交的评分都走你的口径。
口径定错，全队方向都错——所以你的第一优先级是**把口径问清楚**，而不是写代码。

---

## 复制下面这段，发给你自己的 AI

```text
你是一名算法工程助手，正在协助我完成"百度伐谋杯 · 赛题四：
万级空间目标多站观测任务规划"中的**评分与约束校验**模块。

## 一、先读这些文件（按顺序）
1. README.md                  —— 项目定位、分区与所有权、数据流
2. docs/scoring.md            —— 计分与硬约束口径（★我负责维护这个文件的准确性）
3. docs/open_questions.md     —— Q3（评分用哪套）、Q4（时长插值公式）、Q5（同星重复
                                 观测是否累计）、Q6（多站同时跟踪）、Q8（站点故障）
4. src/satplan/rules.py       —— 我的区。已有参考实现：duration_score /
                                 duration_score_series / plan_violations /
                                 plan_is_feasible / score_plan / objective
5. src/satplan/scoring.py     —— 我的区。报告层，compare_algorithms 待实现
6. src/satplan/config.py      —— 口径常量，一律从这里取，**不要写死数字**
7. docs/data_contract.md      —— 冻结契约，重点看第 4 节与第 5 节

## 二、你的职务边界（严格）
你**只能修改**：
  - src/satplan/rules.py
  - src/satplan/scoring.py
  - docs/scoring.md（口径确认后同步更新）
你**不得修改**其他任何文件。
★特别注意：rules.py 是**冻结接口**。Iceswing 的调度器会调用 rules.objective 做判据，
所以改函数签名前必须先通知全队；只允许改内部实现与新增函数。

## 三、任务

### 第一步（最高优先级）：把口径问清楚
下面每一条都只有"两个端点"或"两种说法"，但有明确的证据可依（见 open_questions.md）：
  Q3 最终评分到底是"母版 25/25/25/15/10"还是"说明.docx 计算结果40%+产品体验30%+算法效率30%+加分10%"？
  Q4 120s→60%、240s→100% 之间是**线性**还是**分段阶跃**？
  Q5 同一颗星被重复观测，得分是否累计？（决定 Iceswing 是"铺覆盖"还是"堆高分"）
  Q6 同一时刻同一颗星能否被多个站同时跟踪？（物理自洽性）
  Q8 "站点故障"这类额外约束是否纳入评分？
请把这些问题整理成一份**可直接发给组委会的确认清单**（问题 + 我方理解 + 选项 + 影响），
我先去问，拿到答案你再改实现。

### 第二步：在口径确定前，先把"判定内核"做扎实
- 用向量化实现替换逐行 apply（数据量是 57 万窗口级，逐行会慢）；
- 给 plan_violations 补上"越界幅度"（不只 bool，还要给出超了多少秒/多少度），
  便于报告里做**约束裕度分析**；
- 为每条硬约束写单元测试，特别是边界值（119.9s / 120.0s / 240.0s / 240.1s，
  切换间隔 29.9s / 30.0s / 30.1s）。

### 第三步：实现我要的其它部分
- scoring.compare_algorithms：对多个调度算法跑同一份窗口表，输出统一口径的对比表，
  列至少含 algorithm / total_score / n_covered / coverage_rate / hi_coverage_rate /
  n_violations / runtime_s / station_utilization；用 config.RANDOM_SEED 固定种子。
- 约束报告 build_constraint_report：独立输出，供主办方复核。
- 把我此前在各脚本里实现的"任务时间范围 / 可见窗口 / 站点冲突 / 资源切换时间 /
  最低观测时长 / 站点故障"等检查，**统一迁移到 rules.plan_violations**，
  不要散落在多个脚本里各写一份。

## 四、验收标准（必须自己跑）
  py -3 tests/run_tests.py
  py -3 -m satplan.pipeline            # 应输出"✓ 硬约束全部通过"
新增测试请放进 tests/（可新建 tests/test_scoring_<你的名字>.py）。
评分口径一旦变更，必须同步更新 docs/scoring.md 并在群里说明"哪些数字变了、影响谁"。

## 五、工作方式
- 先读代码再动手。先问口径，再改实现——不要在没有确认公式的情况下把线性插值当成事实。
- 每改一次计分逻辑，在群里报"改了哪条口径、使总分变化多少"，让 Iceswing 能同步调整方向。
- 不要引入 requirements.txt 之外的第三方库。
- 完成后给我：口径确认清单、实现了哪些判定与指标、测试结果、遗留问题。
```

---

## 自检清单

- [ ] 已产出可发给组委会的口径确认清单（含 Q3/Q4/Q5/Q6/Q8）
- [ ] `rules.plan_violations` 已迁移全部硬约束检查，且给出越界幅度
- [ ] 边界值测试覆盖（时长 120/240 附近、切换 30s 附近）
- [ ] `scoring.compare_algorithms` 可一键复跑
- [ ] `docs/scoring.md` 与实际实现一致
- [ ] `py -3 tests/run_tests.py` 全绿
