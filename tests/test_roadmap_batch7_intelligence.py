import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch7_intelligence as batch7
import runtime_status


class RoadmapBatch7IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase57": {
                "memory": root / "memory" / "recursive_self_reflection_state.json",
                "runtime": root / "runtime" / "recursive_self_reflection_status.json",
                "report": root / "reports" / "recursive_self_reflection_report.txt",
            },
            "phase58": {
                "memory": root / "memory" / "long_term_market_memory_state.json",
                "runtime": root / "runtime" / "long_term_market_memory_status.json",
                "report": root / "reports" / "long_term_market_memory_report.txt",
            },
            "phase59": {
                "memory": root / "memory" / "institutional_coordination_intelligence_state.json",
                "runtime": root / "runtime" / "institutional_coordination_intelligence_status.json",
                "report": root / "reports" / "institutional_coordination_intelligence_report.txt",
            },
        }

    def test_batch7_progressive_continuity_cross_phase_and_runtime_visibility(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase_paths = self._phase_paths(root)
            experience_jsonl = root / "experience" / "historical_experience_import.jsonl"
            experience_jsonl.parent.mkdir(parents=True, exist_ok=True)
            experience_jsonl.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "symbol": "AAA",
                                "outcome": "LOSS",
                                "semantic_labels": "fake breakout trap overconfidence drawdown risk_off crisis shock",
                                "failure_reason_label": "late entry chase loss streak sl hit",
                                "regime_label": "volatile transition macro policy inflation",
                                "strategy_family": "BREAKOUT",
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "outcome": "WIN",
                                "semantic_labels": "risk_on boom euphoria pullback",
                                "success_reason_label": "trend synchronized",
                                "regime_label": "volatility expansion",
                                "strategy_family": "PULLBACK",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            input_paths = {
                **batch7.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "historical_replay_progress": root / "runtime" / "historical_replay_progress.json",
                "accuracy_validation": root / "memory" / "accuracy_validation_state.json",
                "meta_learning": root / "memory" / "meta_learning_state.json",
                "explainable_ai": root / "memory" / "explainable_ai_engine_state.json",
                "adversarial_intelligence": root / "memory" / "adversarial_intelligence_state.json",
                "dynamic_risk_intelligence": root / "memory" / "dynamic_risk_intelligence_state.json",
                "hierarchical_brain": root / "memory" / "hierarchical_brain_architecture_state.json",
                "knowledge_distillation": root / "memory" / "knowledge_distillation_engine_state.json",
                "no_trade_memory": root / "memory" / "no_trade_refinement_memory.json",
                "temporal_intelligence": root / "memory" / "temporal_intelligence_state.json",
                "market_narrative": root / "memory" / "market_narrative_intelligence_state.json",
                "meta_regime": root / "memory" / "meta_regime_intelligence_state.json",
                "synthetic_market": root / "memory" / "synthetic_market_simulator_state.json",
                "capital_flow": root / "memory" / "capital_flow_intelligence_state.json",
                "multi_horizon": root / "memory" / "multi_horizon_intelligence_state.json",
                "autonomous_goal_management": root / "memory" / "autonomous_goal_management_state.json",
                "confidence_calibration": root / "confidence" / "latest_confidence_calibration_report.json",
                "options_flow": root / "options" / "latest_options_flow_report.json",
                "institutional_liquidity": root / "liquidity" / "latest_institutional_liquidity_report.json",
            }
            self._write_json(input_paths["historical_replay_progress"], {"last_records_generated": 2, "total_records_generated": 20})
            self._write_json(input_paths["accuracy_validation"], {"validation_drift_score": 0.37, "confidence_mismatch_score": 0.52})
            self._write_json(input_paths["meta_learning"], {"learning_pressure_score": 0.62, "priority_count": 4})
            self._write_json(input_paths["explainable_ai"], {"contradiction_score": 0.57, "explanation_depth_score": 0.66})
            self._write_json(input_paths["adversarial_intelligence"], {"adversarial_replay_signature_score": 0.63, "institutional_bait_score": 0.58, "trap_structure_score": 0.54})
            self._write_json(input_paths["dynamic_risk_intelligence"], {"stress_aware_theoretical_sizing_score": 0.69, "drawdown_aware_caution_score": 0.61})
            self._write_json(input_paths["hierarchical_brain"], {"supervisor_layer_score": 0.64, "arbitration_layer_score": 0.56, "reflex_layer_score": 0.59})
            self._write_json(input_paths["knowledge_distillation"], {"distillation_scores": {"failure_learning_score": 0.6}})
            self._write_json(input_paths["no_trade_memory"], {"missed_opportunity_score": 0.45})
            self._write_json(input_paths["temporal_intelligence"], {"timing_quality_score": 0.42})
            self._write_json(input_paths["market_narrative"], {"narrative_persistence_score": 0.67, "narrative_contradiction_score": 0.48})
            self._write_json(input_paths["meta_regime"], {"global_meta_regime_risk_score": 0.71, "transition_risk_score": 0.53})
            self._write_json(input_paths["synthetic_market"], {"synthetic_market_stress_index": 0.74, "rare_event_replay_score": 0.68, "volatility_shock_score": 0.72})
            self._write_json(input_paths["capital_flow"], {"capital_migration_score": 0.55, "defensive_transition_score": 0.62})
            self._write_json(input_paths["multi_horizon"], {"timeframe_conflict_score": 0.46, "lower_timeframe_instability_score": 0.51})
            self._write_json(input_paths["autonomous_goal_management"], {"goal_priority_scores": {"survival_first": 0.74}})
            self._write_json(input_paths["confidence_calibration"], {"calibrated_confidence_score": 41})
            self._write_json(input_paths["options_flow"], {"options_risk_score": 0.49, "iv_pressure_score": 0.57})
            self._write_json(input_paths["institutional_liquidity"], {"liquidity_risk_score": 0.43})

            master_input = {"market": {"data": {"risk_tone_score": 36, "volatility_score": 84}}}
            context = {"trading_mode": "SELECTIVE", "volatility_score": 84, "risk_tone_score": 36}
            final_decisions = {"ranked": [{"symbol": "AAA", "score": 71, "reason": "high confidence loss conflict"}]}

            phase_specs = {
                "phase57_recursive_self_reflection_engine": {
                    "path": phase_paths["phase57"]["runtime"],
                    "fallback_path": phase_paths["phase57"]["memory"],
                    "placement": "master_controller_phase57_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "repeated_reasoning_mistake_score", "contradiction_persistence_score"),
                },
                "phase58_long_term_market_memory": {
                    "path": phase_paths["phase58"]["runtime"],
                    "fallback_path": phase_paths["phase58"]["memory"],
                    "placement": "master_controller_phase58_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase57_consumed", "phase57_run_count_seen", "crisis_memory_score", "historical_analog_quality_score"),
                },
                "phase59_institutional_coordination_intelligence": {
                    "path": phase_paths["phase59"]["runtime"],
                    "fallback_path": phase_paths["phase59"]["memory"],
                    "placement": "master_controller_phase59_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase57_consumed", "phase58_consumed", "phase57_run_count_seen", "phase58_run_count_seen", "institutional_coordination_score", "desk_coordination_scores"),
                },
            }

            with patch.object(batch7, "PHASE_PATHS", phase_paths), patch.object(
                batch7, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch7.run_roadmap_batch7_intelligence(master_input=master_input, context=context, final_decisions=final_decisions)
                second = batch7.run_roadmap_batch7_intelligence(master_input=master_input, context=context, final_decisions=final_decisions)
                visibility = runtime_status._phase_status_summaries()

        phase57 = second["phase57_recursive_self_reflection_engine"]
        phase58 = second["phase58_long_term_market_memory"]
        phase59 = second["phase59_institutional_coordination_intelligence"]

        self.assertEqual(first["phase57_recursive_self_reflection_engine"]["run_count"], 1)
        self.assertEqual(phase57["run_count"], 2)
        self.assertTrue(phase57["continued_from_previous_state"])
        self.assertTrue(phase57["connected"])
        self.assertGreaterEqual(phase57["repeated_reasoning_mistake_score"], 0.0)
        self.assertEqual(phase57["recommended_live_weight"], 0.0)
        self.assertEqual(phase57["rank_adjustment"], 0.0)

        self.assertEqual(phase58["run_count"], 2)
        self.assertTrue(phase58["continued_from_previous_state"])
        self.assertTrue(phase58["phase57_consumed"])
        self.assertEqual(phase58["phase57_run_count_seen"], 2)
        self.assertGreaterEqual(phase58["historical_analog_quality_score"], 0.0)

        self.assertEqual(phase59["run_count"], 2)
        self.assertTrue(phase59["continued_from_previous_state"])
        self.assertTrue(phase59["phase57_consumed"])
        self.assertTrue(phase59["phase58_consumed"])
        self.assertEqual(phase59["phase57_run_count_seen"], 2)
        self.assertEqual(phase59["phase58_run_count_seen"], 2)
        self.assertGreaterEqual(phase59["institutional_coordination_score"], 0.0)
        self.assertEqual(phase59["recommended_live_weight"], 0.0)
        self.assertEqual(phase59["rank_adjustment"], 0.0)

        for key in (
            "phase57_recursive_self_reflection_engine",
            "phase58_long_term_market_memory",
            "phase59_institutional_coordination_intelligence",
        ):
            self.assertIn(key, visibility)
            summary = visibility[key]
            self.assertTrue(summary["connected"])
            self.assertTrue(summary["values"])
            self.assertTrue(summary["advisory_only"])
            self.assertTrue(summary["shadow_mode"])
            self.assertFalse(summary["safety"]["affects_live_ranking"])
            self.assertFalse(summary["safety"]["affects_execution"])
            self.assertFalse(summary["safety"]["broker_mutation"])
            self.assertFalse(summary["safety"]["telegram_mutation"])
            self.assertFalse(summary["safety"]["supabase_mutation"])

        self.assertTrue(visibility["phase58_long_term_market_memory"]["values"]["phase57_consumed"])
        self.assertTrue(visibility["phase59_institutional_coordination_intelligence"]["values"]["phase57_consumed"])
        self.assertTrue(visibility["phase59_institutional_coordination_intelligence"]["values"]["phase58_consumed"])


if __name__ == "__main__":
    unittest.main()
