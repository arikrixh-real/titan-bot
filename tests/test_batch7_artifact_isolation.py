import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import runtime_artifact_registry
from utils.market_hours import IST


class Batch7ArtifactIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "data" / "runtime"
        self.memory_dir = self.root / "data" / "memory"
        self.reports_dir = self.root / "reports"
        self.research_dir = self.root / "research"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.research_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _patch_paths(self):
        critical_chain = {
            name: {**spec, "path": self.runtime_dir / spec["path"].name}
            for name, spec in runtime_artifact_registry.RUNTIME_CRITICAL_CHAIN.items()
        }
        return patch.multiple(
            runtime_artifact_registry,
            RUNTIME_DIR=self.runtime_dir,
            MEMORY_DIR=self.memory_dir,
            REPORTS_DIR=self.reports_dir,
            RESEARCH_DIR=self.research_dir,
            RUNTIME_ARTIFACT_REGISTRY_PATH=self.runtime_dir / "runtime_artifact_registry.json",
            DEAD_CHAIN_ISOLATION_PATH=self.runtime_dir / "dead_chain_isolation_status.json",
            DUPLICATE_ARTIFACT_ROLES_PATH=self.runtime_dir / "duplicate_artifact_roles.json",
            RUNTIME_CRITICAL_CHAIN_PATH=self.runtime_dir / "runtime_critical_chain_status.json",
            RUNTIME_CRITICAL_CHAIN=critical_chain,
        )

    def test_runtime_artifact_registry_classifies_runtime_and_research(self):
        self._write_json(
            self.runtime_dir / "scanner_status.json",
            {"status": "OK", "timestamp_ist": self.now.isoformat()},
        )
        self._write_json(
            self.memory_dir / "scanner_state.json",
            {"status": "OK", "timestamp_ist": self.now.isoformat()},
        )
        self._write_json(
            self.reports_dir / "scanner_report.txt",
            {"status": "OK"},
        )

        with self._patch_paths():
            registry = runtime_artifact_registry.build_runtime_artifact_registry(now=self.now)

        roles = {item["path"]: item["role"] for item in registry["artifacts"]}
        self.assertEqual(roles[str(self.runtime_dir / "scanner_status.json").replace("\\", "/")], "runtime_critical")
        self.assertEqual(roles[str(self.memory_dir / "scanner_state.json").replace("\\", "/")], "research_memory_artifact")
        self.assertTrue(registry["safety_flags"]["advisory_only"])
        self.assertFalse(registry["safety_flags"]["affects_execution"])
        self.assertFalse(registry["safety_flags"]["affects_live_ranking"])

    def test_dead_chain_isolation_keeps_runtime_critical_visible(self):
        graph = {
            "nodes": {
                "scanner": {
                    "artifact_path": "data/runtime/scanner_status.json",
                    "mode": "live_signal_input",
                    "connected": False,
                    "stale": True,
                    "fresh": False,
                    "visibility_classification": "MISSING",
                },
                "roadmap_meta_learning_status": {
                    "artifact_path": "data/runtime/meta_learning_status.json",
                    "mode": "roadmap_sidecar",
                    "connected": False,
                    "stale": True,
                    "fresh": False,
                    "visibility_classification": "MISSING",
                },
            }
        }

        with self._patch_paths():
            status = runtime_artifact_registry.build_dead_chain_isolation_status(now=self.now, graph=graph)

        by_name = {item["name"]: item for item in status["dead_chains"]}
        self.assertEqual(by_name["scanner"]["isolation_classification"], "runtime_critical_visibility_required")
        self.assertTrue(by_name["scanner"]["requires_manual_review"])
        self.assertEqual(
            by_name["roadmap_meta_learning_status"]["isolation_classification"],
            "isolated_advisory_dead_chain",
        )
        self.assertTrue(by_name["roadmap_meta_learning_status"]["excluded_from_runtime_integrity"])
        self.assertFalse(by_name["roadmap_meta_learning_status"]["delete_recommended"])

    def test_duplicate_artifact_roles_do_not_poison_runtime_integrity(self):
        registry = {
            "artifacts": [
                {
                    "path": "data/runtime/scanner_status.json",
                    "role": "runtime_critical",
                    "scope": "runtime_critical_chain",
                    "status": "OK",
                    "duplicate_key": "scanner",
                    "runtime_critical": True,
                    "research_or_sample": False,
                },
                {
                    "path": "data/memory/scanner_state.json",
                    "role": "research_memory_artifact",
                    "scope": "research_or_advisory",
                    "status": "OK",
                    "duplicate_key": "scanner",
                    "runtime_critical": False,
                    "research_or_sample": True,
                },
            ]
        }

        with self._patch_paths():
            roles = runtime_artifact_registry.build_duplicate_artifact_roles(registry=registry, now=self.now)

        self.assertEqual(roles["duplicate_group_count"], 1)
        group = roles["duplicate_groups"][0]
        self.assertEqual(group["classification"], "runtime_research_name_overlap")
        self.assertFalse(group["poisons_runtime_integrity"])
        self.assertFalse(group["delete_recommended"])

    def test_runtime_critical_chain_warns_on_stale_required_artifact(self):
        fresh = self.now
        stale = self.now - timedelta(hours=2)
        for name, spec in runtime_artifact_registry.RUNTIME_CRITICAL_CHAIN.items():
            timestamp = stale if spec["required"] and name == "scanner" else fresh
            self._write_json(
                self.runtime_dir / spec["path"].name,
                {"status": "OK", "timestamp_ist": timestamp.isoformat()},
            )

        with self._patch_paths(), patch.object(
            runtime_artifact_registry,
            "build_canonical_runtime_mode",
            return_value={"canonical_mode": "MARKET_MODE"},
        ):
            status = runtime_artifact_registry.build_runtime_critical_chain_status(now=self.now, graph={"nodes": {}})

        self.assertEqual(status["runtime_critical_chain_status"], "WARNING")
        self.assertIn("scanner", status["stale_required_nodes"])
        self.assertEqual(status["authoritative_ranking_owner"], "final_decision_engine")
        self.assertFalse(status["execution_behavior_mutated"])
        self.assertFalse(status["scanner_selection_mutated"])


if __name__ == "__main__":
    unittest.main()
