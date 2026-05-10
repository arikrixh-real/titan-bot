"""
Offline tests for TITAN Phase 11 Promotion Gate Engine.

These tests do not scan, call live prices, send Telegram, use broker APIs,
write Supabase state, or change rankings/final decisions.
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

from engines import promotion_gate_engine as gate


def sample_setups():
    return [
        {
            "symbol": "HDFCBANK",
            "side": "LONG",
            "score": 3.4,
            "rr": 2.1,
            "decision": "TRUST",
            "confidence": "HIGH",
        }
    ]


def sample_decisions():
    return {
        "action_mode": "TRADE_CANDIDATES_FOUND",
        "selected": [{"symbol": "HDFCBANK", "side": "LONG"}],
        "rejected": [],
        "summary": ["sample"],
    }


class PromotionGateEngineTests(unittest.TestCase):
    def setUp(self):
        self.old_values = {
            "PHASE6_MEMORY_PATH": gate.PHASE6_MEMORY_PATH,
            "PHASE7_MEMORY_PATH": gate.PHASE7_MEMORY_PATH,
            "PHASE8_MEMORY_PATH": gate.PHASE8_MEMORY_PATH,
            "PHASE9_MEMORY_PATH": gate.PHASE9_MEMORY_PATH,
            "PHASE10_MEMORY_PATH": gate.PHASE10_MEMORY_PATH,
            "MEMORY_PATH": gate.MEMORY_PATH,
            "REPORT_PATH": gate.REPORT_PATH,
            "OUTCOME_PATHS": gate.OUTCOME_PATHS,
            "REPORT_REFRESH_SECONDS": gate.REPORT_REFRESH_SECONDS,
            "RUNTIME_BUDGET_SECONDS": gate.RUNTIME_BUDGET_SECONDS,
            "MAX_FILE_BYTES": gate.MAX_FILE_BYTES,
        }

    def tearDown(self):
        for name, value in self.old_values.items():
            setattr(gate, name, value)

    def _point_paths(self, tmp_path):
        gate.PHASE6_MEMORY_PATH = tmp_path / "missing_phase6.json"
        gate.PHASE7_MEMORY_PATH = tmp_path / "missing_phase7.json"
        gate.PHASE8_MEMORY_PATH = tmp_path / "missing_phase8.json"
        gate.PHASE9_MEMORY_PATH = tmp_path / "missing_phase9.json"
        gate.PHASE10_MEMORY_PATH = tmp_path / "missing_phase10.json"
        gate.MEMORY_PATH = tmp_path / "memory" / "promotion_gate_memory.json"
        gate.REPORT_PATH = tmp_path / "reports" / "promotion_gate_report.txt"
        gate.OUTCOME_PATHS = [tmp_path / "missing_outcomes.jsonl"]

    def _write_sample_artifacts(self, tmp_path):
        phase6 = tmp_path / "phase6.json"
        phase6.write_text(
            json.dumps(
                {
                    "observed_setup_count": 80,
                    "average_consensus_score": 68,
                    "average_conflict_score": 22,
                    "contradiction_frequency": 0.35,
                }
            ),
            encoding="utf-8",
        )
        phase7 = tmp_path / "phase7.json"
        phase7.write_text(
            json.dumps(
                {
                    "trade_lifecycle": {"T1": {}, "T2": {}},
                    "symbol_stats": {
                        "HDFCBANK": {"avg_trade_health_score": 66, "avg_confidence_drift": 4},
                        "ICICIBANK": {"avg_trade_health_score": 58, "avg_confidence_drift": -2},
                    },
                }
            ),
            encoding="utf-8",
        )
        phase8 = tmp_path / "phase8.json"
        phase8.write_text(
            json.dumps(
                {
                    "current_narrative": {
                        "narrative_type": "RISK_ON_TREND",
                        "risk_on_risk_off_state": "RISK_ON",
                        "narrative_confidence": 0.72,
                        "contradiction_flags": [],
                    },
                    "history": [
                        {"narrative_confidence": 0.70},
                        {"narrative_confidence": 0.74},
                        {"narrative_confidence": 0.71},
                    ],
                }
            ),
            encoding="utf-8",
        )
        phase9 = tmp_path / "phase9.json"
        phase9.write_text(
            json.dumps(
                {
                    "current_snapshot": {
                        "observed_setup_count": 80,
                        "portfolio_heat_score": 35,
                        "systemic_contradiction_flags": [],
                    },
                    "history": [
                        {"portfolio_heat_score": 34},
                        {"portfolio_heat_score": 38},
                        {"portfolio_heat_score": 36},
                    ],
                }
            ),
            encoding="utf-8",
        )
        phase10 = tmp_path / "phase10.json"
        phase10.write_text(json.dumps({"phase10_shadow_mode": True}), encoding="utf-8")
        outcomes = tmp_path / "outcomes.jsonl"
        rows = [{"outcome": "WIN"} for _ in range(42)] + [{"outcome": "LOSS"} for _ in range(18)]
        outcomes.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

        gate.PHASE6_MEMORY_PATH = phase6
        gate.PHASE7_MEMORY_PATH = phase7
        gate.PHASE8_MEMORY_PATH = phase8
        gate.PHASE9_MEMORY_PATH = phase9
        gate.PHASE10_MEMORY_PATH = phase10
        gate.OUTCOME_PATHS = [outcomes]

    def test_empty_missing_memory_files_return_neutral_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)

            result = gate.build_promotion_gate_snapshot()

            self.assertTrue(result["phase11_shadow_mode"])
            self.assertEqual(result["status"], "NEUTRAL_OBSERVING")
            self.assertIn("phase6_missing", result["warnings"])
            self.assertEqual(result["promotion_summary"]["recommended_live_weight"], 0.0)
            self.assertFalse(result["promotion_summary"]["any_live_influence"])

    def test_malformed_json_fails_open_for_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            gate.PHASE6_MEMORY_PATH = tmp_path / "phase6.json"
            gate.PHASE6_MEMORY_PATH.write_text("{bad json", encoding="utf-8")

            result = gate.build_promotion_gate_snapshot()

            self.assertTrue(result["phase11_shadow_mode"])
            self.assertIn("phase6_read_error", result["warnings"])
            self.assertEqual(result["phase6"]["recommended_live_weight"], 0.0)

    def test_deterministic_scoring_and_bounded_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            first = gate.build_promotion_gate_snapshot()
            second = gate.build_promotion_gate_snapshot()

            for phase in ("phase6", "phase7", "phase8", "phase9"):
                self.assertEqual(first[phase], second[phase])
                for key in (
                    "usefulness_score",
                    "stability_score",
                    "contradiction_accuracy",
                    "agreement_quality",
                    "confidence_quality",
                    "false_positive_rate",
                    "false_negative_rate",
                    "drift_score",
                    "regime_consistency",
                    "promotion_score",
                    "recommended_live_weight",
                ):
                    self.assertGreaterEqual(first[phase][key], 0.0)
                    self.assertLessEqual(first[phase][key], 1.0)
                self.assertEqual(first[phase]["recommended_live_weight"], 0.0)

    def test_no_mutation_of_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)

            setups = sample_setups()
            decisions = sample_decisions()
            phase_results = {"phase10": {"status": "ACTIVE"}}
            before = (deepcopy(setups), deepcopy(decisions), deepcopy(phase_results))

            gate.build_promotion_gate_snapshot(setups, decisions, phase_results)

            self.assertEqual(setups, before[0])
            self.assertEqual(decisions, before[1])
            self.assertEqual(phase_results, before[2])

    def test_runtime_budget_behavior(self):
        old_reader = gate._read_json_limited

        def slow_reader(path, name):
            time.sleep(0.02)
            return {}, {"available": False, "path": str(path), "status": "MISSING", "age_seconds": None}, []

        gate._read_json_limited = slow_reader
        gate.RUNTIME_BUDGET_SECONDS = 0.001
        try:
            result = gate.build_promotion_gate_snapshot()
        finally:
            gate._read_json_limited = old_reader

        self.assertFalse(result["runtime_bounded"])
        self.assertIn("phase11_runtime_budget_exceeded", result["warnings"])

    def test_report_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_paths(tmp_path)
            self._write_sample_artifacts(tmp_path)
            gate.REPORT_REFRESH_SECONDS = -1

            result = gate.refresh_promotion_gate(force=True)

            self.assertTrue(result["phase11_shadow_mode"])
            self.assertTrue(gate.MEMORY_PATH.exists())
            self.assertTrue(gate.REPORT_PATH.exists())
            self.assertLess(gate.REPORT_PATH.stat().st_size, 10000)

    def test_forbidden_imports_absent(self):
        source_path = PROJECT_ROOT / "engines" / "promotion_gate_engine.py"
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
