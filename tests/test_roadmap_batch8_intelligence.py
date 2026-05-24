import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch8_intelligence as batch8
import runtime_status


class RoadmapBatch8IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase60": {
                "memory": root / "memory" / "agi_transition_layer_state.json",
                "runtime": root / "runtime" / "agi_transition_layer_status.json",
                "report": root / "reports" / "agi_transition_layer_report.txt",
            },
            "phase61": {
                "memory": root / "memory" / "neuro_symbolic_reasoning_state.json",
                "runtime": root / "runtime" / "neuro_symbolic_reasoning_status.json",
                "report": root / "reports" / "neuro_symbolic_reasoning_report.txt",
            },
            "phase62": {
                "memory": root / "memory" / "meta_cognition_engine_state.json",
                "runtime": root / "runtime" / "meta_cognition_engine_status.json",
                "report": root / "reports" / "meta_cognition_engine_report.txt",
            },
        }

    def test_batch8_progressive_continuity_cross_phase_and_runtime_visibility(self):
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
                                "semantic_labels": "macro transition liquidity contradiction conflict overconfidence",
                                "failure_reason_label": "failed missed bias",
                                "regime_label": "risk_off cycle",
                                "strategy_family": "BREAKOUT",
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "outcome": "WIN",
                                "semantic_labels": "trend liquidity transition",
                                "success_reason_label": "causal consistency",
                                "regime_label": "risk_on",
                                "strategy_family": "PULLBACK",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            input_paths = {
                **batch8.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "historical_replay_progress": root / "runtime" / "historical_replay_progress.json",
                "hierarchical_brain": root / "memory" / "hierarchical_brain_architecture_state.json",
                "autonomous_goal_management": root / "memory" / "autonomous_goal_management_state.json",
                "knowledge_distillation": root / "memory" / "knowledge_distillation_engine_state.json",
                "recursive_self_reflection": root / "memory" / "recursive_self_reflection_state.json",
                "long_term_market_memory": root / "memory" / "long_term_market_memory_state.json",
                "institutional_coordination": root / "memory" / "institutional_coordination_intelligence_state.json",
                "explainable_ai": root / "memory" / "explainable_ai_engine_state.json",
                "causal_engine": root / "memory" / "causal_market_reasoning_state.json",
                "meta_regime": root / "memory" / "meta_regime_intelligence_state.json",
                "market_narrative": root / "memory" / "market_narrative_intelligence_state.json",
                "crowd_psychology": root / "memory" / "crowd_psychology_state.json",
                "confidence_calibration": root / "confidence" / "latest_confidence_calibration_report.json",
                "accuracy_validation": root / "memory" / "accuracy_validation_state.json",
                "multi_horizon": root / "memory" / "multi_horizon_intelligence_state.json",
                "dynamic_risk": root / "memory" / "dynamic_risk_intelligence_state.json",
                "capital_flow": root / "memory" / "capital_flow_intelligence_state.json",
            }
            self._write_json(input_paths["hierarchical_brain"], {"hierarchy_balance_score": 0.63, "supervisor_layer_score": 0.71, "arbitration_layer_score": 0.66})
            self._write_json(input_paths["autonomous_goal_management"], {"goal_priority_scores": {"survival_first": 0.82, "learning_priority": 0.68}})
            self._write_json(input_paths["knowledge_distillation"], {"distillation_scores": {"failure_learning_score": 0.61, "principle_stability": 0.57}})
            self._write_json(input_paths["recursive_self_reflection"], {"reflection_evolution_score": 0.58, "repeated_reasoning_mistake_score": 0.43, "self_bias_detection_score": 0.46, "contradiction_persistence_score": 0.52})
            self._write_json(input_paths["long_term_market_memory"], {"historical_analog_quality_score": 0.64, "crisis_memory_score": 0.49, "rare_event_archive_score": 0.44})
            self._write_json(input_paths["institutional_coordination"], {"institutional_coordination_score": 0.59})
            self._write_json(input_paths["explainable_ai"], {"contradiction_score": 0.55, "explanation_depth_score": 0.67})
            self._write_json(input_paths["causal_engine"], {"causal_consistency_score": 0.62, "causal_strength_score": 0.58})
            self._write_json(input_paths["meta_regime"], {"global_meta_regime_risk_score": 0.51, "transition_risk_score": 0.47})
            self._write_json(input_paths["market_narrative"], {"narrative_contradiction_score": 0.48})
            self._write_json(input_paths["crowd_psychology"], {"crowd_instability_score": 0.53, "overconfidence_score": 0.45})
            self._write_json(input_paths["confidence_calibration"], {"calibrated_confidence_score": 44})
            self._write_json(input_paths["accuracy_validation"], {"validation_drift_score": 0.36, "confidence_mismatch_score": 0.42})
            self._write_json(input_paths["multi_horizon"], {"timeframe_conflict_score": 0.39})
            self._write_json(input_paths["dynamic_risk"], {"stress_aware_theoretical_sizing_score": 0.57, "regime_aware_risk_score": 0.46})
            self._write_json(input_paths["capital_flow"], {"capital_migration_score": 0.52, "institutional_flow_proxy_score": 0.49})

            master_input = {"market": {"data": {"risk_tone_score": 37, "volatility_score": 78}}}
            context = {"trading_mode": "SELECTIVE", "volatility_score": 78, "risk_tone_score": 37}
            final_decisions = {"ranked": [{"symbol": "AAA", "score": 71, "reason": "conflict high uncertainty"}]}

            phase_specs = {
                "phase60_agi_transition_layer": {
                    "path": phase_paths["phase60"]["runtime"],
                    "fallback_path": phase_paths["phase60"]["memory"],
                    "placement": "master_controller_phase60_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "world_model_signal_score", "agi_transition_readiness_score"),
                },
                "phase61_neuro_symbolic_reasoning_engine": {
                    "path": phase_paths["phase61"]["runtime"],
                    "fallback_path": phase_paths["phase61"]["memory"],
                    "placement": "master_controller_phase61_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase60_consumed", "phase60_run_count_seen", "contradiction_check_score", "reasoning_integrity_score"),
                },
                "phase62_meta_cognition_engine": {
                    "path": phase_paths["phase62"]["runtime"],
                    "fallback_path": phase_paths["phase62"]["memory"],
                    "placement": "master_controller_phase62_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase60_consumed", "phase61_consumed", "phase60_run_count_seen", "phase61_run_count_seen", "reasoning_reliability_score", "meta_cognition_advisory"),
                },
            }

            with patch.object(batch8, "PHASE_PATHS", phase_paths), patch.object(
                batch8, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch8.run_roadmap_batch8_intelligence(master_input=master_input, context=context, final_decisions=final_decisions)
                second = batch8.run_roadmap_batch8_intelligence(master_input=master_input, context=context, final_decisions=final_decisions)
                visibility = runtime_status._phase_status_summaries()

        phase60 = second["phase60_agi_transition_layer"]
        phase61 = second["phase61_neuro_symbolic_reasoning_engine"]
        phase62 = second["phase62_meta_cognition_engine"]

        self.assertEqual(first["phase60_agi_transition_layer"]["run_count"], 1)
        self.assertEqual(phase60["run_count"], 2)
        self.assertTrue(phase60["continued_from_previous_state"])
        self.assertTrue(phase60["connected"])
        self.assertGreater(phase60["agi_transition_readiness_score"], 0.0)
        self.assertEqual(phase60["recommended_live_weight"], 0.0)
        self.assertEqual(phase60["rank_adjustment"], 0.0)

        self.assertEqual(phase61["run_count"], 2)
        self.assertTrue(phase61["continued_from_previous_state"])
        self.assertTrue(phase61["phase60_consumed"])
        self.assertEqual(phase61["phase60_run_count_seen"], 2)
        self.assertGreater(phase61["reasoning_integrity_score"], 0.0)

        self.assertEqual(phase62["run_count"], 2)
        self.assertTrue(phase62["continued_from_previous_state"])
        self.assertTrue(phase62["phase60_consumed"])
        self.assertTrue(phase62["phase61_consumed"])
        self.assertEqual(phase62["phase60_run_count_seen"], 2)
        self.assertEqual(phase62["phase61_run_count_seen"], 2)
        self.assertGreater(phase62["reasoning_reliability_score"], 0.0)
        self.assertEqual(phase62["recommended_live_weight"], 0.0)
        self.assertEqual(phase62["rank_adjustment"], 0.0)

        for key in (
            "phase60_agi_transition_layer",
            "phase61_neuro_symbolic_reasoning_engine",
            "phase62_meta_cognition_engine",
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

        self.assertTrue(visibility["phase61_neuro_symbolic_reasoning_engine"]["values"]["phase60_consumed"])
        self.assertTrue(visibility["phase62_meta_cognition_engine"]["values"]["phase60_consumed"])
        self.assertTrue(visibility["phase62_meta_cognition_engine"]["values"]["phase61_consumed"])


if __name__ == "__main__":
    unittest.main()
