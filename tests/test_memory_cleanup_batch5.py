import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import legacy_engine_visibility
import memory_cleanup_policy
import memory_contribution_tracker
import memory_freshness_audit
import memory_health
import memory_lineage
import runtime_dependency_graph
from utils.market_hours import IST


class MemoryCleanupBatch5Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.memory_dir = self.root / "memory"
        self.runtime_dir = self.root / "runtime"
        self.reports_dir = self.root / "reports"
        self.now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
        self.old = self.now - timedelta(days=10)
        self.patchers = [
            patch.object(memory_freshness_audit, "MEMORY_DIR", self.memory_dir),
            patch.object(memory_freshness_audit, "RUNTIME_DIR", self.runtime_dir),
            patch.object(memory_freshness_audit, "REPORTS_DIR", self.reports_dir),
            patch.object(memory_lineage, "MEMORY_DIR", self.memory_dir),
            patch.object(memory_lineage, "RUNTIME_DIR", self.runtime_dir),
            patch.object(memory_lineage, "LINEAGE_PATH", self.runtime_dir / "memory_lineage_graph.json"),
            patch.object(memory_contribution_tracker, "CONTRIBUTION_PATH", self.runtime_dir / "memory_contribution_status.json"),
            patch.object(memory_cleanup_policy, "MEMORY_DIR", self.memory_dir),
            patch.object(memory_cleanup_policy, "CLEANUP_POLICY_PATH", self.runtime_dir / "memory_cleanup_policy.json"),
            patch.object(memory_health, "MEMORY_HEALTH_PATH", self.runtime_dir / "titan_memory_health.json"),
            patch.object(legacy_engine_visibility, "RUNTIME_DIR", self.runtime_dir),
            patch.object(legacy_engine_visibility, "MEMORY_DIR", self.memory_dir),
            patch.object(legacy_engine_visibility, "REPORTS_DIR", self.reports_dir),
            patch.object(legacy_engine_visibility, "LEGACY_VISIBILITY_PATH", self.runtime_dir / "legacy_engine_visibility_status.json"),
        ]
        for patcher in self.patchers:
            patcher.start()

        legacy_specs = {
            "reinforcement_learning": {
                "module": "engines.reinforcement_learning_layer",
                "memory": self.memory_dir / "reinforcement_learning_memory.json",
                "status": self.runtime_dir / "reinforcement_learning_status.json",
            },
            "adaptive_intelligence": {
                "module": "engines.adaptive_intelligence",
                "memory": self.memory_dir / "adaptive_intelligence_state.json",
            },
            "cross_setup_memory": {
                "module": "engines.cross_setup_intelligence",
                "memory": self.memory_dir / "cross_setup_memory.json",
            },
            "lifecycle_memory": {
                "module": "engines.trade_lifecycle_intelligence",
                "memory": self.memory_dir / "lifecycle_memory.json",
            },
            "master_shadow_memory": {
                "module": "engines.master_shadow_command_center",
                "memory": self.memory_dir / "master_shadow_memory.json",
            },
            "strategy_family_memory": {
                "module": "engines.strategy_family_memory",
                "memory": self.memory_dir / "strategy_family_memory.json",
            },
        }
        self.legacy_patch = patch.object(legacy_engine_visibility, "LEGACY_ENGINES", legacy_specs)
        self.legacy_patch.start()

    def tearDown(self):
        self.legacy_patch.stop()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def test_orphan_classification_and_archive_candidate_are_deterministic(self):
        self._write_json(self.memory_dir / "unmapped_memory.json", {"last_updated": self.now.isoformat()})

        policy = memory_cleanup_policy.build_memory_cleanup_policy(now=self.now)

        item = policy["memory_policy"]["unmapped_memory"]
        self.assertEqual(item["source_classification"], "ORPHAN")
        self.assertEqual(item["cleanup_classification"], "ARCHIVE_CANDIDATE")
        self.assertTrue(item["safe_to_archive"])
        self.assertEqual(item["recommended_action"], "review_for_manual_archive")

    def test_missing_expected_memory_baselines_generated_safely(self):
        policy = memory_cleanup_policy.build_memory_cleanup_policy(now=self.now)

        self.assertIn("historical_adaptive_intelligence_state", policy["created_baseline_memory"])
        self.assertIn("reinforcement_learning_memory", policy["created_baseline_memory"])
        baseline = json.loads((self.memory_dir / "reinforcement_learning_memory.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["status"], "GENERATED_BASELINE")
        self.assertTrue(baseline["advisory_only"])
        self.assertTrue(baseline["no_fake_learning_history"])
        self.assertTrue(baseline["no_fake_performance_history"])
        self.assertFalse(baseline["runtime_activity"])
        self.assertFalse(baseline["active_runtime_worker"])

    def test_stale_legacy_memory_classified_without_fake_runtime_activity(self):
        self._write_json(
            self.memory_dir / "cross_setup_memory.json",
            {"last_updated": self.old.isoformat(), "status": "OLD"},
        )

        policy = memory_cleanup_policy.build_memory_cleanup_policy(now=self.now)

        item = policy["memory_policy"]["cross_setup_memory"]
        self.assertEqual(item["cleanup_classification"], "LEGACY_VISIBLE")
        self.assertTrue(item["stale_but_visible"])
        self.assertTrue(item["inactive_but_connected"])
        self.assertEqual(item["recommended_action"], "keep_visible_mark_inactive_stale")

    def test_lineage_graph_and_contribution_scoring_generated(self):
        self._write_json(self.memory_dir / "meta_learning_state.json", {"last_updated": self.now.isoformat()})
        self._write_json(self.runtime_dir / "meta_learning_status.json", {"timestamp_ist": self.now.isoformat(), "status": "OK"})

        lineage = memory_lineage.build_memory_lineage_graph(now=self.now)
        contribution = memory_contribution_tracker.build_memory_contribution_status(now=self.now)

        self.assertTrue((self.runtime_dir / "memory_lineage_graph.json").exists())
        self.assertIn("meta_learning_state", lineage["memory_nodes"])
        self.assertTrue(lineage["memory_nodes"]["meta_learning_state"]["runtime_dependency_present"])
        score = contribution["memory_contributions"]["meta_learning_state"]["contribution_score"]
        self.assertGreater(score, 50.0)
        self.assertEqual(contribution["memory_contributions"]["meta_learning_state"]["contribution_visibility"], "RUNTIME_VISIBLE")

    def test_no_memory_deletion_and_no_live_mutation_flags(self):
        path = self.memory_dir / "strategy_family_memory.json"
        self._write_json(path, {"last_updated": self.old.isoformat(), "status": "OLD"})
        before = {item for item in self.memory_dir.rglob("*") if item.is_file()}

        result = memory_health.run_memory_health_check(now=self.now)

        after = {item for item in self.memory_dir.rglob("*") if item.is_file()}
        self.assertTrue(before.issubset(after))
        safety = result["safety_flags"]
        self.assertTrue(safety["advisory_only"])
        self.assertFalse(safety["affects_live_ranking"])
        self.assertFalse(safety["affects_execution"])
        self.assertFalse(safety["broker_mutation"])
        self.assertFalse(safety["telegram_mutation"])
        self.assertFalse(safety["supabase_mutation"])
        self.assertFalse(safety["live_order_behavior"])
        self.assertEqual(safety["recommended_live_weight"], 0.0)
        self.assertEqual(safety["rank_adjustment"], 0.0)

    def test_runtime_dependency_import_only_does_not_claim_worker(self):
        execution = self.runtime_dir / "execution_engine_status.json"
        specs = {
            "execution_engine": {
                "path": execution,
                "fallback_import": "titan_master_brain.execution_engine",
                "mode": "execution_visibility_only",
                "upstream": [],
                "downstream": [],
            }
        }
        with patch.object(runtime_dependency_graph, "CORE_NODES", specs), patch.object(
            runtime_dependency_graph, "_discover_memory_nodes", return_value={}
        ), patch.object(runtime_dependency_graph, "_discover_roadmap_phase_nodes", return_value={}), patch.object(
            runtime_dependency_graph, "build_legacy_engine_visibility", return_value={}
        ):
            graph = runtime_dependency_graph.build_runtime_dependency_graph(path=self.runtime_dir / "graph.json", now=self.now)

        node = graph["nodes"]["execution_engine"]
        self.assertTrue(node["connected"])
        self.assertEqual(node["visibility_classification"], "VISIBLE_IMPORT_ONLY")
        self.assertFalse(node["active_runtime_worker"])
        self.assertTrue(node["connected_visibility_only"])


if __name__ == "__main__":
    unittest.main()
