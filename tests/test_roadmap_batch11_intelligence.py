import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch11_intelligence as batch11
import runtime_status


class RoadmapBatch11IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase69": {
                "memory": root / "memory" / "portfolio_consciousness_engine_state.json",
                "runtime": root / "runtime" / "portfolio_consciousness_engine_status.json",
                "report": root / "reports" / "portfolio_consciousness_engine_report.txt",
            },
            "phase70": {
                "memory": root / "memory" / "autonomous_capital_allocation_intelligence_state.json",
                "runtime": root / "runtime" / "autonomous_capital_allocation_intelligence_status.json",
                "report": root / "reports" / "autonomous_capital_allocation_intelligence_report.txt",
            },
            "phase71": {
                "memory": root / "memory" / "master_agi_trading_orchestrator_state.json",
                "runtime": root / "runtime" / "master_agi_trading_orchestrator_status.json",
                "report": root / "reports" / "master_agi_trading_orchestrator_report.txt",
            },
        }

    def test_batch11_progressive_continuity_cross_phase_and_runtime_visibility(self):
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
                                "sector": "financials",
                                "semantic_labels": "correlation cluster fragile stress macro risk_off preservation bottleneck",
                                "regime_label": "macro divergence disagreement",
                                "strategy_family": "BREAKOUT",
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "sector": "financials",
                                "semantic_labels": "rotation capital efficient risk_on offensive alignment converge",
                                "success_reason_label": "capital migration sector synchronized",
                                "strategy_family": "PULLBACK",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            input_paths = {
                **batch11.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "dynamic_risk": root / "memory" / "dynamic_risk_intelligence_state.json",
                "capital_flow": root / "memory" / "capital_flow_intelligence_state.json",
                "meta_regime": root / "memory" / "meta_regime_intelligence_state.json",
                "macro_mesh": root / "memory" / "global_macro_intelligence_mesh_state.json",
                "institutional_coordination": root / "memory" / "institutional_coordination_intelligence_state.json",
                "multi_horizon": root / "memory" / "multi_horizon_intelligence_state.json",
                "long_term_market_memory": root / "memory" / "long_term_market_memory_state.json",
                "advanced_optimization": root / "memory" / "advanced_optimization_framework_state.json",
                "meta_cognition": root / "memory" / "meta_cognition_engine_state.json",
                "swarm_intelligence": root / "memory" / "swarm_intelligence_architecture_state.json",
                "research_lab": root / "memory" / "autonomous_strategy_research_lab_state.json",
                "synthetic_evolution": root / "memory" / "synthetic_market_evolution_engine_state.json",
                "recursive_reflection": root / "memory" / "recursive_self_reflection_state.json",
                "strategy_genome": root / "memory" / "strategy_genome_memory.json",
                "market_narrative": root / "memory" / "market_narrative_intelligence_state.json",
                "crowd_psychology": root / "memory" / "crowd_psychology_state.json",
                "reinforcement_learning": root / "memory" / "reinforcement_learning_memory.json",
                "historical_replay_progress": root / "runtime" / "historical_replay_progress.json",
                "agi_transition": root / "memory" / "agi_transition_layer_state.json",
            }
            self._write_json(input_paths["dynamic_risk"], {"stress_aware_theoretical_sizing_score": 0.52, "regime_aware_risk_score": 0.48})
            self._write_json(input_paths["capital_flow"], {"capital_migration_score": 0.57, "sector_rotation_score": 0.61, "risk_on_score": 0.46, "risk_off_score": 0.53})
            self._write_json(input_paths["meta_regime"], {"global_meta_regime_risk_score": 0.44})
            self._write_json(input_paths["macro_mesh"], {"global_macro_mesh_pressure_score": 0.49, "macro_divergence_score": 0.55})
            self._write_json(input_paths["institutional_coordination"], {"institutional_coordination_score": 0.56})
            self._write_json(input_paths["multi_horizon"], {"timeframe_conflict_score": 0.37, "lower_timeframe_instability_score": 0.42})
            self._write_json(input_paths["long_term_market_memory"], {"crisis_memory_score": 0.47, "structural_failure_memory_score": 0.43})
            self._write_json(input_paths["advanced_optimization"], {"optimization_readiness_score": 0.59, "resource_allocation_hint_score": 0.62})
            self._write_json(input_paths["meta_cognition"], {"reasoning_reliability_score": 0.61, "confidence_of_reasoning_score": 0.57, "supervision_need_score": 0.39, "uncertainty_introspection_score": 0.44, "cognitive_conflict_score": 0.31})
            self._write_json(input_paths["swarm_intelligence"], {"specialist_consensus_score": 0.54, "swarm_coordination_score": 0.58})
            self._write_json(input_paths["research_lab"], {"research_lab_intelligence_score": 0.6, "strategy_hypothesis_confidence_score": 0.57})
            self._write_json(input_paths["recursive_reflection"], {"contradiction_persistence_score": 0.34, "recurring_failure_chain_score": 0.39})
            self._write_json(input_paths["strategy_genome"], {"genome_quality_score": 0.58, "family_count": 5})
            self._write_json(input_paths["market_narrative"], {"narrative_contradiction_score": 0.36})
            self._write_json(input_paths["crowd_psychology"], {"crowd_instability_score": 0.4})
            self._write_json(input_paths["reinforcement_learning"], {"shadow_learning_score": 0.51})
            self._write_json(input_paths["historical_replay_progress"], {"total_records_generated": 240, "batches_completed": 8})
            self._write_json(input_paths["agi_transition"], {"agi_transition_readiness_score": 0.52, "autonomy_readiness_shadow_score": 0.49})

            phase_specs = {
                "phase69_portfolio_consciousness_engine": {
                    "path": phase_paths["phase69"]["runtime"],
                    "fallback_path": phase_paths["phase69"]["memory"],
                    "placement": "master_controller_phase69_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "portfolio_consciousness_score"),
                },
                "phase70_autonomous_capital_allocation_intelligence": {
                    "path": phase_paths["phase70"]["runtime"],
                    "fallback_path": phase_paths["phase70"]["memory"],
                    "placement": "master_controller_phase70_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase69_consumed", "phase69_run_count_seen", "shadow_allocation_intelligence_score"),
                },
                "phase71_master_agi_trading_orchestrator": {
                    "path": phase_paths["phase71"]["runtime"],
                    "fallback_path": phase_paths["phase71"]["memory"],
                    "placement": "master_controller_phase71_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase69_consumed", "phase70_consumed", "phase69_run_count_seen", "phase70_run_count_seen", "master_agi_orchestration_score"),
                },
            }

            with patch.object(batch11, "PHASE_PATHS", phase_paths), patch.object(
                batch11, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch11.run_roadmap_batch11_intelligence(
                    master_input={"market": {"data": {"risk_tone_score": 41, "volatility_score": 64}}},
                    context={"trading_mode": "RESEARCH_ONLY", "risk_tone_score": 41},
                    final_decisions={"ranked": [{"symbol": "AAA", "sector": "financials", "score": 69}, {"symbol": "BBB", "sector": "financials", "score": 63}]},
                )
                second = batch11.run_roadmap_batch11_intelligence(
                    master_input={"market": {"data": {"risk_tone_score": 41, "volatility_score": 64}}},
                    context={"trading_mode": "RESEARCH_ONLY", "risk_tone_score": 41},
                    final_decisions={"ranked": [{"symbol": "AAA", "sector": "financials", "score": 69}, {"symbol": "BBB", "sector": "financials", "score": 63}]},
                )
                visibility = runtime_status._phase_status_summaries()

        phase69 = second["phase69_portfolio_consciousness_engine"]
        phase70 = second["phase70_autonomous_capital_allocation_intelligence"]
        phase71 = second["phase71_master_agi_trading_orchestrator"]

        self.assertEqual(first["phase69_portfolio_consciousness_engine"]["run_count"], 1)
        self.assertEqual(phase69["run_count"], 2)
        self.assertTrue(phase69["continued_from_previous_state"])
        self.assertTrue(phase69["connected"])
        self.assertGreater(phase69["portfolio_consciousness_score"], 0.0)
        self.assertEqual(phase69["recommended_live_weight"], 0.0)
        self.assertEqual(phase69["rank_adjustment"], 0.0)

        self.assertEqual(phase70["run_count"], 2)
        self.assertTrue(phase70["continued_from_previous_state"])
        self.assertTrue(phase70["phase69_consumed"])
        self.assertEqual(phase70["phase69_run_count_seen"], 2)
        self.assertGreater(phase70["shadow_allocation_intelligence_score"], 0.0)

        self.assertEqual(phase71["run_count"], 2)
        self.assertTrue(phase71["continued_from_previous_state"])
        self.assertTrue(phase71["phase69_consumed"])
        self.assertTrue(phase71["phase70_consumed"])
        self.assertEqual(phase71["phase69_run_count_seen"], 2)
        self.assertEqual(phase71["phase70_run_count_seen"], 2)
        self.assertGreater(phase71["master_agi_orchestration_score"], 0.0)
        self.assertEqual(phase71["recommended_live_weight"], 0.0)
        self.assertEqual(phase71["rank_adjustment"], 0.0)

        for key in (
            "phase69_portfolio_consciousness_engine",
            "phase70_autonomous_capital_allocation_intelligence",
            "phase71_master_agi_trading_orchestrator",
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

        self.assertTrue(visibility["phase70_autonomous_capital_allocation_intelligence"]["values"]["phase69_consumed"])
        self.assertTrue(visibility["phase71_master_agi_trading_orchestrator"]["values"]["phase69_consumed"])
        self.assertTrue(visibility["phase71_master_agi_trading_orchestrator"]["values"]["phase70_consumed"])


if __name__ == "__main__":
    unittest.main()
