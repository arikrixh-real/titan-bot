import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_dashboard_sync
import runtime_truth
from scanner_ohlc_setup_truth import classify_scanner_status
from utils.market_hours import IST


class RuntimeTruthRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime = self.root / "data" / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 6, 7, 12, 30, tzinfo=IST)
        self.paths = {
            "AUTHORITATIVE_RUNTIME_TRUTH_PATH": self.runtime / "authoritative_runtime_truth.json",
            "DAEMON_HEALTH_PATH": self.runtime / "daemon_health.json",
            "HEARTBEAT_PATH": self.runtime / "titan_heartbeat.json",
            "WORKER_HEALTH_PATH": self.runtime / "worker_health.json",
            "SCANNER_SCHEDULER_STATUS_PATH": self.runtime / "scanner_scheduler_status.json",
            "SCANNER_STATUS_PATH": self.runtime / "scanner_status.json",
            "SETUP_ENGINE_STATUS_PATH": self.runtime / "setup_engine_status.json",
            "MASTER_BRAIN_STATUS_PATH": self.runtime / "master_brain_status.json",
            "OUTCOME_TRACKER_STATUS_PATH": self.runtime / "outcome_tracker_status.json",
            "PAPER_ENGINE_STATUS_PATH": self.runtime / "paper_engine_status.json",
            "DASHBOARD_SYNC_STATUS_PATH": self.runtime / "dashboard_sync_status.json",
            "OHLC_HEALTH_PATH": self.runtime / "ohlc_health.json",
            "DAEMON_LOCK_PATH": self.runtime / "locks" / "titan_daemon.lock",
            "RUNTIME_OWNER_TRANSITION_PATH": self.runtime / "runtime_owner_transition.json",
        }
        self.patchers = [patch.object(runtime_truth, name, path) for name, path in self.paths.items()]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _write_json(self, path, payload):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _stale(self):
        return (self.now - timedelta(hours=4)).isoformat()

    def _fresh(self):
        return self.now.isoformat()

    def test_stale_heartbeat_cannot_override_stopped_daemon(self):
        self._write_json(runtime_truth.DAEMON_HEALTH_PATH, {"status": "STOPPED", "pid": 123456, "timestamp_ist": self._fresh()})
        self._write_json(runtime_truth.HEARTBEAT_PATH, {"status": "ALIVE", "pid": 123456, "timestamp_ist": self._stale()})

        with patch.object(runtime_truth, "process_visible", return_value=False):
            truth = runtime_truth.build_authoritative_runtime_truth(now=self.now, write=True)

        daemon = truth["components"]["daemon"]
        self.assertEqual(daemon["status"], "STOPPED")
        self.assertEqual(daemon["reason"], "daemon_health_stopped_overrides_heartbeat_without_process")
        self.assertTrue(daemon["restart_blocker"])

    def test_dead_daemon_pid_fresh_heartbeat_pid_rotates_owner_live(self):
        self._write_json(runtime_truth.DAEMON_HEALTH_PATH, {"status": "RUNNING", "pid": 1111, "timestamp_ist": self._fresh()})
        self._write_json(runtime_truth.HEARTBEAT_PATH, {"status": "ALIVE", "pid": 2222, "timestamp_ist": self._fresh()})

        with patch.object(runtime_truth, "process_visible", side_effect=lambda pid: int(pid) == 2222):
            truth = runtime_truth.build_authoritative_runtime_truth(now=self.now, write=True)

        daemon = truth["components"]["daemon"]
        self.assertEqual(daemon["status"], "LIVE")
        self.assertEqual(daemon["runtime_owner"], "heartbeat")
        self.assertEqual(daemon["transition_reason"], "OWNER_ROTATED")
        self.assertEqual(daemon["old_daemon_pid"], 1111)
        self.assertEqual(daemon["new_heartbeat_pid"], 2222)
        self.assertEqual(daemon["process_pid"], 2222)
        transition = json.loads(runtime_truth.RUNTIME_OWNER_TRANSITION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(transition["runtime_owner"], "heartbeat")
        self.assertEqual(transition["transition_reason"], "OWNER_ROTATED")
        self.assertEqual(transition["old_daemon_pid"], 1111)
        self.assertEqual(transition["new_heartbeat_pid"], 2222)

    def test_dead_daemon_pid_stale_heartbeat_stays_stale(self):
        self._write_json(runtime_truth.DAEMON_HEALTH_PATH, {"status": "RUNNING", "pid": 1111, "timestamp_ist": self._fresh()})
        self._write_json(runtime_truth.HEARTBEAT_PATH, {"status": "ALIVE", "pid": 2222, "timestamp_ist": self._stale()})

        with patch.object(runtime_truth, "process_visible", side_effect=lambda pid: int(pid) == 2222):
            truth = runtime_truth.build_authoritative_runtime_truth(now=self.now, write=True)

        daemon = truth["components"]["daemon"]
        self.assertEqual(daemon["status"], "STALE")
        self.assertEqual(daemon["reason"], "active_marker_stale_or_process_missing")
        self.assertTrue(daemon["restart_blocker"])

    def test_matching_daemon_and_heartbeat_pid_keeps_normal_owner_live(self):
        self._write_json(
            runtime_truth.DAEMON_HEALTH_PATH,
            {"status": "RUNNING", "pid": 3333, "runtime_mode": "READ_ONLY", "timestamp_ist": self._fresh()},
        )
        self._write_json(runtime_truth.HEARTBEAT_PATH, {"status": "ALIVE", "pid": 3333, "timestamp_ist": self._fresh()})
        self._write_json(runtime_truth.DAEMON_LOCK_PATH, {"pid": 3333, "acquired_at_ist": self._fresh()})

        with patch.object(runtime_truth, "process_visible", side_effect=lambda pid: int(pid) == 3333):
            truth = runtime_truth.build_authoritative_runtime_truth(now=self.now, write=True)

        daemon = truth["components"]["daemon"]
        self.assertEqual(daemon["status"], "LIVE")
        self.assertEqual(daemon["runtime_state"], "RUNNING_READ_ONLY_PROOF")
        self.assertEqual(daemon["runtime_owner"], "daemon_health")
        self.assertEqual(daemon["transition_reason"], "OWNER_STABLE")
        self.assertEqual(daemon["process_pid"], 3333)
        self.assertNotEqual(daemon["status"], "STOPPED")

    def test_parent_child_python_launcher_pair_is_not_duplicate_owner(self):
        summary = runtime_truth.classify_daemon_process_tree(
            [
                {
                    "pid": 16124,
                    "ppid": 24440,
                    "command": r"D:\TITAN\.venv\Scripts\python.exe titan_daemon.py",
                    "lock_owner": False,
                    "writes_runtime": False,
                },
                {
                    "pid": 11676,
                    "ppid": 16124,
                    "command": r"C:\Python311\python.exe titan_daemon.py",
                    "lock_owner": True,
                    "writes_runtime": True,
                    "evidence_paths": ["data/runtime/daemon_health.json", "data/runtime/locks/titan_daemon.lock"],
                },
            ],
            lock_pid=11676,
            runtime_writer_pid=11676,
        )

        by_pid = {item["pid"]: item for item in summary["processes"]}
        self.assertFalse(summary["duplicate_owner_conflict"])
        self.assertEqual(by_pid[11676]["classification"], "ACTIVE_OWNER")
        self.assertEqual(by_pid[16124]["classification"], "WRAPPER_PARENT")

    def test_two_independent_daemon_writers_are_duplicate_conflict(self):
        summary = runtime_truth.classify_daemon_process_tree(
            [
                {"pid": 1001, "ppid": 1, "command": "python titan_daemon.py", "lock_owner": True, "writes_runtime": True},
                {"pid": 2002, "ppid": 1, "command": "python titan_daemon.py", "lock_owner": False, "writes_runtime": True},
            ],
            lock_pid=1001,
        )

        self.assertTrue(summary["duplicate_owner_conflict"])
        classifications = {item["pid"]: item["classification"] for item in summary["processes"]}
        self.assertEqual(classifications[1001], "DUPLICATE_OWNER")
        self.assertEqual(classifications[2002], "DUPLICATE_OWNER")

    def test_stale_worker_running_becomes_stale(self):
        self._write_json(
            runtime_truth.WORKER_HEALTH_PATH,
            {"heartbeat": {"status": "RUNNING", "last_started_at": self._stale(), "last_finished_at": self._stale()}},
        )

        truth = runtime_truth.build_authoritative_runtime_truth(now=self.now, write=False)

        workers = truth["components"]["workers"]
        self.assertEqual(workers["status"], "STALE")
        self.assertIn("heartbeat", workers["stale_running_workers"])

    def test_missing_worker_active_pid_becomes_stale_pid(self):
        self._write_json(
            runtime_truth.WORKER_HEALTH_PATH,
            {"heartbeat": {"status": "RUNNING", "active_pid": 6488, "last_started_at": self._fresh()}},
        )

        workers = runtime_truth.classify_workers(now=self.now, process_checker=lambda pid: False)

        self.assertEqual(workers["status"], "STALE_PID")
        self.assertIn("heartbeat", workers["stale_pid_workers"])
        self.assertFalse(workers["workers"]["heartbeat"]["active_pid_visible"])

    def test_expired_proof_worker_pid_is_not_stale_pid(self):
        self._write_json(
            runtime_truth.WORKER_HEALTH_PATH,
            {
                "heartbeat": {
                    "status": "OK",
                    "active_pid": 6488,
                    "proof_mode": True,
                    "last_finished_at": self._stale(),
                }
            },
        )

        workers = runtime_truth.classify_workers(now=self.now, process_checker=lambda pid: False)

        self.assertEqual(workers["status"], "PROOF_EXPIRED")
        self.assertIn("heartbeat", workers["proof_expired_workers"])
        self.assertEqual(workers["stale_pid_workers"], [])
        self.assertFalse(workers["restart_blocker"])

    def test_stale_dashboard_status_cannot_be_live(self):
        stale_payload = {"status": "FULL_RUNTIME_PIPELINE_COMPLETE", "timestamp_ist": self._stale()}
        self._write_json(runtime_truth.DASHBOARD_SYNC_STATUS_PATH, stale_payload)

        dashboard = runtime_truth.classify_status_file(
            "dashboard_sync",
            runtime_truth.DASHBOARD_SYNC_STATUS_PATH,
            now=self.now,
        )

        self.assertEqual(dashboard["status"], "STALE_LIVE_CLAIM")
        self.assertTrue(dashboard["stale_live_claim"])
        self.assertNotEqual(dashboard["status"], "LIVE")

    def test_stale_scanner_live_claim_cannot_be_live(self):
        scanner_path = self.runtime / "scanner_status.json"
        final_path = self.runtime / "final_validated_setups.json"
        self._write_json(scanner_path, {"status": "FULL_RUNTIME_PIPELINE_COMPLETE", "timestamp_ist": self._stale()})
        self._write_json(final_path, {"setups": [], "timestamp_ist": self._stale()})

        scanner = classify_scanner_status(scanner_path, final_path, now=self.now)

        self.assertEqual(scanner["status"], "STALE_LIVE_CLAIM")
        self.assertTrue(scanner["stale_live_claim"])

    def test_stale_dashboard_active_flags_become_stale(self):
        stale = self._stale()
        self._write_json(runtime_truth.DAEMON_HEALTH_PATH, {"status": "STOPPED", "pid": 123456, "mode": "WEEKEND_MODE", "timestamp_ist": stale})
        self._write_json(runtime_truth.HEARTBEAT_PATH, {"status": "ALIVE", "pid": 123456, "mode": "WEEKEND_MODE", "timestamp_ist": stale})
        self._write_json(runtime_truth.SCANNER_STATUS_PATH, {"status": "SCAN_ONLY_COMPLETE", "timestamp_ist": stale, "scan_finished_at_ist": stale})
        self._write_json(runtime_truth.MASTER_BRAIN_STATUS_PATH, {"status": "MASTER_BRAIN_READ_ONLY_COMPLETE", "runtime_mode": "READ_ONLY", "timestamp_ist": stale})
        self._write_json(runtime_truth.PAPER_ENGINE_STATUS_PATH, {"status": "PAPER_ENGINE_MONITOR_ONLY_OUTSIDE_TRADE_WINDOW", "timestamp_ist": stale, "open_positions_count": 0})

        sources = {
            "titan_heartbeat": runtime_truth.HEARTBEAT_PATH,
            "daemon_health": runtime_truth.DAEMON_HEALTH_PATH,
            "titan_runtime_status": self.runtime / "titan_runtime_status.json",
            "scanner_status": runtime_truth.SCANNER_STATUS_PATH,
            "final_validated_setups": self.runtime / "final_validated_setups.json",
            "setup_engine_status": runtime_truth.SETUP_ENGINE_STATUS_PATH,
            "live_price_monitor_status": self.runtime / "live_price_monitor_status.json",
            "master_brain_status": runtime_truth.MASTER_BRAIN_STATUS_PATH,
            "paper_engine_status": runtime_truth.PAPER_ENGINE_STATUS_PATH,
            "news_pulse_status": self.runtime / "news_pulse_status.json",
            "light_news_pulse_status": self.runtime / "light_news_pulse_status.json",
            "news_intelligence_status": self.runtime / "news_intelligence_status.json",
            "runtime_resilience_status": self.runtime / "runtime_resilience_status.json",
            "pyramid_governance_status": self.runtime / "pyramid_governance_status.json",
            "weekend_research_mode_status": self.runtime / "weekend_research_mode_status.json",
        }
        self._write_json(sources["titan_runtime_status"], {"mode": "WEEKEND_MODE", "timestamp_ist": stale})

        with patch.object(runtime_truth, "process_visible", return_value=False), patch.object(
            runtime_dashboard_sync, "RUNTIME_STATUS_SOURCES", sources
        ), patch.object(
            runtime_dashboard_sync, "DASHBOARD_SYNC_STATUS_PATH", self.runtime / "dashboard_sync_status.json"
        ), patch.object(
            runtime_dashboard_sync, "upsert_runtime_status_rows", return_value={"supabase_sync_enabled": False}
        ):
            payload = runtime_dashboard_sync.run_dashboard_sync(path=self.runtime / "dashboard_sync_status.json")

        summary = payload["autonomous_runtime_summary"]
        self.assertFalse(summary["daemon_alive"])
        self.assertFalse(summary["scanner_active"])
        self.assertFalse(summary["master_brain_active"])
        self.assertFalse(summary["paper_engine_active"])
        self.assertIn(summary["component_truth_statuses"]["scanner"], {"STALE", "ASLEEP_EXPECTED", "STALE_LIVE_CLAIM"})
        self.assertEqual(summary["component_truth_statuses"]["master_brain"], "STALE_LIVE_CLAIM")

    def test_marker_only_setup_engine_is_not_real_active(self):
        self._write_json(
            runtime_truth.SETUP_ENGINE_STATUS_PATH,
            {
                "status": "SETUP_ENGINE_MARKER_UPDATED",
                "marker_only": True,
                "real_setup_engine_called": False,
                "timestamp_ist": self._fresh(),
            },
        )

        truth = runtime_truth.build_authoritative_runtime_truth(now=self.now, write=False)

        setup = truth["components"]["setup_engine"]
        self.assertEqual(setup["status"], "MARKER_ONLY")
        self.assertEqual(setup["reason"], "marker_only_status_not_runtime_liveness")

    def test_read_only_master_brain_is_not_execution_active(self):
        self._write_json(
            runtime_truth.MASTER_BRAIN_STATUS_PATH,
            {
                "status": "MASTER_BRAIN_READ_ONLY_COMPLETE",
                "runtime_mode": "READ_ONLY",
                "observe_only": True,
                "live_execution_enabled": False,
                "timestamp_ist": self._fresh(),
            },
        )

        truth = runtime_truth.build_authoritative_runtime_truth(now=self.now, write=False)

        master = truth["components"]["master_brain"]
        self.assertEqual(master["status"], "MARKER_ONLY")
        self.assertEqual(master["reason"], "fresh_but_not_execution_active")


if __name__ == "__main__":
    unittest.main()
