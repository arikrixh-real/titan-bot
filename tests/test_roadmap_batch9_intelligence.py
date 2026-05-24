import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch9_intelligence as batch9
import runtime_status


class RoadmapBatch9IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase63": {
                "memory": root / "memory" / "swarm_intelligence_architecture_state.json",
                "runtime": root / "runtime" / "swarm_intelligence_architecture_status.json",
                "report": root / "reports" / "swarm_intelligence_architecture_report.txt",
            },
            "phase64": {
                "memory": root / "memory" / "federated_intelligence_system_state.json",
                "runtime": root / "runtime" / "federated_intelligence_system_status.json",
                "report": root / "reports" / "federated_intelligence_system_report.txt",
            },
            "phase65": {
                "memory": root / "memory" / "advanced_optimization_framework_state.json",
                "runtime": root / "runtime" / "advanced_optimization_framework_status.json",
                "report": root / "reports" / "advanced_optimization_framework_report.txt",
            },
        }

    def test_batch9_progressive_continuity_cross_phase_and_runtime_visibility(self):
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
                                "semantic_labels": "strategy risk regime narrative execution reflection contradiction",
                                "failure_reason_label": "missed uncertain stress loss",
                                "regime_label": "macro transition",
                                "strategy_family": "BREAKOUT",
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "semantic_labels": "memory distill principle pattern scenario shock",
                                "success_reason_label": "strategy setup lesson",
                                "regime_label": "risk_on cycle",
                                "strategy_family": "PULLBACK",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            input_paths = {
                **batch9.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "meta_cognition": root / "memory" / "meta_cognition_engine_state.json",
                "agi_transition": root / "memory" / "agi_transition_layer_state.json",
                "neuro_symbolic": root / "memory" / "neuro_symbolic_reasoning_state.json",
                "institutional_coordination": root / "memory" / "institutional_coordination_intelligence_state.json",
                "knowledge_distillation": root / "memory" / "knowledge_distillation_engine_state.json",
                "memory_consolidation": root / "memory_consolidation" / "latest_memory_consolidation_report.json",
                "long_term_market_memory": root / "memory" / "long_term_market_memory_state.json",
                "meta_learning": root / "memory" / "meta_learning_state.json",
                "goal_management": root / "memory" / "autonomous_goal_management_state.json",
                "dynamic_risk": root / "memory" / "dynamic_risk_intelligence_state.json",
                "strategy_genome": root / "memory" / "strategy_genome_memory.json",
                "market_narrative": root / "memory" / "market_narrative_intelligence_state.json",
                "crowd_psychology": root / "memory" / "crowd_psychology_state.json",
                "explainable_ai": root / "memory" / "explainable_ai_engine_state.json",
                "accuracy_validation": root / "memory" / "accuracy_validation_state.json",
                "synthetic_market": root / "memory" / "synthetic_market_simulator_state.json",
                "recursive_reflection": root / "memory" / "recursive_self_reflection_state.json",
            }
            self._write_json(input_paths["meta_cognition"], {"reasoning_reliability_score": 0.61, "confidence_of_reasoning_score": 0.58, "supervision_need_score": 0.42})
            self._write_json(input_paths["agi_transition"], {"world_model_signal_score": 0.66, "governance_alignment_score": 0.64, "agi_transition_readiness_score": 0.57, "improvement_planning_shadow_score": 0.53})
            self._write_json(input_paths["neuro_symbolic"], {"reasoning_integrity_score": 0.59})
            self._write_json(input_paths["institutional_coordination"], {"institutional_coordination_score": 0.62})
            self._write_json(input_paths["knowledge_distillation"], {"distillation_scores": {"principle_stability": 0.68, "failure_learning": 0.54}})
            self._write_json(input_paths["memory_consolidation"], {"memory_quality_score": 0.57})
            self._write_json(input_paths["long_term_market_memory"], {"historical_analog_quality_score": 0.55, "volatility_regime_transition_score": 0.49})
            self._write_json(input_paths["meta_learning"], {"priority_count": 7, "learning_velocity_score": 0.46})
            self._write_json(input_paths["goal_management"], {"goal_priority_scores": {"learning_priority": 0.72, "survival_first": 0.81}})
            self._write_json(input_paths["dynamic_risk"], {"regime_aware_risk_score": 0.37, "stress_aware_theoretical_sizing_score": 0.31})
            self._write_json(input_paths["strategy_genome"], {"family_count": 4, "genome_quality_score": 0.52})
            self._write_json(input_paths["market_narrative"], {"narrative_persistence_score": 0.48})
            self._write_json(input_paths["crowd_psychology"], {"crowd_instability_score": 0.33, "overconfidence_score": 0.36})
            self._write_json(input_paths["explainable_ai"], {"explanation_depth_score": 0.63})
            self._write_json(input_paths["accuracy_validation"], {"validation_drift_score": 0.29, "confidence_mismatch_score": 0.35})
            self._write_json(input_paths["synthetic_market"], {"synthetic_market_stress_index": 0.44, "regime_stress_score": 0.39})
            self._write_json(input_paths["recursive_reflection"], {"reflection_evolution_score": 0.56, "self_bias_detection_score": 0.41, "missed_opportunity_pattern_score": 0.38})

            phase_specs = {
                "phase63_swarm_intelligence_architecture": {
                    "path": phase_paths["phase63"]["runtime"],
                    "fallback_path": phase_paths["phase63"]["memory"],
                    "placement": "master_controller_phase63_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "agent_roles", "specialist_consensus_score"),
                },
                "phase64_federated_intelligence_system": {
                    "path": phase_paths["phase64"]["runtime"],
                    "fallback_path": phase_paths["phase64"]["memory"],
                    "placement": "master_controller_phase64_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase63_consumed", "phase63_run_count_seen", "federated_readiness_score"),
                },
                "phase65_advanced_optimization_framework": {
                    "path": phase_paths["phase65"]["runtime"],
                    "fallback_path": phase_paths["phase65"]["memory"],
                    "placement": "master_controller_phase65_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase63_consumed", "phase64_consumed", "phase63_run_count_seen", "phase64_run_count_seen", "optimization_readiness_score"),
                },
            }

            with patch.object(batch9, "PHASE_PATHS", phase_paths), patch.object(
                batch9, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch9.run_roadmap_batch9_intelligence(
                    master_input={"market": {"data": {"risk_tone_score": 44}}},
                    context={"trading_mode": "RESEARCH_ONLY"},
                    final_decisions={"ranked": [{"symbol": "AAA", "score": 71}]},
                )
                second = batch9.run_roadmap_batch9_intelligence(
                    master_input={"market": {"data": {"risk_tone_score": 44}}},
                    context={"trading_mode": "RESEARCH_ONLY"},
                    final_decisions={"ranked": [{"symbol": "AAA", "score": 71}]},
                )
                visibility = runtime_status._phase_status_summaries()

        phase63 = second["phase63_swarm_intelligence_architecture"]
        phase64 = second["phase64_federated_intelligence_system"]
        phase65 = second["phase65_advanced_optimization_framework"]

        self.assertEqual(first["phase63_swarm_intelligence_architecture"]["run_count"], 1)
        self.assertEqual(phase63["run_count"], 2)
        self.assertTrue(phase63["continued_from_previous_state"])
        self.assertTrue(phase63["connected"])
        self.assertGreater(phase63["specialist_consensus_score"], 0.0)
        self.assertIn("strategy_agent", phase63["agent_roles"])
        self.assertEqual(phase63["recommended_live_weight"], 0.0)
        self.assertEqual(phase63["rank_adjustment"], 0.0)

        self.assertEqual(phase64["run_count"], 2)
        self.assertTrue(phase64["continued_from_previous_state"])
        self.assertTrue(phase64["phase63_consumed"])
        self.assertEqual(phase64["phase63_run_count_seen"], 2)
        self.assertGreater(phase64["federated_readiness_score"], 0.0)

        self.assertEqual(phase65["run_count"], 2)
        self.assertTrue(phase65["continued_from_previous_state"])
        self.assertTrue(phase65["phase63_consumed"])
        self.assertTrue(phase65["phase64_consumed"])
        self.assertEqual(phase65["phase63_run_count_seen"], 2)
        self.assertEqual(phase65["phase64_run_count_seen"], 2)
        self.assertGreater(phase65["optimization_readiness_score"], 0.0)
        self.assertEqual(phase65["recommended_live_weight"], 0.0)
        self.assertEqual(phase65["rank_adjustment"], 0.0)

        for key in (
            "phase63_swarm_intelligence_architecture",
            "phase64_federated_intelligence_system",
            "phase65_advanced_optimization_framework",
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

        self.assertTrue(visibility["phase64_federated_intelligence_system"]["values"]["phase63_consumed"])
        self.assertTrue(visibility["phase65_advanced_optimization_framework"]["values"]["phase63_consumed"])
        self.assertTrue(visibility["phase65_advanced_optimization_framework"]["values"]["phase64_consumed"])


if __name__ == "__main__":
    unittest.main()
