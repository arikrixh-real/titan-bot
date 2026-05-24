import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch5_intelligence as batch5
import runtime_status


class RoadmapBatch5IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase51": {
                "memory": root / "memory" / "hierarchical_brain_architecture_state.json",
                "runtime": root / "runtime" / "hierarchical_brain_architecture_status.json",
                "report": root / "reports" / "hierarchical_brain_architecture_report.txt",
            },
            "phase52": {
                "memory": root / "memory" / "autonomous_goal_management_state.json",
                "runtime": root / "runtime" / "autonomous_goal_management_status.json",
                "report": root / "reports" / "autonomous_goal_management_report.txt",
            },
            "phase53": {
                "memory": root / "memory" / "knowledge_distillation_engine_state.json",
                "runtime": root / "runtime" / "knowledge_distillation_engine_status.json",
                "report": root / "reports" / "knowledge_distillation_engine_report.txt",
            },
        }

    def test_batch5_progressive_continuity_cross_phase_and_runtime_visibility(self):
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
                                "semantic_labels": "fake breakout trap volatile transition",
                                "failure_reason_label": "late entry chase drawdown",
                                "strategy_family": "BREAKOUT",
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "outcome": "WIN",
                                "semantic_labels": "trend pullback recovery",
                                "success_reason_label": "momentum aligned",
                                "strategy_family": "PULLBACK",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            input_paths = {
                **batch5.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "historical_replay_progress": root / "runtime" / "historical_replay_progress.json",
                "accuracy_validation": root / "memory" / "accuracy_validation_state.json",
                "meta_learning": root / "memory" / "meta_learning_state.json",
                "strategy_genome": root / "memory" / "strategy_genome_memory.json",
                "meta_regime": root / "memory" / "meta_regime_intelligence_state.json",
                "temporal_intelligence": root / "memory" / "temporal_intelligence_state.json",
                "market_breadth": root / "memory" / "market_breadth_intelligence_state.json",
                "crowd_psychology": root / "memory" / "crowd_psychology_state.json",
                "market_narrative": root / "memory" / "market_narrative_intelligence_state.json",
                "synthetic_market": root / "memory" / "synthetic_market_simulator_state.json",
                "adversarial_intelligence": root / "memory" / "adversarial_intelligence_state.json",
                "explainable_ai": root / "memory" / "explainable_ai_engine_state.json",
                "memory_consolidation": root / "memory_consolidation" / "latest_memory_consolidation_report.json",
                "strategic_memory_index": root / "memory_consolidation" / "strategic_memory_index.json",
                "master_shadow": root / "memory" / "master_shadow_memory.json",
                "promotion_gate": root / "memory" / "promotion_gate_memory.json",
                "meta_evolution": root / "memory" / "meta_evolution_memory.json",
            }
            self._write_json(input_paths["historical_replay_progress"], {"last_records_generated": 2, "total_records_generated": 10})
            self._write_json(input_paths["accuracy_validation"], {"validation_drift_score": 0.33, "closed_records_this_run": 2})
            self._write_json(input_paths["meta_learning"], {"learning_pressure_score": 0.62, "priority_count": 3})
            self._write_json(input_paths["strategy_genome"], {"family_count": 5, "families": {"BREAKOUT": {"samples": 4}}})
            self._write_json(input_paths["meta_regime"], {"global_meta_regime_risk_score": 0.71, "transition_risk_score": 0.48})
            self._write_json(input_paths["temporal_intelligence"], {"timing_quality_score": 0.44})
            self._write_json(input_paths["market_breadth"], {"hidden_weakness_strength_score": 0.68, "breadth_divergence_score": 0.52})
            self._write_json(input_paths["crowd_psychology"], {"crowd_instability_score": 0.66, "panic_behavior_score": 0.57})
            self._write_json(input_paths["market_narrative"], {"dominant_narrative": "RISK_OFF", "narrative_contradiction_score": 0.49})
            self._write_json(input_paths["synthetic_market"], {"synthetic_market_stress_index": 0.73, "regime_stress_score": 0.67})
            self._write_json(input_paths["adversarial_intelligence"], {"adversarial_replay_signature_score": 0.61, "institutional_bait_score": 0.58})
            self._write_json(input_paths["explainable_ai"], {"explanation_depth_score": 0.75, "contradiction_score": 0.5})
            self._write_json(input_paths["memory_consolidation"], {"memory_quality_score": 71})
            self._write_json(input_paths["strategic_memory_index"], {"patterns": ["fake breakout"]})
            self._write_json(input_paths["master_shadow"], {"run_count": 4})
            self._write_json(input_paths["promotion_gate"], {"run_count": 4})
            self._write_json(input_paths["meta_evolution"], {"run_count": 4})

            phase_specs = {
                "phase51_hierarchical_brain_architecture": {
                    "path": phase_paths["phase51"]["runtime"],
                    "fallback_path": phase_paths["phase51"]["memory"],
                    "placement": "master_controller_phase51_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "reflex_layer_score", "hierarchy_balance_score", "organized_existing_outputs"),
                },
                "phase52_autonomous_goal_management": {
                    "path": phase_paths["phase52"]["runtime"],
                    "fallback_path": phase_paths["phase52"]["memory"],
                    "placement": "master_controller_phase52_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase51_consumed", "phase51_run_count_seen", "dominant_goal", "goal_priority_scores"),
                },
                "phase53_knowledge_distillation_engine": {
                    "path": phase_paths["phase53"]["runtime"],
                    "fallback_path": phase_paths["phase53"]["memory"],
                    "placement": "master_controller_phase53_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase51_consumed", "phase52_consumed", "phase51_run_count_seen", "phase52_run_count_seen", "prior_intelligence_consumed", "high_value_principles", "failure_summaries", "distillation_scores"),
                },
            }
            master_input = {"market": {"data": {"risk_tone_score": 78}}}
            context = {"trading_mode": "SELECTIVE", "risk_tone_score": 78}
            final_decisions = {"ranked": [{"symbol": "AAA", "score": 71}]}

            with patch.object(batch5, "PHASE_PATHS", phase_paths), patch.object(
                batch5, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch5.run_roadmap_batch5_intelligence(master_input=master_input, context=context, final_decisions=final_decisions)
                second = batch5.run_roadmap_batch5_intelligence(master_input=master_input, context=context, final_decisions=final_decisions)
                visibility = runtime_status._phase_status_summaries()

        phase51 = second["phase51_hierarchical_brain_architecture"]
        phase52 = second["phase52_autonomous_goal_management"]
        phase53 = second["phase53_knowledge_distillation_engine"]

        self.assertEqual(first["phase51_hierarchical_brain_architecture"]["run_count"], 1)
        self.assertEqual(phase51["run_count"], 2)
        self.assertTrue(phase51["continued_from_previous_state"])
        self.assertTrue(phase51["connected"])
        self.assertTrue(phase51["hierarchy_layers"])
        self.assertGreaterEqual(phase51["hierarchy_balance_score"], 0.0)

        self.assertEqual(phase52["run_count"], 2)
        self.assertTrue(phase52["continued_from_previous_state"])
        self.assertTrue(phase52["phase51_consumed"])
        self.assertEqual(phase52["phase51_run_count_seen"], 2)
        self.assertTrue(phase52["goal_priority_scores"])
        self.assertTrue(phase52["advisory_objectives"])

        self.assertEqual(phase53["run_count"], 2)
        self.assertTrue(phase53["continued_from_previous_state"])
        self.assertTrue(phase53["phase51_consumed"])
        self.assertTrue(phase53["phase52_consumed"])
        self.assertEqual(phase53["phase51_run_count_seen"], 2)
        self.assertEqual(phase53["phase52_run_count_seen"], 2)
        self.assertTrue(phase53["high_value_principles"])
        self.assertTrue(phase53["distillation_scores"])
        self.assertTrue(phase53["prior_intelligence_consumed"]["strategy_genome"])

        for key in (
            "phase51_hierarchical_brain_architecture",
            "phase52_autonomous_goal_management",
            "phase53_knowledge_distillation_engine",
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

        self.assertTrue(visibility["phase52_autonomous_goal_management"]["values"]["phase51_consumed"])
        self.assertTrue(visibility["phase53_knowledge_distillation_engine"]["values"]["phase51_consumed"])
        self.assertTrue(visibility["phase53_knowledge_distillation_engine"]["values"]["phase52_consumed"])


if __name__ == "__main__":
    unittest.main()
