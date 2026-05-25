import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import final_operational_stabilization
from utils.market_hours import IST


class Batch12FinalOperationalStabilizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _patch_paths(self):
        return patch.multiple(
            final_operational_stabilization,
            RUNTIME_DIR=self.runtime_dir,
            TITAN_FINAL_OPERATIONAL_AUDIT_PATH=self.runtime_dir / "titan_final_operational_audit.json",
            TITAN_STABILITY_SCORE_PATH=self.runtime_dir / "titan_stability_score.json",
            TITAN_DEPENDENCY_CERTIFICATION_PATH=self.runtime_dir / "titan_dependency_certification.json",
            TITAN_RUNTIME_CERTIFICATION_PATH=self.runtime_dir / "titan_runtime_certification.json",
        )

    def test_dependency_certification_warns_on_stale_engines(self):
        graph = {
            "dependency_status": "WARNING",
            "dependency_integrity_score": 88.0,
            "connected_engines": ["runtime_status"],
            "disconnected_engines": [],
            "stale_engines": ["scanner"],
        }
        topology = {"topology_health": "WARNING"}

        with self._patch_paths():
            cert = final_operational_stabilization.build_titan_dependency_certification(
                graph=graph,
                topology=topology,
                now=self.now,
            )

        self.assertEqual(cert["titan_dependency_certification_status"], "WARNING")
        self.assertEqual(cert["stale_engine_count"], 1)
        self.assertTrue(cert["dependency_chain_stable"])

    def test_runtime_certification_blocks_auto_restart_and_reports_stale_sources(self):
        topology = {
            "runtime_integrity_score": 40.0,
            "runtime_consistency_score": 55.0,
            "topology_health": "WARNING",
            "stale_runtime_sources": ["heartbeat"],
            "runtime_conflicts": ["heartbeat_alive_but_daemon_stopped"],
        }
        watchdog = {
            "status": "WARNING",
            "summary": {
                "runtime_owner": "none_confirmed",
                "authoritative_pid": None,
                "owner_confidence": "LOW",
                "automatic_restart_allowed": False,
                "automatic_process_kill_allowed": False,
                "auto_healing_mutation_allowed": False,
            },
        }
        artifact_isolation = {"summary": {"runtime_critical_chain_status": "WARNING"}}

        with self._patch_paths():
            cert = final_operational_stabilization.build_titan_runtime_certification(
                topology=topology,
                watchdog=watchdog,
                artifact_isolation=artifact_isolation,
                now=self.now,
            )

        self.assertEqual(cert["titan_runtime_certification_status"], "WARNING")
        self.assertFalse(cert["automatic_restart_allowed"])
        self.assertFalse(cert["automatic_process_kill_allowed"])
        self.assertIn("heartbeat", cert["stale_runtime_sources"])

    def test_stability_score_uses_required_scores(self):
        topology = {"topology_health": "PASS"}
        dependency = {"titan_dependency_certification_status": "PASS", "dependency_integrity_score": 100.0}
        runtime = {"titan_runtime_certification_status": "PASS", "runtime_integrity_score": 100.0}
        ranking = {"ranking_integrity_score": 100.0, "authoritative_owner": "final_decision_engine"}
        memory = {"memory_integrity_score": 100.0}
        mutation = {"status": "PASS"}
        dashboard = {"status": "PASS"}

        with self._patch_paths():
            score = final_operational_stabilization.build_titan_stability_score(
                topology=topology,
                dependency=dependency,
                runtime=runtime,
                ranking=ranking,
                memory=memory,
                mutation=mutation,
                dashboard=dashboard,
                now=self.now,
            )

        self.assertEqual(score["titan_stability_score_status"], "PASS")
        self.assertEqual(score["stability_score"], 100.0)
        self.assertEqual(score["ranking_integrity_score"], 100.0)

    def test_stability_score_reports_clock_skew_for_future_dated_artifacts(self):
        topology = {"topology_health": "PASS"}
        dependency = {"titan_dependency_certification_status": "PASS", "dependency_integrity_score": 100.0}
        runtime = {"titan_runtime_certification_status": "PASS", "runtime_integrity_score": 100.0}
        ranking = {"ranking_integrity_score": 100.0, "authoritative_owner": "final_decision_engine"}
        memory = {"memory_integrity_score": 100.0}
        mutation = {"status": "PASS"}
        dashboard = {"status": "PASS"}
        future_timestamp = datetime(2026, 5, 25, 10, 5, tzinfo=IST).isoformat()
        future_artifact = self.runtime_dir / "future_runtime_artifact.json"
        future_artifact.write_text(
            json.dumps({"generated_at_ist": future_timestamp}),
            encoding="utf-8",
        )
        os.utime(future_artifact, (self.now.timestamp(), self.now.timestamp()))

        with self._patch_paths():
            score = final_operational_stabilization.build_titan_stability_score(
                topology=topology,
                dependency=dependency,
                runtime=runtime,
                ranking=ranking,
                memory=memory,
                mutation=mutation,
                dashboard=dashboard,
                now=self.now,
            )

        self.assertEqual(score["titan_stability_score_status"], "WARNING")
        self.assertEqual(score["runtime_clock_ist"], self.now.isoformat())
        self.assertEqual(score["max_artifact_timestamp_ist"], future_timestamp)
        self.assertTrue(score["clock_skew_detected"])
        self.assertEqual(score["future_artifact_count"], 1)
        self.assertEqual(score["clock_skew_warning"], "CLOCK_SKEW_WARNING")
        self.assertFalse(score["freshness_certification_reliable"])
        self.assertIn("CLOCK_SKEW_WARNING", score["warnings"])

    def test_final_audit_fails_if_ranking_owner_changes(self):
        topology = {"topology_health": "PASS", "runtime_integrity_score": 100.0, "runtime_consistency_score": 100.0}
        graph = {"dependency_status": "PASS", "dependency_integrity_score": 100.0, "connected_engines": [], "disconnected_engines": [], "stale_engines": []}
        memory = {"overall_status": "PASS", "memory_integrity_score": 100.0}
        ranking = {"ranking_integrity_score": 100.0, "authoritative_owner": "other", "ranking_chain_valid": True, "dangerous_live_overrides": []}
        integrity = {"integrity_monitor_status": "PASS"}
        artifact = {"status": "PASS", "summary": {"runtime_critical_chain_status": "PASS", "dead_chains": 0, "isolated_advisory_dead_chains": 0}}
        watchdog = {"status": "PASS", "summary": {"runtime_owner": "confirmed_daemon_pid", "automatic_restart_allowed": False, "automatic_process_kill_allowed": False}}
        mutation = {"status": "PASS", "summary": {"unsafe_live_mutation_vector_count": 0, "leaking_system_count": 0}}
        dashboard = {"status": "PASS"}

        with self._patch_paths(), patch.object(final_operational_stabilization, "build_runtime_topology", return_value=topology), patch.object(
            final_operational_stabilization, "build_runtime_dependency_graph", return_value=graph
        ), patch.object(final_operational_stabilization, "run_memory_health_check", return_value=memory), patch.object(
            final_operational_stabilization, "build_ranking_integrity_status", return_value=ranking
        ), patch.object(final_operational_stabilization, "build_titan_integrity_monitor", return_value=integrity), patch.object(
            final_operational_stabilization, "run_batch7_artifact_isolation", return_value=artifact
        ), patch.object(final_operational_stabilization, "run_batch8_runtime_watchdog", return_value=watchdog), patch.object(
            final_operational_stabilization, "run_batch10_mutation_containment", return_value=mutation
        ), patch.object(final_operational_stabilization, "run_batch11_dashboard_truth_foundation", return_value=dashboard):
            audit = final_operational_stabilization.build_titan_final_operational_audit(now=self.now)

        self.assertEqual(audit["titan_final_operational_audit_status"], "FAIL")
        self.assertIn("ranking_fail", audit["failures"])
        self.assertIn("ranking_owner_changed", audit["failures"])

    def test_batch12_generates_required_artifacts_and_safety_flags(self):
        audit = {
            "generated_at_ist": self.now.isoformat(),
            "titan_final_operational_audit_status": "PASS",
            "runtime_integrity_score": 100.0,
            "topology_health": "PASS",
            "stability_score": 100.0,
            "dependency_integrity_score": 100.0,
            "ranking_integrity_score": 100.0,
            "memory_integrity_score": 100.0,
            "component_statuses": {},
            "warnings": [],
            "failures": [],
        }

        with self._patch_paths(), patch.object(
            final_operational_stabilization,
            "build_titan_final_operational_audit",
            return_value=audit,
        ):
            result = final_operational_stabilization.run_batch12_final_operational_stabilization(now=self.now)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["summary"]["stability_score"], 100.0)
        self.assertTrue(result["safety_flags"]["advisory_only"])
        self.assertFalse(result["safety_flags"]["affects_execution"])
        self.assertFalse(result["safety_flags"]["affects_live_ranking"])


if __name__ == "__main__":
    unittest.main()
