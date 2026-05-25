import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_artifact_registry
import runtime_mode_resolver
import runtime_topology
import runtime_watchdog
from utils.market_hours import IST


class Batch13RuntimeCleanlinessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.lock_dir = self.runtime_dir / "locks"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 19, 45, tzinfo=IST)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_conflicting_raw_modes_resolve_to_canonical_mode(self):
        fresh = self.now.isoformat()
        stale = (self.now - timedelta(hours=2)).isoformat()
        paths = {
            "runtime_mode_status": self.runtime_dir / "runtime_mode_status.json",
            "runtime_status": self.runtime_dir / "titan_runtime_status.json",
            "runtime_health": self.runtime_dir / "titan_authoritative_runtime_health.json",
            "scanner_status": self.runtime_dir / "scanner_status.json",
            "daemon_health": self.runtime_dir / "daemon_health.json",
            "heartbeat": self.runtime_dir / "titan_heartbeat.json",
            "setup_engine_status": self.runtime_dir / "setup_engine_status.json",
            "master_brain_status": self.runtime_dir / "master_brain_status.json",
        }
        self._write_json(paths["runtime_mode_status"], {"current_mode": "RESEARCH_MODE", "generated_at": fresh})
        self._write_json(paths["runtime_status"], {"runtime_mode": {"current_mode": "RESEARCH_MODE"}, "timestamp_ist": fresh})
        self._write_json(paths["runtime_health"], {"current_mode": "RESEARCH_MODE", "generated_at_ist": fresh})
        self._write_json(paths["setup_engine_status"], {"mode": "INTELLIGENCE_MODE", "timestamp_ist": fresh})
        self._write_json(paths["master_brain_status"], {"runtime_mode": "READ_ONLY", "timestamp_ist": fresh})
        self._write_json(paths["scanner_status"], {"mode": "FULL_RUNTIME_PIPELINE", "timestamp_ist": stale})
        self._write_json(paths["daemon_health"], {"mode": "WEEKEND_MODE", "timestamp_ist": stale})
        self._write_json(paths["heartbeat"], {"mode": "MARKET_MODE", "timestamp_ist": stale})

        with patch.object(runtime_mode_resolver, "MODE_SOURCES", paths), patch.object(
            runtime_mode_resolver, "CANONICAL_RUNTIME_MODE_PATH", self.runtime_dir / "canonical_runtime_mode.json"
        ), patch.object(
            runtime_mode_resolver,
            "RUNTIME_WARNING_RESOLUTION_STATUS_PATH",
            self.runtime_dir / "runtime_warning_resolution_status.json",
        ), patch.object(
            runtime_mode_resolver,
            "runtime_mode_snapshot",
            return_value={"current_mode": "RESEARCH_MODE", "generated_at": fresh},
        ):
            canonical = runtime_mode_resolver.build_canonical_runtime_mode(now=self.now)
            resolution = runtime_mode_resolver.build_runtime_warning_resolution_status(
                canonical=canonical,
                now=self.now,
            )

        self.assertEqual(canonical["canonical_mode"], "RESEARCH_MODE")
        self.assertEqual(canonical["resolution_status"], "DOWNGRADED_STALE_RAW_MODE_CONFLICT")
        self.assertTrue(canonical["topology_warning_reduction_allowed"])
        self.assertEqual(resolution["runtime_warning_resolution_status"], "PASS")
        self.assertTrue(resolution["conflicting_runtime_modes"]["resolved_by_canonical_mode"])

    def test_topology_downgrades_stale_only_mode_conflict(self):
        sources = {
            "runtime_status": {"mode": "INTELLIGENCE_MODE"},
            "scanner_status": {"mode": "FULL_RUNTIME_PIPELINE"},
            "daemon_health": {"mode": "WEEKEND_MODE"},
            "heartbeat": {"mode": "MARKET_MODE"},
        }
        canonical = {"topology_warning_reduction_allowed": True}

        conflicts, downgraded = runtime_topology.detect_runtime_conflicts(sources, canonical_runtime_mode=canonical)

        self.assertNotIn("conflicting_runtime_modes", conflicts)
        self.assertIn("conflicting_runtime_modes", downgraded)

    def test_benign_child_pid_mismatch_when_owner_confirmed(self):
        timestamp = self.now.isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "RUNNING", "pid": 1111, "timestamp_ist": timestamp})
        self._write_json(self.runtime_dir / "titan_heartbeat.json", {"status": "ALIVE", "pid": 2222, "timestamp_ist": timestamp})
        self._write_json(self.lock_dir / "titan_daemon.lock", {"name": "titan_daemon", "pid": 1111, "acquired_at_ist": timestamp})
        sources = {
            name: {**spec, "path": self.runtime_dir / spec["path"].name}
            for name, spec in runtime_watchdog.RUNTIME_SOURCES.items()
        }
        sources["daemon_lock"]["path"] = self.lock_dir / "titan_daemon.lock"

        with patch.object(runtime_watchdog, "RUNTIME_SOURCES", sources), patch.object(
            runtime_watchdog,
            "_process_visible",
            side_effect=lambda pid: int(pid) == 1111,
        ), patch.object(
            runtime_watchdog,
            "_process_command",
            side_effect=lambda pid: "python -m multiprocessing.resource_tracker" if int(pid) == 2222 else "python titan_daemon.py",
        ):
            status = runtime_watchdog.build_runtime_reconciliation_status(now=self.now)

        self.assertEqual(status["deterministic_runtime_owner"], "confirmed_daemon_pid")
        self.assertNotIn("daemon_health_heartbeat_pid_mismatch", status["remaining_contradictions"])
        self.assertEqual(status["benign_pid_mismatches"][0]["classification"], "benign_child_pid_mismatch")

    def test_no_false_pass_when_owner_unknown(self):
        timestamp = self.now.isoformat()
        self._write_json(self.runtime_dir / "daemon_health.json", {"status": "RUNNING", "pid": 1111, "timestamp_ist": timestamp})
        self._write_json(self.runtime_dir / "titan_heartbeat.json", {"status": "ALIVE", "pid": 2222, "timestamp_ist": timestamp})
        sources = {
            name: {**spec, "path": self.runtime_dir / spec["path"].name}
            for name, spec in runtime_watchdog.RUNTIME_SOURCES.items()
        }
        sources["daemon_lock"]["path"] = self.lock_dir / "titan_daemon.lock"

        with patch.object(runtime_watchdog, "RUNTIME_SOURCES", sources), patch.object(
            runtime_watchdog,
            "_process_visible",
            return_value=False,
        ), patch.object(
            runtime_watchdog,
            "_process_command",
            return_value="python -m multiprocessing.resource_tracker",
        ):
            status = runtime_watchdog.build_runtime_reconciliation_status(now=self.now)

        self.assertNotEqual(status["deterministic_runtime_owner"], "confirmed_daemon_pid")
        self.assertIn("daemon_health_heartbeat_pid_mismatch", status["remaining_contradictions"])
        self.assertFalse(status["benign_pid_mismatches"])

    def test_runtime_critical_chain_distinguishes_expected_lag(self):
        critical_chain = {
            name: {**spec, "path": self.runtime_dir / spec["path"].name}
            for name, spec in runtime_artifact_registry.RUNTIME_CRITICAL_CHAIN.items()
        }
        fresh = self.now.isoformat()
        stale = (self.now - timedelta(hours=2)).isoformat()
        for name, spec in critical_chain.items():
            self._write_json(
                spec["path"],
                {"status": "OK", "timestamp_ist": stale if name == "scanner" else fresh},
            )

        with patch.object(runtime_artifact_registry, "RUNTIME_CRITICAL_CHAIN", critical_chain), patch.object(
            runtime_artifact_registry,
            "RUNTIME_CRITICAL_CHAIN_PATH",
            self.runtime_dir / "runtime_critical_chain_status.json",
        ), patch.object(
            runtime_artifact_registry,
            "RUNTIME_CRITICAL_CHAIN_CLEANLINESS_PATH",
            self.runtime_dir / "runtime_critical_chain_cleanliness.json",
        ), patch.object(
            runtime_artifact_registry,
            "build_canonical_runtime_mode",
            return_value={"canonical_mode": "RESEARCH_MODE"},
        ):
            status = runtime_artifact_registry.build_runtime_critical_chain_status(now=self.now, graph={"nodes": {}})

        self.assertEqual(status["runtime_critical_chain_status"], "PASS")
        self.assertIn("scanner", status["expected_mode_transition_lag_nodes"])
        self.assertFalse(status["dangerous_stale_critical_nodes"])

    def test_no_live_mutation_flags_enabled(self):
        canonical = {
            "resolution_status": "PASS",
            "canonical_mode": "RESEARCH_MODE",
            "canonical_source": "runtime_mode_status",
            "raw_conflicts_visible": [],
        }
        status = runtime_mode_resolver.build_runtime_warning_resolution_status(
            canonical=canonical,
            path=self.runtime_dir / "runtime_warning_resolution_status.json",
            now=self.now,
        )

        self.assertTrue(status["safety_flags"]["advisory_only"])
        for enabled in status["mutation_controls"].values():
            self.assertFalse(enabled)


if __name__ == "__main__":
    unittest.main()
