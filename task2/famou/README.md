# 赛题二 · 伐谋（FAMOU）适配

把星座设计策略交给伐谋演化：伐谋改写 `init.py` 的 EVOLVE-BLOCK，评估器运行每个候选、按赛题公式打分。
接口按伐谋官方 Skills 规范（`famou-artifact-generator`）：
`evaluate(path_user_py, task_name="default", timeout=3600) -> dict`，返回 `validity` / `combined_score` /
`cost_time` / `error_info` / `metric`。

| 文件 | 作用 |
|---|---|
| `evaluator.py` | 评估器：对每个 N 并行运行候选 → 合法性检查 → 快速评估 → 各 N 赛题分取平均 |
| `init.py` | 被演化的初始程序；EVOLVE-BLOCK 内是设计策略（基线同 `optimizer.py`，初选也按预算截停） |
| `prompt.md` | 给伐谋的任务说明（专业版"内容与优化目标"） |
| `refs.json` / `make_refs.py` | 固定参考值及其生成脚本（长三角整体重访口径） |
| `build/walker_baseline.py` | 区分度验证用的弱候选（普通 Walker） |
| `build/validation.json` | 两个候选在 default 任务上的评估结果 |

## 用法（task2 目录下）

```bash
python famou/evaluator.py famou/init.py --task quick     # N=28、预算 30 s，冒烟测试
python famou/evaluator.py famou/init.py                  # default：N=28/37/60/100、各 120 s，并行约 2 分钟
python famou/make_refs.py                                # 评分口径变化后重算参考值
python -m unittest tests.test_famou -v                   # 评估器自测
```

`task_name`：`default`（N = 28、37、60、100，每个 N 预算 120 s）、`quick`（N = 28，30 s）、
`full`（同 default，600 s，与 `generate.py` 默认预算一致）。单个 N 的硬超时为 预算 × 1.25 + 60 s。

## 评分规则

- 候选的调用契约：`python <候选> --n N --budget 秒 --out 星座.csv`。工作目录为 `famou/`，
  PYTHONPATH 指向 `task2/`，所以候选可以 `import designs / fasteval / score / sso / constellation`。
- 任一 N 报错、超时、没写出文件、列不全或含 NaN、构型非法（`evaluate.legal`：星数、高度 500–700 km、
  太阳同步倾角、e = 0），整个候选 `validity = 0`、`combined_score = 0`。
  赛题要求程序对任意 N 都能出合法解，所以没有"部分合法"。
- 候选运行前后会对 `task2/*.py`、`refs.json` 和评估器做哈希比对，有改动就判非法，防止候选改评分口径。
  在本地自测时，如果有别的进程同时在改这些文件，也会触发这一条。
- 分数：`score.official`（长三角整体不足两次访问时重访项 0 分），参考值取 `refs.json`，
  各 N 取平均。参考值在演化期间必须固定，候选之间才可比。

## 参考值（refs.json，2026-10-23）

与 `generate.py` 的 refs 算法相同（初选 + 整体旋转扫描中各指标的最优值，不含坐标下降），但不写 `out/`：

| N | T90 (d) | T100 (d) | Tavg (h) | Tmax (h) |
|---|---|---|---|---|
| 28 | 2.491 | 4.644 | 1.112 | 1.405 |
| 37 | 1.899 | 3.656 | 0.752 | 1.583 |
| 60 | 0.975 | 2.200 | 0.506 | 0.794 |
| 100 | 0.662 | 1.503 | 0.301 | 0.402 |

单是初选这一步，28 星就要约 65 s，100 星约 230 s（本机、有其他计算并行）。所以 `init.py` 的初选
按预算截停，`optimizer.py` 的初选则不受预算限制。

## 验证（default 任务）

| 候选 | N=28 | N=37 | N=60 | N=100 | 平均 |
|---|---|---|---|---|---|
| `init.py` | 91.9 | 85.3 | 79.3 | 80.0 | **84.1** |
| 普通 Walker | 54.8 | 42.4 | 59.9 | 70.0 | 56.8 |

评估器能正确区分好坏；`init.py` 每个 N 用时 115–117 s，在 120 s 预算内。
按时间预算停止的搜索在不同机器上结果会有小幅差别。

## 上传到伐谋专业版

1. 上传 `task2/` 文件夹（可去掉 `out/`、`tests/`），在其中选 `famou/init.py` 为"待改进算法"、
   `famou/evaluator.py` 为评估器，`prompt.md` 的内容填进"内容与优化目标"。
2. 未确认：比赛账号是哪一档、云端 Python 有没有 numpy / pandas、上传大小限制；
   专业版界面怎样调用评估器、默认 timeout 是多少。上线前先用 1–2 轮小实验确认。
3. 演化出的好策略由人审查后移植回 `optimizer.py`。之后若 `optimizer.py` 再改，
   `init.py` 的基线需要同步。
