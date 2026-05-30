import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_health
from utils.market_hours import IST


class RuntimeHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.memory_dir = self.root / "memory"
        self.output_path = self.runtime_dir / "titan_authoritative_runtime_health.json"
        self.now = datetime(2026, 5, 25, 10, 0, 0, tzinfo=IST)
        self.paths = {
            "DAEMON_HEALTH_PATH": self.runtime_dir / "daemon_health.json",
            "HEARTBEAT_PATH": self.runtime_dir / "titan_heartbeat.json",
            "AUTHORITATIVE_RUNTIME_HEALTH_PATH": self.output_path,
            "DAEMON_LOCK_PATH": self.runtime_dir / "locks" / "titan_daemon.lock",
            "SCANNER_STATUS_PATH": self.runtime_dir / "scanner_status.json",
            "MASTER_BRAIN_STATUS_PATH": self.runtime_dir / "master_brain_status.json",
            "REPLAY_STATUS_PATH": self.runtime_dir / "historical_replay_status.json",
            "REPLAY_PROGRESS_PATH": self.runtime_dir / "historical_replay_progress.json",
            "REINFORCEMENT_LEARNING_STATUS_PATH": self.runtime_dir / "reinforcement_learning_status.json",
            "REINFORCEMENT_LEARNING_MEMORY_PATH": self.memory_dir / "reinforcement_learning_memory.json",
            "META_LEARNING_STATUS_PATH": self.runtime_dir / "meta_learning_status.json",
            "META_LEARNING_MEMORY_PATH": self.memory_dir / "meta_learning_state.json",
            "DASHBOARD_SYNC_STATUS_PATH": self.runtime_dir / "dashboard_sync_status.json",
        }
        self.patchers = [patch.object(runtime_health, name, path) for name, path in self.paths.items()]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _write_json(self, path, payload):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_fresh_artifacts(self, pid=None):
        pid = pid or os.getpid()
        timestamp = self.now.isoformat()
        self._write_json(runtime_health.DAEMON_HEALTH_PATH, {"status": "RUNNING", "pid": pid, "mode": "TEST", "timestamp_ist": timestamp})
        self._write_json(runtime_health.HEARTBEAT_PATH, {"status": "ALIVE", "pid": pid, "mode": "TEST", "timestamp_ist": timestamp})
        self._write_json(runtime_health.DAEMON_LOCK_PATH, {"name": "titan_daemon", "pid": pid, "acquired_at_ist": timestamp})
        self._write_json(runtime_health.SCANNER_STATUS_PATH, {"status": "OK", "scan_finished_at_ist": timestamp})
        self._write_json(runtime_health.MASTER_BRAIN_STATUS_PATH, {"status": "OK", "timestamp_ist": timestamp})
        self._write_json(runtime_health.REPLAY_PROGRESS_PATH, {"status": "OK", "last_completed_at_ist": timestamp})
        self._write_json(runtime_health.REINFORCEMENT_LEARNING_STATUS_PATH, {"status": "OK", "timestamp_ist": timestamp})
        self._write_json(runtime_health.META_LEARNING_STATUS_PATH, {"status": "OK", "timestamp_ist": timestamp})
        self._write_json(runtime_health.DASHBOARD_SYNC_STATUS_PATH, {"status": "OK", "timestamp_ist": timestamp})

    def test_stale_lock_becomes_warning_or_fail_not_ok(self):
        self._write_fresh_artifacts()
        stale_time = (self.now - timedelta(minutes=10)).isoformat()
        self._write_json(runtime_health.DAEMON_LOCK_PATH, {"name": "titan_daemon", "pid": 999999, "acquired_at_ist": stale_time})
        self._write_json(runtime_health.DAEMON_HEALTH_PATH, {"status": "STOPPED", "pid": 999999, "timestamp_ist": stale_time})
        self._write_json(runtime_health.HEARTBEAT_PATH, {"status": "STOPPED", "pid": 999999, "timestamp_ist": stale_time})

        with patch.object(runtime_health, "_process_visible", return_value=False):
            payload = runtime_health.run_authoritative_runtime_health_check(now=self.now)

        self.assertIn(payload["overall_status"], {"WARNING", "FAIL"})
        self.assertTrue(payload["daemon_lock_stale"])
        self.assertNotEqual(payload["overall_status"], "PASS")

    def test_missing_process_running_artifact_creates_contradiction_flag(self):
        self._write_fresh_artifacts(pid=999999)

        with patch.object(runtime_health, "_process_visible", return_value=False):
            payload = runtime_health.run_authoritative_runtime_health_check(now=self.now)

        self.assertEqual(payload["overall_status"], "FAIL")
        self.assertIn("running_artifact_without_visible_process", payload["contradiction_flags"])

    def test_fresh_heartbeat_becomes_pass(self):
        self._write_fresh_artifacts()

        with patch.object(runtime_health, "_process_visible", return_value=True):
            payload = runtime_health.run_authoritative_runtime_health_check(now=self.now)

        self.assertEqual(payload["overall_status"], "PASS")
        self.assertTrue(payload["process_visible"])
        self.assertFalse(payload["stale_artifacts"])

    def test_no_files_deleted(self):
        self._write_fresh_artifacts()
        before = {path for path in self.runtime_dir.rglob("*") if path.is_file()}

        with patch.object(runtime_health, "_process_visible", return_value=True):
            runtime_health.run_authoritative_runtime_health_check(now=self.now)

        after = {path for path in self.runtime_dir.rglob("*") if path.is_file()}
        self.assertTrue(before.issubset(after))
        self.assertTrue(runtime_health.DAEMON_LOCK_PATH.exists())

    def test_no_live_mutation_flags_enabled(self):
        self._write_fresh_artifacts()

        with patch.object(runtime_health, "_process_visible", return_value=True):
            payload = runtime_health.run_authoritative_runtime_health_check(now=self.now)

        safety = payload["safety_flags"]
        self.assertTrue(safety["advisory_only"])
        self.assertTrue(safety["research_only"])
        self.assertFalse(safety["affects_live_ranking"])
        self.assertFalse(safety["affects_execution"])
        self.assertFalse(safety["broker_mutation"])
        self.assertFalse(safety["telegram_mutation"])
        self.assertFalse(safety["supabase_mutation"])
        self.assertFalse(safety["live_order_behavior"])
        self.assertEqual(safety["recommended_live_weight"], 0.0)
        self.assertEqual(safety["rank_adjustment"], 0.0)


if __name__ == "__main__":
    unittest.main()
