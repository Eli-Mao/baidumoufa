# 变更记录（留痕）

所有条目都注明**依据**与**可复现方式**，便于事后审计与被质疑时回溯。

---

## 交付件版本

### v1.0 — 2026-10-20 —「过顶盲区任务修正补丁 + 独立复核脚本」

**交付人**：川谷　**承接人**：Iceswing
**针对**：`SatelliteProject/Task4_Phase0_DataCheck` 的 50 目标 / 6 天 / 142 条任务计划

**依据（一手证据）**
| 来源 | 用途 |
|---|---|
| `outputs/v3_fifty_physics_all_0p5s.json`（Iceswing 产出） | 确认 142 条中 3 条 `core_pass=false`，越界类型 `bad_core_elevation` |
| `outputs/v3_fifty_plan_6d_auto_insert_1s.csv` | 被修补的计划表；也用于取同站占用与冷却约束 |
| `outputs/fifty_target_visibility_6d.csv` | 窗口表（30 s 粗扫口径），用于对照真实峰值 |
| `data/raw/orbits.tle`、`data/raw/stations.txt` | 独立重算仰角 |
| `config/competition_rules.json` | 物理与计分口径对齐依据 |
| `de421.bsp` / Skyfield 1.55 / SGP4 2.27 | 独立重算所用参考实现 |

**做的事**
1. 用 1 s 重扫确认根因：三条任务均为**过顶窗口**，真实峰值仰角
   85.499° / 86.185° / 85.981° **超过 85° 上限**，而 30 s 粗扫未采到峰值，
   导致"被 >85° 盲区劈成两段"的窗口被当成一个连续窗口。
2. 用 0.5 s 采样独立复现了越界（越界秒数 5 s / 8 s / 7 s，与 Iceswing 记录的
   10 / 16 / 13 个采样点在采样精度内一致）。
3. 生成修正补丁：三条任务改为在真实合法段内留 1 s 边距放置，时长按段长自适应收缩。
4. 独立复核：修正后 **142/142 全 PASS，0 结构性违规**。

**结果**
| 指标 | 修正前 | 修正后 |
|---|---|---|
| 物理越界任务 | 3 | **0** |
| 总分 | 460.333 | 459.223（−1.110，−0.241%） |
| 结构性违规 | 0 | 0 |

**新增文件**
- `TASK.md`：交付主文档（AI 可直接阅读的完整交接说明）
- `CHANGELOG.md`：本文件
- `src/rules_fine.py`：细粒度物理判定与放置规则（生成端与复核端共用）
- `src/make_patch.py`：补丁生成器（自动扫描全表）
- `src/verify_patch.py`：独立复核器
- `requirements.txt`
- `outputs/patch_plan_fix.csv` / `.json`：补丁表与证据
- `outputs/plan_fixed_v3_fifty_plan_6d_auto_insert_1s.csv`：可直接替换的计划
- `outputs/make_patch_report.txt`：生成留痕
- `outputs/verify_patch_report.txt`：复核留痕
- `outputs/verify_patch_result.json`：逐条复核明细

**遗留（未解决，不要当成已解决）**
- 0.5 s 采样 ≠ 连续时间证明
- TLE 年龄约 58–65 天，SGP4 长跨度误差未评估
- 窗口表缺陷是全局性的；本补丁只修了 50 目标实验暴露的 3 条，
  10000 目标规模下需按 `TASK.md §1-B` 根治

**复现方式**：见 `TASK.md §3`（两条命令，退出码 0 表示全部通过）

---

## 主仓库（sat-planning）提交记录

| 提交 | 日期 | 说明 | 依据 |
|---|---|---|---|
| `a1043cf` | 2026-10-20 | 按组委会答疑更新口径，并记录窗口表在过顶处必须切分的缺陷 | Iceswing 的 `competition_rules.json` + 本次 1 s 重扫实测 |
| `d359e5c` | 2026-10-20 | 移除误提交到 main 的空占位文件 `WangBinyao`，成员内容一律走各自分支 | 远端 `e47dfe7`（GitHub 网页端新建文件）；该文件为空，非任何人的成果 |
| `8e4ed6b` | 2026-10-19 | 合并远端占位 `Initial commit`（保留远端历史，未 force） | 远端 `20416f4` |
| `d919d54` | 2026-10-19 | 初始化赛题四观测任务规划的项目骨架与数据契约（30 文件 / 2969 行） | 本人 |

**口径变更明细（`a1043cf`）**

| 项 | 变更前 | 变更后 | 依据 |
|---|---|---|---|
| `PLAN_T0_UTC` | `2026-08-03T00:00:00Z`（占位） | `2026-10-01T00:00:00Z` | 答疑确认规划期为 2026-10-01 ~ 10-07 |
| `REPEAT_COOLDOWN_S` | 无 | `172800.0`（48 h） | 答疑：同一目标距上次观测结束满 48 h 才可再观测，且重复观测可再次计分 |
| 评分口径 | 两套并存未定 | 补入第三套更细版本：计算结果 40%（覆盖率 50% + 总分 50%）+ 产品体验 30% + 算法效率 30% + 加分 ≤10% | Iceswing 的 `competition_rules.json` |

**仍未确认**：时间基准是 UTC 还是北京时间（`docs/open_questions.md` Q2）
