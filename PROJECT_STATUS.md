# Project Status

Updated 2026-10-22 (Asia/Shanghai)

## Competition Date Amendment and 3,000-Target Rerun

- Latest user-provided competition period is **2026-08-01 00:00 through 2026-08-07 00:00 UTC**. `src/satplan/config.py` now uses `PLAN_T0_UTC=2026-08-01T00:00:00Z` and retains the six-day duration; UTC remains the project time basis.
- Updated UTC-offset unit expectation and the open-question record. Reports describe the TLE epoch offset relative to August (epochs Aug 2-4; up to about 1-3 days backward and 3-5 days forward propagation). This date amendment was supplied by the user and was not independently checked against a new organizer document.
- Previous October-period experiments and checkpoints remain untouched and historical only. The 3,000-target experiment was rerun into `data/out/real_aug2026_3000/` with deterministic seed `20261021`; no October checkpoint was reused. It propagated 3,000 unique targets and produced 160,435 windows; propagation took 1,299.91 s, initial pipeline 1,556.01 s, and peak RSS was 368.14 MB.
- Initial plan: 5,432 tasks / 2,305 covered / 18,706.235 points, with zero scheduler violations. Full 1-second interval sampling found elevation overruns in 57 tasks. Physical repair changed 43 tasks and dropped 14 with no legal replacement; final plan is 5,418 tasks / 2,304 covered / 18,630.095 points, with zero scheduler violations.
- Final full-interval audit passed all 5,418/5,418 tasks at 1-second discrete samples (no elevation, darkness, or illumination failures). This is not a continuous-time proof or official orbit-accuracy certification. TLEs from Aug 2-4 require up to about 1-3 days backward and 3-5 days forward propagation around the Aug 1-7 planning period.
- Final report: `data/out/real_aug2026_3000/profile_report.json`; repaired plan and audit are in the same folder. The 1,556.01 s pipeline runtime excludes later repair and full-task audit durations.
- Regression check after the date change: 36/36 unit tests passed.
- The 3,000-target August run is the current real-data performance baseline for the amended planning period; October-period metrics below are historical and not directly comparable.
- 5,000-target real run started with the same seed (`20261021`), UTC dates, 30-second coarse scan setting, and a separate output/checkpoint directory `data/out/real_aug2026_5000/`. At start: 2.15 GB free RAM and 88.37 GB free disk; estimated propagation peak about 614 MB from the 3,000-target measured peak. Status remains in progress until full-task audit passes.

## Completed

- Copied the five local raw input files into `data/raw/` with matching SHA-256 hashes. The directory remains ignored by Git.
- Copied `de421.bsp` for Skyfield solar geometry.
- Fixed `satplan.config` to read `orbits.tle`, `stations.txt`, and `priority_*.txt`.
- All 35 repository tests pass, including the seven raw-data contract tests.
- Implemented chunked Skyfield/SGP4 propagation, UTC handling, station geometry, solar altitude, satellite illumination, sampled windows, edge bisection, window assembly, statistics, and a resumable CSV checkpoint.
- Optimized real propagation by sharing the six-day time grid, caching station solar altitude and per-satellite illumination, and vectorizing boundary bisection. The optimized result is numerically equivalent to the prior implementation for the fixed 10-target set (408 windows; boundary differences 0 s; peak elevation difference <1.5e-11 degrees).
- Added checkpoint input/physics/ephemeris signatures, atomic CSV and metadata writes, truncation detection, target progress output, CPU/wall-clock stage timing, and independent scheduler/physical-sampling evidence.

## Historical October Evidence (superseded by the amended August period above)

