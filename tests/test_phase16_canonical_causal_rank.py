"""
Focused tests for Phase 16 causal ranking ownership.

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

from engines import setup_engine as setup_engine_module
from titan_master_brain import final_decision_engine


def fake_causal_report(setup, context, news_items=None):
    symbol = str(setup.get("symbol") or setup.get("stock") or "").upper()
    score_by_symbol = {
        "LOWBASE": 90.0,
        "HIGHBASE": 20.0,
        "STALE": 80.0,
    }
    causal_score = score_by_symbol.get(symbol, 50.0)
    return {
        "primary_cause": "test causal chain",
        "cause_confidence_score": causal_score,
        "event_classification": "EARNINGS",
        "market_wide_pressure": {"active": False},
        "sector_leadership_cause": {"leadership_score": 0.0},
        "delayed_effect_tracking": {"active": False},
        "cascading_event_risk": {"active": False, "risk_score": 0.0},
        "false_news_caution": {"active": False},
        "index_sector_stock_causality": {"active": True, "causal_score": 0.0},
        "news_to_sector_stock_chain": {"chain_strength": 0.0},
        "narrative_causality_graph": {"edges": []},
        "explanations": ["test causal report"],
    }


class Phase16CanonicalCausalRankTests(unittest.TestCase):
    def setUp(self):
        self.old_setup_report = setup_engine_module.build_causal_reasoning_report
        self.old_final_report = final_decision_engine.build_causal_reasoning_report

        setup_engine_module.build_causal_reasoning_report = fake_causal_report
        final_decision_engine.build_causal_reasoning_report = fake_causal_report

    def tearDown(self):
        setup_engine_module.build_causal_reasoning_report = self.old_setup_report
        final_decision_engine.build_causal_reasoning_report = self.old_final_report

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

    def test_setup_engine_phase16_is_advisory_only(self):
        for relative_path in ("engines/setup_engine.py", "setup_engine.py"):
            path = PROJECT_ROOT / relative_path
            fields_node = self._function_node(path, "apply_causal_fields")
            ranking_node = self._function_node(path, "apply_causal_ranking")
            source = ast.get_source_segment(path.read_text(encoding="utf-8"), fields_node)

            self.assertNotIn("new_blended_rank_score", self._assigned_string_keys(fields_node), relative_path)
            self.assertIn("advisory_causal_confidence_score", source)
            self.assertIn("advisory_setup_only", source)
            self.assertFalse(
                any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "sort" for node in ast.walk(ranking_node)),
                relative_path,
            )

    def test_setup_engine_preserves_order_and_existing_live_rank(self):
        candidates = [
            {"symbol": "LOWBASE", "score": 10.0, "blended_rank_score": 10.0, "new_blended_rank_score": 77.0},
            {"symbol": "HIGHBASE", "score": 90.0, "blended_rank_score": 90.0},
        ]

        annotated = setup_engine_module.apply_causal_ranking(deepcopy(candidates), {})

        self.assertEqual([row["symbol"] for row in annotated], ["LOWBASE", "HIGHBASE"])
        self.assertEqual(annotated[0]["new_blended_rank_score"], 77.0)
        self.assertNotIn("new_blended_rank_score", annotated[1])
        self.assertEqual(annotated[0]["causal_confidence_score"], 90.0)
        self.assertEqual(annotated[0]["advisory_causal_confidence_score"], 90.0)
        self.assertEqual(annotated[0]["causal_rank_role"], "advisory_setup_only")

    def test_final_decision_engine_is_only_live_causal_rank_writer(self):
        candidate = {"symbol": "LOWBASE", "score": 10.0, "blended_rank_score": 10.0}

        setup_annotated = setup_engine_module.apply_causal_fields(deepcopy(candidate), {})
        self.assertNotIn("new_blended_rank_score", setup_annotated)

        final_ranked = final_decision_engine._attach_causal_fields(setup_annotated, {})

        self.assertEqual(final_ranked["new_blended_rank_score"], 22.0)
        self.assertEqual(final_ranked["causal_confidence_score"], 90.0)

    def test_prefilled_causal_rank_is_overwritten_not_double_weighted(self):
        candidate = {
            "symbol": "STALE",
            "score": 50.0,
            "blended_rank_score": 59.0,
            "causal_confidence_score": 80.0,
            "advisory_causal_confidence_score": 80.0,
            "new_blended_rank_score": 79.0,
        }

        final_ranked = final_decision_engine._attach_causal_fields(deepcopy(candidate), {})

        self.assertEqual(final_ranked["new_blended_rank_score"], 62.15)
        self.assertNotEqual(final_ranked["new_blended_rank_score"], 79.15)


if __name__ == "__main__":
    unittest.main()
