"""契约层测试：Alpha-5 解码、列名校验、时间辅助。分区：川谷。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from satplan import io_schema  # noqa: E402
from satplan.io_schema import SchemaError  # noqa: E402


class TestAlpha5(unittest.TestCase):
    def test_plain_digits(self):
        self.assertEqual(io_schema.decode_satnum("50574"), 50574)
        self.assertEqual(io_schema.decode_satnum("00046"), 46)

    def test_alpha5_letters(self):
        # A = 10 -> 10*10000 + 45
        self.assertEqual(io_schema.decode_satnum("A0045"), 100045)
        # T = 27 -> 27*10000 + 288
        self.assertEqual(io_schema.decode_satnum("T0288"), 270288)

    def test_roundtrip(self):
        for sat_id in (50574, 100045, 270288, 339999):
            self.assertEqual(io_schema.decode_satnum(io_schema.encode_satnum(sat_id)), sat_id)

    def test_rejects_garbage(self):
        for bad in ("", "I0001", "O0001", "AB123", "X12"):
            with self.assertRaises(SchemaError):
                io_schema.decode_satnum(bad)


class TestValidation(unittest.TestCase):
    def _plan(self, **overrides):
        base = {
            "task_id": [1, 2],
            "station_id": [1, 2],
            "sat_id": [101, 102],
            "priority": ["high", "low"],
            "priority_score": [5, 2],
            "t_start_s": [0.0, 100.0],
            "t_end_s": [240.0, 320.0],
            "dur_s": [240.0, 220.0],
            "duration_score": [1.0, 0.9333],
        }
        base.update(overrides)
        return pd.DataFrame(base)

    def test_accepts_valid(self):
        io_schema.validate_frame(self._plan(), "plan")

    def test_detects_missing_column(self):
        df = self._plan().drop(columns=["dur_s"])
        with self.assertRaises(SchemaError) as ctx:
            io_schema.validate_frame(df, "plan")
        self.assertIn("dur_s", str(ctx.exception))

    def test_detects_wrong_type(self):
        df = self._plan()
        df["t_start_s"] = df["t_start_s"].astype(str)
        with self.assertRaises(SchemaError):
            io_schema.validate_frame(df, "plan")

    def test_detects_null_required(self):
        df = self._plan()
        df.loc[0, "priority"] = None
        with self.assertRaises(SchemaError):
            io_schema.validate_frame(df, "plan")

    def test_rejects_unknown_schema(self):
        with self.assertRaises(SchemaError):
            io_schema.validate_frame(self._plan(), "不存在")


class TestTimeHelpers(unittest.TestCase):
    def test_roundtrip_utc(self):
        dt = io_schema.parse_utc("2026-08-03T00:00:00Z")
        self.assertEqual(io_schema.to_utc_str(dt), "2026-08-03T00:00:00.000Z")

    def test_offset(self):
        # 相对 t0（config.PLAN_T0_UTC = 2026-08-01T00:00:00Z）的秒 -> ISO8601
        self.assertEqual(io_schema.offset_to_utc(3661.5), "2026-08-01T01:01:01.500Z")

    def test_rejects_bad_format(self):
        with self.assertRaises(SchemaError):
            io_schema.parse_utc("2026/08/03 00:00")


if __name__ == "__main__":
    unittest.main()
