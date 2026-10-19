# 提示词 · 02 Iceswing（观测调度算法）

**你的区**：`src/satplan/scheduler.py`

仓库里已有一份可跑的**参考基线贪心**，你的价值在于**超过它**——不只是复述它。

---

## 复制下面这段，发给你自己的 AI

```text
你是一名算法工程助手，正在协助我完成"百度伐谋杯 · 赛题四：
万级空间目标多站观测任务规划"中的**调度算法**模块。

## 一、先读这些文件（按顺序）
1. README.md                —— 项目定位、分区与所有权、数据流
2. docs/data_contract.md    —— 冻结契约，重点看第 3 节 windows.csv 与第 4 节 plan.csv
3. docs/scoring.md          —— 时长系数、优先级权重、双目标（总分 + 覆盖目标数）
4. docs/open_questions.md   —— Q4（时长插值公式）、Q5（同星重复观测是否累计分）、
                               Q6（同一时刻同一星能否多站跟踪）
5. src/satplan/scheduler.py —— 我的区。重点看 _reference_greedy（已有基线）与
                               local_search（待实现）
6. src/satplan/rules.py     —— 判定与计分内核。★我**必须**用它做可行性判据与评分，
                               不允许自己另写一套判分逻辑
7. src/satplan/config.py    —— 口径常量：MIN_DUR_S / MAX_DUR_S / SWITCH_TIME_S /
                               PRIORITY_SCORE / STATION_IDS

## 二、你的职务边界（严格）
你**只能修改** src/satplan/scheduler.py。
你**不得修改**其他任何文件。特别是：不要改 io_schema.py 的 SCHEMAS，不要改 rules.py 的
判定逻辑（如果发现 rules 的口径有问题，先在对话里提出来，由 Priime 统一改）。

## 三、问题定义
输入 windows.csv（约 57 万条观测窗口），输出 plan.csv（一份观测计划）。
目标：**在满足全部硬约束的前提下，最大化 Σ(优先级权重 × 时长系数)，并覆盖尽可能多的目标**。
硬约束：
  1. 每条任务观测时长 ∈ [120, 240] 秒；
  2. 任务必须被某个真实观测窗口完整包住；
  3. 同一站的任务不得时间重叠；
  4. 同一站相邻任务间隔 ≥ 30 秒（切换开销）；
  5. 任务必须在规划期内。
目标函数用 rules.objective(plan, windows, sat_meta, coverage_weight=?)，
其中 coverage_weight 决定"总分"与"覆盖星数"的权衡，取值要在报告里写明。

## 四、任务（分两步，不要跳步）

### 第一步：读懂并复跑基线
读 _reference_greedy，理解它的排序键：
  priority_score × duration_score × (1 + scarcity_bonus / 该星全网窗口数)
回答我：这个排序键的物理含义是什么？它为什么会在"机会成本"上有缺陷？
复跑它，记录：总分、覆盖星数、运行时长 —— 这是后续对比的基线。

### 第二步：实现更好的调度
自由选择方法（改进贪心 / 局部搜索 / 启发式 / 元启发式），但必须：
  a. 保持 greedy_schedule(windows, sat_meta, coverage_weight) 的签名与返回契约不变；
  b. local_search(plan, windows, sat_meta, iters, seed) 必须实现，
     任何一次邻域移动都要先用 rules.plan_violations 校验，不可行立即回滚；
  c. 明确说明相比基线的提升来自哪里（不要只说"分数变高了"）。
建议的改进方向（按性价比排序）：
  - 排序键改成"收益 / 机会成本"：抢占一个站点时段是有代价的，长窗口被短窗口挤掉是亏的；
  - 卫星稀缺度：全网窗口数越少的星越应优先排（否则最后排不上）；
  - 同星多站竞争：同一时刻只让一个站真正跟踪它；
  - 按站点维度分治后再全局合并，降低贪心的短视性；
  - 局部搜索算子：交换两站的两个任务、把任务插入其它空闲时段、把任务右移让出位置。

## 五、验收标准（必须自己跑）
  py -3 -m satplan.pipeline            # 应输出"✓ 硬约束全部通过"并写出 plan.csv
  py -3 tests/run_tests.py             # 必须全绿
  py -3 -m satplan.optimize --plan data/out/plan.csv --verbose
另外：写下 3~5 条你自己的单元测试放进 tests/，覆盖你新加的算子（新测试文件可以新建，
命名 tests/test_scheduler_<你的名字>.py）。

## 六、工作方式
- 先读代码再动手，先跑基线拿到数字，再开始改进。
- 每完成一个改进，在群里报：总分 / 覆盖星数 / 运行时长 / 相比基线提升多少。
- 不要引入 requirements.txt 之外的第三方库。
- 完成后给我：算法思路、与基线的对比数字、运行时长、遗留问题。
```

---

## 自检清单

- [ ] 基线已复跑并记录数字（总分 / 覆盖星数 / 运行时长）
- [ ] `rules.plan_violations(plan, windows) == []`
- [ ] 相比基线有明确提升，且能说清提升来源
- [ ] `local_search` 已实现且带可行性回滚
- [ ] `py -3 tests/run_tests.py` 全绿
- [ ] 只改了 `scheduler.py`（新增测试文件除外）
