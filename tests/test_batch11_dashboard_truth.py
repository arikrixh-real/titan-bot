import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import dashboard_truth_foundation
from utils.market_hours import IST


class Batch11DashboardTruthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _patch_paths(self):
        return patch.multiple(
            dashboard_truth_foundation,
            RUNTIME_DIR=self.runtime_dir,
            DASHBOARD_TRUTH_REGISTRY_PATH=self.runtime_dir / "dashboard_truth_registry.json",
            METRIC_DEPENDENCY_GRAPH_PATH=self.runtime_dir / "metric_dependency_graph.json",
            CANONICAL_METRIC_OWNERSHIP_PATH=self.runtime_dir / "canonical_metric_ownership.json",
            DASHBOARD_RUNTIME_INTEGRITY_PATH=self.runtime_dir / "dashboard_runtime_integrity.json",
        )

    def _specs(self, runtime_status_path=None, ranking_path=None):
        runtime_status_path = runtime_status_path or self.runtime_dir / "titan_runtime_status.json"
        ranking_path = ranking_path or self.runtime_dir / "ranking_integrity_status.json"
        return {
            "runtime_mode": {
                "owner": "titan_runtime_status",
                "artifact_path": runtime_status_path,
                "field": "mode",
                "classification": "runtime_critical",
                "fresh_seconds": 900,
                "dependencies": ["authoritative_runtime_health"],
            },
            "ranking_integrity_score": {
                "owner": "ranking_integrity",
                "artifact_path": ranking_path,
                "field": "ranking_integrity_score",
                "classification": "runtime_critical",
                "fresh_seconds": 86400,
                "dependencies": ["final_decision_engine"],
            },
            "topology_health": {
                "owner": "runtime_topology",
                "artifact_path": self.runtime_dir / "titan_runtime_topology.json",
                "field": "topology_health",
                "classification": "advisory",
                "fresh_seconds": 86400,
                "dependencies": ["runtime_dependency_graph"],
            },
            "live_trades_count": {
                "owner": "supabase_trades_read_only",
                "artifact_path": None,
                "field": "open_trade_count",
                "classification": "external_readonly",
                "fresh_seconds": 900,
                "dependencies": ["supabase_read_only_client"],
            },
        }

    def test_canonical_metric_ownership_classifies_metric_roles(self):
        self._write_json(
            self.runtime_dir / "titan_runtime_status.json",
            {"status": "OK", "mode": "MARKET_MODE", "timestamp_ist": self.now.isoformat()},
        )
        self._write_json(
            self.runtime_dir / "ranking_integrity_status.json",
            {"status": "OK", "ranking_integrity_score": 100, "generated_at_ist": self.now.isoformat()},
        )
        self._write_json(
            self.runtime_dir / "titan_runtime_topology.json",
            {"status": "OK", "topology_health": "PASS", "generated_at_ist": self.now.isoformat()},
        )

        with self._patch_paths():
            ownership = dashboard_truth_foundation.build_canonical_metric_ownership(
                metric_specs=self._specs(),
                now=self.now,
            )

        self.assertEqual(ownership["canonical_metric_ownership_status"], "PASS")
        self.assertEqual(ownership["runtime_critical_metric_count"], 2)
        self.assertEqual(ownership["advisory_metric_count"], 1)
        self.assertEqual(ownership["external_readonly_metric_count"], 1)
        self.assertTrue(ownership["metrics"]["runtime_mode"]["runtime_critical"])
        self.assertTrue(ownership["metrics"]["topology_health"]["advisory"])
        self.assertTrue(ownership["metrics"]["live_trades_count"]["external_readonly"])

    def test_stale_runtime_critical_metric_is_detected(self):
        stale_time = (self.now - timedelta(seconds=1200)).isoformat()
        self._write_json(
            self.runtime_dir / "titan_runtime_status.json",
            {"status": "OK", "mode": "MARKET_MODE", "timestamp_ist": stale_time},
        )

        with self._patch_paths():
            ownership = dashboard_truth_foundation.build_canonical_metric_ownership(
                metric_specs={"runtime_mode": self._specs()["runtime_mode"]},
                now=self.now,
            )

        self.assertEqual(ownership["canonical_metric_ownership_status"], "WARNING")
        self.assertIn("runtime_mode", ownership["stale_runtime_critical_metrics"])
        self.assertTrue(ownership["metrics"]["runtime_mode"]["stale_runtime_critical_metric"])

    def test_metric_dependency_graph_links_owners_and_dependencies(self):
        self._write_json(
            self.runtime_dir / "titan_runtime_status.json",
            {"status": "OK", "mode": "MARKET_MODE", "timestamp_ist": self.now.isoformat()},
        )
        with self._patch_paths():
            ownership = dashboard_truth_foundation.build_canonical_metric_ownership(
                metric_specs={"runtime_mode": self._specs()["runtime_mode"]},
                now=self.now,
            )
            graph = dashboard_truth_foundation.build_metric_dependency_graph(ownership=ownership, now=self.now)

        self.assertEqual(graph["metric_dependency_graph_status"], "PASS")
        self.assertIn("titan_runtime_status", graph["owner_nodes"])
        self.assertIn({"from": "titan_runtime_status", "to": "runtime_mode", "type": "owns_metric"}, graph["dependencies"])
        self.assertIn({"from": "authoritative_runtime_health", "to": "runtime_mode", "type": "upstream_dependency"}, graph["dependencies"])

    def test_dashboard_runtime_integrity_reports_missing_local_owner(self):
        with self._patch_paths():
            ownership = dashboard_truth_foundation.build_canonical_metric_ownership(
                metric_specs={"runtime_mode": self._specs()["runtime_mode"]},
                now=self.now,
            )
            graph = dashboard_truth_foundation.build_metric_dependency_graph(ownership=ownership, now=self.now)
            registry = dashboard_truth_foundation.build_dashboard_truth_registry(
                ownership=ownership,
                dependency_graph=graph,
                now=self.now,
            )
            integrity = dashboard_truth_foundation.build_dashboard_runtime_integrity(
                registry=registry,
                ownership=ownership,
                dependency_graph=graph,
                now=self.now,
            )

        self.assertEqual(integrity["dashboard_runtime_integrity_status"], "WARNING")
        self.assertIn("runtime_mode", integrity["missing_local_metric_owners"])
        self.assertTrue(integrity["dashboard_backend_truth_stabilized"])

    def test_batch11_generates_required_artifacts_without_live_mutation_flags(self):
        self._write_json(
            self.runtime_dir / "titan_runtime_status.json",
            {"status": "OK", "mode": "MARKET_MODE", "timestamp_ist": self.now.isoformat()},
        )
        self._write_json(
            self.runtime_dir / "ranking_integrity_status.json",
            {"status": "OK", "ranking_integrity_score": 100, "generated_at_ist": self.now.isoformat()},
        )
        self._write_json(
            self.runtime_dir / "titan_runtime_topology.json",
            {"status": "OK", "topology_health": "PASS", "generated_at_ist": self.now.isoformat()},
        )

        with self._patch_paths(), patch.object(
            dashboard_truth_foundation,
            "DASHBOARD_METRIC_SPECS",
            self._specs(),
        ):
            result = dashboard_truth_foundation.run_batch11_dashboard_truth_foundation(now=self.now)

        self.assertEqual(result["status"], "PASS")
        for path in result["artifacts"].values():
            self.assertTrue(Path(path).exists())
        self.assertTrue(result["safety_flags"]["advisory_only"])
        self.assertFalse(result["safety_flags"]["affects_execution"])
        self.assertFalse(result["safety_flags"]["affects_live_ranking"])


if __name__ == "__main__":
    unittest.main()
