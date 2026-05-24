import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import roadmap_batch3_intelligence as batch3
import runtime_status


class RoadmapBatch3IntelligenceTests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _phase_paths(self, root):
        return {
            "phase44": {
                "memory": root / "memory" / "temporal_intelligence_state.json",
                "runtime": root / "runtime" / "temporal_intelligence_status.json",
                "report": root / "reports" / "temporal_intelligence_report.txt",
            },
            "phase45": {
                "memory": root / "memory" / "market_breadth_intelligence_state.json",
                "runtime": root / "runtime" / "market_breadth_intelligence_status.json",
                "report": root / "reports" / "market_breadth_intelligence_report.txt",
            },
            "phase46": {
                "memory": root / "memory" / "crowd_psychology_state.json",
                "runtime": root / "runtime" / "crowd_psychology_status.json",
                "report": root / "reports" / "crowd_psychology_report.txt",
            },
            "phase47": {
                "memory": root / "memory" / "market_narrative_intelligence_state.json",
                "runtime": root / "runtime" / "market_narrative_intelligence_status.json",
                "report": root / "reports" / "market_narrative_intelligence_report.txt",
            },
        }

    def test_batch3_progressive_continuity_cross_phase_and_runtime_visibility(self):
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
                                "outcome": "WIN",
                                "entry_time": "2026-05-22T09:45:00+05:30",
                                "entry_timing_label": "OPENING_DRIVE",
                                "volatility_score": 72,
                                "semantic_labels": {"panic_euphoria_label": "FOMO_EUPHORIA"},
                                "behavioral_pattern_label": "overconfidence chase",
                            }
                        ),
                        json.dumps(
                            {
                                "symbol": "BBB",
                                "outcome": "LOSS",
                                "entry_time": "2026-05-22T14:35:00+05:30",
                                "entry_timing_label": "LATE_SESSION",
                                "volatility_score": 88,
                                "trap_label": "BULL_TRAP",
                                "failure_reason_label": "panic selloff trap",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            input_paths = {
                **batch3.INPUT_PATHS,
                "historical_experience_jsonl": experience_jsonl,
                "historical_replay_progress": root / "runtime" / "historical_replay_progress.json",
                "no_trade_report": root / "no_trade" / "latest_no_trade_intelligence_report.json",
                "strategy_genome": root / "memory" / "strategy_genome_memory.json",
                "meta_regime": root / "memory" / "meta_regime_intelligence_state.json",
                "advanced_regime": root / "memory" / "advanced_regime_intelligence_memory.json",
                "trap_memory": root / "memory" / "trap_fakeout_memory.json",
                "news_intelligence": root / "news" / "latest_news_intelligence_2_report.json",
                "news_batch": root / "memory" / "news_batch_state.json",
                "phase8_narrative": root / "memory" / "market_narrative_memory.json",
            }
            self._write_json(input_paths["historical_replay_progress"], {"last_records_generated": 2, "total_records_generated": 9})
            self._write_json(input_paths["no_trade_report"], {"no_trade_score": 61})
            self._write_json(input_paths["strategy_genome"], {"run_count": 4, "families": {"BREAKOUT_PULLBACK": {"samples": 3}}})
            self._write_json(input_paths["meta_regime"], {"global_meta_regime_risk_score": 0.44})
            self._write_json(input_paths["trap_memory"], {"pattern_buckets": {"bull_trap": {"samples": 12, "loss_rate": 0.75}}})
            self._write_json(
                input_paths["news_intelligence"],
                {"event_classification": "MACRO", "market_narrative": {"narrative_type": "RISK_OFF_NEWS"}},
            )
            self._write_json(
                input_paths["news_batch"],
                {
                    "news": [
                        {
                            "title": "RBI policy and inflation pressure hit banks",
                            "summary": "Rate policy narrative dominates market behavior.",
                            "sectors": ["Banking"],
                            "event_classification": "MACRO",
                        }
                    ]
                },
            )

            master_input = {
                "market": {
                    "data": {
                        "index_breadth": {"breadth_score": 34, "advance_decline_ratio": 0.62},
                        "risk_tone_score": 71,
                        "sector_strength": {"Banking": {"strength_score": 38, "breadth_20dma_ratio": 0.25, "symbols_counted": 10}},
                        "sector_rankings": [{"sector": "Banking", "strength_score": 38}],
                    }
                }
            }
            context = {"trading_mode": "SELECTIVE", "risk_tone_score": 71}
            news_items = [{"title": "Inflation and RBI policy dominate market", "sectors": ["Banking"], "event_classification": "MACRO"}]

            phase_specs = {
                "phase44_temporal_intelligence": {
                    "path": phase_paths["phase44"]["runtime"],
                    "fallback_path": phase_paths["phase44"]["memory"],
                    "placement": "master_controller_phase44_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "continued_from_previous_state", "timing_quality_score"),
                },
                "phase45_market_breadth_intelligence": {
                    "path": phase_paths["phase45"]["runtime"],
                    "fallback_path": phase_paths["phase45"]["memory"],
                    "placement": "master_controller_phase45_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "phase44_consumed", "phase44_run_count_seen"),
                },
                "phase46_crowd_psychology_engine": {
                    "path": phase_paths["phase46"]["runtime"],
                    "fallback_path": phase_paths["phase46"]["memory"],
                    "placement": "master_controller_phase46_sidecar",
                    "mode": "advisory_only",
                    "fields": (
                        "status",
                        "connected",
                        "run_count",
                        "continued_from_previous_state",
                        "phase44_consumed",
                        "phase45_consumed",
                        "phase44_run_count_seen",
                        "phase45_run_count_seen",
                        "fear_euphoria",
                        "panic_behavior_score",
                        "crowd_instability_score",
                        "trap_psychology_score",
                        "overconfidence_score",
                        "emotional_replay_patterns",
                    ),
                },
                "phase47_market_narrative_intelligence": {
                    "path": phase_paths["phase47"]["runtime"],
                    "fallback_path": phase_paths["phase47"]["memory"],
                    "placement": "master_controller_phase47_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "connected", "run_count", "phase45_consumed", "phase46_consumed", "dominant_narrative"),
                },
            }

            with patch.object(batch3, "PHASE_PATHS", phase_paths), patch.object(
                batch3, "INPUT_PATHS", input_paths
            ), patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                first = batch3.run_roadmap_batch3_intelligence(master_input=master_input, context=context, news_items=news_items)
                second = batch3.run_roadmap_batch3_intelligence(master_input=master_input, context=context, news_items=news_items)
                visibility = runtime_status._phase_status_summaries()

        phase44 = second["phase44_temporal_intelligence"]
        phase45 = second["phase45_market_breadth_intelligence"]
        phase46 = second["phase46_crowd_psychology_engine"]
        phase47 = second["phase47_market_narrative_intelligence"]

        self.assertIn("phase46_crowd_psychology_engine", second)
        self.assertTrue(second["phase46_crowd_psychology_engine"])
        self.assertIs(second["phase46_crowd_psychology_engine"], second["phase46_crowd_psychology"])
        self.assertEqual(first["phase44_temporal_intelligence"]["run_count"], 1)
        self.assertEqual(phase44["run_count"], 2)
        self.assertTrue(phase44["continued_from_previous_state"])
        self.assertEqual(phase45["run_count"], 2)
        self.assertTrue(phase45["phase44_consumed"])
        self.assertEqual(phase45["phase44_run_count_seen"], 2)
        self.assertTrue(phase46["phase44_consumed"])
        self.assertTrue(phase46["phase45_consumed"])
        self.assertTrue(phase46["continued_from_previous_state"])
        self.assertEqual(phase46["run_count"], 2)
        self.assertEqual(phase46["phase44_run_count_seen"], 2)
        self.assertEqual(phase46["phase45_run_count_seen"], 2)
        self.assertTrue(phase46["fear_euphoria"])
        self.assertIn("dominant_state", phase46["fear_euphoria"])
        self.assertIn("emotional_replay_patterns", phase46)
        self.assertTrue(phase47["phase45_consumed"])
        self.assertTrue(phase47["phase46_consumed"])
        self.assertEqual(phase47["phase46_run_count_seen"], 2)
        self.assertGreaterEqual(phase45["breadth_divergence_score"], 0.0)
        self.assertGreaterEqual(phase46["crowd_instability_score"], 0.0)
        self.assertTrue(phase47["dominant_narrative"])

        self.assertIn("phase46_crowd_psychology_engine", visibility)
        phase46_visibility = visibility["phase46_crowd_psychology_engine"]
        self.assertTrue(phase46_visibility["connected"])
        self.assertTrue(phase46_visibility["values"]["connected"])
        self.assertEqual(phase46_visibility["values"]["run_count"], 2)
        self.assertTrue(phase46_visibility["values"]["continued_from_previous_state"])
        self.assertTrue(phase46_visibility["values"]["phase44_consumed"])
        self.assertTrue(phase46_visibility["values"]["phase45_consumed"])
        self.assertEqual(phase46_visibility["values"]["phase44_run_count_seen"], 2)
        self.assertEqual(phase46_visibility["values"]["phase45_run_count_seen"], 2)
        self.assertTrue(phase46_visibility["values"]["fear_euphoria"])
        self.assertIn("dominant_state", phase46_visibility["values"]["fear_euphoria"])
        self.assertIn("panic_behavior_score", phase46_visibility["values"])
        self.assertIn("crowd_instability_score", phase46_visibility["values"])
        self.assertIn("trap_psychology_score", phase46_visibility["values"])
        self.assertIn("overconfidence_score", phase46_visibility["values"])
        self.assertIn("emotional_replay_patterns", phase46_visibility["values"])

        for phase in visibility.values():
            self.assertTrue(phase["connected"])
            self.assertTrue(phase["values"])
            self.assertTrue(phase["advisory_only"])
            self.assertTrue(phase["shadow_mode"])
            self.assertFalse(phase["safety"]["affects_live_ranking"])
            self.assertFalse(phase["safety"]["affects_execution"])
            self.assertFalse(phase["safety"]["broker_mutation"])
            self.assertFalse(phase["safety"]["telegram_mutation"])
            self.assertFalse(phase["safety"]["supabase_mutation"])


if __name__ == "__main__":
    unittest.main()
