import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import integrity_monitor
from utils.market_hours import IST


class Batch9IntegrityMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _patch_paths(self):
        return patch.multiple(
            integrity_monitor,
            RUNTIME_DIR=self.runtime_dir,
            TITAN_INTEGRITY_MONITOR_PATH=self.runtime_dir / "titan_integrity_monitor.json",
            RUNTIME_REGRESSION_AUDIT_PATH=self.runtime_dir / "runtime_regression_audit.json",
            DEPENDENCY_REGRESSION_STATUS_PATH=self.runtime_dir / "dependency_regression_status.json",
            RANKING_REGRESSION_STATUS_PATH=self.runtime_dir / "ranking_regression_status.json",
            MEMORY_REGRESSION_STATUS_PATH=self.runtime_dir / "memory_regression_status.json",
        )

    def test_runtime_regression_detects_owner_drift_and_stale_artifacts(self):
        watchdog = {
            "runtime_owner": "none_confirmed",
            "runtime_ownership_deterministic": True,
            "remaining_contradictions": ["heartbeat_alive_but_stale"],
            "stale_writer_count": 2,
        }
        registry = {
            "artifacts": [
                {
                    "path": "data/runtime/scanner_status.json",
                    "scope": "runtime_critical_chain",
                    "role": "runtime_critical",
                    "runtime_critical": True,
                    "stale": True,
                    "status": "STALE",
                    "age_seconds": 1000,
                    "fresh_seconds": 900,
                }
            ]
        }

        with self._patch_paths():
            audit = integrity_monitor.build_runtime_regression_audit(watchdog=watchdog, registry=registry, now=self.now)

        self.assertEqual(audit["runtime_regression_status"], "WARNING")
        self.assertTrue(audit["runtime_drift_detection"]["owner_drift_detected"])
        self.assertEqual(audit["stale_runtime_critical_artifact_count"], 1)
        self.assertFalse(audit["safety_flags"]["affects_execution"])

    def test_dependency_regression_detects_disconnected_engine(self):
        graph = {
            "dependency_status": "WARNING",
            "dependency_integrity_score": 70.0,
            "connected_engines": ["scanner"],
            "disconnected_engines": ["execution_engine"],
            "stale_engines": ["scanner"],
        }

        with self._patch_paths():
            status = integrity_monitor.build_dependency_regression_status(graph=graph, now=self.now)

        self.assertEqual(status["dependency_regression_status"], "WARNING")
        self.assertTrue(status["dependency_graph_integrity"]["disconnected_engine_regression_detected"])
        self.assertIn("dependency_integrity_score_below_threshold", status["warnings"])

    def test_ranking_regression_fails_on_owner_change(self):
        ranking = {
            "ranking_integrity_score": 100.0,
            "authoritative_owner": "other_engine",
            "ranking_chain_valid": True,
            "conflicting_mutators": [],
            "dangerous_live_overrides": [],
            "duplicate_rank_writers": {},
        }

        with self._patch_paths():
            status = integrity_monitor.build_ranking_regression_status(ranking=ranking, now=self.now)

        self.assertEqual(status["ranking_regression_status"], "FAIL")
        self.assertIn("authoritative_ranking_owner_changed", status["failures"])

    def test_memory_regression_detects_lineage_and_stale_memory(self):
        memory = {
            "memory_integrity_score": 100.0,
            "memory_freshness_score": 50.0,
            "lineage_integrity_score": 70.0,
            "stale_memory_files": 2,
            "orphan_memory_files": 1,
            "corrupted_memory_files": 0,
            "missing_expected_memory_files": 0,
            "memory_lineage_summary": {
                "dead_memory_chains": ["old_memory"],
                "orphan_lineage_breaks": ["old_memory"],
            },
            "memory_contribution_summary": {
                "memory_files_contributing_nothing": ["old_memory"],
            },
        }

        with self._patch_paths():
            status = integrity_monitor.build_memory_regression_status(memory=memory, now=self.now)

        self.assertEqual(status["memory_regression_status"], "WARNING")
        self.assertTrue(status["memory_lineage_integrity_detection"]["lineage_regression_detected"])
        self.assertIn("stale_memory_regression", status["warnings"])

    def test_integrity_monitor_generates_required_artifacts(self):
        graph = {
            "dependency_status": "PASS",
            "dependency_integrity_score": 100.0,
            "connected_engines": ["scanner"],
            "disconnected_engines": [],
            "stale_engines": [],
        }
        watchdog = {
            "runtime_owner": "confirmed_daemon_pid",
            "authoritative_pid": 123,
            "owner_confidence": "HIGH",
            "runtime_ownership_deterministic": True,
            "stale_writer_count": 0,
            "remaining_contradictions": [],
        }
        registry = {"artifacts": []}
        ranking = {
            "ranking_integrity_score": 100.0,
            "authoritative_owner": "final_decision_engine",
            "ranking_chain_valid": True,
            "conflicting_mutators": [],
            "dangerous_live_overrides": [],
            "duplicate_rank_writers": {},
        }
        memory = {
            "memory_integrity_score": 100.0,
            "memory_freshness_score": 100.0,
            "lineage_integrity_score": 100.0,
            "stale_memory_files": 0,
            "orphan_memory_files": 0,
            "corrupted_memory_files": 0,
            "missing_expected_memory_files": 0,
            "memory_lineage_summary": {},
            "memory_contribution_summary": {},
        }

        with self._patch_paths(), patch.object(integrity_monitor, "build_runtime_dependency_graph", return_value=graph), patch.object(
            integrity_monitor, "build_titan_runtime_watchdog", return_value=watchdog
        ), patch.object(integrity_monitor, "build_runtime_artifact_registry", return_value=registry), patch.object(
            integrity_monitor, "build_ranking_integrity_status", return_value=ranking
        ), patch.object(integrity_monitor, "run_memory_health_check", return_value=memory):
            result = integrity_monitor.run_batch9_integrity_monitor(now=self.now)

        self.assertEqual(result["status"], "PASS")
        for path in result["artifacts"].values():
            self.assertTrue(Path(path).exists())
        self.assertTrue(result["safety_flags"]["advisory_only"])
        self.assertFalse(result["safety_flags"]["affects_live_ranking"])
        self.assertFalse(result["safety_flags"]["affects_execution"])


if __name__ == "__main__":
    unittest.main()
