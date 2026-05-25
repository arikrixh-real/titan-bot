import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ranking_integrity
import ranking_mutation_audit
import ranking_ownership_guard


class RankingIntegrityBatch6Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_final_decision_engine_is_sole_authoritative_owner(self):
        with patch.object(ranking_mutation_audit, "PROJECT_ROOT", self.root), patch.object(
            ranking_mutation_audit, "AUDIT_PATH", self.runtime_dir / "ranking_mutation_audit.json"
        ), patch.object(ranking_ownership_guard, "OWNERSHIP_PATH", self.runtime_dir / "ranking_ownership_status.json"):
            status = ranking_ownership_guard.build_ranking_ownership_status()

        self.assertEqual(status["authoritative_ranking_owner"], "final_decision_engine")
        self.assertTrue(status["ownership_hierarchy"]["final_decision_engine"]["authoritative_live_ranking"])
        self.assertFalse(status["ownership_hierarchy"]["advisory_contributors"]["setup_engine"]["authoritative_live_owner"])
        self.assertTrue(status["ownership_hierarchy"]["advisory_contributors"]["setup_engine"]["contributes_to_ranking"])

    def test_advisory_payload_override_is_guarded(self):
        result = ranking_ownership_guard.classify_ranking_payload(
            "setup_engine",
            {"symbol": "TCS", "final_master_rank": 99.0, "rank_score": 91.0},
        )

        self.assertTrue(result["attempted_live_rank_override"])
        self.assertEqual(result["guard_action"], "visibility_only_no_silent_override")
        self.assertIn("final_master_rank", result["attempted_override_fields"])

    def test_duplicate_writers_detected(self):
        self._write(
            "titan_master_brain/final_decision_engine.py",
            "def own(x):\n    x['final_master_rank'] = 1\n    return x\n",
        )
        self._write(
            "engines/setup_engine.py",
            "def advise(x):\n    return {'rank_score': 1, 'final_score': 2}\n",
        )
        self._write(
            "setup_engine.py",
            "def advise(x):\n    x['rank_score'] = 3\n    return x\n",
        )

        audit = ranking_mutation_audit.run_ranking_mutation_audit(
            path=self.runtime_dir / "ranking_mutation_audit.json",
            root=self.root,
        )

        self.assertIn("rank_score", audit["duplicate_rank_writers"])

    def test_dangerous_runtime_override_detected(self):
        self._write(
            "titan_master_brain/final_decision_engine.py",
            "def own(x):\n    x['final_master_rank'] = 1\n    return x\n",
        )
        self._write(
            "setup_engine.py",
            "def bad(x):\n    x['final_master_rank'] = 2\n    return x\n",
        )

        audit = ranking_mutation_audit.run_ranking_mutation_audit(
            path=self.runtime_dir / "ranking_mutation_audit.json",
            root=self.root,
        )

        self.assertEqual(len(audit["dangerous_live_overrides"]), 1)
        self.assertEqual(audit["dangerous_live_overrides"][0]["component"], "setup_engine")

    def test_ranking_chain_deterministic_and_no_execution_mutation(self):
        self._write(
            "titan_master_brain/final_decision_engine.py",
            "def own(x):\n    x['final_master_rank'] = 1\n    return x\n",
        )
        self._write(
            "setup_engine.py",
            "RANKING_OWNERSHIP = {'contributes_to_ranking': True, 'authoritative_live_owner': False}\n"
            "def setup(x):\n    return {'rank_score': 1}\n",
        )

        with patch.object(ranking_mutation_audit, "PROJECT_ROOT", self.root), patch.object(
            ranking_mutation_audit, "AUDIT_PATH", self.runtime_dir / "ranking_mutation_audit.json"
        ), patch.object(ranking_ownership_guard, "OWNERSHIP_PATH", self.runtime_dir / "ranking_ownership_status.json"), patch.object(
            ranking_integrity, "INTEGRITY_PATH", self.runtime_dir / "ranking_integrity_status.json"
        ):
            result = ranking_integrity.build_ranking_integrity_status()

        self.assertTrue(result["ranking_chain_valid"])
        self.assertEqual(result["authoritative_owner"], "final_decision_engine")
        self.assertFalse(result["safety_flags"]["affects_execution"])
        self.assertFalse(result["safety_flags"]["broker_mutation"])
        self.assertFalse(result["safety_flags"]["telegram_mutation"])
        self.assertFalse(result["safety_flags"]["supabase_mutation"])
        self.assertFalse(result["safety_flags"]["live_order_behavior"])

    def test_roadmap_phases_are_advisory_only(self):
        with patch.object(ranking_mutation_audit, "PROJECT_ROOT", self.root), patch.object(
            ranking_mutation_audit, "AUDIT_PATH", self.runtime_dir / "ranking_mutation_audit.json"
        ), patch.object(ranking_ownership_guard, "OWNERSHIP_PATH", self.runtime_dir / "ranking_ownership_status.json"):
            status = ranking_ownership_guard.build_ranking_ownership_status()

        roadmap = status["roadmap_phase_classification"]
        self.assertTrue(roadmap["advisory_only"])
        self.assertFalse(roadmap["affects_live_ranking"])


if __name__ == "__main__":
    unittest.main()
