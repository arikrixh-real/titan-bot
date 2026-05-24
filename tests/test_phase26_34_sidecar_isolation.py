"""
Focused tests for Phase 26-34 live-weighted sidecar ownership.

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

from titan_master_brain import final_decision_engine, master_controller


PHASE_RANK_KEYS = {
    "final_microstructure_rank",
    "final_options_rank",
    "final_news_intelligence_rank",
    "final_calendar_rank",
    "final_liquidity_rank",
    "final_scenario_rank",
    "final_debate_rank",
    "final_reflection_rank",
    "final_calibration_rank",
}

SIDECAR_ENGINE_PATHS = (
    "engines/order_book_microstructure_engine.py",
    "engines/options_flow_intelligence_engine.py",
    "engines/news_intelligence_2_engine.py",
    "engines/economic_calendar_intelligence_engine.py",
    "engines/institutional_liquidity_map_engine.py",
    "engines/scenario_simulation_engine.py",
    "engines/multi_agent_debate_engine.py",
    "engines/self_reflection_meta_cognition_engine.py",
    "engines/confidence_calibration_engine.py",
)

MASTER_REFRESH_FUNCTIONS = (
    "refresh_phase26_microstructure_safely",
    "refresh_phase27_options_flow_safely",
    "refresh_phase28_news_intelligence_safely",
    "refresh_phase29_economic_calendar_safely",
    "refresh_phase30_liquidity_map_safely",
    "refresh_phase31_scenario_simulation_safely",
    "refresh_phase32_multi_agent_debate_safely",
    "refresh_phase33_self_reflection_safely",
    "refresh_phase34_confidence_calibration_safely",
)


def mutating_report(*args, **kwargs):
    setup = kwargs.get("setup")
    if setup is None and args:
        setup = args[0]
    if isinstance(setup, dict):
        setup["symbol"] = "MUTATED"
        if isinstance(setup.get("raw"), dict):
            setup["raw"]["nested"] = "MUTATED"
    return {
        "microstructure_score": 80.0,
        "microstructure_bias": "BULLISH",
        "execution_warning": "NONE",
        "data_mode": "PROXY",
        "options_flow_score": 80.0,
        "options_flow_bias": "BULLISH",
        "options_warning": "NONE",
        "news_intelligence_score": 80.0,
        "news_bias": "BULLISH",
        "news_warning": "NONE",
        "news_data_mode": "PROXY",
        "overall_news_sentiment_score": 80.0,
        "credibility_score": 80.0,
        "market_narrative": {},
        "calendar_intelligence_score": 80.0,
        "calendar_bias": "BULLISH",
        "calendar_warning": "NONE",
        "calendar_data_mode": "PROXY",
        "liquidity_map_score": 80.0,
        "liquidity_bias": "BULLISH",
        "liquidity_warning": "NONE",
        "liquidity_data_mode": "PROXY",
        "scenario_score": 80.0,
        "scenario_bias": "BULLISH",
        "scenario_warning": "NONE",
        "scenario_data_mode": "PROXY",
        "debate_score": 80.0,
        "debate_bias": "BULLISH",
        "debate_warning": "NONE",
        "debate_data_mode": "PROXY",
        "reflection_score": 80.0,
        "reflection_bias": "BULLISH",
        "reflection_warning": "NONE",
        "reflection_data_mode": "PROXY",
        "calibrated_confidence_score": 80.0,
        "calibration_bias": "RELIABLE",
        "calibration_warning": "NONE",
        "calibration_data_mode": "PROXY",
        "explanations": ["test report"],
        "live_order_allowed": False,
    }


class Phase2634SidecarIsolationTests(unittest.TestCase):
    def setUp(self):
        self.final_builders = {
            "build_microstructure_report": final_decision_engine.build_microstructure_report,
            "build_options_flow_report": final_decision_engine.build_options_flow_report,
            "build_news_intelligence_report": final_decision_engine.build_news_intelligence_report,
            "build_economic_calendar_report": final_decision_engine.build_economic_calendar_report,
            "build_institutional_liquidity_report": final_decision_engine.build_institutional_liquidity_report,
            "build_scenario_simulation_report": final_decision_engine.build_scenario_simulation_report,
            "build_multi_agent_debate_report": final_decision_engine.build_multi_agent_debate_report,
            "build_self_reflection_report": final_decision_engine.build_self_reflection_report,
            "build_confidence_calibration_report": final_decision_engine.build_confidence_calibration_report,
        }
        self.master_builders = {
            name: getattr(master_controller, name)
            for name in self.final_builders
            if hasattr(master_controller, name)
        }
        for name in self.final_builders:
            setattr(final_decision_engine, name, mutating_report)
        for name in self.master_builders:
            setattr(master_controller, name, mutating_report)

    def tearDown(self):
        for name, value in self.final_builders.items():
            setattr(final_decision_engine, name, value)
        for name, value in self.master_builders.items():
            setattr(master_controller, name, value)

    def _candidate(self):
        return {
            "symbol": "SAFE",
            "side": "LONG",
            "score": 60.0,
            "rank_score": 60.0,
            "raw": {"nested": "ORIGINAL"},
        }

    def _function_node(self, path, name):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail(f"{name} not found in {path}")

    def _assigned_string_keys(self, tree):
        keys = set()
        for child in ast.walk(tree):
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

    def _called_names(self, node):
        names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    names.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    names.add(child.func.attr)
        return names

    def test_final_decision_phase26_34_isolates_original_candidate(self):
        attach_functions = (
            final_decision_engine._attach_microstructure_fields,
            final_decision_engine._attach_options_flow_fields,
            final_decision_engine._attach_news_intelligence_fields,
            final_decision_engine._attach_calendar_fields,
            final_decision_engine._attach_liquidity_fields,
            final_decision_engine._attach_scenario_fields,
            final_decision_engine._attach_debate_fields,
            final_decision_engine._attach_reflection_fields,
            final_decision_engine._attach_calibration_fields,
        )

        for attach in attach_functions:
            candidate = self._candidate()
            original = deepcopy(candidate)
            result = attach(candidate, {})

            self.assertEqual(candidate, original, attach.__name__)
            self.assertEqual(result["symbol"], original["symbol"], attach.__name__)
            self.assertEqual(result["raw"]["nested"], original["raw"]["nested"], attach.__name__)
            self.assertTrue(set(result) & PHASE_RANK_KEYS, attach.__name__)

    def test_master_controller_phase26_34_refreshes_are_report_only_snapshots(self):
        refresh_functions = [getattr(master_controller, name) for name in MASTER_REFRESH_FUNCTIONS]
        for refresh in refresh_functions:
            final_decisions = {
                "selected": [self._candidate()],
                "rejected": [{"symbol": "REJECTED", "raw": {"nested": "ORIGINAL"}}],
                "summary": ["keep"],
            }
            original = deepcopy(final_decisions)
            report = refresh(final_decisions=final_decisions, context={"volume_ratio": 1.2})

            self.assertEqual(final_decisions, original, refresh.__name__)
            self.assertIsInstance(report, dict, refresh.__name__)
            self.assertFalse(report.get("live_order_allowed"), refresh.__name__)

    def test_final_decision_engine_is_only_phase26_34_live_rank_writer(self):
        writers_by_file = {}
        checked_paths = (
            "titan_master_brain/final_decision_engine.py",
            "titan_master_brain/master_controller.py",
            "setup_engine.py",
            "engines/setup_engine.py",
        ) + SIDECAR_ENGINE_PATHS
        for relative_path in checked_paths:
            path = PROJECT_ROOT / relative_path
            tree = ast.parse(path.read_text(encoding="utf-8"))
            assigned = self._assigned_string_keys(tree) & PHASE_RANK_KEYS
            if assigned:
                writers_by_file[relative_path] = assigned

        self.assertEqual(
            set(writers_by_file),
            {"titan_master_brain/final_decision_engine.py"},
            writers_by_file,
        )

    def test_sidecar_engines_do_not_write_live_candidate_or_execution_state(self):
        forbidden_keys = PHASE_RANK_KEYS | {
            "selected",
            "rejected",
            "alert_candidates",
            "execution_packets",
            "scanner_output",
            "broker_state",
            "telegram_state",
            "supabase_state",
        }
        for relative_path in SIDECAR_ENGINE_PATHS:
            path = PROJECT_ROOT / relative_path
            tree = ast.parse(path.read_text(encoding="utf-8"))
            self.assertFalse(self._assigned_string_keys(tree) & forbidden_keys, relative_path)

    def test_master_controller_phase26_34_refreshes_do_not_call_downstream_mutators(self):
        forbidden_calls = {
            "filter_alert_candidates",
            "select_daily_alerts",
            "prepare_execution_packets",
            "send_telegram_signals",
            "mark_alerts_sent",
            "_get_supabase",
            "_safe_supabase_insert",
            "_safe_supabase_update",
            "track_trade_outcomes",
        }
        path = PROJECT_ROOT / "titan_master_brain/master_controller.py"
        for function_name in MASTER_REFRESH_FUNCTIONS:
            node = self._function_node(path, function_name)
            self.assertFalse(self._called_names(node) & forbidden_calls, function_name)


if __name__ == "__main__":
    unittest.main()
