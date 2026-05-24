"""
Focused tests for Phase 19 elite-selection ownership.

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

from engines import elite_selector
from titan_master_brain import final_decision_engine


class Phase19CanonicalEliteSelectionTests(unittest.TestCase):
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

    def test_legacy_elite_selector_is_advisory_only(self):
        path = PROJECT_ROOT / "engines" / "elite_selector.py"
        fields_node = self._function_node(path, "apply_elite_selection")
        ranking_node = self._function_node(path, "rank_elite_setups")
        source = ast.get_source_segment(path.read_text(encoding="utf-8"), fields_node)

        self.assertNotIn("rank_score", self._assigned_string_keys(fields_node))
        self.assertIn("advisory_elite_probability_score", source)
        self.assertIn("advisory_legacy_only", source)
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sort"
                for node in ast.walk(ranking_node)
            )
        )

    def test_legacy_elite_selector_preserves_order_and_live_rank(self):
        candidates = [
            {
                "symbol": "LOWLEGACY",
                "score": 80.0,
                "rank_score": 80.0,
                "rr": 0.5,
                "pattern_confidence": 0.1,
            },
            {
                "symbol": "HIGHLEGACY",
                "score": 10.0,
                "rank_score": 10.0,
                "rr": 3.0,
                "pattern_confidence": 1.0,
            },
        ]

        annotated = elite_selector.rank_elite_setups(deepcopy(candidates))

        self.assertEqual([row["symbol"] for row in annotated], ["LOWLEGACY", "HIGHLEGACY"])
        self.assertEqual([row["rank_score"] for row in annotated], [80.0, 10.0])
        self.assertIn("elite_probability_score", annotated[0])
        self.assertEqual(
            annotated[0]["elite_probability_score"],
            annotated[0]["advisory_elite_probability_score"],
        )
        self.assertEqual(annotated[0]["elite_rank_role"], "advisory_legacy_only")

    def test_final_decision_engine_uses_canonical_filter_as_live_elite_gate(self):
        old_report = final_decision_engine.build_elite_selection_report
        old_filter = final_decision_engine.filter_elite_setups

        selected_by_filter = {
            "symbol": "FILTERPASS",
            "side": "LONG",
            "rank_score": 20.0,
            "elite_probability_score": 1.0,
            "elite_quality_score": 88.0,
        }
        rejected_by_filter = {
            "symbol": "FILTERBLOCK",
            "side": "LONG",
            "rank_score": 99.0,
            "elite_probability_score": 150.0,
            "elite_quality_score": 30.0,
            "elite_reject_reason": "below_elite_threshold",
        }

        def fake_report(setups, context=None, max_alerts=3):
            return {
                "low_quality_day": False,
                "trade_scarcity_score": 42.0,
                "selected_elite_setups": [{"symbol": "FILTERPASS"}],
                "rejected_setups": [{"symbol": "FILTERBLOCK"}],
            }

        def fake_filter(setups, context=None, max_alerts=3):
            return {
                "selected": [selected_by_filter],
                "rejected": [rejected_by_filter],
                "low_quality_day": False,
            }

        try:
            final_decision_engine.build_elite_selection_report = fake_report
            final_decision_engine.filter_elite_setups = fake_filter

            selected, rejected, report, applied = final_decision_engine._apply_elite_filter_to_selected_pool(
                [rejected_by_filter, selected_by_filter],
                context={},
                max_candidates=1,
            )
        finally:
            final_decision_engine.build_elite_selection_report = old_report
            final_decision_engine.filter_elite_setups = old_filter

        self.assertTrue(applied)
        self.assertEqual([row["symbol"] for row in selected], ["FILTERPASS"])
        self.assertTrue(selected[0]["elite_selected"])
        self.assertEqual([row["symbol"] for row in rejected], ["FILTERBLOCK"])
        self.assertFalse(rejected[0]["elite_selected"])
        self.assertEqual(rejected[0]["elite_rejection_reason"], "below_elite_threshold")
        self.assertEqual(report["trade_scarcity_score"], 42.0)


if __name__ == "__main__":
    unittest.main()
