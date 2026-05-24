"""
Focused tests for Phase 15 probabilistic ranking ownership.

These tests do not scan markets, send alerts, touch Supabase, use broker APIs,
or execute orders.
"""

from copy import deepcopy
import ast
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from titan_master_brain import final_decision_engine


def fake_probability_report(setup, context):
    symbol = str(setup.get("symbol") or setup.get("stock") or "").upper()
    score_by_symbol = {
        "LOWBASE": 90.0,
        "HIGHBASE": 20.0,
        "STALE": 80.0,
    }
    probability_score = score_by_symbol.get(symbol, 50.0)
    return {
        "final_probability_score": probability_score,
        "recommendation": "TEST",
        "expected_value": 1.23,
        "probability_confidence_score": 66.0,
        "uncertainty_score": 12.0,
        "explanations": ["test probability report"],
    }


class Phase15CanonicalProbabilityRankTests(unittest.TestCase):
    def setUp(self):
        self.old_final_report = final_decision_engine.build_probability_report
        self.old_final_rank = final_decision_engine.rank_setups_by_probability

        final_decision_engine.build_probability_report = fake_probability_report
        final_decision_engine.rank_setups_by_probability = None

    def tearDown(self):
        final_decision_engine.build_probability_report = self.old_final_report
        final_decision_engine.rank_setups_by_probability = self.old_final_rank

    def _function_node(self, path, name):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail(f"{name} not found in {path}")

    def _assigned_string_keys(self, node):
        keys = set()
        for child in ast.walk(node):
            targets = []
            if isinstance(child, ast.Assign):
                targets.extend(child.targets)
            elif isinstance(child, ast.AnnAssign):
                targets.append(child.target)
            elif isinstance(child, ast.AugAssign):
                targets.append(child.target)
            for target in targets:
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    keys.add(target.slice.value)
        return keys

    def test_setup_engine_phase15_is_advisory_only(self):
        for relative_path in ("engines/setup_engine.py", "setup_engine.py"):
            path = PROJECT_ROOT / relative_path
            fields_node = self._function_node(path, "apply_probability_fields")
            ranking_node = self._function_node(path, "apply_probability_ranking")
            source = ast.get_source_segment(path.read_text(encoding="utf-8"), fields_node)

            self.assertNotIn("blended_rank_score", self._assigned_string_keys(fields_node), relative_path)
            self.assertNotIn("rank_score", self._assigned_string_keys(fields_node), relative_path)
            self.assertIn("advisory_probability_score", source)
            self.assertIn("advisory_setup_only", source)
            self.assertFalse(
                any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "sort" for node in ast.walk(ranking_node)),
                relative_path,
            )

    def test_final_decision_engine_is_only_live_blended_rank_writer(self):
        candidate = {"symbol": "LOWBASE", "score": 10.0, "rank_score": 10.0}

        setup_annotated = dict(candidate)
        setup_annotated["probability_score"] = 90.0
        setup_annotated["advisory_probability_score"] = 90.0
        setup_annotated["probability_rank_role"] = "advisory_setup_only"

        final_ranked = final_decision_engine._attach_probability_fields(setup_annotated, {})
        self.assertEqual(final_ranked["blended_rank_score"], 34.0)
        self.assertEqual(final_ranked["probability_score"], 90.0)

    def test_prefilled_setup_blended_rank_is_overwritten_not_double_weighted(self):
        candidate = {
            "symbol": "STALE",
            "score": 50.0,
            "rank_score": 50.0,
            "probability_score": 80.0,
            "advisory_probability_score": 80.0,
            "blended_rank_score": 79.0,
        }

        final_ranked = final_decision_engine._attach_probability_fields(deepcopy(candidate), {})

        self.assertEqual(final_ranked["blended_rank_score"], 59.0)
        self.assertNotEqual(final_ranked["blended_rank_score"], 79.3)


if __name__ == "__main__":
    unittest.main()
