"""原始数据契约测试（需要 data/raw 就位；缺失则跳过）。分区：川谷。

    py -3 scripts/prepare_raw_data.py   # 先准备数据
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satplan import config, io_schema  # noqa: E402

_RAW_READY = (
    config.RAW_TLE_FILE.exists()
    and config.RAW_STATION_FILE.exists()
    and all(p.exists() for p in config.RAW_PRIORITY_FILES.values())
)


@unittest.skipUnless(_RAW_READY, "原始数据未就位，先跑 scripts/prepare_raw_data.py")
class TestRawData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stations = io_schema.read_stations_raw()
        cls.tle = io_schema.read_tle_raw()
        cls.priority = io_schema.read_priority_raw()
        cls.meta = io_schema.build_sat_meta(cls.tle, cls.priority)

    def test_stations(self):
        self.assertEqual(len(self.stations), len(config.STATION_IDS))
        self.assertEqual(sorted(self.stations["station_id"]), list(config.STATION_IDS))
        self.assertTrue((self.stations["min_elev_deg"] == config.MIN_ELEV_DEG).all())
        self.assertTrue((self.stations["max_elev_deg"] == config.MAX_ELEV_DEG).all())

    def test_tle_unique(self):
        self.assertEqual(len(self.tle), 10000)
        self.assertEqual(self.tle["sat_id"].nunique(), 10000)

    def test_alpha5_satellites_present(self):
        """108 颗 Alpha-5 编号的星必须被正确解码，否则会静默丢失。"""
        alpha5 = self.tle.loc[~self.tle["satnum_raw"].str.isdigit()]
        self.assertEqual(len(alpha5), 108, "Alpha-5 卫星数量与实测不符，检查 decode_satnum")
        self.assertTrue((alpha5["sat_id"] > 99999).all())

    def test_priority_counts(self):
        self.assertEqual(len(self.priority["high"]), 2024)
        self.assertEqual(len(self.priority["mid"]), 3990)
        self.assertEqual(len(self.priority["low"]), 3986)

    def test_sat_meta_join_is_perfect(self):
        """TLE 与优先级表必须 1:1 对齐，零缺失、零重叠。"""
        self.assertEqual(len(self.meta), 10000)
        self.assertFalse(self.meta["priority"].isna().any())
        expected = sum(len(v) for v in self.priority.values())
        self.assertEqual(expected, 10000)
        counts = self.meta["priority"].value_counts().to_dict()
        self.assertEqual(counts, {"mid": 3990, "low": 3986, "high": 2024})

    def test_priority_score_mapping(self):
        for level, score in config.PRIORITY_SCORE.items():
            sub = self.meta[self.meta["priority"] == level]
            self.assertTrue((sub["priority_score"] == score).all(), f"{level} 权重映射错误")

    def test_tle_epoch_is_iso_utc(self):
        epoch = io_schema.parse_utc(self.meta["tle_epoch_utc"].iloc[0])
        self.assertIsNotNone(epoch.tzinfo)
        self.assertEqual(epoch.year, 2026)


if __name__ == "__main__":
    unittest.main()
