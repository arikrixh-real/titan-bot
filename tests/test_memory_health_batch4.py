import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import legacy_engine_visibility
import memory_freshness_audit
import memory_health
import runtime_dependency_graph
from utils.market_hours import IST


class MemoryHealthBatch4Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.memory_dir = self.root / "memory"
        self.runtime_dir = self.root / "runtime"
        self.reports_dir = self.root / "reports"
        self.now = datetime(2026, 5, 25, 10, 0, 0, tzinfo=IST)
        self.old = self.now - timedelta(days=10)
        self.patchers = [
            patch.object(memory_freshness_audit, "MEMORY_DIR", self.memory_dir),
            patch.object(memory_freshness_audit, "RUNTIME_DIR", self.runtime_dir),
            patch.object(memory_freshness_audit, "REPORTS_DIR", self.reports_dir),
            patch.object(memory_health, "MEMORY_HEALTH_PATH", self.runtime_dir / "titan_memory_health.json"),
            patch.object(legacy_engine_visibility, "RUNTIME_DIR", self.runtime_dir),
            patch.object(legacy_engine_visibility, "MEMORY_DIR", self.memory_dir),
            patch.object(legacy_engine_visibility, "REPORTS_DIR", self.reports_dir),
            patch.object(legacy_engine_visibility, "LEGACY_VISIBILITY_PATH", self.runtime_dir / "legacy_engine_visibility_status.json"),
        ]
        for patcher in self.patchers:
            patcher.start()

        legacy_specs = {
            "execution_engine": {
                "module": "titan_master_brain.execution_engine",
                "status": self.runtime_dir / "execution_engine_status.json",
            },
            "reinforcement_learning": {
                "module": "engines.reinforcement_learning_layer",
                "status": self.runtime_dir / "reinforcement_learning_status.json",
                "memory": self.memory_dir / "reinforcement_learning_memory.json",
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

    def test_stale_corrupted_and_orphan_memory_detected(self):
        self._write_json(
            self.memory_dir / "adaptive_intelligence_state.json",
            {"last_updated": self.old.isoformat(), "status": "OK"},
        )
        self._write_json(
            self.memory_dir / "strategy_genome_memory.json",
            {"last_updated": self.now.isoformat(), "status": "OK"},
        )
        orphan_path = self.memory_dir / "experimental_unmapped_memory.json"
        self._write_json(orphan_path, {"last_updated": self.now.isoformat()})
        corrupt_path = self.memory_dir / "cross_setup_memory.json"
        corrupt_path.parent.mkdir(parents=True, exist_ok=True)
        corrupt_path.write_text("{bad json", encoding="utf-8")
        self._write_json(
            self.memory_dir / "reinforcement_learning_memory.json",
            {"last_updated": self.now.isoformat(), "status": "OK"},
        )

        result = memory_health.run_memory_health_check(now=self.now)

        self.assertIn("adaptive_intelligence_state", result["stale_memory_summary"])
        self.assertIn("experimental_unmapped_memory", result["orphan_memory_summary"])
        self.assertIn("cross_setup_memory", result["corrupted_memory_summary"])
        self.assertGreater(result["stale_memory_files"], 0)
        self.assertGreater(result["orphan_memory_files"], 0)
        self.assertGreater(result["corrupted_memory_files"], 0)

    def test_legacy_engine_visibility_generated_for_execution_and_reinforcement(self):
        self._write_json(
            self.memory_dir / "reinforcement_learning_memory.json",
            {"last_updated": self.now.isoformat(), "status": "OK"},
        )

        result = legacy_engine_visibility.build_legacy_engine_visibility(now=self.now)

        self.assertTrue((self.runtime_dir / "legacy_engine_visibility_status.json").exists())
        self.assertIn("execution_engine", result["connected_legacy_engines"])
        self.assertIn("reinforcement_learning", result["connected_legacy_engines"])
        self.assertTrue(result["engines"]["execution_engine"]["connected_visibility_only"])
        self.assertFalse(result["safety_flags"]["affects_execution"])

    def test_disconnected_execution_engine_becomes_visibility_connected(self):
        scanner = self.runtime_dir / "scanner.json"
        execution = self.runtime_dir / "execution_engine_status.json"
        self._write_json(scanner, {"status": "OK", "timestamp_ist": self.now.isoformat()})
        specs = {
            "scanner": {
                "path": scanner,
                "mode": "live_signal_input",
                "upstream": [],
                "downstream": ["execution_engine"],
            },
            "execution_engine": {
                "path": execution,
                "fallback_import": "titan_master_brain.execution_engine",
                "mode": "execution_visibility_only",
                "upstream": ["scanner"],
                "downstream": [],
            },
        }
        with patch.object(runtime_dependency_graph, "CORE_NODES", specs), patch.object(
            runtime_dependency_graph, "_discover_memory_nodes", return_value={}
        ), patch.object(runtime_dependency_graph, "_discover_roadmap_phase_nodes", return_value={}), patch.object(
            runtime_dependency_graph, "build_legacy_engine_visibility", return_value={}
        ):
            graph = runtime_dependency_graph.build_runtime_dependency_graph(path=self.runtime_dir / "graph.json", now=self.now)

        self.assertNotIn("execution_engine", graph["disconnected_engines"])
        self.assertTrue(graph["nodes"]["execution_engine"]["connected"])
        self.assertTrue(graph["nodes"]["execution_engine"]["connected_visibility_only"])
        self.assertTrue(graph["nodes"]["execution_engine"]["stale"])

    def test_no_live_mutation_flags_enabled_and_no_memory_files_deleted(self):
        memory_path = self.memory_dir / "strategy_family_memory.json"
        self._write_json(memory_path, {"last_updated": self.now.isoformat(), "status": "OK"})
        before = {path for path in self.memory_dir.rglob("*") if path.is_file()}

        result = memory_health.run_memory_health_check(now=self.now)

        after = {path for path in self.memory_dir.rglob("*") if path.is_file()}
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


if __name__ == "__main__":
    unittest.main()
