"""
Offline tests for TITAN Phase 14 Meta Evolution Intelligence.

These tests do not scan, call live prices, send Telegram, use broker APIs,
write Supabase state, self-modify code, or change ranking/final decisions.
"""

from copy import deepcopy
import ast
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import meta_evolution_intelligence as meta


def sample_setups():
    return [{"symbol": "HDFCBANK", "side": "LONG", "score": 3.2}]


def sample_decisions():
    return {"selected": [{"symbol": "HDFCBANK"}], "rejected": []}


def sample_context():
    return {"trading_mode": "SELECTIVE", "risk_level": "MEDIUM"}


class MetaEvolutionIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.old_values = {
            "LAYER_PATHS": meta.LAYER_PATHS,
            "MEMORY_PATH": meta.MEMORY_PATH,
            "REPORT_PATH": meta.REPORT_PATH,
            "OUTCOME_PATHS": meta.OUTCOME_PATHS,
            "REPORT_REFRESH_SECONDS": meta.REPORT_REFRESH_SECONDS,
            "RUNTIME_BUDGET_SECONDS": meta.RUNTIME_BUDGET_SECONDS,
            "MAX_FILE_BYTES": meta.MAX_FILE_BYTES,
        }

    def tearDown(self):
        for name, value in self.old_values.items():
            setattr(meta, name, value)

    def _point_paths(self, tmp_path):
        meta.LAYER_PATHS = {
            name: tmp_path / f"missing_{name}.json"
            for name in meta.LAYER_PATHS
        }
        meta.MEMORY_PATH = tmp_path / "memory" / "meta_evolution_memory.json"
        meta.REPORT_PATH = tmp_path / "reports" / "meta_evolution_report.txt"
        meta.OUTCOME_PATHS = [tmp_path / "missing_outcomes.jsonl"]

    def _write_sample_artifacts(self, tmp_path, high_confidence=False):
        paths = {
            name: tmp_path / f"{name}.json"
            for name in meta.LAYER_PATHS
        }
        paths["phase5_strategy_family"].write_text(json.dumps({"total_closed_trades": 60}), encoding="utf-8")
        paths["phase6_multi_agent"].write_text(
            json.dumps({"observed_setup_count": 60, "average_consensus_score": 72, "contradiction_frequency": 0.25}),
            encoding="utf-8",
        )
        paths["phase7_lifecycle"].write_text(
            json.dumps({"trade_lifecycle": {"T1": {}}, "setup_family_stats": {"breakout": {"avg_trade_health_score": 35}}}),
            encoding="utf-8",
        )
        paths["phase8_market_narrative"].write_text(
            json.dumps(
                {
                    "current_narrative": {
                        "risk_on_risk_off_state": "RISK_ON",
                        "narrative_confidence": 0.95 if high_confidence else 0.72,
                        "contradiction_flags": [],
                    },
                    "history": [{"narrative_confidence": 0.7}],
                }
            ),
            encoding="utf-8",
        )
        paths["phase9_cross_setup"].write_text(
            json.dumps({"current_snapshot": {"observed_setup_count": 60, "portfolio_heat_score": 80, "systemic_contradiction_flags": []}}),
            encoding="utf-8",
        )
        paths["phase10_master_shadow"].write_text(
            json.dumps({"command_status": {"overall_state": "ACTIVE", "confidence": 70}, "dashboard_cards": {"shadow_warnings": 1, "tracked_lifecycle_trades": 10}}),
            encoding="utf-8",
        )
        paths["phase11_promotion_gate"].write_text(
            json.dumps({"promotion_summary": {"max_promotion_score": 0.0, "minimum_samples_required": 50}, "warnings": []}),
            encoding="utf-8",
        )
        paths["phase12_regime"].write_text(
            json.dumps({"active_regime": {"primary": "CHOPPY_NO_EDGE", "confidence": 0.45}}),
            encoding="utf-8",
        )
        paths["phase13_strategy_genome"].write_text(
            json.dumps({"promotion_gate_features": {"family_stability_score": 0.85, "samples": 5}, "failure_clusters": {}}),
            encoding="utf-8",
        )
        outcomes = tmp_path / "outcomes.jsonl"
        rows = [{"outcome": "WIN"} for _ in range(36)] + [{"outcome": "LOSS"} for _ in range(24)]
        outcomes.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

        meta.LAYER_PATHS = paths
        meta.OUTCOME_PATHS = [outcomes]

    def test_missing_memory_files_return_neutral_meta_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)

            result = meta.build_meta_evolution_snapshot()

            self.assertTrue(result["phase14_shadow_mode"])
            self.assertEqual(result["recommended_live_weight"], 0.0)
            self.assertEqual(result["rank_adjustment"], 0.0)
            self.assertIn("phase5_strategy_family", result["layers"])
            self.assertFalse(result["promotion_gate_features"]["promotion_eligible"])

    def test_malformed_json_fails_open_for_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            bad = tmp_path / "phase8.json"
            bad.write_text("{bad json", encoding="utf-8")
            meta.LAYER_PATHS["phase8_market_narrative"] = bad

            result = meta.build_meta_evolution_snapshot()

            self.assertIn("phase8_market_narrative_read_error", result["warnings"])
            self.assertEqual(result["safety"]["recommended_live_weight"], 0.0)

    def test_scores_bounded_and_all_layers_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            result = meta.build_meta_evolution_snapshot()

            self.assertEqual(set(result["layers"].keys()), set(meta.LAYER_PATHS.keys()))
            for layer in result["layers"].values():
                for key in ("usefulness_score", "stability_score", "drift_score", "overfit_risk", "winner_alignment", "loser_warning_quality"):
                    self.assertGreaterEqual(layer[key], 0.0)
                    self.assertLessEqual(layer[key], 1.0)
                self.assertEqual(layer["recommended_live_weight"], 0.0)

    def test_overfit_risk_rises_with_high_confidence_low_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path, high_confidence=True)
            outcomes = tmp_path / "outcomes.jsonl"
            outcomes.write_text(json.dumps({"outcome": "WIN"}), encoding="utf-8")
            meta.OUTCOME_PATHS = [outcomes]

            result = meta.build_meta_evolution_snapshot()

            self.assertGreater(result["layers"]["phase8_market_narrative"]["overfit_risk"], 0.2)

    def test_drift_detection_compares_previous_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            meta.MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            meta.MEMORY_PATH.write_text(
                json.dumps(
                    {
                        "layers": {
                            "phase8_market_narrative": {
                                "usefulness_score": 0.0,
                                "stability_score": 0.0,
                                "overfit_risk": 1.0,
                            }
                        },
                        "history": [],
                    }
                ),
                encoding="utf-8",
            )

            result = meta.build_meta_evolution_snapshot()

            self.assertGreater(result["layers"]["phase8_market_narrative"]["drift_score"], 0.0)

    def test_contradiction_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            result = meta.build_meta_evolution_snapshot()
            types = {item.get("type") for item in result["contradictions"]}

            self.assertIn("risk_state_conflict", types)

    def test_regime_specific_usefulness_section_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            result = meta.build_meta_evolution_snapshot()

            self.assertIn("CHOPPY_NO_EDGE", result["regime_layer_usefulness"])
            self.assertIn("phase8_market_narrative", result["regime_layer_usefulness"]["CHOPPY_NO_EDGE"])

    def test_no_mutation_of_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            setups = sample_setups()
            decisions = sample_decisions()
            context = sample_context()
            phase_results = {"phase13": {"status": "ACTIVE"}}
            before = (deepcopy(setups), deepcopy(decisions), deepcopy(context), deepcopy(phase_results))

            meta.build_meta_evolution_snapshot(setups, decisions, context, phase_results)

            self.assertEqual(setups, before[0])
            self.assertEqual(decisions, before[1])
            self.assertEqual(context, before[2])
            self.assertEqual(phase_results, before[3])

    def test_runtime_budget_behavior(self):
        old_reader = meta._read_json_limited

        def slow_reader(path, name):
            time.sleep(0.02)
            return {}, {"available": False, "path": str(path), "status": "MISSING", "age_seconds": None}, []

        meta._read_json_limited = slow_reader
        meta.RUNTIME_BUDGET_SECONDS = 0.001
        try:
            result = meta.build_meta_evolution_snapshot()
        finally:
            meta._read_json_limited = old_reader

        self.assertFalse(result["runtime_bounded"])
        self.assertIn("phase14_runtime_budget_exceeded", result["warnings"])

    def test_report_generation_writes_compact_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            meta.REPORT_REFRESH_SECONDS = -1

            result = meta.refresh_meta_evolution_intelligence(force=True)

            self.assertTrue(result["phase14_shadow_mode"])
            self.assertTrue(meta.MEMORY_PATH.exists())
            self.assertTrue(meta.REPORT_PATH.exists())
            self.assertLess(meta.REPORT_PATH.stat().st_size, 10000)

    def test_forbidden_imports_absent(self):
        source_path = PROJECT_ROOT / "engines" / "meta_evolution_intelligence.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        forbidden = {
            "requests",
            "yfinance",
            "websocket",
            "websockets",
            "supabase",
            "data.live_price",
            "scanners",
            "alerts",
            "notifications",
            "titan_master_brain.execution_engine",
            "titan_master_brain.input_aggregator",
            "engines.setup_engine",
        }

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        self.assertTrue(forbidden.isdisjoint(imported), imported & forbidden)


if __name__ == "__main__":
    unittest.main()
