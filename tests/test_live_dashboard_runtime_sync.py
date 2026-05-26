import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_status
import scanner_filter_truth
from utils.market_hours import IST


class LiveDashboardRuntimeSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.data = self.root / "data"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.data.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 30, tzinfo=IST)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_json(self, path, payload):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _paths(self):
        return {
            "scanner_status_path": self.runtime / "scanner_status.json",
            "scan_selection_state_path": self.data / "scan_selection_state.json",
            "setup_engine_status_path": self.runtime / "setup_engine_status.json",
            "output_path": self.runtime / "scanner_filter_truth_status.json",
        }

    def _patch_truth_paths(self):
        return patch.multiple(
            scanner_filter_truth,
            SCANNER_PREVIOUS_SIGNATURE_PATH=self.runtime / "scanner_previous_signature.json",
            SIGNAL_PATH_DIAGNOSTICS_PATH=self.runtime / "signal_path_diagnostics.json",
            DASHBOARD_TRUTH_REGISTRY_PATH=self.runtime / "dashboard_truth_registry.json",
            TRADE_LIFECYCLE_HEALTH_PATH=self.runtime / "trade_lifecycle_health.json",
            MASTER_BRAIN_RUNTIME_HEALTH_PATH=self.runtime / "master_brain_runtime_health.json",
            SETUP_ENGINE_RUNTIME_HEALTH_PATH=self.runtime / "setup_engine_runtime_health.json",
            RUNTIME_FALLBACK_RESOLUTION_PATH=self.runtime / "runtime_fallback_resolution.json",
            LIVE_SCANNER_SYNC_AUDIT_PATH=self.runtime / "live_scanner_sync_audit.json",
        )

    def test_market_hours_scan_cycle_advances_and_publishes_authoritative_cycle(self):
        paths = self._paths()
        ts = self.now.isoformat()
        self._write_json(
            paths["scanner_status_path"],
            {
                "timestamp_ist": ts,
                "scanner_cycle_id": "cycle-2",
                "stocks_checked": 50,
                "trend_passed_count": 8,
                "momentum_passed_count": 5,
                "structure_passed_count": 3,
                "breakout_ready_count": 2,
                "final_passed_count": 1,
            },
        )
        self._write_json(paths["scan_selection_state_path"], {"selected_symbols_count": 50})
        with self._patch_truth_paths():
            status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)

        self.assertEqual(status["authoritative_scan_cycle_id"], "cycle-2")
        self.assertEqual(status["dashboard_scan_sync_status"], "SYNCHRONIZED")
        self.assertEqual(status["scanner_publication_health"], "HEALTHY")
        self.assertEqual(status["market_hours_runtime_sync"], "PASS")

    def test_dashboard_preserves_previous_valid_cycle_during_brief_zero_refresh_gap(self):
        paths = self._paths()
        previous_ts = (self.now - timedelta(seconds=30)).isoformat()
        self._write_json(
            paths["output_path"],
            {
                "authoritative_scan_cycle_id": "cycle-good",
                "authoritative_scan_timestamp": previous_ts,
                "authoritative_counters": {
                    "stocks_checked": 50,
                    "trend_passed": 9,
                    "momentum_passed": 6,
                    "structure_passed": 4,
                    "breakout_ready": 2,
                    "final_passed": 1,
                    "alerts_this_scan": 0,
                },
            },
        )
        self._write_json(
            paths["scanner_status_path"],
            {
                "timestamp_ist": self.now.isoformat(),
                "scanner_cycle_id": "cycle-zero",
                "stocks_checked": 50,
                "trend_passed_count": 0,
                "momentum_passed_count": 0,
                "structure_passed_count": 0,
                "breakout_ready_count": 0,
                "final_passed_count": 0,
            },
        )
        with self._patch_truth_paths():
            status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)

        self.assertTrue(status["zero_overwrite_detected"])
        self.assertTrue(status["preserved_previous_valid_cycle"])
        self.assertEqual(status["authoritative_scan_cycle_id"], "cycle-zero")
        self.assertEqual(status["preserved_counter_cycle_id"], "cycle-good")
        self.assertEqual(status["counters"]["trend_passed"], 9)
        self.assertEqual(status["dashboard_scan_sync_status"], "PRESERVED_DURING_REFRESH_GAP")

    def test_scanner_pipeline_unavailable_is_explicit_instead_of_fake_zeros(self):
        paths = self._paths()
        self._write_json(paths["scanner_status_path"], {"timestamp_ist": self.now.isoformat(), "scanner_cycle_id": "cycle-empty"})
        with self._patch_truth_paths():
            status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)

        self.assertTrue(status["scan_pipeline_unavailable"])
        self.assertEqual(status["recommended_dashboard_display_mode"], "SCAN_PIPELINE_UNAVAILABLE")
        self.assertEqual(status["dashboard_scan_sync_status"], "SCAN_PIPELINE_UNAVAILABLE")
        self.assertEqual(status["counter_confidence"], "UNKNOWN")

    def test_market_hours_fallback_standby_cannot_mask_live_runtime(self):
        paths = self._paths()
        self._write_json(
            paths["scanner_status_path"],
            {
                "timestamp_ist": self.now.isoformat(),
                "scanner_cycle_id": "cycle-fallback",
                "scan_only": True,
                "fallback_reason": "MASTER_BRAIN_UNAVAILABLE",
                "stocks_checked": 50,
                "trend_passed_count": 4,
                "momentum_passed_count": 2,
                "structure_passed_count": 1,
                "breakout_ready_count": 1,
            },
        )
        self._write_json(self.runtime / "runtime_fallback_resolution.json", {"fallback_truthfulness": "OFF_HOURS_RESEARCH_STANDBY", "fallback_active": False})
        with self._patch_truth_paths():
            status = scanner_filter_truth.build_scanner_filter_truth_status(now=self.now, **paths)

        self.assertFalse(status["off_hours_runtime_continuity"])
        self.assertNotEqual(status["recommended_dashboard_display_mode"], "off_hours_research_standby")
        self.assertIn("fallback_mode_counter_reliability_low", status["warnings"])

    def test_runtime_status_exposes_shared_canonical_runtime_and_trade_sync_fields(self):
        scanner_truth = {
            "authoritative_scan_cycle_id": "cycle-7",
            "dashboard_scan_sync_status": "SYNCHRONIZED",
            "market_hours_runtime_sync": "PASS",
            "scanner_publication_health": "HEALTHY",
            "counter_confidence": "HIGH",
        }
        lifecycle = {"overall_status": "PASS", "open_trades_count": 2, "dashboard_mismatch": False, "unresolved_eod_trades_count": 0}
        with patch.object(runtime_status, "_authoritative_runtime_health_summary", return_value={}), \
            patch.object(runtime_status, "_market_data_health_summary", return_value={}), \
            patch.object(runtime_status, "_runtime_topology_summary", return_value={}), \
            patch.object(runtime_status, "build_canonical_runtime_mode", return_value={}), \
            patch.object(runtime_status, "build_runtime_warning_resolution_status", return_value={}), \
            patch.object(runtime_status, "_master_brain_runtime_health_summary", return_value={}), \
            patch.object(runtime_status, "_setup_engine_runtime_health_summary", return_value={}), \
            patch.object(runtime_status, "_runtime_fallback_resolution_summary", return_value={}), \
            patch.object(runtime_status, "_scanner_filter_truth_summary", return_value=scanner_truth), \
            patch.object(runtime_status, "_trade_lifecycle_health_summary", return_value=lifecycle), \
            patch.object(runtime_status, "_read_json_safe", return_value={}), \
            patch.object(runtime_status, "_historical_replay_status_summary", return_value={}), \
            patch.object(runtime_status, "_phase39_research_memory_observatory", return_value={}), \
            patch.object(runtime_status, "_phase_status_summaries", return_value={}):
            status = runtime_status.build_runtime_status(self.now)

        self.assertEqual(status["canonical_scan_cycle"], "cycle-7")
        self.assertEqual(status["dashboard_runtime_sync_health"], "SYNCHRONIZED")
        self.assertEqual(status["dashboard_trade_sync_health"], "PASS")
        self.assertEqual(status["lifecycle_sync_status"], "SYNCHRONIZED")
        self.assertEqual(status["performance_sync_status"], "SYNCHRONIZED")
        self.assertEqual(status["dashboard_scan_truth"]["authoritative_scan_cycle_id"], "cycle-7")
        self.assertFalse(status["safety_flags"]["broker_mutation"] if "safety_flags" in status else False)


if __name__ == "__main__":
    unittest.main()
