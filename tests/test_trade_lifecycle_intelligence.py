"""
Offline tests for TITAN Phase 7 trade lifecycle intelligence.

These tests do not send Telegram alerts, change alert caps, call broker APIs,
or alter TP/SL/RR/outcome behavior.
"""

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from engines import trade_lifecycle_intelligence as lifecycle


def sample_long_trade():
    return {
        "trade_id": "T1",
        "scan_id": "S1",
        "symbol": "RELIANCE",
        "side": "LONG",
        "entry": "100",
        "sl": "95",
        "target": "110",
        "rr": "2.0",
        "score": "3.0",
        "status": "OPEN",
        "opened_at": "2026-05-04 10:00:00",
    }


class TradeLifecycleIntelligenceTests(unittest.TestCase):
    def test_observation_calculates_health_and_excursions_without_mutating_trade(self):
        row = sample_long_trade()
        before = dict(row)

        observation = lifecycle.observe_trade_lifecycle(
            row,
            live_price=104,
            outcome_status="OPEN",
            observed_at=datetime(2026, 5, 4, 10, 30, tzinfo=lifecycle.IST),
        )

        self.assertEqual(row, before)
        self.assertEqual(observation["trade_health_score"], 97.0)
        self.assertEqual(observation["current_favorable_excursion"], 4.0)
        self.assertEqual(observation["current_adverse_excursion"], 0.0)
        self.assertEqual(observation["distance_to_tp"], 6.0)
        self.assertEqual(observation["distance_to_sl"], 9.0)
        self.assertEqual(observation["post_entry_momentum_status"], "STRONG_FOLLOW_THROUGH")
        self.assertFalse(observation["setup_decay_warning"])
        self.assertEqual(observation["invalidation_warning"], "")

    def test_short_trade_mae_and_distance_are_directional(self):
        row = {
            **sample_long_trade(),
            "trade_id": "T2",
            "symbol": "ONGC",
            "side": "SHORT",
            "entry": "100",
            "sl": "105",
            "target": "90",
        }

        observation = lifecycle.observe_trade_lifecycle(
            row,
            live_price=103,
            outcome_status="OPEN",
            observed_at=datetime(2026, 5, 4, 10, 30, tzinfo=lifecycle.IST),
        )

        self.assertEqual(observation["current_favorable_excursion"], 0.0)
        self.assertEqual(observation["current_adverse_excursion"], 3.0)
        self.assertEqual(observation["distance_to_tp"], 13.0)
        self.assertEqual(observation["distance_to_sl"], 2.0)
        self.assertEqual(observation["post_entry_momentum_status"], "WEAKENING")

    def test_memory_writer_tracks_mfe_mae_and_report_fails_open(self):
        old_memory_path = lifecycle.MEMORY_PATH
        old_report_path = lifecycle.REPORT_PATH
        old_refresh = lifecycle.REPORT_REFRESH_SECONDS

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lifecycle.MEMORY_PATH = tmp_path / "memory" / "lifecycle_memory.json"
            lifecycle.REPORT_PATH = tmp_path / "reports" / "lifecycle_shadow_report.txt"
            lifecycle.REPORT_REFRESH_SECONDS = -1

            obs1 = lifecycle.observe_trade_lifecycle(sample_long_trade(), 102, "OPEN")
            obs2 = lifecycle.observe_trade_lifecycle(sample_long_trade(), 94, "SL")
            result = lifecycle.update_lifecycle_memory_safely([obs1, obs2])

            self.assertEqual(result["updated"], 2)
            data = lifecycle._load_memory()
            tracked = data["trade_lifecycle"]["T1"]
            self.assertEqual(tracked["max_favorable_excursion"], 2.0)
            self.assertEqual(tracked["max_adverse_excursion"], 6.0)
            self.assertTrue(lifecycle.REPORT_PATH.exists())

            lifecycle.REPORT_PATH = tmp_path
            fail_result = lifecycle.write_lifecycle_report_safely(data, force=True)
            self.assertIn("error", fail_result)

        lifecycle.MEMORY_PATH = old_memory_path
        lifecycle.REPORT_PATH = old_report_path
        lifecycle.REPORT_REFRESH_SECONDS = old_refresh

    def test_safe_observer_fails_open(self):
        self.assertIsNone(lifecycle.observe_trade_lifecycle_safely(sample_long_trade(), live_price=""))

    def test_observer_does_not_fetch_live_price(self):
        source = Path(PROJECT_ROOT / "engines" / "trade_lifecycle_intelligence.py").read_text(encoding="utf-8")
        self.assertNotIn("get_live_price(", source)
        self.assertNotIn("requests.", source)


if __name__ == "__main__":
    unittest.main()
