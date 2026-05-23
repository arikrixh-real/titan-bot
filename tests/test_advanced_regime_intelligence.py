"""
Offline tests for TITAN Phase 12 Advanced Regime Intelligence.

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

from engines import advanced_regime_intelligence as regime


def sample_setups():
    return [{"symbol": "HDFCBANK", "side": "LONG", "score": 3.2}]


def sample_decisions():
    return {"selected": [{"symbol": "HDFCBANK"}], "rejected": []}


def sample_context():
    return {"trading_mode": "SELECTIVE", "risk_level": "MEDIUM"}


class AdvancedRegimeIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.old_values = {
            "MARKET_NARRATIVE_MEMORY_PATH": regime.MARKET_NARRATIVE_MEMORY_PATH,
            "CROSS_SETUP_MEMORY_PATH": regime.CROSS_SETUP_MEMORY_PATH,
            "LIFECYCLE_MEMORY_PATH": regime.LIFECYCLE_MEMORY_PATH,
            "STRATEGY_FAMILY_MEMORY_PATH": regime.STRATEGY_FAMILY_MEMORY_PATH,
            "PROMOTION_GATE_MEMORY_PATH": regime.PROMOTION_GATE_MEMORY_PATH,
            "MASTER_SHADOW_MEMORY_PATH": regime.MASTER_SHADOW_MEMORY_PATH,
            "HISTORICAL_REGIME_TRANSITION_MEMORY_PATH": regime.HISTORICAL_REGIME_TRANSITION_MEMORY_PATH,
            "HISTORICAL_REGIME_TRANSITION_REPORT_PATH": regime.HISTORICAL_REGIME_TRANSITION_REPORT_PATH,
            "MEMORY_PATH": regime.MEMORY_PATH,
            "REPORT_PATH": regime.REPORT_PATH,
            "OUTCOME_PATHS": regime.OUTCOME_PATHS,
            "REPORT_REFRESH_SECONDS": regime.REPORT_REFRESH_SECONDS,
            "RUNTIME_BUDGET_SECONDS": regime.RUNTIME_BUDGET_SECONDS,
            "MAX_FILE_BYTES": regime.MAX_FILE_BYTES,
        }

    def tearDown(self):
        for name, value in self.old_values.items():
            setattr(regime, name, value)

    def _point_paths(self, tmp_path):
        regime.MARKET_NARRATIVE_MEMORY_PATH = tmp_path / "missing_market_narrative.json"
        regime.CROSS_SETUP_MEMORY_PATH = tmp_path / "missing_cross_setup.json"
        regime.LIFECYCLE_MEMORY_PATH = tmp_path / "missing_lifecycle.json"
        regime.STRATEGY_FAMILY_MEMORY_PATH = tmp_path / "missing_strategy_family.json"
        regime.PROMOTION_GATE_MEMORY_PATH = tmp_path / "missing_promotion_gate.json"
        regime.MASTER_SHADOW_MEMORY_PATH = tmp_path / "missing_master_shadow.json"
        regime.HISTORICAL_REGIME_TRANSITION_MEMORY_PATH = tmp_path / "memory" / "historical_regime_transition_memory.json"
        regime.HISTORICAL_REGIME_TRANSITION_REPORT_PATH = tmp_path / "reports" / "historical_regime_transition_report.txt"
        regime.MEMORY_PATH = tmp_path / "memory" / "advanced_regime_intelligence_memory.json"
        regime.REPORT_PATH = tmp_path / "reports" / "advanced_regime_intelligence_report.txt"
        regime.OUTCOME_PATHS = [tmp_path / "missing_outcomes.jsonl"]

    def _write_sample_artifacts(self, tmp_path):
        market = tmp_path / "market.json"
        market.write_text(
            json.dumps(
                {
                    "current_narrative": {
                        "narrative_type": "RISK_ON_TREND",
                        "risk_on_risk_off_state": "RISK_ON",
                        "risk_tone_score": 72,
                        "narrative_confidence": 0.78,
                        "breadth_pressure": {"state": "BROAD_PARTICIPATION", "score": 70},
                        "volatility_pressure": {"state": "NORMAL", "score": 35},
                        "event_pressure": {"state": "LOW", "score": 8},
                        "contradiction_flags": [],
                    }
                }
            ),
            encoding="utf-8",
        )
        cross = tmp_path / "cross.json"
        cross.write_text(
            json.dumps(
                {
                    "current_snapshot": {
                        "relational_state": "MODERATE_CONCENTRATION",
                        "portfolio_heat_score": 45,
                        "sector_concentration": {"score": 52},
                        "directional_crowding": {"score": 66},
                        "systemic_contradiction_flags": [],
                    }
                }
            ),
            encoding="utf-8",
        )
        lifecycle = tmp_path / "lifecycle.json"
        lifecycle.write_text(
            json.dumps({"failure_cause_counts": {"news_shock": 1, "time_decay": 2, "market_reversal": 1}}),
            encoding="utf-8",
        )
        strategy = tmp_path / "strategy.json"
        strategy.write_text(json.dumps({"total_closed_trades": 60}), encoding="utf-8")
        promotion = tmp_path / "promotion.json"
        promotion.write_text(json.dumps({"phase11_shadow_mode": True}), encoding="utf-8")
        master = tmp_path / "master.json"
        master.write_text(json.dumps({"phase10_shadow_mode": True}), encoding="utf-8")
        outcomes = tmp_path / "outcomes.jsonl"
        rows = [
            {"outcome": "WIN", "strategy_family": "breakout"},
            {"outcome": "LOSS", "strategy_family": "breakout"},
            {"outcome": "WIN", "strategy_family": "pullback"},
        ]
        outcomes.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

        regime.MARKET_NARRATIVE_MEMORY_PATH = market
        regime.CROSS_SETUP_MEMORY_PATH = cross
        regime.LIFECYCLE_MEMORY_PATH = lifecycle
        regime.STRATEGY_FAMILY_MEMORY_PATH = strategy
        regime.PROMOTION_GATE_MEMORY_PATH = promotion
        regime.MASTER_SHADOW_MEMORY_PATH = master
        regime.OUTCOME_PATHS = [outcomes]

    def test_missing_memory_files_return_neutral_choppy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)

            result = regime.build_advanced_regime_snapshot()

            self.assertTrue(result["phase12_shadow_mode"])
            self.assertEqual(result["active_regime"]["primary"], "CHOPPY_NO_EDGE")
            self.assertEqual(set(result["regime_scores"].keys()), set(regime.REQUIRED_REGIMES))
            self.assertEqual(result["recommended_live_weight"], 0.0)
            self.assertEqual(result["rank_adjustment"], 0.0)

    def test_malformed_json_fails_open_for_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            regime.MARKET_NARRATIVE_MEMORY_PATH = tmp_path / "market.json"
            regime.MARKET_NARRATIVE_MEMORY_PATH.write_text("{bad json", encoding="utf-8")

            result = regime.build_advanced_regime_snapshot()

            self.assertIn("market_narrative_read_error", result["warnings"])
            self.assertTrue(result["phase12_shadow_mode"])
            self.assertEqual(result["safety"]["recommended_live_weight"], 0.0)

    def test_deterministic_regime_scores_and_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            first = regime.build_advanced_regime_snapshot()
            second = regime.build_advanced_regime_snapshot()

            self.assertEqual(first["regime_scores"], second["regime_scores"])
            self.assertEqual(set(first["regime_scores"].keys()), set(regime.REQUIRED_REGIMES))
            for value in first["regime_scores"].values():
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)
            self.assertIn(first["active_regime"]["primary"], regime.REQUIRED_REGIMES)

    def test_transition_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            regime.MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            regime.MEMORY_PATH.write_text(
                json.dumps(
                    {
                        "active_regime": {"primary": "RISK_OFF", "confidence": 0.7},
                        "regime_scores": {"RISK_OFF": 0.7},
                        "history": [{"primary": "RISK_ON", "confidence": 0.6}],
                    }
                ),
                encoding="utf-8",
            )

            result = regime.build_advanced_regime_snapshot()

            self.assertTrue(result["active_regime"]["transition_detected"])
            self.assertEqual(result["active_regime"]["previous_primary"], "RISK_OFF")

    def test_strategy_family_regime_performance_sample_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            result = regime.build_advanced_regime_snapshot()
            performance = result["strategy_family_regime_performance"]

            self.assertIn("breakout", performance)
            primary = result["active_regime"]["primary"]
            self.assertIn(primary, performance["breakout"])
            self.assertLessEqual(performance["breakout"][primary]["confidence"], 1.0)
            self.assertGreaterEqual(performance["breakout"][primary]["confidence"], 0.0)

    def test_no_mutation_of_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            setups = sample_setups()
            decisions = sample_decisions()
            context = sample_context()
            phase_results = {"phase11": {"status": "ACTIVE"}}
            before = (deepcopy(setups), deepcopy(decisions), deepcopy(context), deepcopy(phase_results))

            regime.build_advanced_regime_snapshot(setups, decisions, context, phase_results)

            self.assertEqual(setups, before[0])
            self.assertEqual(decisions, before[1])
            self.assertEqual(context, before[2])
            self.assertEqual(phase_results, before[3])

    def test_runtime_budget_behavior(self):
        old_reader = regime._read_json_limited

        def slow_reader(path, name):
            time.sleep(0.02)
            return {}, {"available": False, "path": str(path), "status": "MISSING", "age_seconds": None}, []

        regime._read_json_limited = slow_reader
        regime.RUNTIME_BUDGET_SECONDS = 0.001
        try:
            result = regime.build_advanced_regime_snapshot()
        finally:
            regime._read_json_limited = old_reader

        self.assertFalse(result["runtime_bounded"])
        self.assertIn("phase12_runtime_budget_exceeded", result["warnings"])

    def test_report_generation_writes_compact_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            regime.REPORT_REFRESH_SECONDS = -1

            result = regime.refresh_advanced_regime_intelligence(force=True)

            self.assertTrue(result["phase12_shadow_mode"])
            self.assertTrue(regime.MEMORY_PATH.exists())
            self.assertTrue(regime.REPORT_PATH.exists())
            self.assertTrue(regime.HISTORICAL_REGIME_TRANSITION_MEMORY_PATH.exists())
            self.assertTrue(regime.HISTORICAL_REGIME_TRANSITION_REPORT_PATH.exists())
            self.assertLess(regime.REPORT_PATH.stat().st_size, 10000)

    def test_forbidden_imports_absent(self):
        source_path = PROJECT_ROOT / "engines" / "advanced_regime_intelligence.py"
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
