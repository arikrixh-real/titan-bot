import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import advisory_mutation_containment
from utils.market_hours import IST


class Batch10MutationContainmentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        (self.root / "engines").mkdir(parents=True, exist_ok=True)
        (self.root / "research").mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.now = datetime(2026, 5, 25, 10, 0, tzinfo=IST)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _patch_paths(self):
        return patch.multiple(
            advisory_mutation_containment,
            PROJECT_ROOT=self.root,
            RUNTIME_DIR=self.runtime_dir,
            ADVISORY_MUTATION_AUDIT_PATH=self.runtime_dir / "advisory_mutation_audit.json",
            LIVE_MUTATION_GUARD_STATUS_PATH=self.runtime_dir / "live_mutation_guard_status.json",
            SHADOW_SYSTEM_ISOLATION_STATUS_PATH=self.runtime_dir / "shadow_system_isolation_status.json",
        )

    def test_advisory_audit_detects_forbidden_live_call(self):
        self._write(
            "engines/roadmap_test.py",
            "def run():\n"
            "    send_telegram_signals([])\n"
            "    return {'affects_live_ranking': False, 'affects_execution': False}\n",
        )

        with self._patch_paths():
            audit = advisory_mutation_containment.build_advisory_mutation_audit(root=self.root, now=self.now)

        self.assertEqual(audit["advisory_mutation_audit_status"], "WARNING")
        self.assertEqual(audit["unsafe_live_mutation_vector_count"], 1)
        self.assertEqual(audit["unsafe_live_mutation_vectors"][0]["file"], "engines/roadmap_test.py")

    def test_true_mutation_flag_is_guarded(self):
        self._write(
            "engines/meta_test.py",
            "def run():\n"
            "    return {'affects_execution': True, 'affects_live_ranking': False}\n",
        )

        with self._patch_paths():
            audit = advisory_mutation_containment.build_advisory_mutation_audit(root=self.root, now=self.now)

        vectors = audit["unsafe_live_mutation_vectors"][0]["vectors"]
        self.assertEqual(vectors[0]["type"], "unsafe_true_mutation_flag")
        self.assertEqual(vectors[0]["field"], "affects_execution")

    def test_live_mutation_guard_fails_on_dangerous_ranking_override(self):
        audit = {"unsafe_live_mutation_vectors": []}
        ranking = {
            "authoritative_owner": "final_decision_engine",
            "ranking_chain_valid": False,
            "dangerous_live_overrides": [{"component": "setup_engine"}],
        }

        with self._patch_paths():
            guard = advisory_mutation_containment.build_live_mutation_guard_status(
                audit=audit,
                ranking=ranking,
                now=self.now,
            )

        self.assertEqual(guard["live_mutation_guard_status"], "FAIL")
        self.assertIn("dangerous_live_ranking_override_detected", guard["failures"])
        self.assertTrue(guard["guard_visibility"]["visibility_only_no_runtime_mutation"])

    def test_shadow_system_isolation_reports_leaking_systems(self):
        audit = {
            "systems": [
                {
                    "file": "engines/roadmap_safe.py",
                    "system_role": "roadmap_phase",
                    "isolated": True,
                    "unsafe_live_mutation_vectors": [],
                },
                {
                    "file": "engines/roadmap_bad.py",
                    "system_role": "roadmap_phase",
                    "isolated": False,
                    "unsafe_live_mutation_vectors": [{"type": "forbidden_live_call"}],
                },
            ]
        }

        with self._patch_paths():
            status = advisory_mutation_containment.build_shadow_system_isolation_status(audit=audit, now=self.now)

        self.assertEqual(status["shadow_system_isolation_status"], "WARNING")
        self.assertEqual(status["leaking_system_count"], 1)
        self.assertFalse(status["isolation_contract"]["affects_execution"])

    def test_batch10_generates_required_artifacts_and_safety_flags(self):
        self._write(
            "engines/roadmap_safe.py",
            "def run():\n"
            "    return {'affects_live_ranking': False, 'affects_execution': False, 'broker_mutation': False}\n",
        )
        ranking = {
            "authoritative_owner": "final_decision_engine",
            "ranking_chain_valid": True,
            "dangerous_live_overrides": [],
        }

        with self._patch_paths(), patch.object(
            advisory_mutation_containment,
            "build_ranking_integrity_status",
            return_value=ranking,
        ):
            result = advisory_mutation_containment.run_batch10_mutation_containment(now=self.now)

        self.assertEqual(result["status"], "PASS")
        for path in result["artifacts"].values():
            self.assertTrue(Path(path).exists())
        self.assertTrue(result["safety_flags"]["advisory_only"])
        self.assertFalse(result["safety_flags"]["affects_live_ranking"])
        self.assertFalse(result["safety_flags"]["affects_execution"])


if __name__ == "__main__":
    unittest.main()
