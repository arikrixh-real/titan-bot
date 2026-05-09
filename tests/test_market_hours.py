"""
Safe market-hours guard tests.

These tests do not scan, journal, send Telegram alerts, or create trades.
"""

from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.market_hours import IST, is_trade_window


class MarketHoursTests(unittest.TestCase):
    def test_0919_is_outside_trade_window(self):
        value = datetime(2026, 5, 4, 9, 19, tzinfo=IST)
        self.assertFalse(is_trade_window(value))

    def test_0920_is_inside_trade_window(self):
        value = datetime(2026, 5, 4, 9, 20, tzinfo=IST)
        self.assertTrue(is_trade_window(value))

    def test_1520_is_inside_trade_window(self):
        value = datetime(2026, 5, 4, 15, 20, tzinfo=IST)
        self.assertTrue(is_trade_window(value))

    def test_1521_is_outside_trade_window(self):
        value = datetime(2026, 5, 4, 15, 21, tzinfo=IST)
        self.assertFalse(is_trade_window(value))

    def test_weekend_is_outside_trade_window(self):
        value = datetime(2026, 5, 9, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        self.assertFalse(is_trade_window(value))


if __name__ == "__main__":
    unittest.main()
