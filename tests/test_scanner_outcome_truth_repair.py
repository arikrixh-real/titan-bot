import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import scanner_filter_truth
import trade_lifecycle_health
from utils.market_hours import IST


class ScannerOutcomeTruthRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.data_dir = self.root / "data"
        self.journal_dir = self.data_dir / "journals"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 16, 0, tzinfo=IST)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _write_active_trades(self, rows):
        path = self.journal_dir / "active_trades.csv"
        fields = [
            "trade_id",
            "opened_at",
            "scan_id",
            "symbol",
            "side",
            "entry",
            "sl",
            "target",
            "status",
            "outcome",
            "result",
            "last_checked_at",
            "result_reason",
        ]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _write_outcomes(self, rows=None):
        path = self.journal_dir / "trade_outcomes.csv"
        fields = ["closed_at", "trade_id", "symbol", "side", "outcome", "result"]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows or [])
        return path

    def _scanner_paths(self):
        return {
            "scanner_status_path": self.runtime_dir / "scanner_status.json",
            "scan_selection_state_path": self.data_dir / "scan_selection_state.json",
            "setup_engine_status_path": self.runtime_dir / "setup_engine_status.json",
            "output_path": self.runtime_dir / "scanner_filter_truth_status.json",
        }

    def test_identical_copied_counters_are_detected(self):
        paths = self._scanner_paths()
        ts = self.now.isoformat()
        self._write_json(
            paths["scanner_status_path"],
            {
                "timestamp_ist": ts,
                "scanner_cycle_id": "cycle-1",
                "stocks_checked": 50,
                "trend_passed": 1,
                "momentum_passed": 1,
                "structure_passed": 1,
                "breakout_ready_count": 1,
                "final_passed": 1,
            },
        )
        self._write_json(paths["scan_selection_state_path"], {"selected_symbols_count": 50, "timestamp": ts})
        self._write_json(paths["setup_engine_status_path"], {"final_passed": 1, "timestamp_ist": ts})

        status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)

        self.assertTrue(status["identical_counter_warning"])
        self.assertEqual(status["counter_confidence"], "LOW")

    def test_frozen_scan_cycle_detected(self):
        paths = self._scanner_paths()
        ts = self.now.isoformat()
        self._write_json(
            paths["scanner_status_path"],
            {
                "timestamp_ist": ts,
                "scanner_cycle_id": "cycle-current",
                "data_signature": "same",
                "repeated_data_signature": True,
                "stocks_checked": 50,
                "trend_passed": 10,
                "momentum_passed": 5,
                "structure_passed": 3,
                "breakout_ready_count": 2,
                "final_passed": 1,
            },
        )
        with patch.object(scanner_filter_truth, "SCANNER_PREVIOUS_SIGNATURE_PATH", self.runtime_dir / "scanner_previous_signature.json"):
            self._write_json(scanner_filter_truth.SCANNER_PREVIOUS_SIGNATURE_PATH, {"scanner_cycle_id": "cycle-old", "data_signature": "same"})
            status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)

        self.assertTrue(status["frozen_counter_warning"])

    def test_fallback_counters_are_low_confidence_not_fake_precise(self):
        paths = self._scanner_paths()
        ts = self.now.isoformat()
        self._write_json(
            paths["scanner_status_path"],
            {
                "timestamp_ist": ts,
                "scanner_cycle_id": "cycle-1",
                "scan_only": True,
                "fallback_reason": "OHLC_STALE",
                "stocks_checked": 50,
                "trend_passed": 0,
            },
        )

        status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)

        self.assertEqual(status["counter_confidence"], "LOW")
        self.assertEqual(status["recommended_dashboard_display_mode"], "low_confidence_fallback")
        self.assertIsNone(status["counters"]["final_passed"])

    def test_independent_counters_are_preserved_when_present(self):
        paths = self._scanner_paths()
        ts = self.now.isoformat()
        self._write_json(
            paths["scanner_status_path"],
            {
                "timestamp_ist": ts,
                "scanner_cycle_id": "cycle-1",
                "stocks_checked": 50,
                "trend_passed_count": 12,
                "momentum_passed_count": 6,
                "structure_passed_count": 4,
                "breakout_ready_count": 2,
                "final_passed_count": 1,
                "alerts_this_scan": 0,
            },
        )

        status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)

        self.assertEqual(status["counters"]["trend_passed"], 12)
        self.assertEqual(status["counters"]["momentum_passed"], 6)
        self.assertEqual(status["counters"]["structure_passed"], 4)
        self.assertEqual(status["counters"]["final_passed"], 1)
        self.assertEqual(status["counter_confidence"], "HIGH")

    def test_stale_open_and_eod_unresolved_trades_detected(self):
        opened = (self.now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        active = self._write_active_trades(
            [
                {
                    "trade_id": "T1",
                    "opened_at": opened,
                    "symbol": "ABC",
                    "side": "LONG",
                    "entry": "100",
                    "sl": "95",
                    "target": "110",
                    "status": "OPEN",
                }
            ]
        )
        outcomes = self._write_outcomes()

        status = trade_lifecycle_health.build_trade_lifecycle_health(
            now=self.now,
            active_trades_path=active,
            outcomes_path=outcomes,
            output_path=self.runtime_dir / "trade_lifecycle_health.json",
        )

        self.assertEqual(status["open_trades_count"], 1)
        self.assertEqual(status["stale_open_trades_count"], 1)
        self.assertEqual(status["unresolved_eod_trades_count"], 1)
        self.assertEqual(status["unresolved_trades"][0]["lifecycle_status"], "EOD_UNRESOLVED")

    def test_dashboard_live_trade_mismatch_detected(self):
        active = self._write_active_trades(
            [
                {
                    "trade_id": "T1",
                    "opened_at": self.now.isoformat(),
                    "symbol": "ABC",
                    "side": "LONG",
                    "entry": "100",
                    "sl": "95",
                    "target": "110",
                    "status": "OPEN",
                    "last_checked_at": self.now.isoformat(),
                }
            ]
        )
        outcomes = self._write_outcomes()
        self._write_json(
            self.runtime_dir / "titan_runtime_status.json",
            {"dashboard_trade_truth": {"live_trades_count": 0}},
        )

        with patch.object(trade_lifecycle_health, "RUNTIME_DIR", self.runtime_dir):
            status = trade_lifecycle_health.build_trade_lifecycle_health(
                now=self.now,
                active_trades_path=active,
                outcomes_path=outcomes,
                output_path=self.runtime_dir / "trade_lifecycle_health.json",
            )

        self.assertTrue(status["dashboard_mismatch"])

    def test_no_mutation_flags_enabled(self):
        paths = self._scanner_paths()
        self._write_json(paths["scanner_status_path"], {"timestamp_ist": self.now.isoformat(), "stocks_checked": 1})
        scanner_status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)
        trade_status = trade_lifecycle_health.build_trade_lifecycle_health(
            now=self.now,
            active_trades_path=self._write_active_trades([]),
            outcomes_path=self._write_outcomes(),
            output_path=self.runtime_dir / "trade_lifecycle_health.json",
        )

        for payload in (scanner_status, trade_status):
            self.assertTrue(payload["safety_flags"]["advisory_only"])
            self.assertFalse(payload["safety_flags"]["affects_execution"])
            self.assertFalse(payload["safety_flags"]["affects_live_ranking"])
            self.assertFalse(payload["safety_flags"]["broker_mutation"])
            self.assertFalse(payload["safety_flags"]["telegram_mutation"])
            self.assertFalse(payload["safety_flags"]["supabase_mutation"])


if __name__ == "__main__":
    unittest.main()