- Parsed input: 10,000 unique satellites, 10 stations, priority counts 2024/3990/3986.
- TLE epochs: 2026-08-02 through 2026-08-04; planning period is 2026-10-01 through 2026-10-07 UTC. Results must retain the long-term extrapolation warning.
- The old `data/out/real_100/raw_checkpoint.csv` remains an incomplete artifact and is not scored. New validated runs are in `data/out/benchmark_real_10`, `data/out/benchmark_real_20`, `data/out/benchmark_real_50`, and `data/out/benchmark_real_100`; their reports include target IDs, data hashes, stage wall/CPU time, peak RSS, V4 scores, constraint checks, and sampled physical checks.
- Real benchmark results: 10 targets = 408 windows, V4 58 tasks / 10 covered / 260.00 score; 20 = 803 windows, V4 72 tasks / 20 covered / 298.92 score; 50 = 2,627 windows, V4 103 tasks / 48 covered / 402.08 score; 100 = 5,822 windows, V4 146 tasks / 86 covered / 559.21 score. All completed runs passed independent scheduling checks and sampled physical boundary checks. Wall-clock propagation was approximately 85 s, 121 s, 286 s, and 717 s respectively; 100-target peak RSS was 182 MB.
- These are extrapolated SGP4 results: TLE epochs are 2026-08-02 through 2026-08-04 while the planning period is 2026-10-01 through 2026-10-07. They are not a formal continuous-time orbit certification.

## Historical October Validation: V4 Quality and Earlier Scales

- Fair comparison on the exact legacy 50-target selection and the exact same current 2,973-window set: repaired V3 = 142 tasks, 49/50 covered, 458.073 points; V4 = 147 tasks, 49/50 covered, 489.217 points. Both schedules have zero current-rule violations and passed independent 1-second sampling of every task. This is a 6.8% V4 gain under the shared scorer. The legacy reported 459.223 is not the comparable figure: current re-evaluation of the V3 plan is 458.073 after physical repair.
- The comparison showed that the prior greedy scheduler tracked only the last accepted station task, so it rejected feasible earlier intervals after accepting later candidates. It now maintains ordered station and satellite timelines, inserts in feasible time gaps, and enforces the 48-hour repeat cooldown. The independent checker now validates that cooldown too.
- The 100-target schedule regenerated under the corrected scheduler has 292 tasks, 98/100 targets covered, and 902.189 points after physical repair. All tasks passed 1-second interval sampling and all schedule rules.
- The 500-target schedule used saved real propagation windows (no synthetic data): 27,320 windows, 1,388 tasks after repair, 477/500 covered, 4,130.821 points; zero schedule-rule violations and 1,388/1,388 tasks passed full interval sampling at 1-second increments. One low-priority repeat (task 479, satellite 69616) could not be shifted or reassigned without causing station conflicts and was dropped; that satellite remains covered by two other observations.
- Fair V1/V2/V3/V4 comparison on the same 50-target refined Skyfield windows is in `data/out/fair_v3_v4_50/v1_v4_common_candidates/comparison.json`: V1 time-first = 432.870 points / 48 covered; V2 global-value = 460.870 / 48; V3 fixed repaired = 458.073 / 49; V4 local search repaired = 489.217 / 49. All four schedules have zero current-rule violations and passed full task physical sampling. V1/V2 share a 30-second start grid and 120/180/240-second durations, so their candidate action set is narrower than the continuous-duration V3/V4 plans; the report marks this limitation.
- Real 1,000-target run completed with 57,300 windows; propagation 411.05 seconds; full pipeline 505.11 seconds; peak RSS 194.23 MB. The repaired V4 schedule has 2,642 tasks, 952/1,000 covered, 7,935.326 points; 1 task was dropped because no legal physical alternative was found. Remaining 2,642 tasks pass all current scheduler rules and full 1-second interval physical sampling. Artifacts are in `data/out/timeline_run_1000`.
- The full interval audit is discrete sampling, not proof of continuous-time validity or an official orbit-accuracy certification. TLE epochs are in August and the plan is in October 2026, so long-term SGP4 extrapolation uncertainty remains material.
- 500-target propagation measured 167.19 seconds wall time and the earlier measured peak RSS was about 140 MB. The corrected scheduler and physical repair were run on cached windows; propagation performance is unchanged. The latest system sample showed 3.16 GB free of 15.77 GB visible RAM. 1,000 targets passed at 194 MB peak. Linear propagation alone projects about 68.5 minutes at 10,000, with total runtime higher; 3,000 targets is the next safe measured step. Do not infer 10,000-target peak memory from the propagation-only RSS because scheduler and audit phases scale with candidate/task counts.
- Final benchmark reports distinguish `completed_pending_full_task_audit` from `completed`; only reports linked to a passing all-task audit are marked completed. The current 50/100/500 final reports are in `data/out/timeline_fixed_real_50`, `data/out/timeline_run_v2_100`, and `data/out/timeline_run_v2_500`.

