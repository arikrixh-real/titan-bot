import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_engine_health
import runtime_fallback_resolver
import scanner_filter_truth
from utils.market_hours import IST


class MasterSetupRuntimeStabilizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
        self.off_hours = datetime(2026, 5, 25, 16, 0, tzinfo=IST)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_json(self, path, payload):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_fresh_master_brain_removes_unavailable_state(self):
        path = self.runtime / "master_brain_status.json"
        out = self.runtime / "master_brain_runtime_health.json"
        self._write_json(path, {"timestamp_ist": self.now.isoformat(), "status": "MASTER_BRAIN_READ_ONLY_COMPLETE", "runtime_mode": "READ_ONLY"})

        result = runtime_engine_health.build_master_brain_runtime_health(now=self.now, status_path=path, output_path=out)

        self.assertEqual(result["master_brain_runtime_health"], "ACTIVE")
        self.assertEqual(result["master_brain_freshness_confidence"], "HIGH")

    def test_fresh_setup_engine_removes_unavailable_state(self):
        path = self.runtime / "setup_engine_status.json"
        out = self.runtime / "setup_engine_runtime_health.json"
        self._write_json(path, {"timestamp_ist": self.now.isoformat(), "status": "SETUP_ENGINE_MARKER_UPDATED", "mode": "MARKET_MODE"})

        result = runtime_engine_health.build_setup_engine_runtime_health(now=self.now, status_path=path, output_path=out)

        self.assertEqual(result["setup_runtime_health"], "ACTIVE")
        self.assertEqual(result["setup_freshness_confidence"], "HIGH")

    def test_stale_state_transitions_to_stale_low_confidence(self):
        path = self.runtime / "master_brain_status.json"
        out = self.runtime / "master_brain_runtime_health.json"
        stale = self.now - timedelta(minutes=30)
        self._write_json(path, {"timestamp_ist": stale.isoformat(), "status": "MASTER_BRAIN_READ_ONLY_COMPLETE"})

        result = runtime_engine_health.build_master_brain_runtime_health(now=self.now, status_path=path, output_path=out)

        self.assertEqual(result["master_brain_runtime_health"], "STALE")
        self.assertEqual(result["master_brain_freshness_confidence"], "LOW")

    def test_fallback_resolver_distinguishes_stale_false_fallback(self):
        paths = self._resolver_paths()
        self._write_json(paths["master_status"], {"timestamp_ist": self.now.isoformat(), "status": "MASTER_BRAIN_READ_ONLY_COMPLETE", "runtime_mode": "READ_ONLY"})
        self._write_json(paths["setup_status"], {"timestamp_ist": self.now.isoformat(), "status": "SETUP_ENGINE_MARKER_UPDATED"})
        self._write_json(paths["scanner"], {"timestamp_ist": (self.now - timedelta(minutes=30)).isoformat(), "scan_only": True, "fallback_reason": "MASTER_BRAIN_UNAVAILABLE"})
        self._write_json(paths["scanner_truth"], {"stale_snapshot_warning": True, "counter_confidence": "LOW"})

        with self._patch_resolver_paths(paths):
            result = runtime_fallback_resolver.run_runtime_fallback_resolution(now=self.now, output_path=paths["resolution"])

        self.assertEqual(result["fallback_truthfulness"], "STALE_FALSE_FALLBACK")
        self.assertEqual(result["scanner_confidence"], "MEDIUM")

    def test_fallback_resolver_keeps_low_when_engine_actually_stale(self):
        paths = self._resolver_paths()
        stale = self.now - timedelta(minutes=30)
        self._write_json(paths["master_status"], {"timestamp_ist": stale.isoformat(), "status": "MASTER_BRAIN_READ_ONLY_COMPLETE"})
        self._write_json(paths["setup_status"], {"timestamp_ist": self.now.isoformat(), "status": "SETUP_ENGINE_MARKER_UPDATED"})
        self._write_json(paths["scanner"], {"timestamp_ist": self.now.isoformat(), "scan_only": True, "fallback_reason": "MASTER_BRAIN_UNAVAILABLE"})
        self._write_json(paths["scanner_truth"], {"stale_snapshot_warning": False, "counter_confidence": "LOW"})

        with self._patch_resolver_paths(paths):
            result = runtime_fallback_resolver.run_runtime_fallback_resolution(now=self.now, output_path=paths["resolution"])

        self.assertEqual(result["fallback_truthfulness"], "ENGINE_UNAVAILABLE")
        self.assertEqual(result["scanner_confidence"], "LOW")

    def test_off_hours_daemon_alive_turns_stale_engines_into_standby(self):
        paths = self._resolver_paths()
        stale = self.off_hours - timedelta(minutes=45)
        self._write_json(paths["master_status"], {"timestamp_ist": stale.isoformat(), "status": "MASTER_BRAIN_READ_ONLY_COMPLETE"})
        self._write_json(paths["setup_status"], {"timestamp_ist": stale.isoformat(), "status": "SETUP_ENGINE_MARKER_UPDATED"})
        self._write_json(paths["scanner"], {
            "timestamp_ist": stale.isoformat(),
            "scan_only": True,
            "fallback_reason": "MASTER_BRAIN_UNAVAILABLE|SETUP_ENGINE_UNAVAILABLE",
        })
        self._write_json(paths["scanner_truth"], {"stale_snapshot_warning": True, "counter_confidence": "LOW"})
        self._write_json(paths["daemon"], {"timestamp_ist": self.off_hours.isoformat(), "status": "RUNNING", "pid": 1234})

        with self._patch_resolver_paths(paths):
            result = runtime_fallback_resolver.run_runtime_fallback_resolution(now=self.off_hours, output_path=paths["resolution"])

        self.assertTrue(result["off_hours_runtime_continuity"])
        self.assertEqual(result["master_brain_runtime_health"]["master_brain_runtime_health"], "RESEARCH_ACTIVE")
        self.assertEqual(result["setup_engine_runtime_health"]["setup_runtime_health"], "OFF_HOURS_STANDBY")
        self.assertEqual(result["setup_engine_runtime_health"]["setup_pipeline_health"], "OFF_HOURS_STANDBY")
        self.assertEqual(result["fallback_truthfulness"], "OFF_HOURS_RESEARCH_STANDBY")
        self.assertFalse(result["fallback_active"])
        self.assertEqual(result["fallback_severity"], "LOW")
        self.assertEqual(result["scanner_confidence"], "MEDIUM")
        self.assertNotEqual(result["fallback_truthfulness"], "ENGINE_UNAVAILABLE")
        self.assertFalse(result["safety_flags"]["broker_mutation"])
        self.assertFalse(result["safety_flags"]["telegram_mutation"])
        self.assertFalse(result["safety_flags"]["supabase_mutation"])
        self.assertFalse(result["safety_flags"]["affects_execution"])
        self.assertFalse(result["safety_flags"]["affects_live_ranking"])

    def test_market_hours_stale_engines_still_warn(self):
        paths = self._resolver_paths()
        stale = self.now - timedelta(minutes=45)
        self._write_json(paths["master_status"], {"timestamp_ist": stale.isoformat(), "status": "MASTER_BRAIN_READ_ONLY_COMPLETE"})
        self._write_json(paths["setup_status"], {"timestamp_ist": stale.isoformat(), "status": "SETUP_ENGINE_MARKER_UPDATED"})
        self._write_json(paths["scanner"], {
            "timestamp_ist": self.now.isoformat(),
            "scan_only": True,
            "fallback_reason": "MASTER_BRAIN_UNAVAILABLE|SETUP_ENGINE_UNAVAILABLE",
        })
        self._write_json(paths["scanner_truth"], {"stale_snapshot_warning": False, "counter_confidence": "LOW"})
        self._write_json(paths["daemon"], {"timestamp_ist": self.now.isoformat(), "status": "RUNNING", "pid": 1234})

        with self._patch_resolver_paths(paths):
            result = runtime_fallback_resolver.run_runtime_fallback_resolution(now=self.now, output_path=paths["resolution"])

        self.assertFalse(result["off_hours_runtime_continuity"])
        self.assertEqual(result["fallback_truthfulness"], "ENGINE_UNAVAILABLE")
        self.assertEqual(result["scanner_confidence"], "LOW")

    def test_scanner_confidence_elevates_when_engines_are_healthy(self):
        scanner = self.runtime / "scanner_status.json"
        selection = self.root / "scan_selection_state.json"
        output = self.runtime / "scanner_filter_truth_status.json"
        master_health = self.runtime / "master_brain_runtime_health.json"
        setup_health = self.runtime / "setup_engine_runtime_health.json"
        resolution = self.runtime / "runtime_fallback_resolution.json"
        self._write_json(scanner, {
            "timestamp_ist": (self.now - timedelta(minutes=30)).isoformat(),
            "stocks_checked": 5,
            "trend_passed_count": 4,
            "momentum_passed_count": 3,
            "structure_passed_count": 2,
            "breakout_ready_count": 1,
            "final_passed_count": 1,
            "alerts_this_scan": 0,
        })
        self._write_json(selection, {"selected_symbols": ["A", "B", "C", "D", "E"]})
        self._write_json(master_health, {"master_brain_runtime_health": "ACTIVE", "master_brain_freshness_confidence": "HIGH"})
        self._write_json(setup_health, {"setup_runtime_health": "ACTIVE", "setup_freshness_confidence": "HIGH"})
        self._write_json(resolution, {"fallback_truthfulness": "STALE_FALSE_FALLBACK", "scanner_confidence": "MEDIUM"})

        with patch.object(scanner_filter_truth, "MASTER_BRAIN_RUNTIME_HEALTH_PATH", master_health), \
            patch.object(scanner_filter_truth, "SETUP_ENGINE_RUNTIME_HEALTH_PATH", setup_health), \
            patch.object(scanner_filter_truth, "RUNTIME_FALLBACK_RESOLUTION_PATH", resolution), \
            patch.object(scanner_filter_truth, "SIGNAL_PATH_DIAGNOSTICS_PATH", self.runtime / "missing_diagnostics.json"), \
            patch.object(scanner_filter_truth, "DASHBOARD_TRUTH_REGISTRY_PATH", self.runtime / "missing_dashboard.json"), \
            patch.object(scanner_filter_truth, "TRADE_LIFECYCLE_HEALTH_PATH", self.runtime / "missing_lifecycle.json"):
            result = scanner_filter_truth.build_scanner_filter_truth_status(
                now=self.now,
                scanner_status_path=scanner,
                scan_selection_state_path=selection,
                setup_engine_status_path=self.runtime / "missing_setup.json",
                output_path=output,
            )

        self.assertEqual(result["raw_counter_confidence"], "LOW")
        self.assertEqual(result["counter_confidence"], "MEDIUM")

    def test_scanner_confidence_improves_to_medium_off_hours_standby(self):
        scanner = self.runtime / "scanner_status.json"
        selection = self.root / "scan_selection_state.json"
        output = self.runtime / "scanner_filter_truth_status.json"
        master_health = self.runtime / "master_brain_runtime_health.json"
        setup_health = self.runtime / "setup_engine_runtime_health.json"
        resolution = self.runtime / "runtime_fallback_resolution.json"
        stale = self.off_hours - timedelta(minutes=45)
        self._write_json(scanner, {
            "timestamp_ist": stale.isoformat(),
            "stocks_checked": 5,
            "trend_passed_count": 3,
            "momentum_passed_count": 3,
            "structure_passed_count": 3,
            "breakout_ready_count": 3,
            "final_passed_count": 0,
            "alerts_this_scan": 0,
            "scan_only": True,
            "fallback_reason": "MASTER_BRAIN_UNAVAILABLE",
        })
        self._write_json(selection, {"selected_symbols": ["A", "B", "C", "D", "E"]})
        self._write_json(master_health, {"master_brain_runtime_health": "RESEARCH_ACTIVE", "master_brain_freshness_confidence": "MEDIUM"})
        self._write_json(setup_health, {"setup_runtime_health": "OFF_HOURS_STANDBY", "setup_freshness_confidence": "MEDIUM"})
        self._write_json(resolution, {"fallback_truthfulness": "OFF_HOURS_RESEARCH_STANDBY", "scanner_confidence": "MEDIUM", "fallback_active": False})

        with patch.object(scanner_filter_truth, "MASTER_BRAIN_RUNTIME_HEALTH_PATH", master_health), \
            patch.object(scanner_filter_truth, "SETUP_ENGINE_RUNTIME_HEALTH_PATH", setup_health), \
            patch.object(scanner_filter_truth, "RUNTIME_FALLBACK_RESOLUTION_PATH", resolution), \
            patch.object(scanner_filter_truth, "SIGNAL_PATH_DIAGNOSTICS_PATH", self.runtime / "missing_diagnostics.json"), \
            patch.object(scanner_filter_truth, "DASHBOARD_TRUTH_REGISTRY_PATH", self.runtime / "missing_dashboard.json"), \
            patch.object(scanner_filter_truth, "TRADE_LIFECYCLE_HEALTH_PATH", self.runtime / "missing_lifecycle.json"):
            result = scanner_filter_truth.build_scanner_filter_truth_status(
                now=self.off_hours,
                scanner_status_path=scanner,
                scan_selection_state_path=selection,
                setup_engine_status_path=self.runtime / "missing_setup.json",
                output_path=output,
            )

        self.assertEqual(result["counter_confidence"], "MEDIUM")
        self.assertEqual(result["recommended_dashboard_display_mode"], "off_hours_research_standby")
        self.assertTrue(result["identical_counter_warning_downgraded"])
        self.assertFalse(result["identical_counter_warning"])

    def test_safety_flags_keep_mutation_disabled(self):
        payload = runtime_engine_health.enrich_master_brain_payload({"timestamp_ist": self.now.isoformat(), "status": "MASTER_BRAIN_READ_ONLY_COMPLETE"}, now=self.now)
        self.assertFalse(payload.get("live_execution_enabled", False))
        self.assertFalse(payload.get("telegram_enabled", False))

    def _resolver_paths(self):
        return {
            "master_status": self.runtime / "master_brain_status.json",
            "setup_status": self.runtime / "setup_engine_status.json",
            "master_health": self.runtime / "master_brain_runtime_health.json",
            "setup_health": self.runtime / "setup_engine_runtime_health.json",
            "scanner": self.runtime / "scanner_status.json",
            "scanner_truth": self.runtime / "scanner_filter_truth_status.json",
            "market": self.runtime / "titan_market_data_health.json",
            "live_price": self.runtime / "live_price_health.json",
            "daemon": self.runtime / "daemon_health.json",
            "authoritative_runtime": self.runtime / "titan_authoritative_runtime_health.json",
            "resolution": self.runtime / "runtime_fallback_resolution.json",
        }

    def _patch_resolver_paths(self, paths):
        master_builder = lambda now=None: runtime_engine_health.build_master_brain_runtime_health(
            now=now,
            status_path=paths["master_status"],
            output_path=paths["master_health"],
        )
        setup_builder = lambda now=None: runtime_engine_health.build_setup_engine_runtime_health(
            now=now,
            status_path=paths["setup_status"],
            output_path=paths["setup_health"],
        )
        return patch.multiple(
            runtime_fallback_resolver,
            SCANNER_STATUS_PATH=paths["scanner"],
            SCANNER_FILTER_TRUTH_STATUS_PATH=paths["scanner_truth"],
            MARKET_DATA_HEALTH_PATH=paths["market"],
            LIVE_PRICE_HEALTH_PATH=paths["live_price"],
            DAEMON_HEALTH_PATH=paths["daemon"],
            AUTHORITATIVE_RUNTIME_HEALTH_PATH=paths["authoritative_runtime"],
            build_master_brain_runtime_health=master_builder,
            build_setup_engine_runtime_health=setup_builder,
        )


if __name__ == "__main__":
    unittest.main()
