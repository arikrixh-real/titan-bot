import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch6_intelligence as batch6
import runtime_status


class RoadmapBatch6IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase54": {
                "memory": root / "memory" / "multi_horizon_intelligence_state.json",
                "runtime": root / "runtime" / "multi_horizon_intelligence_status.json",
                "report": root / "reports" / "multi_horizon_intelligence_report.txt",
            },
            "phase55": {
                "memory": root / "memory" / "capital_flow_intelligence_state.json",
                "runtime": root / "runtime" / "capital_flow_intelligence_status.json",
                "report": root / "reports" / "capital_flow_intelligence_report.txt",
            },
            "phase56": {
                "memory": root / "memory" / "dynamic_risk_intelligence_state.json",
                "runtime": root / "runtime" / "dynamic_risk_intelligence_status.json",
                "report": root / "reports" / "dynamic_risk_intelligence_report.txt",
            },
        }

    def test_batch6_progressive_continuity_cross_phase_and_runtime_visibility(self):
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
                                "semantic_labels": "fake breakout trap drawdown risk_off exhaustion",
                                "failure_reason_label": "late entry chase loss streak",
                                "regime_label": "volatile transition",
                                "strategy_family": "BREAKOUT",
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "outcome": "WIN",
                                "semantic_labels": "trend pullback risk_on aligned",
                                "success_reason_label": "momentum synchronized",
                                "strategy_family": "PULLBACK",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            input_paths = {
                **batch6.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "historical_replay_progress": root / "runtime" / "historical_replay_progress.json",
                "temporal_intelligence": root / "memory" / "temporal_intelligence_state.json",
                "market_breadth": root / "memory" / "market_breadth_intelligence_state.json",
                "crowd_psychology": root / "memory" / "crowd_psychology_state.json",
                "market_narrative": root / "memory" / "market_narrative_intelligence_state.json",
                "strategy_genome": root / "memory" / "strategy_genome_memory.json",
                "meta_regime": root / "memory" / "meta_regime_intelligence_state.json",
                "accuracy_validation": root / "memory" / "accuracy_validation_state.json",
                "synthetic_market": root / "memory" / "synthetic_market_simulator_state.json",
                "adversarial_intelligence": root / "memory" / "adversarial_intelligence_state.json",
                "autonomous_goal_management": root / "memory" / "autonomous_goal_management_state.json",
                "confidence_calibration": root / "confidence" / "latest_confidence_calibration_report.json",
            }
            self._write_json(input_paths["historical_replay_progress"], {"last_records_generated": 2, "total_records_generated": 10})
            self._write_json(input_paths["temporal_intelligence"], {"timing_quality_score": 0.42})
            self._write_json(input_paths["market_breadth"], {"market_participation_health_score": 0.44, "market_wide_confirmation_quality": 0.41, "hidden_weakness_strength_score": 0.68})
            self._write_json(input_paths["crowd_psychology"], {"crowd_instability_score": 0.66, "panic_behavior_score": 0.57})
            self._write_json(input_paths["market_narrative"], {"dominant_narrative": "RISK_OFF", "narrative_persistence_score": 0.62, "narrative_contradiction_score": 0.49})
            self._write_json(input_paths["strategy_genome"], {"family_count": 5})
            self._write_json(input_paths["meta_regime"], {"global_meta_regime_risk_score": 0.71, "transition_risk_score": 0.48, "strategy_regime_mismatch_score": 0.52})
            self._write_json(input_paths["accuracy_validation"], {"validation_drift_score": 0.33})
            self._write_json(input_paths["synthetic_market"], {"synthetic_market_stress_index": 0.73})
            self._write_json(input_paths["adversarial_intelligence"], {"adversarial_replay_signature_score": 0.61})
            self._write_json(input_paths["autonomous_goal_management"], {"goal_priority_scores": {"survival_first": 0.74}})
            self._write_json(input_paths["confidence_calibration"], {"calibrated_confidence_score": 42})

            master_input = {
                "market": {
                    "data": {
                        "risk_tone_score": 35,
                        "volatility_score": 82,
                        "trend_score": 46,
                        "momentum_score": 40,
                        "sector_strength": {
                            "IT": {"strength_score": 72},
                            "BANK": {"strength_score": 31},
                        },
                    }
                }
            }
            context = {"trading_mode": "SELECTIVE", "volatility_score": 82, "risk_tone_score": 35}
            final_decisions = {"ranked": [{"symbol": "AAA", "score": 71}]}
            evaluated_setups = [{"symbol": "AAA", "setup_type": "BREAKOUT", "semantic_labels": "intraday trap"}]

            phase_specs = {
                "phase54_multi_horizon_intelligence": {
                    "path": phase_paths["phase54"]["runtime"],
                    "fallback_path": phase_paths["phase54"]["memory"],
                    "placement": "master_controller_phase54_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "horizon_alignment_scores", "horizon_agreement_score", "timeframe_conflict_score"),
                },
                "phase55_capital_flow_intelligence": {
                    "path": phase_paths["phase55"]["runtime"],
                    "fallback_path": phase_paths["phase55"]["memory"],
                    "placement": "master_controller_phase55_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase54_consumed", "phase54_run_count_seen", "capital_migration_score", "risk_off_score"),
                },
                "phase56_dynamic_risk_intelligence": {
                    "path": phase_paths["phase56"]["runtime"],
                    "fallback_path": phase_paths["phase56"]["memory"],
                    "placement": "master_controller_phase56_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase54_consumed", "phase55_consumed", "phase54_run_count_seen", "phase55_run_count_seen", "stress_aware_theoretical_sizing_score", "theoretical_shadow_size_multiplier", "risk_advisory"),
                },
            }

            with patch.object(batch6, "PHASE_PATHS", phase_paths), patch.object(
                batch6, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch6.run_roadmap_batch6_intelligence(master_input=master_input, context=context, evaluated_setups=evaluated_setups, final_decisions=final_decisions)
                second = batch6.run_roadmap_batch6_intelligence(master_input=master_input, context=context, evaluated_setups=evaluated_setups, final_decisions=final_decisions)
                visibility = runtime_status._phase_status_summaries()

        phase54 = second["phase54_multi_horizon_intelligence"]
        phase55 = second["phase55_capital_flow_intelligence"]
        phase56 = second["phase56_dynamic_risk_intelligence"]

        self.assertEqual(first["phase54_multi_horizon_intelligence"]["run_count"], 1)
        self.assertEqual(phase54["run_count"], 2)
        self.assertTrue(phase54["continued_from_previous_state"])
        self.assertTrue(phase54["connected"])
        self.assertTrue(phase54["horizon_alignment_scores"])
        self.assertGreaterEqual(phase54["timeframe_conflict_score"], 0.0)

        self.assertEqual(phase55["run_count"], 2)
        self.assertTrue(phase55["continued_from_previous_state"])
        self.assertTrue(phase55["phase54_consumed"])
        self.assertEqual(phase55["phase54_run_count_seen"], 2)
        self.assertGreaterEqual(phase55["capital_migration_score"], 0.0)

        self.assertEqual(phase56["run_count"], 2)
        self.assertTrue(phase56["continued_from_previous_state"])
        self.assertTrue(phase56["phase54_consumed"])
        self.assertTrue(phase56["phase55_consumed"])
        self.assertEqual(phase56["phase54_run_count_seen"], 2)
        self.assertEqual(phase56["phase55_run_count_seen"], 2)
        self.assertGreaterEqual(phase56["stress_aware_theoretical_sizing_score"], 0.0)
        self.assertEqual(phase56["recommended_live_weight"], 0.0)
        self.assertEqual(phase56["rank_adjustment"], 0.0)

        for key in (
            "phase54_multi_horizon_intelligence",
            "phase55_capital_flow_intelligence",
            "phase56_dynamic_risk_intelligence",
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

        self.assertTrue(visibility["phase55_capital_flow_intelligence"]["values"]["phase54_consumed"])
        self.assertTrue(visibility["phase56_dynamic_risk_intelligence"]["values"]["phase54_consumed"])
        self.assertTrue(visibility["phase56_dynamic_risk_intelligence"]["values"]["phase55_consumed"])


if __name__ == "__main__":
    unittest.main()
