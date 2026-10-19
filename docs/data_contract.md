# 数据契约（冻结接口）

本文件与 `src/satplan/io_schema.py` 中的 `SCHEMAS` **必须保持一致**。
改列名或类型时，两处一起改，并在群里通知四个人。

## 全局约定

| 项 | 约定 |
|---|---|
| 编码 | UTF-8，英文逗号分隔，首行为列名 |
| 时间 | 统一 **UTC**；相对时间用"自规划期起点 `t0` 起的秒" |
| 角度 | 度（deg），东经 / 北纬为正 |
| 长度 | 站址海拔用 m，轨道相关用 km（本赛题未涉及） |
| 空值 | 必需列不得为空，否则 `io_schema` 直接抛 `SchemaError` |

时间列约定：**每张时间相关的表同时给 `*_utc`（ISO8601，形如 `2026-08-03T01:01:01.500Z`）
和 `*_s`（相对 `t0` 的秒）**。这样既能和其他系统对接，也能在内部做纯数值计算。

`t0` 取自 `config.PLAN_T0_UTC`（★当前是占位值，见 `open_questions.md` Q1）。

---

## 1. `stations.csv` — 站点表

产出：契约层（`io_schema.read_stations_raw`）
消费：楼心荡（可见性计算）、全队

| 列名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `station_id` | int | ✓ | 1~10，与 `站址.txt` 编号一致 |
| `lon_deg` | float | ✓ | 经度，东经为正 |
| `lat_deg` | float | ✓ | 纬度，北纬为正 |
| `alt_m` | float | ✓ | 海拔 |
| `min_elev_deg` | float | ✓ | 最低仰角，取 `config.MIN_ELEV_DEG` = 10 |
| `max_elev_deg` | float | ✓ | 最高仰角，取 `config.MAX_ELEV_DEG` = 85 |

> 注：`站址.txt` 中的经度有 290°、358° 这样的值，属于 **0~360 惯例**。
> 下游若要用 0~±180 惯例，请在 `propagate.py` 内部换算，**不要改这张表的口径**。

---

## 2. `sat_meta.csv` — 卫星元数据

产出：契约层（`io_schema.build_sat_meta`）
消费：全队

| 列名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sat_id` | int | ✓ | 解码后的整数 NORAD 编号（含 Alpha-5 解码结果） |
| `name` | str | ✓ | 卫星名称（原始 `0 NAME` 行） |
| `priority` | str | ✓ | `high` / `mid` / `low` |
| `priority_score` | int | ✓ | 5 / 3 / 2 |
| `tle_epoch_utc` | str | ✓ | 该星 TLE 历元（ISO8601 UTC） |

**实测规模**：10000 行；`high`=2024、`mid`=3990、`low`=3986。

---

## 3. `windows.csv` — 观测窗口表 ★ 全队唯一数据源

产出：**楼心荡**（`windows.assemble_windows` → `io_schema.save_windows`）
消费：**Iceswing 调度**、**Priime 评分**、川谷出图

| 列名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `window_id` | int | ✓ | 全表唯一，连续 |
| `station_id` | int | ✓ | 站点编号 |
| `sat_id` | int | ✓ | 卫星编号 |
| `priority` | str | ✓ | 冗余自 `sat_meta`，便于免 join 直接用 |
| `priority_score` | int | ✓ | 冗余自 `sat_meta` |
| `t_start_s` | float | ✓ | 窗口起点（秒，相对 t0） |
| `t_end_s` | float | ✓ | 窗口终点 |
| `dur_s` | float | ✓ | `t_end_s - t_start_s` |
| `t_start_utc` | str | ✓ | ISO8601 |
| `t_end_utc` | str | ✓ | ISO8601 |
| `max_elev_deg` | float | ✓ | 窗口内最大仰角（用于诊断/可视化） |

**窗口口径**：窗口 = 连续满足可见条件的时段，可见条件为
站点仰角 ∈ [10°, 85°]、测站太阳高度角 < −6°、卫星受太阳照亮。
**窗口之间是分离的**：同一站对同一颗星的相邻窗口，中间隔着轨道周期级别的间隔。

---

## 4. `plan.csv` — 观测计划表

产出：**Iceswing**（`scheduler.greedy_schedule` / `local_search`）
消费：**Priime 评分**、**川谷提交**、伐谋 Evaluator

| 列名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task_id` | int | ✓ | 全表唯一（从 1 开始） |
| `station_id` | int | ✓ | 执行该任务的站 |
| `sat_id` | int | ✓ | 观测目标 |
| `priority` | str | ✓ | `high` / `mid` / `low` |
| `priority_score` | int | ✓ | 5 / 3 / 2 |
| `t_start_s` | float | ✓ | 观测开始（秒，相对 t0） |
| `t_end_s` | float | ✓ | 观测结束 |
| `dur_s` | float | ✓ | 观测时长，**必须在 [120, 240] 内** |
| `duration_score` | float | ✓ | 时长得分系数，由 `rules.duration_score` 算出 |

**硬约束（`rules.plan_violations` 会逐条检查）**

1. `dur_s ∈ [120, 240]`；
2. `t_start_s ≥ 0` 且 `t_end_s ≤ 规划期长度`；
3. 任务必须被 `windows.csv` 中某个窗口完整包住（否则等于"凭空观测"）；
4. 同站任务不得时间重叠；
5. 同站相邻任务间隔 ≥ `config.SWITCH_TIME_S` = 30 s；
6. `dur_s == t_end_s - t_start_s`（自洽）。

---

## 5. `score.json` — 评分报告

产出：**Priime**（`scoring.build_score_report`）

| 字段 | 说明 |
|---|---|
| `weighted_score` | 加权总分 = Σ(`priority_score` × `duration_score`) |
| `n_tasks` / `n_covered` / `coverage_rate` | 任务数、覆盖卫星数、覆盖率 |
| `hi_covered` / `hi_coverage_rate` | 高优目标覆盖数与覆盖率 |
| `avg_dur_s` / `station_utilization` | 平均观测时长、站点占用率 |
| `by_priority` | 分优先级的任务数 / 覆盖数 / 覆盖率 / 得分 |
| `feasible` / `n_violations` / `violations` | 可行性与违规明细 |

---

## 6. 原始数据文件解析口径

| 文件 | 解析要点 |
|---|---|
| `轨道.txt` | 三行一组：`0 NAME` / `1 ...` / `2 ...`；**编号字段是定宽 5 字符，可能是 Alpha-5（A0045 / T0288）** |
| `站址.txt` | 跳过表头行（含 `站址：`）与尾行（含 `设备观测限制`）；行格式 `编号:经度, 纬度, 海拔` |
| `高/中/低优先级目标.txt` | 单行或几行的逗号分隔整数编号 |

**Alpha-5 是这套数据的头号坑**：108 颗卫星的编号带字母前缀，用 `int()` 直接转会因为
5 字符里混了字母而报错或被静默跳过，导致与优先级表关联时丢失这些星。
统一走 `io_schema.decode_satnum()`。
