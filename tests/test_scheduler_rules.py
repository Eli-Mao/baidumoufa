"""规则与调度测试：时长得分、硬约束判定、基线贪心可行性。分区：川谷（守护契约）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from satplan import config, io_schema, rules, scheduler  # noqa: E402


def make_windows() -> pd.DataFrame:
    """构造一份确定性的小窗口表，用于回归测试基线与约束。"""
    rows = [
        # 101（高优）只在 1 站可见 -> 稀缺，最该被排上
        {"station_id": 1, "sat_id": 101, "priority": "high", "priority_score": 5, "t_start_s": 0.0, "t_end_s": 300.0, "max_elev_deg": 60.0},
        # 102（高优）两站可见；1 站那个窗口与 101 冲突，用来测"机会成本"
        {"station_id": 1, "sat_id": 102, "priority": "high", "priority_score": 5, "t_start_s": 400.0, "t_end_s": 700.0, "max_elev_deg": 55.0},
        {"station_id": 2, "sat_id": 102, "priority": "high", "priority_score": 5, "t_start_s": 0.0, "t_end_s": 300.0, "max_elev_deg": 50.0},
        # 103（低优）可用但收益低
        {"station_id": 3, "sat_id": 103, "priority": "low", "priority_score": 2, "t_start_s": 1000.0, "t_end_s": 1200.0, "max_elev_deg": 40.0},
        # 104（中优）窗口只有 100 s，低于最短观测时长 -> 必须被丢弃
        {"station_id": 4, "sat_id": 104, "priority": "mid", "priority_score": 3, "t_start_s": 0.0, "t_end_s": 100.0, "max_elev_deg": 30.0},
    ]
    df = pd.DataFrame(rows)
    df.insert(0, "window_id", range(1, len(df) + 1))
    df["dur_s"] = df["t_end_s"] - df["t_start_s"]
    df["t_start_utc"] = df["t_start_s"].map(io_schema.offset_to_utc)
    df["t_end_utc"] = df["t_end_s"].map(io_schema.offset_to_utc)
    return io_schema.validate_frame(df, "windows")


def make_meta() -> pd.DataFrame:
    rows = [
        {"sat_id": 101, "name": "T-101", "priority": "high", "priority_score": 5, "tle_epoch_utc": "2026-08-03T00:00:00.000Z"},
        {"sat_id": 102, "name": "T-102", "priority": "high", "priority_score": 5, "tle_epoch_utc": "2026-08-03T00:00:00.000Z"},
        {"sat_id": 103, "name": "T-103", "priority": "low", "priority_score": 2, "tle_epoch_utc": "2026-08-03T00:00:00.000Z"},
        {"sat_id": 104, "name": "T-104", "priority": "mid", "priority_score": 3, "tle_epoch_utc": "2026-08-03T00:00:00.000Z"},
    ]
    return io_schema.validate_frame(pd.DataFrame(rows), "sat_meta")


class TestDurationScore(unittest.TestCase):
    def test_boundaries(self):
        self.assertAlmostEqual(rules.duration_score(120), 0.60, places=9)
        self.assertAlmostEqual(rules.duration_score(180), 0.80, places=9)
        self.assertAlmostEqual(rules.duration_score(240), 1.00, places=9)
        self.assertAlmostEqual(rules.duration_score(300), 0.00, places=9)
        self.assertAlmostEqual(rules.duration_score(119.9), 0.00, places=9)

    def test_task_score(self):
        self.assertAlmostEqual(rules.task_score(5, 240), 5.0, places=9)
        self.assertAlmostEqual(rules.task_score(5, 120), 3.0, places=9)


class TestConstraintChecks(unittest.TestCase):
    def setUp(self):
        self.win = make_windows()

    def _task(self, **kw):
        base = {
            "task_id": 1, "station_id": 1, "sat_id": 101, "priority": "high",
            "priority_score": 5, "t_start_s": 0.0, "t_end_s": 240.0,
            "dur_s": 240.0, "duration_score": 1.0,
        }
        base.update(kw)
        return base

    def test_valid_single_task(self):
        plan = pd.DataFrame([self._task()])
        self.assertEqual(rules.plan_violations(plan, self.win), [])
        self.assertTrue(rules.plan_is_feasible(plan, self.win))

    def test_detects_short_duration(self):
        plan = pd.DataFrame([self._task(dur_s=60.0, t_end_s=60.0)])
        types = {v["type"] for v in rules.plan_violations(plan, self.win)}
        self.assertIn("duration", types)

    def test_detects_overlap_and_switch_gap(self):
        plan = pd.DataFrame(
            [
                self._task(task_id=1, station_id=1, sat_id=101, t_start_s=0.0, t_end_s=240.0),
                self._task(task_id=2, station_id=1, sat_id=102, t_start_s=250.0, t_end_s=490.0),
            ]
        )
        types = {v["type"] for v in rules.plan_violations(plan, self.win)}
        self.assertIn("switch_time", types, "间隔 10s < 30s，应判违规")

    def test_detects_no_opportunity(self):
        # 站 5 没有任何窗口，任务落在这里就是"凭空观测"
        plan = pd.DataFrame([self._task(station_id=5)])
        types = {v["type"] for v in rules.plan_violations(plan, self.win)}
        self.assertIn("no_opportunity", types)

    def test_detects_out_of_period(self):
        plan = pd.DataFrame([self._task(t_start_s=-5.0, t_end_s=235.0)])
        types = {v["type"] for v in rules.plan_violations(plan, self.win)}
        self.assertIn("out_of_period", types)


class TestReferenceGreedy(unittest.TestCase):
    def setUp(self):
        self.win = make_windows()
        self.meta = make_meta()
        self.plan = scheduler.greedy_schedule(self.win, self.meta)

    def test_plan_satisfies_schema(self):
        io_schema.validate_frame(self.plan, "plan")

    def test_plan_is_feasible(self):
        self.assertEqual(rules.plan_violations(self.plan, self.win), [])

    def test_all_durations_in_range(self):
        self.assertTrue((self.plan["dur_s"] >= config.MIN_DUR_S).all())
        self.assertTrue((self.plan["dur_s"] <= config.MAX_DUR_S).all())

    def test_switch_gap_respected(self):
        per_station = self.plan.sort_values(["station_id", "t_start_s"]).groupby("station_id")
        for _, grp in per_station:
            ends = grp["t_end_s"].tolist()
            starts = grp["t_start_s"].tolist()
            for i in range(1, len(grp)):
                self.assertGreaterEqual(
                    starts[i] - ends[i - 1], config.SWITCH_TIME_S - 1e-9,
                    "同站相邻任务间隔必须 ≥ 切换时间",
                )

    def test_short_window_is_dropped(self):
        """104 的窗口只有 100s < 120s，不应出现在计划里。"""
        self.assertNotIn(104, set(self.plan["sat_id"]))

    def test_expected_tasks(self):
        """确定性小例子：应排上 4 条任务、覆盖 3 颗星。"""
        self.assertEqual(len(self.plan), 4)
        self.assertEqual(self.plan["sat_id"].nunique(), 3)

    def test_score_report_shape(self):
        rep = rules.score_plan(self.plan, self.win, self.meta)
        for key in ("weighted_score", "n_covered", "coverage_rate", "hi_coverage_rate", "station_utilization"):
            self.assertIn(key, rep)
        self.assertGreater(rep["weighted_score"], 0.0)
        self.assertEqual(rep["n_covered"], 3)

    def test_objective_is_finite_for_feasible_plan(self):
        val = rules.objective(self.plan, self.win, self.meta, coverage_weight=0.5)
        self.assertNotEqual(val, float("-inf"))

    def test_v4_local_search_returns_feasible_plan(self):
        improved = scheduler.local_search(self.plan, self.win, self.meta, iters=100, seed=7)
        self.assertEqual(rules.plan_violations(improved, self.win), [])
        self.assertGreaterEqual(
            rules.objective(improved, self.win, self.meta, coverage_weight=0.25),
            rules.objective(self.plan, self.win, self.meta, coverage_weight=0.25),
        )


if __name__ == "__main__":
    unittest.main()
