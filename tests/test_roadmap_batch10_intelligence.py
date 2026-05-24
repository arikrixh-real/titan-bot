import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch10_intelligence as batch10
import runtime_status


class RoadmapBatch10IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase66": {
                "memory": root / "memory" / "autonomous_strategy_research_lab_state.json",
                "runtime": root / "runtime" / "autonomous_strategy_research_lab_status.json",
                "report": root / "reports" / "autonomous_strategy_research_lab_report.txt",
            },
            "phase67": {
                "memory": root / "memory" / "synthetic_market_evolution_engine_state.json",
                "runtime": root / "runtime" / "synthetic_market_evolution_engine_status.json",
                "report": root / "reports" / "synthetic_market_evolution_engine_report.txt",
            },
            "phase68": {
                "memory": root / "memory" / "global_macro_intelligence_mesh_state.json",
                "runtime": root / "runtime" / "global_macro_intelligence_mesh_status.json",
                "report": root / "reports" / "global_macro_intelligence_mesh_report.txt",
            },
        }

    def test_batch10_progressive_continuity_cross_phase_and_runtime_visibility(self):
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
                                "semantic_labels": "failed repeat hypothesis sandbox macro liquidity transition risk_off",
                                "failure_reason_label": "contradiction overfit missed volatility shock",
                                "regime_label": "macro divergence cross asset",
                                "strategy_family": "BREAKOUT",
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "semantic_labels": "innovation mutation experiment fake stability trap capital migration risk_on",
                                "success_reason_label": "new hypothesis validation",
                                "regime_label": "sector rotation global liquidity",
                                "strategy_family": "PULLBACK",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            input_paths = {
                **batch10.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "historical_replay_progress": root / "runtime" / "historical_replay_progress.json",
                "strategy_genome": root / "memory" / "strategy_genome_memory.json",
                "meta_learning": root / "memory" / "meta_learning_state.json",
                "autonomous_research": root / "research" / "autonomous_research_report.json",
                "backtesting_validation": root / "research" / "backtesting_validation_report.json",
                "advanced_optimization": root / "memory" / "advanced_optimization_framework_state.json",
                "swarm_intelligence": root / "memory" / "swarm_intelligence_architecture_state.json",
                "recursive_reflection": root / "memory" / "recursive_self_reflection_state.json",
                "meta_cognition": root / "memory" / "meta_cognition_engine_state.json",
                "knowledge_distillation": root / "memory" / "knowledge_distillation_engine_state.json",
                "synthetic_market": root / "memory" / "synthetic_market_simulator_state.json",
                "adversarial_intelligence": root / "memory" / "adversarial_intelligence_state.json",
                "dynamic_risk": root / "memory" / "dynamic_risk_intelligence_state.json",
                "multi_horizon": root / "memory" / "multi_horizon_intelligence_state.json",
                "scenario_simulation": root / "scenario" / "latest_scenario_simulation_report.json",
                "meta_regime": root / "memory" / "meta_regime_intelligence_state.json",
                "capital_flow": root / "memory" / "capital_flow_intelligence_state.json",
                "institutional_coordination": root / "memory" / "institutional_coordination_intelligence_state.json",
                "temporal_intelligence": root / "memory" / "temporal_intelligence_state.json",
                "long_term_market_memory": root / "memory" / "long_term_market_memory_state.json",
                "market_narrative": root / "memory" / "market_narrative_intelligence_state.json",
            }
            self._write_json(input_paths["historical_replay_progress"], {"total_records_generated": 240, "batches_completed": 8})
            self._write_json(input_paths["strategy_genome"], {"family_count": 5, "genome_quality_score": 0.58})
            self._write_json(input_paths["meta_learning"], {"priority_count": 6, "learning_velocity_score": 0.49})
            self._write_json(input_paths["autonomous_research"], {"research_mode": "SHADOW", "research_priority_score": 0.61})
            self._write_json(input_paths["backtesting_validation"], {"validation_score": 0.57, "validation_quality_score": 0.55})
            self._write_json(input_paths["advanced_optimization"], {"research_priority_optimization_score": 0.63, "optimization_readiness_score": 0.59})
            self._write_json(input_paths["swarm_intelligence"], {"specialist_consensus_score": 0.54, "swarm_coordination_score": 0.52})
            self._write_json(input_paths["recursive_reflection"], {"repeated_reasoning_mistake_score": 0.38, "recurring_failure_chain_score": 0.42})
            self._write_json(input_paths["meta_cognition"], {"reasoning_reliability_score": 0.61, "uncertainty_introspection_score": 0.44, "supervision_need_score": 0.39, "self_doubt_score": 0.35})
            self._write_json(input_paths["knowledge_distillation"], {"distillation_scores": {"principle_stability": 0.62, "failure_learning": 0.55}})
            self._write_json(input_paths["synthetic_market"], {"synthetic_market_stress_index": 0.47, "regime_stress_score": 0.43, "volatility_shock_score": 0.51, "panic_simulation_score": 0.46, "liquidity_collapse_score": 0.41, "fake_breakout_environment_score": 0.49})
            self._write_json(input_paths["adversarial_intelligence"], {"adversarial_replay_signature_score": 0.48, "institutional_bait_score": 0.45})
            self._write_json(input_paths["dynamic_risk"], {"stress_aware_theoretical_sizing_score": 0.52, "regime_aware_risk_score": 0.46})
            self._write_json(input_paths["multi_horizon"], {"timeframe_conflict_score": 0.37, "lower_timeframe_instability_score": 0.42})
            self._write_json(input_paths["scenario_simulation"], {"scenario_risk_score": 0.5, "stress_score": 0.47})
            self._write_json(input_paths["meta_regime"], {"global_meta_regime_risk_score": 0.44, "transition_risk_score": 0.39})
            self._write_json(input_paths["capital_flow"], {"risk_on_score": 0.46, "risk_off_score": 0.51, "capital_migration_score": 0.57, "institutional_flow_proxy_score": 0.53, "defensive_transition_score": 0.49, "offensive_transition_score": 0.43})
            self._write_json(input_paths["institutional_coordination"], {"institutional_coordination_score": 0.56})
            self._write_json(input_paths["temporal_intelligence"], {"timing_synchronization_score": 0.52, "timing_quality_score": 0.58})
            self._write_json(input_paths["long_term_market_memory"], {"macro_event_memory_score": 0.48, "historical_analog_quality_score": 0.54})
            self._write_json(input_paths["market_narrative"], {"narrative_persistence_score": 0.55})

            phase_specs = {
                "phase66_autonomous_strategy_research_lab": {
                    "path": phase_paths["phase66"]["runtime"],
                    "fallback_path": phase_paths["phase66"]["memory"],
                    "placement": "master_controller_phase66_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "experiment_quality_score", "research_lab_intelligence_score"),
                },
                "phase67_synthetic_market_evolution_engine": {
                    "path": phase_paths["phase67"]["runtime"],
                    "fallback_path": phase_paths["phase67"]["memory"],
                    "placement": "master_controller_phase67_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase66_consumed", "phase66_run_count_seen", "synthetic_evolution_intelligence_score"),
                },
                "phase68_global_macro_intelligence_mesh": {
                    "path": phase_paths["phase68"]["runtime"],
                    "fallback_path": phase_paths["phase68"]["memory"],
                    "placement": "master_controller_phase68_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase66_consumed", "phase67_consumed", "phase66_run_count_seen", "phase67_run_count_seen", "global_macro_mesh_pressure_score"),
                },
            }

            with patch.object(batch10, "PHASE_PATHS", phase_paths), patch.object(
                batch10, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch10.run_roadmap_batch10_intelligence(
                    master_input={"market": {"data": {"risk_tone_score": 41, "volatility_score": 64}}},
                    context={"trading_mode": "RESEARCH_ONLY", "risk_tone_score": 41},
                    final_decisions={"ranked": [{"symbol": "AAA", "score": 69}]},
                )
                second = batch10.run_roadmap_batch10_intelligence(
                    master_input={"market": {"data": {"risk_tone_score": 41, "volatility_score": 64}}},
                    context={"trading_mode": "RESEARCH_ONLY", "risk_tone_score": 41},
                    final_decisions={"ranked": [{"symbol": "AAA", "score": 69}]},
                )
                visibility = runtime_status._phase_status_summaries()

        phase66 = second["phase66_autonomous_strategy_research_lab"]
        phase67 = second["phase67_synthetic_market_evolution_engine"]
        phase68 = second["phase68_global_macro_intelligence_mesh"]

        self.assertEqual(first["phase66_autonomous_strategy_research_lab"]["run_count"], 1)
        self.assertEqual(phase66["run_count"], 2)
        self.assertTrue(phase66["continued_from_previous_state"])
        self.assertTrue(phase66["connected"])
        self.assertGreater(phase66["research_lab_intelligence_score"], 0.0)
        self.assertEqual(phase66["recommended_live_weight"], 0.0)
        self.assertEqual(phase66["rank_adjustment"], 0.0)

        self.assertEqual(phase67["run_count"], 2)
        self.assertTrue(phase67["continued_from_previous_state"])
        self.assertTrue(phase67["phase66_consumed"])
        self.assertEqual(phase67["phase66_run_count_seen"], 2)
        self.assertGreater(phase67["synthetic_evolution_intelligence_score"], 0.0)

        self.assertEqual(phase68["run_count"], 2)
        self.assertTrue(phase68["continued_from_previous_state"])
        self.assertTrue(phase68["phase66_consumed"])
        self.assertTrue(phase68["phase67_consumed"])
        self.assertEqual(phase68["phase66_run_count_seen"], 2)
        self.assertEqual(phase68["phase67_run_count_seen"], 2)
        self.assertGreater(phase68["global_macro_mesh_pressure_score"], 0.0)
        self.assertEqual(phase68["recommended_live_weight"], 0.0)
        self.assertEqual(phase68["rank_adjustment"], 0.0)

        for key in (
            "phase66_autonomous_strategy_research_lab",
            "phase67_synthetic_market_evolution_engine",
            "phase68_global_macro_intelligence_mesh",
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

        self.assertTrue(visibility["phase67_synthetic_market_evolution_engine"]["values"]["phase66_consumed"])
        self.assertTrue(visibility["phase68_global_macro_intelligence_mesh"]["values"]["phase66_consumed"])
        self.assertTrue(visibility["phase68_global_macro_intelligence_mesh"]["values"]["phase67_consumed"])


if __name__ == "__main__":
    unittest.main()
