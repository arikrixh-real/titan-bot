import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_dashboard_sync
import runtime_truth
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

    def test_stale_worker_running_becomes_stale(self):
        self._write_json(
            runtime_truth.WORKER_HEALTH_PATH,
            {"heartbeat": {"status": "RUNNING", "last_started_at": self._stale(), "last_finished_at": self._stale()}},
        )

        truth = runtime_truth.build_authoritative_runtime_truth(now=self.now, write=False)

        workers = truth["components"]["workers"]
        self.assertEqual(workers["status"], "STALE")
        self.assertIn("heartbeat", workers["stale_running_workers"])

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
        self.assertEqual(summary["component_truth_statuses"]["scanner"], "STALE")
        self.assertEqual(summary["component_truth_statuses"]["master_brain"], "STALE")

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
