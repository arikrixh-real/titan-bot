"""
Offline tests for TITAN Phase 13 Strategy Genome Engine.

These tests do not scan, call live prices, send Telegram, use broker APIs,
write Supabase state, or change ranking/final decisions.
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

from engines import strategy_genome_engine as genome


def sample_setups():
    return [
        {
            "symbol": "HDFCBANK",
            "side": "LONG",
            "score": 3.2,
            "rr": 2.1,
            "reason": "breakout pullback retest with volume expansion",
        }
    ]


def sample_decisions():
    return {"selected": [{"symbol": "HDFCBANK"}], "rejected": []}


def sample_context():
    return {"trading_mode": "SELECTIVE", "risk_level": "MEDIUM"}


class StrategyGenomeEngineTests(unittest.TestCase):
    def setUp(self):
        self.old_values = {
            "REGIME_MEMORY_PATH": genome.REGIME_MEMORY_PATH,
            "LIFECYCLE_MEMORY_PATH": genome.LIFECYCLE_MEMORY_PATH,
            "PROMOTION_GATE_MEMORY_PATH": genome.PROMOTION_GATE_MEMORY_PATH,
            "MASTER_SHADOW_MEMORY_PATH": genome.MASTER_SHADOW_MEMORY_PATH,
            "MEMORY_PATH": genome.MEMORY_PATH,
            "REPORT_PATH": genome.REPORT_PATH,
            "OUTCOME_PATHS": genome.OUTCOME_PATHS,
            "REPORT_REFRESH_SECONDS": genome.REPORT_REFRESH_SECONDS,
            "RUNTIME_BUDGET_SECONDS": genome.RUNTIME_BUDGET_SECONDS,
            "MAX_FILE_BYTES": genome.MAX_FILE_BYTES,
        }

    def tearDown(self):
        for name, value in self.old_values.items():
            setattr(genome, name, value)

    def _point_paths(self, tmp_path):
        genome.REGIME_MEMORY_PATH = tmp_path / "missing_regime.json"
        genome.LIFECYCLE_MEMORY_PATH = tmp_path / "missing_lifecycle.json"
        genome.PROMOTION_GATE_MEMORY_PATH = tmp_path / "missing_promotion.json"
        genome.MASTER_SHADOW_MEMORY_PATH = tmp_path / "missing_master.json"
        genome.MEMORY_PATH = tmp_path / "memory" / "strategy_genome_memory.json"
        genome.REPORT_PATH = tmp_path / "reports" / "strategy_genome_report.txt"
        genome.OUTCOME_PATHS = [tmp_path / "missing_outcomes.jsonl"]

    def _write_sample_artifacts(self, tmp_path):
        regime_path = tmp_path / "regime.json"
        regime_path.write_text(
            json.dumps({"active_regime": {"primary": "TRENDING_BREAKOUT"}}),
            encoding="utf-8",
        )
        lifecycle_path = tmp_path / "lifecycle.json"
        lifecycle_path.write_text(
            json.dumps(
                {
                    "setup_family_stats": {
                        "BREAKOUT_PULLBACK": {"avg_trade_health_score": 66},
                        "MEAN_REVERSION_FADE": {"avg_trade_health_score": 44},
                    }
                }
            ),
            encoding="utf-8",
        )
        promotion_path = tmp_path / "promotion.json"
        promotion_path.write_text(json.dumps({"phase11_shadow_mode": True}), encoding="utf-8")
        master_path = tmp_path / "master.json"
        master_path.write_text(json.dumps({"phase10_shadow_mode": True}), encoding="utf-8")
        outcomes_path = tmp_path / "outcomes.jsonl"
        rows = [
            {"outcome": "WIN", "strategy_family": "BREAKOUT_PULLBACK", "side": "LONG", "score": 3.2, "rr": 2.1},
            {"outcome": "LOSS", "strategy_family": "BREAKOUT_PULLBACK", "side": "LONG", "score": 2.6, "rr": 1.8},
            {"outcome": "WIN", "reason": "mean reversion oversold fade", "side": "LONG", "score": 2.2, "rr": 1.6},
            {"outcome": "LOSS", "reason": "liquidity sweep wick rejection", "side": "SHORT", "score": 2.0, "rr": 2.0, "result_reason": "bad_entry"},
        ]
        outcomes_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

        genome.REGIME_MEMORY_PATH = regime_path
        genome.LIFECYCLE_MEMORY_PATH = lifecycle_path
        genome.PROMOTION_GATE_MEMORY_PATH = promotion_path
        genome.MASTER_SHADOW_MEMORY_PATH = master_path
        genome.OUTCOME_PATHS = [outcomes_path]

    def test_missing_memory_files_return_neutral_genome(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)

            result = genome.build_strategy_genome_snapshot()

            self.assertTrue(result["phase13_shadow_mode"])
            self.assertEqual(result["active_regime"], "CHOPPY_NO_EDGE")
            self.assertEqual(result["recommended_live_weight"], 0.0)
            self.assertEqual(result["rank_adjustment"], 0.0)
            self.assertFalse(result["promotion_gate_features"]["promotion_eligible"])

    def test_malformed_json_fails_open_for_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            genome.REGIME_MEMORY_PATH = tmp_path / "regime.json"
            genome.REGIME_MEMORY_PATH.write_text("{bad json", encoding="utf-8")

            result = genome.build_strategy_genome_snapshot()

            self.assertIn("regime_read_error", result["warnings"])
            self.assertEqual(result["safety"]["recommended_live_weight"], 0.0)

    def test_family_classification_examples(self):
        examples = {
            "BREAKOUT_PULLBACK": {"reason": "breakout pullback retest support"},
            "EMA_CONTINUATION": {"reason": "ema trend continuation"},
            "OPENING_RANGE_BREAKOUT": {"reason": "opening range breakout"},
            "MEAN_REVERSION_FADE": {"reason": "mean reversion overbought fade"},
            "TREND_RECLAIM": {"reason": "price reclaim above vwap"},
            "FAILED_BREAKDOWN_REVERSAL": {"reason": "failed breakdown reversal bear trap"},
            "VOLUME_EXPANSION_BREAKOUT": {"reason": "breakout with volume expansion"},
            "SHORT_COVERING_SPIKE": {"reason": "short covering squeeze spike"},
            "LIQUIDITY_SWEEP_REVERSAL": {"reason": "liquidity sweep wick rejection"},
            "TREND_EXHAUSTION_FADE": {"reason": "trend exhaustion climax fade"},
            "UNKNOWN": {"reason": "plain setup"},
        }
        for expected, row in examples.items():
            self.assertEqual(genome.classify_strategy_family(row), expected)

    def test_dna_fingerprint_is_deterministic(self):
        row = {"strategy_family": "BREAKOUT_PULLBACK", "side": "LONG", "score": 3.1, "rr": 2.2, "reason": "volume breakout"}
        family = genome.classify_strategy_family(row)

        first = genome.build_dna_fingerprint(row, family, "TRENDING_BREAKOUT", 0.7)
        second = genome.build_dna_fingerprint(dict(row), family, "TRENDING_BREAKOUT", 0.7)

        self.assertEqual(first, second)
        self.assertIn("BREAKOUT_PULLBACK|LONG|TRENDING_BREAKOUT", first)

    def test_family_stats_and_regime_scores_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            result = genome.build_strategy_genome_snapshot(sample_setups(), sample_decisions(), sample_context())

            self.assertIn("BREAKOUT_PULLBACK", result["families"])
            for stats in result["families"].values():
                for key in ("win_rate", "loss_rate", "stability_score", "drift_score", "decay_score", "dominance_score"):
                    self.assertGreaterEqual(stats[key], 0.0)
                    self.assertLessEqual(stats[key], 1.0)
                self.assertEqual(stats["recommended_live_weight"], 0.0)
                self.assertEqual(stats["rank_adjustment"], 0.0)

            compat = result["regime_family_compatibility"]["TRENDING_BREAKOUT"]["BREAKOUT_PULLBACK"]
            self.assertGreaterEqual(compat["compatibility_score"], 0.0)
            self.assertLessEqual(compat["compatibility_score"], 1.0)

    def test_lifecycle_neutral_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            genome.LIFECYCLE_MEMORY_PATH = tmp_path / "missing_lifecycle.json"

            result = genome.build_strategy_genome_snapshot()
            self.assertEqual(result["families"]["BREAKOUT_PULLBACK"]["avg_lifecycle_health"], 0.5)

    def test_drift_decay_and_dominance_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            genome.MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            genome.MEMORY_PATH.write_text(
                json.dumps(
                    {
                        "families": {
                            "BREAKOUT_PULLBACK": {
                                "win_rate": 0.9,
                                "samples": 50,
                            }
                        },
                        "history": [],
                    }
                ),
                encoding="utf-8",
            )
            extra_rows = []
            for idx in range(20):
                extra_rows.append(
                    {
                        "outcome": "WIN" if idx % 2 == 0 else "LOSS",
                        "strategy_family": "BREAKOUT_PULLBACK",
                        "side": "LONG",
                        "score": 3.0,
                        "rr": 2.0,
                    }
                )
            genome.OUTCOME_PATHS[0].write_text("\n".join(json.dumps(row) for row in extra_rows), encoding="utf-8")

            result = genome.build_strategy_genome_snapshot()
            stats = result["families"]["BREAKOUT_PULLBACK"]

            self.assertGreaterEqual(stats["drift_score"], 0.0)
            self.assertGreaterEqual(stats["decay_score"], 0.0)
            self.assertIn("BREAKOUT_PULLBACK", result["dominant_families"])

    def test_no_mutation_of_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            setups = sample_setups()
            decisions = sample_decisions()
            context = sample_context()
            phase_results = {"phase12": {"active_regime": "TRENDING_BREAKOUT"}}
            before = (deepcopy(setups), deepcopy(decisions), deepcopy(context), deepcopy(phase_results))

            genome.build_strategy_genome_snapshot(setups, decisions, context, phase_results)

            self.assertEqual(setups, before[0])
            self.assertEqual(decisions, before[1])
            self.assertEqual(context, before[2])
            self.assertEqual(phase_results, before[3])

    def test_runtime_budget_behavior(self):
        old_reader = genome._read_json_limited

        def slow_reader(path, name):
            time.sleep(0.02)
            return {}, {"available": False, "path": str(path), "status": "MISSING", "age_seconds": None}, []

        genome._read_json_limited = slow_reader
        genome.RUNTIME_BUDGET_SECONDS = 0.001
        try:
            result = genome.build_strategy_genome_snapshot()
        finally:
            genome._read_json_limited = old_reader

        self.assertFalse(result["runtime_bounded"])
        self.assertIn("phase13_runtime_budget_exceeded", result["warnings"])

    def test_report_generation_writes_compact_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            genome.REPORT_REFRESH_SECONDS = -1

            result = genome.refresh_strategy_genome(force=True)

            self.assertTrue(result["phase13_shadow_mode"])
            self.assertTrue(genome.MEMORY_PATH.exists())
            self.assertTrue(genome.REPORT_PATH.exists())
            self.assertLess(genome.REPORT_PATH.stat().st_size, 10000)

    def test_forbidden_imports_absent(self):
        source_path = PROJECT_ROOT / "engines" / "strategy_genome_engine.py"
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
