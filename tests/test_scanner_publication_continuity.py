import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_scanner
import scanner_filter_truth
import scanner_publication_health
from utils.market_hours import IST


class ScannerPublicationContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.data = self.root / "data"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.data.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 15, tzinfo=IST)

    def tearDown(self):
        self.tmp.cleanup()

    def _read_json(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def _write_json(self, path, payload):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _scanner_payload(self, cycle, timestamp):
        return {
            "timestamp_ist": timestamp,
            "scanner_timestamp": timestamp,
            "scanner_cycle_id": cycle,
            "scan_finished_at_ist": timestamp,
            "mode": "FULL_RUNTIME_PIPELINE",
            "status": "FULL_RUNTIME_PIPELINE_COMPLETE",
            "stocks_checked": 50,
            "trend_passed": 7,
            "trend_passed_count": 7,
            "momentum_passed": 4,
            "momentum_passed_count": 4,
            "structure_passed": 3,
            "structure_passed_count": 3,
            "breakout_ready_count": 2,
            "entry_passed": 2,
            "final_passed": 1,
            "final_passed_count": 1,
            "alerts_this_scan": 0,
            "scan_only": False,
            "data_signature": cycle,
        }

    def _patch_paths(self):
        scanner_status = self.runtime / "scanner_status.json"
        scanner_truth = self.runtime / "scanner_filter_truth_status.json"
        scanner_heartbeat = self.runtime / "scanner_runtime_heartbeat.json"
        previous_signature = self.runtime / "scanner_previous_signature.json"
        return patch.multiple(
            runtime_scanner,
            SCANNER_FILTER_TRUTH_STATUS_PATH=scanner_truth,
            SCANNER_RUNTIME_HEARTBEAT_PATH=scanner_heartbeat,
            SCANNER_PREVIOUS_SIGNATURE_PATH=previous_signature,
        ), patch.multiple(
            scanner_filter_truth,
            SIGNAL_PATH_DIAGNOSTICS_PATH=self.runtime / "missing_signal_path_diagnostics.json",
            DASHBOARD_TRUTH_REGISTRY_PATH=self.runtime / "missing_dashboard_truth_registry.json",
            TRADE_LIFECYCLE_HEALTH_PATH=self.runtime / "missing_trade_lifecycle_health.json",
            MASTER_BRAIN_RUNTIME_HEALTH_PATH=self.runtime / "missing_master_health.json",
            SETUP_ENGINE_RUNTIME_HEALTH_PATH=self.runtime / "missing_setup_health.json",
            RUNTIME_FALLBACK_RESOLUTION_PATH=self.runtime / "missing_fallback_resolution.json",
            SCANNER_PUBLICATION_HEALTH_PATH=self.runtime / "missing_scanner_publication_health.json",
            LIVE_SCANNER_SYNC_AUDIT_PATH=self.runtime / "live_scanner_sync_audit.json",
        ), scanner_status, scanner_truth, scanner_heartbeat

    def test_scan_cycle_id_advances_timestamp_refreshes_and_heartbeat_updates(self):
        patch_runtime, patch_truth, scanner_status, scanner_truth, scanner_heartbeat = self._patch_paths()
        first_ts = self.now.isoformat()
        second_ts = (self.now + timedelta(minutes=5)).isoformat()
        with patch_runtime, patch_truth:
            first = runtime_scanner._publish_scanner_outputs(
                scanner_status,
                self._scanner_payload("cycle-1", first_ts),
                "sig-1",
                "cycle-1",
                first_ts,
            )
            second = runtime_scanner._publish_scanner_outputs(
                scanner_status,
                self._scanner_payload("cycle-2", second_ts),
                "sig-2",
                "cycle-2",
                second_ts,
            )

        written = self._read_json(scanner_status)
        truth = self._read_json(scanner_truth)
        heartbeat = self._read_json(scanner_heartbeat)
        self.assertEqual(first["publish_status"], "PUBLISHED")
        self.assertEqual(second["publish_status"], "PUBLISHED")
        self.assertEqual(written["scanner_cycle_id"], "cycle-2")
        self.assertEqual(written["scan_finished_at_ist"], second_ts)
        self.assertEqual(truth["authoritative_scan_cycle_id"], "cycle-2")
        self.assertEqual(heartbeat["latest_cycle"], "cycle-2")
        self.assertEqual(heartbeat["publish_status"], "PUBLISHED")
        self.assertEqual(heartbeat["publish_count"], 2)

    def test_stale_publication_detected_correctly(self):
        stale = self.now - timedelta(minutes=30)
        scanner_status = self._write_json(
            self.runtime / "scanner_status.json",
            self._scanner_payload("cycle-stale", stale.isoformat()),
        )
        heartbeat = self._write_json(
            self.runtime / "scanner_runtime_heartbeat.json",
            {
                "latest_cycle": "cycle-stale",
                "latest_publish_time": stale.isoformat(),
                "publish_status": "PUBLISHED",
                "publish_count": 1,
                "failed_publish_count": 0,
                "scanner_loop_health": "ACTIVE",
            },
        )
        result = scanner_publication_health.run_scanner_publication_health_check(
            now=self.now,
            scanner_status_path=scanner_status,
            scanner_truth_path=self.runtime / "missing_truth.json",
            heartbeat_path=heartbeat,
            worker_health_path=self.runtime / "missing_worker.json",
            output_path=self.runtime / "scanner_publication_health.json",
        )

        self.assertTrue(result["publish_stall_detected"])
        self.assertTrue(result["stale_cycle_detected"])
        self.assertEqual(result["publish_health"], "STALE")

    def test_partial_publish_failure_is_visible_and_runtime_survives(self):
        patch_runtime, patch_truth, scanner_status, scanner_truth, scanner_heartbeat = self._patch_paths()
        original_write = runtime_scanner._atomic_write_json

        def flaky_write(path, payload):
            if Path(path) == scanner_truth:
                raise OSError("truth write blocked")
            return original_write(path, payload)

        with patch_runtime, patch_truth, patch.object(scanner_filter_truth, "_write_json", side_effect=flaky_write):
            result = runtime_scanner._publish_scanner_outputs(
                scanner_status,
                self._scanner_payload("cycle-partial", self.now.isoformat()),
                "sig-partial",
                "cycle-partial",
                self.now.isoformat(),
            )

        heartbeat = self._read_json(scanner_heartbeat)
        self.assertEqual(result["publish_status"], "PARTIAL")
        self.assertTrue(result["scanner_status_published"])
        self.assertFalse(result["scanner_truth_published"])
        self.assertEqual(heartbeat["publish_status"], "PARTIAL")
        self.assertIn("scanner_filter_truth", heartbeat["last_publish_exception"])

    def test_invalid_zero_overwrite_is_detected_without_fake_freeze(self):
        truth = self._write_json(
            self.runtime / "scanner_filter_truth_status.json",
            {"zero_overwrite_detected": True, "authoritative_scan_cycle_id": "cycle-good"},
        )
        status = self._write_json(
            self.runtime / "scanner_status.json",
            self._scanner_payload("cycle-zero", self.now.isoformat()),
        )
        heartbeat = self._write_json(
            self.runtime / "scanner_runtime_heartbeat.json",
            {
                "latest_cycle": "cycle-zero",
                "latest_publish_time": self.now.isoformat(),
                "publish_status": "PUBLISHED",
                "publish_count": 2,
                "failed_publish_count": 0,
                "scanner_loop_health": "ACTIVE",
            },
        )
        result = scanner_publication_health.run_scanner_publication_health_check(
            now=self.now,
            scanner_status_path=status,
            scanner_truth_path=truth,
            heartbeat_path=heartbeat,
            worker_health_path=self.runtime / "missing_worker.json",
            output_path=self.runtime / "scanner_publication_health.json",
        )

        self.assertIn("invalid_zero_overwrite_detected", result["warnings"])
        self.assertTrue(result["scanner_publish_active"])
        self.assertFalse(result["publish_stall_detected"])

    def test_safety_flags_keep_mutations_disabled(self):
        result = scanner_publication_health.run_scanner_publication_health_check(
            now=self.now,
            scanner_status_path=self.runtime / "missing_status.json",
            scanner_truth_path=self.runtime / "missing_truth.json",
            heartbeat_path=self.runtime / "missing_heartbeat.json",
            worker_health_path=self.runtime / "missing_worker.json",
            output_path=self.runtime / "scanner_publication_health.json",
        )
        flags = result["safety_flags"]
        self.assertFalse(flags["affects_live_ranking"])
        self.assertFalse(flags["affects_execution"])
        self.assertFalse(flags["broker_mutation"])
        self.assertFalse(flags["telegram_mutation"])
        self.assertFalse(flags["supabase_mutation"])


if __name__ == "__main__":
    unittest.main()
