import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_watchdog
from utils.market_hours import IST


class Batch8RuntimeWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.lock_dir = self.runtime_dir / "locks"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _patch_paths(self):
        sources = {
            name: {**spec, "path": self.runtime_dir / spec["path"].name}
            for name, spec in runtime_watchdog.RUNTIME_SOURCES.items()
        }
        sources["daemon_lock"]["path"] = self.lock_dir / "titan_daemon.lock"
        return patch.multiple(
            runtime_watchdog,
            RUNTIME_DIR=self.runtime_dir,
            LOCK_DIR=self.lock_dir,
            TITAN_RUNTIME_WATCHDOG_PATH=self.runtime_dir / "titan_runtime_watchdog.json",
            RUNTIME_RECOVERY_POLICY_PATH=self.runtime_dir / "runtime_recovery_policy.json",
            STALE_WRITER_AUDIT_PATH=self.runtime_dir / "stale_writer_audit.json",
            RUNTIME_RECONCILIATION_STATUS_PATH=self.runtime_dir / "runtime_reconciliation_status.json",
            RUNTIME_SOURCES=sources,
        )

    def test_stale_writer_audit_classifies_owner_and_secondary_sources(self):
        stale_time = (self.now - timedelta(hours=2)).isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "RUNNING", "pid": 999999, "timestamp_ist": stale_time})
        self._write_json(self.runtime_dir / "titan_runtime_status.json", {"status": "OK", "timestamp_ist": stale_time})

        with self._patch_paths(), patch.object(runtime_watchdog, "_process_visible", return_value=False):
            sources = runtime_watchdog._collect_sources(self.now)
            audit = runtime_watchdog.build_stale_writer_audit(now=self.now, sources=sources)

        by_name = {item["name"]: item for item in audit["stale_writers"]}
        self.assertEqual(by_name["daemon_health"]["classification"], "stale_runtime_owner_signal")
        self.assertEqual(by_name["runtime_status"]["classification"], "stale_secondary_runtime_source")
        self.assertFalse(by_name["daemon_health"]["automatic_restart_allowed"])
        self.assertFalse(by_name["daemon_health"]["automatic_kill_allowed"])

    def test_visible_daemon_owner_wins_deterministically(self):
        timestamp = self.now.isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "RUNNING", "pid": 1234, "timestamp_ist": timestamp})
        self._write_json(self.runtime_dir / "titan_heartbeat.json", {"status": "ALIVE", "pid": 1234, "timestamp_ist": timestamp})

        with self._patch_paths(), patch.object(runtime_watchdog, "_process_visible", return_value=True):
            status = runtime_watchdog.build_runtime_reconciliation_status(now=self.now)

        self.assertEqual(status["runtime_reconciliation_status"], "PASS")
        self.assertEqual(status["deterministic_runtime_owner"], "confirmed_daemon_pid")
        self.assertEqual(status["authoritative_pid"], 1234)
        self.assertEqual(status["owner_confidence"], "HIGH")
        self.assertTrue(status["runtime_ownership_deterministic"])
        self.assertFalse(status["restart_recommended"])
        self.assertFalse(status["kill_recommended"])

    def test_visible_process_stale_heartbeat_mismatch_still_resolves_owner(self):
        fresh_time = self.now.isoformat()
        stale_time = (self.now - timedelta(hours=2)).isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "RUNNING", "pid": 1234, "timestamp_ist": fresh_time})
        self._write_json(self.runtime_dir / "titan_heartbeat.json", {"status": "ALIVE", "pid": 9999, "timestamp_ist": stale_time})
        self._write_json(self.lock_dir / "titan_daemon.lock", {"name": "titan_daemon", "pid": 1234, "acquired_at_ist": fresh_time})

        with self._patch_paths(), patch.object(runtime_watchdog, "_process_visible", side_effect=lambda pid: int(pid) == 1234):
            status = runtime_watchdog.build_runtime_reconciliation_status(now=self.now)

        self.assertEqual(status["deterministic_runtime_owner"], "confirmed_daemon_pid")
        self.assertEqual(status["authoritative_pid"], 1234)
        self.assertEqual(status["owner_confidence"], "HIGH")
        self.assertIn("daemon_health_heartbeat_pid_mismatch", status["remaining_contradictions"])
        self.assertTrue(status["pid_reconciliation"]["pid_mismatch"])
        self.assertIn(9999, status["pid_reconciliation"]["ghost_pids"])

    def test_no_visible_process_remains_none_confirmed(self):
        stale_time = (self.now - timedelta(hours=2)).isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "RUNNING", "pid": 1234, "timestamp_ist": stale_time})
        self._write_json(self.runtime_dir / "titan_heartbeat.json", {"status": "ALIVE", "pid": 1234, "timestamp_ist": stale_time})
        self._write_json(self.lock_dir / "titan_daemon.lock", {"name": "titan_daemon", "pid": 1234, "acquired_at_ist": stale_time})

        with self._patch_paths(), patch.object(runtime_watchdog, "_process_visible", return_value=False):
            status = runtime_watchdog.build_runtime_reconciliation_status(now=self.now)

        self.assertEqual(status["deterministic_runtime_owner"], "none_confirmed")
        self.assertIsNone(status["authoritative_pid"])
        self.assertEqual(status["owner_confidence"], "LOW")
        self.assertIn(1234, status["pid_reconciliation"]["ghost_pids"])

    def test_pid_mismatch_classified_correctly(self):
        timestamp = self.now.isoformat()
        stale_time = (self.now - timedelta(hours=2)).isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "RUNNING", "pid": 1111, "timestamp_ist": timestamp})
        self._write_json(self.runtime_dir / "titan_heartbeat.json", {"status": "ALIVE", "pid": 2222, "timestamp_ist": stale_time})
        self._write_json(self.lock_dir / "titan_daemon.lock", {"name": "titan_daemon", "pid": 3333, "acquired_at_ist": stale_time})

        with self._patch_paths(), patch.object(runtime_watchdog, "_process_visible", side_effect=lambda pid: int(pid) == 3333):
            status = runtime_watchdog.build_runtime_reconciliation_status(now=self.now)

        reconciliation = status["pid_reconciliation"]
        by_pid = {item["pid"]: item for item in reconciliation["pids"]}
        self.assertTrue(reconciliation["pid_mismatch"])
        self.assertEqual(status["authoritative_pid"], 3333)
        self.assertIn("daemon_health_pid", by_pid[1111]["roles"])
        self.assertIn("heartbeat_pid", by_pid[2222]["roles"])
        self.assertIn("lock_pid", by_pid[3333]["roles"])
        self.assertEqual(by_pid[3333]["classification"], "visible_process_pid")
        self.assertEqual(by_pid[1111]["classification"], "ghost_pid")
        self.assertEqual(by_pid[2222]["classification"], "ghost_pid")
        self.assertTrue(status["stale_pid_flags"])
        self.assertTrue(status["ghost_pid_flags"])

    def test_visible_titan_daemon_command_resolves_owner_even_with_stale_artifact_pids(self):
        stale_time = (self.now - timedelta(hours=2)).isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "STOPPED", "pid": 1111, "timestamp_ist": stale_time})
        self._write_json(self.runtime_dir / "titan_heartbeat.json", {"status": "ALIVE", "pid": 2222, "timestamp_ist": stale_time})
        self._write_json(self.lock_dir / "titan_daemon.lock", {"name": "titan_daemon", "pid": 3333, "acquired_at_ist": stale_time})
        visible = [
            {
                "pid": 2195564,
                "command": "/home/ubuntu/titan-bot/.venv/bin/python -B /home/ubuntu/titan-bot/titan_daemon.py",
                "source": "pgrep",
            }
        ]

        with self._patch_paths(), patch.object(runtime_watchdog, "_process_visible", return_value=False), patch.object(
            runtime_watchdog, "_discover_visible_daemon_processes", return_value=visible
        ):
            status = runtime_watchdog.build_runtime_reconciliation_status(now=self.now)

        self.assertEqual(status["deterministic_runtime_owner"], "confirmed_daemon_pid")
        self.assertEqual(status["authoritative_pid"], 2195564)
        self.assertEqual(status["owner_confidence"], "HIGH")
        self.assertTrue(status["pid_reconciliation"]["pid_mismatch"])
        by_pid = {item["pid"]: item for item in status["pid_reconciliation"]["pids"]}
        self.assertIn("visible_process_pid", by_pid[2195564]["roles"])
        self.assertEqual(by_pid[2195564]["classification"], "visible_process_pid")
        self.assertIn(1111, status["pid_reconciliation"]["ghost_pids"])
        self.assertIn(2222, status["pid_reconciliation"]["ghost_pids"])
        self.assertIn(3333, status["pid_reconciliation"]["ghost_pids"])

    def test_recovery_policy_forbids_auto_healing_mutations(self):
        with self._patch_paths():
            policy = runtime_watchdog.build_runtime_recovery_policy(now=self.now)

        self.assertEqual(policy["runtime_recovery_policy_status"], "PASS")
        self.assertFalse(policy["automatic_restart_allowed"])
        self.assertFalse(policy["automatic_process_kill_allowed"])
        self.assertFalse(policy["automatic_lock_delete_allowed"])
        self.assertTrue(policy["safe_self_healing_classification"]["visibility_refresh"]["allowed"])
        self.assertFalse(policy["safe_self_healing_classification"]["daemon_restart"]["allowed"])
        self.assertTrue(policy["safety_flags"]["advisory_only"])
        self.assertFalse(policy["safety_flags"]["affects_execution"])

    def test_watchdog_generates_all_required_artifacts(self):
        stale_time = (self.now - timedelta(hours=2)).isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "STOPPED", "pid": 999999, "timestamp_ist": stale_time})
        self._write_json(self.runtime_dir / "titan_heartbeat.json", {"status": "ALIVE", "pid": 999999, "timestamp_ist": stale_time})
        self._write_json(self.lock_dir / "titan_daemon.lock", {"name": "titan_daemon", "pid": 999999, "acquired_at_ist": stale_time})

        with self._patch_paths(), patch.object(runtime_watchdog, "_process_visible", return_value=False):
            result = runtime_watchdog.run_batch8_runtime_watchdog(now=self.now)

        self.assertEqual(result["status"], "WARNING")
        self.assertIn("daemon_stopped_but_heartbeat_alive", result["summary"]["heartbeat_daemon_inconsistencies"])
        for path in result["artifacts"].values():
            self.assertTrue(Path(path).exists())
        self.assertFalse(result["summary"]["automatic_restart_allowed"])
        self.assertFalse(result["summary"]["automatic_process_kill_allowed"])
        self.assertFalse(result["summary"]["auto_healing_mutation_allowed"])


if __name__ == "__main__":
    unittest.main()
