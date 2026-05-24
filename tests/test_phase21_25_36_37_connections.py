"""
Focused connection tests for Phases 21-25, 36, and 37.

These tests do not scan markets, send Telegram alerts, touch Supabase, use
broker APIs, mutate live rankings, or place broker orders.
"""

import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import runtime_status
from titan_master_brain import master_controller


PHASE_REFRESH_FUNCTIONS = (
    "refresh_phase21_autonomous_research_safely",
    "refresh_phase22_backtesting_validation_safely",
    "refresh_phase23_paper_trading_safely",
    "refresh_phase24_execution_safety_safely",
    "refresh_phase25_smart_execution_safely",
    "refresh_phase36_memory_consolidation_safely",
    "refresh_phase37_auto_repair_safely",
)


class PhaseConnectionTests(unittest.TestCase):
    def _function_node(self, path, name):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail(f"{name} not found in {path}")

    def _called_names(self, node):
        names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    names.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    names.add(child.func.attr)
        return names

    def test_master_controller_phase_refreshes_exist(self):
        for function_name in PHASE_REFRESH_FUNCTIONS:
            self.assertTrue(callable(getattr(master_controller, function_name, None)), function_name)

    def test_refreshes_do_not_call_live_mutators(self):
        forbidden_calls = {
            "filter_alert_candidates",
            "select_daily_alerts",
            "prepare_execution_packets",
            "send_telegram_signals",
            "mark_alerts_sent",
            "_get_supabase",
            "_safe_supabase_insert",
            "_safe_supabase_update",
            "save_sent_packets_to_trade_results",
            "track_trade_outcomes",
            "make_final_decisions",
        }
        path = PROJECT_ROOT / "titan_master_brain" / "master_controller.py"
        for function_name in PHASE_REFRESH_FUNCTIONS:
            node = self._function_node(path, function_name)
            self.assertFalse(self._called_names(node) & forbidden_calls, function_name)

    def test_runtime_status_summarizes_sidecar_artifacts_as_non_mutating(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "phase21.json"
            artifact.write_text(
                json.dumps(
                    {
                        "research_mode": "OBSERVE",
                        "research_priority_score": 51,
                        "advisory_only": True,
                        "research_only": True,
                        "shadow_mode": True,
                        "live_order_allowed": False,
                        "live_rank_mutation_allowed": False,
                    }
                ),
                encoding="utf-8",
            )
            phase_specs = {
                "phase21_autonomous_research": {
                    "path": artifact,
                    "placement": "master_controller_research_sidecar",
                    "mode": "research_only",
                    "fields": ("research_mode", "research_priority_score"),
                }
            }

            with patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                summaries = runtime_status._phase_status_summaries()

        summary = summaries["phase21_autonomous_research"]
        self.assertTrue(summary["connected"])
        self.assertTrue(summary["advisory_only"])
        self.assertTrue(summary["research_only"])
        self.assertTrue(summary["shadow_mode"])
        self.assertFalse(summary["safety"]["live_order_allowed"])
        self.assertFalse(summary["safety"]["live_rank_mutation_allowed"])
        self.assertFalse(summary["safety"]["broker_orders"])
        self.assertFalse(summary["safety"]["telegram_changes"])
        self.assertEqual(summary["values"]["research_mode"], "OBSERVE")


if __name__ == "__main__":
    unittest.main()
