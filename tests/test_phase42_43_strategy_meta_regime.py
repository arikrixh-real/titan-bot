import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import meta_regime_intelligence as phase43
from engines import strategy_genome_engine as phase42
from engines.meta_regime_intelligence import run_meta_regime_intelligence
from engines.strategy_genome_engine import run_strategy_genome_engine
import runtime_status


class Phase42Phase43Tests(unittest.TestCase):
    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_phase43_continues_and_consumes_phase42_genome_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase42_memory = root / "memory" / "strategy_genome_memory.json"
            phase43_memory = root / "memory" / "meta_regime_intelligence_state.json"
            phase43_runtime = root / "runtime" / "meta_regime_intelligence_status.json"
            phase43_report = root / "reports" / "meta_regime_intelligence_report.txt"
            regime = root / "memory" / "advanced_regime_intelligence_memory.json"
            transition = root / "memory" / "transition_instability_memory.json"
            volatility = root / "memory" / "volatility_expansion_compression_memory.json"
            trap = root / "memory" / "trap_fakeout_memory.json"

            self._write_json(
                phase42_memory,
                {
                    "phase": "PHASE_42_STRATEGY_GENOME_ARCHITECTURE",
                    "run_count": 7,
                    "active_regime": "TRENDING_BREAKOUT",
                    "families": {
                        "BREAKOUT_PULLBACK": {
                            "decay_score": 0.20,
                            "drift_score": 0.15,
                            "durability_score": 0.55,
                        }
                    },
                    "regime_family_compatibility": {
                        "TRENDING_BREAKOUT": {
                            "BREAKOUT_PULLBACK": {"compatibility_score": 0.30}
                        }
                    },
                },
            )
            self._write_json(
                regime,
                {
                    "active_regime": {
                        "primary": "TRENDING_BREAKOUT",
                        "previous_primary": "CHOPPY_NO_EDGE",
                        "confidence": 0.65,
                        "transition_detected": True,
                        "transition_strength": 0.45,
                    }
                },
            )
            self._write_json(
                transition,
                {"instability_buckets": {"UNCONFIRMED": {"samples": 12, "loss_rate": 0.75}}},
            )
            self._write_json(
                volatility,
                {"phase_buckets": {"EXPANSION": {"samples": 18, "loss_rate": 0.60}}},
            )
            self._write_json(
                trap,
                {"pattern_buckets": {"fake_breakout": {"samples": 8, "loss_rate": 0.50}}},
            )

            inputs = {
                **phase43.MEMORY_INPUTS,
                "phase42_strategy_genome": phase42_memory,
                "advanced_regime": regime,
                "transition_instability": transition,
                "volatility_memory": volatility,
                "trap_memory": trap,
            }
            with patch.object(phase43, "MEMORY_PATH", phase43_memory), patch.object(
                phase43, "RUNTIME_STATUS_PATH", phase43_runtime
            ), patch.object(phase43, "REPORT_PATH", phase43_report), patch.object(
                phase43, "MEMORY_INPUTS", inputs
            ):
                first = phase43.run_meta_regime_intelligence(write_files=True)
                second = phase43.run_meta_regime_intelligence(write_files=True)

                phase_specs = {
                    "phase43_meta_regime_intelligence": {
                        "path": phase43_runtime,
                        "fallback_path": phase43_memory,
                        "placement": "master_controller_meta_regime_sidecar",
                        "mode": "advisory_only",
                        "fields": (
                            "status",
                            "run_count",
                            "phase42_consumed",
                            "phase42_run_count_seen",
                            "global_meta_regime_risk_score",
                        ),
                    }
                }
                with patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                    visibility = runtime_status._phase_status_summaries()
                artifacts_written = phase43_memory.exists() and phase43_runtime.exists() and phase43_report.exists()

        self.assertEqual(first["run_count"], 1)
        self.assertEqual(second["run_count"], 2)
        self.assertTrue(second["continued_from_previous_state"])
        self.assertTrue(second["phase42_consumed"])
        self.assertEqual(second["phase42_run_count_seen"], 7)
        self.assertTrue(second["strategy_regime_mismatch_signals"])
        self.assertTrue(second["advisory_only"])
        self.assertTrue(second["research_only"])
        self.assertTrue(second["shadow_mode"])
        self.assertFalse(second["affects_live_ranking"])
        self.assertFalse(second["affects_execution"])
        self.assertFalse(second["broker_mutation"])
        self.assertFalse(second["telegram_mutation"])
        self.assertFalse(second["supabase_mutation"])
        self.assertTrue(artifacts_written)
        self.assertTrue(visibility["phase43_meta_regime_intelligence"]["connected"])
        self.assertEqual(visibility["phase43_meta_regime_intelligence"]["values"]["run_count"], 2)
        self.assertTrue(visibility["phase43_meta_regime_intelligence"]["values"]["phase42_consumed"])

    def test_public_phase42_phase43_callables_progress_and_runtime_status_is_visible(self):
        self.assertTrue(callable(run_strategy_genome_engine))
        self.assertTrue(callable(run_meta_regime_intelligence))

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase42_memory = root / "memory" / "strategy_genome_memory.json"
            phase42_runtime = root / "runtime" / "strategy_genome_status.json"
            phase42_report = root / "reports" / "strategy_genome_report.txt"
            phase43_memory = root / "memory" / "meta_regime_intelligence_state.json"
            phase43_runtime = root / "runtime" / "meta_regime_intelligence_status.json"
            phase43_report = root / "reports" / "meta_regime_intelligence_report.txt"
            regime = root / "memory" / "advanced_regime_intelligence_memory.json"

            self._write_json(
                regime,
                {
                    "active_regime": {
                        "primary": "TRENDING_BREAKOUT",
                        "previous_primary": "CHOPPY_NO_EDGE",
                        "confidence": 0.7,
                        "transition_detected": False,
                        "transition_strength": 0.1,
                    }
                },
            )

            phase43_inputs = {
                **phase43.MEMORY_INPUTS,
                "phase42_strategy_genome": phase42_memory,
                "advanced_regime": regime,
            }
            phase_specs = {
                "phase42_strategy_genome_architecture": {
                    "path": phase42_runtime,
                    "fallback_path": phase42_memory,
                    "placement": "master_controller_strategy_genome_sidecar",
                    "mode": "advisory_only",
                    "fields": ("status", "run_count", "continued_from_previous_state", "family_count", "active_regime"),
                },
                "phase43_meta_regime_intelligence": {
                    "path": phase43_runtime,
                    "fallback_path": phase43_memory,
                    "placement": "master_controller_meta_regime_sidecar",
                    "mode": "advisory_only",
                    "fields": (
                        "status",
                        "run_count",
                        "continued_from_previous_state",
                        "phase42_consumed",
                        "phase42_run_count_seen",
                    ),
                },
            }

            with patch.object(phase42, "MEMORY_PATH", phase42_memory), patch.object(
                phase42, "RUNTIME_STATUS_PATH", phase42_runtime
            ), patch.object(phase42, "REPORT_PATH", phase42_report), patch.object(
                phase42, "OUTCOME_PATHS", [root / "missing_outcomes.jsonl"]
            ), patch.object(phase43, "MEMORY_PATH", phase43_memory), patch.object(
                phase43, "RUNTIME_STATUS_PATH", phase43_runtime
            ), patch.object(phase43, "REPORT_PATH", phase43_report), patch.object(
                phase43, "MEMORY_INPUTS", phase43_inputs
            ), patch.object(
                runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs
            ):
                first42 = run_strategy_genome_engine(write_files=True)
                second42 = run_strategy_genome_engine(write_files=True)
                first43 = run_meta_regime_intelligence(write_files=True)
                second43 = run_meta_regime_intelligence(write_files=True)
                visibility = runtime_status._phase_status_summaries()

        self.assertEqual(first42["run_count"], 1)
        self.assertEqual(second42["run_count"], 2)
        self.assertTrue(second42["continued_from_previous_state"])
        self.assertEqual(first43["run_count"], 1)
        self.assertEqual(second43["run_count"], 2)
        self.assertTrue(second43["continued_from_previous_state"])
        self.assertTrue(second43["phase42_consumed"])
        self.assertEqual(second43["phase42_run_count_seen"], 2)
        self.assertTrue(visibility["phase42_strategy_genome_architecture"]["connected"])
        self.assertTrue(visibility["phase43_meta_regime_intelligence"]["connected"])
        self.assertEqual(visibility["phase42_strategy_genome_architecture"]["values"]["run_count"], 2)
        self.assertEqual(visibility["phase43_meta_regime_intelligence"]["values"]["run_count"], 2)
        self.assertTrue(visibility["phase43_meta_regime_intelligence"]["values"]["phase42_consumed"])
        self.assertEqual(visibility["phase43_meta_regime_intelligence"]["values"]["phase42_run_count_seen"], 2)


if __name__ == "__main__":
    unittest.main()
