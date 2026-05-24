import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch4_intelligence as batch4
import runtime_status


class RoadmapBatch4IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase48": {
                "memory": root / "memory" / "synthetic_market_simulator_state.json",
                "runtime": root / "runtime" / "synthetic_market_simulator_status.json",
                "report": root / "reports" / "synthetic_market_simulator_report.txt",
            },
            "phase49": {
                "memory": root / "memory" / "adversarial_intelligence_state.json",
                "runtime": root / "runtime" / "adversarial_intelligence_status.json",
                "report": root / "reports" / "adversarial_intelligence_report.txt",
            },
            "phase50": {
                "memory": root / "memory" / "explainable_ai_engine_state.json",
                "runtime": root / "runtime" / "explainable_ai_engine_status.json",
                "report": root / "reports" / "explainable_ai_engine_report.txt",
            },
        }

    def test_batch4_progressive_continuity_cross_phase_and_runtime_visibility(self):
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
                                "semantic_labels": "panic liquidity sweep stop hunt fake breakout",
                                "trap_label": "BULL_TRAP",
                                "failure_reason_label": "fake momentum chase failed breakout",
                                "volatility_score": 91,
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "outcome": "WIN",
                                "semantic_labels": "regime shock recovery",
                                "behavioral_pattern_label": "overconfidence exhaustion",
                                "volatility_score": 74,
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            input_paths = {
                **batch4.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "historical_replay_progress": root / "runtime" / "historical_replay_progress.json",
                "strategy_genome": root / "memory" / "strategy_genome_memory.json",
                "meta_regime": root / "memory" / "meta_regime_intelligence_state.json",
                "crowd_psychology": root / "memory" / "crowd_psychology_state.json",
                "temporal_intelligence": root / "memory" / "temporal_intelligence_state.json",
                "market_narrative": root / "memory" / "market_narrative_intelligence_state.json",
                "market_breadth": root / "memory" / "market_breadth_intelligence_state.json",
                "trap_memory": root / "memory" / "trap_fakeout_memory.json",
                "no_trade_memory": root / "memory" / "no_trade_refinement_memory.json",
                "confidence_calibration": root / "confidence" / "latest_confidence_calibration_report.json",
                "meta_learning": root / "memory" / "meta_learning_state.json",
                "master_shadow": root / "memory" / "master_shadow_memory.json",
            }
            self._write_json(input_paths["historical_replay_progress"], {"last_records_generated": 2, "total_records_generated": 10})
            self._write_json(input_paths["strategy_genome"], {"family_count": 4, "families": {"BREAKOUT": {"samples": 3}}})
            self._write_json(input_paths["meta_regime"], {"global_meta_regime_risk_score": 0.71})
            self._write_json(input_paths["crowd_psychology"], {"crowd_instability_score": 0.66, "overconfidence_score": 0.58})
            self._write_json(input_paths["temporal_intelligence"], {"timing_quality_score": 0.41})
            self._write_json(input_paths["market_narrative"], {"dominant_narrative": "RISK_OFF_NEWS", "narrative_persistence_score": 0.67, "narrative_contradiction_score": 0.49})
            self._write_json(input_paths["market_breadth"], {"hidden_weakness_strength_score": 0.73})
            self._write_json(input_paths["trap_memory"], {"pattern_buckets": {"bull_trap": {"samples": 12, "loss_rate": 0.75}}})
            self._write_json(input_paths["no_trade_memory"], {"danger_score": 64})
            self._write_json(input_paths["confidence_calibration"], {"calibrated_confidence_score": 42})
            self._write_json(input_paths["meta_learning"], {"learning_pressure_score": 0.38})

            master_input = {
                "market": {
                    "data": {
                        "volatility_score": 82,
                        "liquidity_score": 29,
                        "risk_tone_score": 77,
                        "market_regime": "VOLATILE",
                    }
                }
            }
            context = {"trading_mode": "SELECTIVE", "volatility_score": 82, "liquidity_score": 29}
            final_decisions = {"ranked": [{"symbol": "AAA", "score": 71}]}

            phase_specs = {
                "phase48_synthetic_market_simulator": {
                    "path": phase_paths["phase48"]["runtime"],
                    "fallback_path": phase_paths["phase48"]["memory"],
                    "placement": "master_controller_phase48_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "simulation_count", "synthetic_market_stress_index"),
                },
                "phase49_adversarial_intelligence": {
                    "path": phase_paths["phase49"]["runtime"],
                    "fallback_path": phase_paths["phase49"]["memory"],
                    "placement": "master_controller_phase49_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase48_consumed", "phase48_run_count_seen", "adversarial_replay_signature_score"),
                },
                "phase50_explainable_ai_engine": {
                    "path": phase_paths["phase50"]["runtime"],
                    "fallback_path": phase_paths["phase50"]["memory"],
                    "placement": "master_controller_phase50_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "phase48_consumed", "phase49_consumed", "phase48_run_count_seen", "phase49_run_count_seen", "engine_contribution_trace", "reasoning_summary", "contradiction_score", "explanation_depth_score"),
                },
            }

            with patch.object(batch4, "PHASE_PATHS", phase_paths), patch.object(
                batch4, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch4.run_roadmap_batch4_intelligence(master_input=master_input, context=context, final_decisions=final_decisions)
                second = batch4.run_roadmap_batch4_intelligence(master_input=master_input, context=context, final_decisions=final_decisions)
                visibility = runtime_status._phase_status_summaries()

        phase48 = second["phase48_synthetic_market_simulator"]
        phase49 = second["phase49_adversarial_intelligence"]
        phase50 = second["phase50_explainable_ai_engine"]

        self.assertEqual(first["phase48_synthetic_market_simulator"]["run_count"], 1)
        self.assertEqual(phase48["run_count"], 2)
        self.assertEqual(phase48["simulation_count"], 12)
        self.assertTrue(phase48["continued_from_previous_state"])
        self.assertTrue(phase48["connected"])
        self.assertGreaterEqual(phase48["synthetic_market_stress_index"], 0.0)

        self.assertEqual(phase49["run_count"], 2)
        self.assertTrue(phase49["continued_from_previous_state"])
        self.assertTrue(phase49["phase48_consumed"])
        self.assertEqual(phase49["phase48_run_count_seen"], 2)
        self.assertGreaterEqual(phase49["adversarial_replay_signature_score"], 0.0)

        self.assertEqual(phase50["run_count"], 2)
        self.assertTrue(phase50["continued_from_previous_state"])
        self.assertTrue(phase50["phase48_consumed"])
        self.assertTrue(phase50["phase49_consumed"])
        self.assertEqual(phase50["phase48_run_count_seen"], 2)
        self.assertEqual(phase50["phase49_run_count_seen"], 2)
        self.assertTrue(phase50["engine_contribution_trace"])
        self.assertTrue(phase50["reasoning_summary"])
        self.assertGreaterEqual(phase50["explanation_depth_score"], 0.0)

        for key in (
            "phase48_synthetic_market_simulator",
            "phase49_adversarial_intelligence",
            "phase50_explainable_ai_engine",
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

        self.assertTrue(visibility["phase49_adversarial_intelligence"]["values"]["phase48_consumed"])
        self.assertTrue(visibility["phase50_explainable_ai_engine"]["values"]["phase48_consumed"])
        self.assertTrue(visibility["phase50_explainable_ai_engine"]["values"]["phase49_consumed"])


if __name__ == "__main__":
    unittest.main()
