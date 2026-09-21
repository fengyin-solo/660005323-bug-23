"""统计口径测试：python -m unittest app.tests.test_statistics -v"""
import os
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 在导入 config 前固定 .env 为默认口径，保证测试不依赖本机文件
os.environ["STAT_SHIFT_START_HOURS"] = "0,8,16"
os.environ["STAT_SAMPLE_INTERVAL"] = "1"
os.environ["STAT_RETENTION_SECONDS"] = "60"

from app import config, statistics  # noqa: E402


class TestDefaultsMatchLegacy(unittest.TestCase):
    def test_defaults_are_legacy_values(self):
        # 改造前：sleep(1)、[-60:] 60 个采样点、无班次（隐含 0 点归零）
        self.assertEqual(config.SHIFT_START_HOURS, [0, 8, 16])
        self.assertEqual(config.SAMPLE_INTERVAL, 1.0)
        self.assertEqual(config.RETENTION_SECONDS, 60.0)

    def test_oee_formula_matches_legacy(self):
        # 对照改造前 main.py 的内联公式
        uptime, prod, faults, quality = 10.0, 3, 1, 0.97
        availability = min(1.0, uptime / max(1, uptime + faults))
        performance = min(1.0, prod / max(1, uptime / 2))
        legacy = round(availability * performance * quality * 100, 1)
        self.assertEqual(statistics.oee_for_device(uptime, prod, faults, quality), legacy)
        self.assertEqual(statistics.oee_for_device(0, 5, 0, 0.9), 0.0)

    def test_retention_window_equivalent_to_60_points(self):
        now = 1000.0
        # 1s 采样下，保留 60s == 改造前 production_log[-60:]
        log = [{"timestamp": now - i, "count": i} for i in range(120, 0, -1)]
        kept = statistics.filter_retention(log, now, retention_seconds=60)
        self.assertEqual(len(kept), 60)
        self.assertGreaterEqual(min(r["timestamp"] for r in kept), now - 60)


class TestShiftBoundary(unittest.TestCase):
    def test_shift_index_default_boundaries(self):
        def ts_at(hour):
            return datetime(2026, 9, 21, hour, 0, 0).timestamp()

        self.assertEqual(statistics.shift_index(ts_at(0)), 0)
        self.assertEqual(statistics.shift_index(ts_at(3)), 0)
        self.assertEqual(statistics.shift_index(ts_at(8)), 1)
        self.assertEqual(statistics.shift_index(ts_at(15)), 1)
        self.assertEqual(statistics.shift_index(ts_at(16)), 2)
        self.assertEqual(statistics.shift_index(ts_at(23)), 2)

    def test_overnight_shift(self):
        def ts_at(hour):
            return datetime(2026, 9, 21, hour, 0, 0).timestamp()

        # 边界不含 0 点时，凌晨归属前一天开始的夜班
        self.assertEqual(statistics.shift_index(ts_at(2), [8, 16, 22]), 2)
        self.assertEqual(statistics.shift_index(ts_at(9), [8, 16, 22]), 0)

    def test_current_shift_start_ts(self):
        t = datetime(2026, 9, 21, 10, 30, 0).timestamp()
        shift = statistics.current_shift(t)
        self.assertEqual(shift["start_hour"], 8)
        self.assertEqual(shift["end_hour"], 16)
        self.assertEqual(datetime.fromtimestamp(shift["start_ts"]).hour, 8)


class TestConfigParsing(unittest.TestCase):
    def test_invalid_shift_hours_raises(self):
        from app.config import _parse_shift_hours
        with self.assertRaises(ValueError):
            _parse_shift_hours("0,xx,16")
        with self.assertRaises(ValueError):
            _parse_shift_hours("0,24")
        with self.assertRaises(ValueError):
            _parse_shift_hours("")

    def test_sorted_dedup(self):
        from app.config import _parse_shift_hours
        self.assertEqual(_parse_shift_hours("16,8,8,0"), [0, 8, 16])


if __name__ == "__main__":
    unittest.main()