## Git Identity and Checkpoint

- Current branch remains `codex/v4-scale-engine`. Both repository and global `user.name`/`user.email` are unset, and `gh` is unavailable. Existing local checkpoint commits used a generic local identity, so it is not safe to infer the requested author. New commits must wait for the user's intended name and email; no remote push or merge has occurred.

## 10000-target acceptance started (2026-10-23)

- Local data verified: 10000 unique real targets, 10 stations, priorities 2024/3990/3986. August UTC period retained.
- No 10000-target cache existed at inspection. Reuse the signature-verified 5000-target cache; propagate remaining targets only.
- 5000-target repaired artifact exists: 6324 tasks / 2891 covered / 23629.67496089333 model points; exact-endpoint final acceptance still pending for that historical run.
- Original dirty working tree and staged changes retained and backed up. No commit/push: intended Git identity is unset.
- Handoff and reproducible runner: docs/PROJECT_HANDOFF_10000.md and scripts/run_real_10000.py. Status remains in progress until final all-task audit and consistency checks pass.

- User supplied the intended local commit author during this run: Iceswing <755875603@qq.com>. Preserve the active branch and original index; create an isolated acceptance branch after validation, with no remote push.

## 10000-target August acceptance (2026-10-23)

- Completed real-data V4 run: 531432 windows; 6849 final tasks; 3117/10000 targets; model score 29443.647526047.
- Zero hard-constraint violations; all tasks passed independent one-second interval sampling including exact fractional endpoints and SGP4 status. Discrete sampling is not continuous-time certification.
- Full evidence: `data/out/real_aug2026_10000/experiment_report.json`. Official-rule and orbit-accuracy questions remain open.

- Acceptance reconciliation passed: task counts, coverage, scoring weights, fractional durations, 30-second station gaps, global 48-hour cooldown, all input/source/artifact hashes. 39/39 tests passed.
- Total actual processing time across all attempts (including controlled repair restart): 3368.657 s; peak process RSS: 805.203 MiB. Preserved cache historical propagation time is separate.
- Local acceptance author: Iceswing <755875603@qq.com>; acceptance branch `codex/v4-10000-accepted`. Active branch and original index are retained; no remote push.
- Original `.git/objects` has an explicit Windows deny ACL even after requested write access. Original staged diff SHA-256 remains 222a3ef3723e4e140194033f7ea4c2ef90d48fd9e84d098e698fcefed3efd1ba. Acceptance commit is created in an isolated local bare repository and delivered as a one-commit incremental Git bundle; original active branch/index remain untouched.

## V5 equal-budget accepted optimization (2026-10-23)

- Frozen V4: 29443.647526046665 points, 6849 tasks, 3117 targets. Original source/data/results unchanged.
- V5 best: 30682.990429547 points (+4.209%), 7658 tasks, 3822 targets, high 2024/2024.
- Same V4 start, 531432 cached windows, three seeds (11/22/33), 20/60-second optimizer caps. Every formal V5 run improved. Full hard/physical acceptance passed; 45 tests passed.
- Isolated branch codex/v5-score-engine; GitHub push not attempted. See docs/V5_HANDOFF.md and outputs/v5_results.
