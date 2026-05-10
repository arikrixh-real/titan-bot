"""
Offline tests for TITAN Phase 9 cross-setup relational shadow intelligence.

These tests do not scan, collect market data, send alerts, use broker APIs,
write trade state, or change rankings/final decisions.
"""

from copy import deepcopy
import ast
from pathlib import Path
import sys
import tempfile
import time
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import cross_setup_intelligence as phase9
from titan_master_brain.execution_engine import build_signal_message
from titan_master_brain.final_decision_engine import make_final_decisions


def sample_context():
    return {
        "trading_mode": "SELECTIVE",
        "risk_level": "MEDIUM",
        "setup_environment": "NORMAL_SETUP_PHASE",
    }


def sample_setups():
    return [
        {
            "symbol": "HDFCBANK",
            "side": "LONG",
            "score": 3.4,
            "rr": 2.1,
            "decision": "TRUST",
            "confidence": "HIGH",
            "strategy_family": "breakout",
            "raw": {"sector": "Banking", "strategy_family": "breakout"},
        },
        {
            "symbol": "ICICIBANK",
            "side": "LONG",
            "score": 3.2,
            "rr": 2.0,
            "decision": "TRUST",
            "confidence": "HIGH",
            "strategy_family": "breakout",
            "raw": {"sector": "Banking", "strategy_family": "breakout"},
        },
        {
            "symbol": "TATASTEEL",
            "side": "SHORT",
            "score": 3.0,
            "rr": 1.9,
            "decision": "DOWNGRADE",
            "confidence": "MEDIUM",
            "strategy_family": "reversal",
            "raw": {"sector": "Metals", "strategy_family": "reversal"},
        },
    ]


class CrossSetupIntelligenceTests(unittest.TestCase):
    def test_empty_setup_list_returns_neutral(self):
        result = phase9.build_cross_setup_intelligence_shadow([], sample_context(), {}, {})

        self.assertTrue(result["phase9_shadow_mode"])
        self.assertTrue(result["phase9_applied"])
        self.assertEqual(result["relational_state"], "NEUTRAL")
        self.assertEqual(result["phase9_rank_adjustment"], 0.0)
        self.assertIn("no_setups_to_observe", result["warnings"])

    def test_malformed_setup_data_fails_open(self):
        old_symbol = phase9._symbol

        def broken_symbol(setup):
            raise RuntimeError("forced failure")

        phase9._symbol = broken_symbol
        try:
            result = phase9.build_cross_setup_intelligence_shadow([{"symbol": "BAD"}], sample_context(), {}, {})
        finally:
            phase9._symbol = old_symbol

        self.assertFalse(result["phase9_applied"])
        self.assertTrue(result["phase9_shadow_mode"])
        self.assertEqual(result["phase9_rank_adjustment"], 0.0)
        self.assertIn("error", result)

    def test_no_mutation_of_input_setup_list_or_context(self):
        setups = sample_setups()
        context = sample_context()
        decisions = make_final_decisions(deepcopy(setups), context)
        before = (deepcopy(setups), deepcopy(context), deepcopy(decisions))

        result = phase9.build_cross_setup_intelligence_shadow(setups, context, decisions, {})

        self.assertTrue(result["phase9_applied"])
        self.assertEqual(setups, before[0])
        self.assertEqual(context, before[1])
        self.assertEqual(decisions, before[2])

    def test_no_telegram_or_final_decision_packet_changes(self):
        setups = sample_setups()
        context = sample_context()

        before = make_final_decisions(deepcopy(setups), context)
        phase9.build_cross_setup_intelligence_shadow(setups, context, before, {})
        after = make_final_decisions(deepcopy(setups), context)

        self.assertEqual(before, after)

        packet = {
            "symbol": "HDFCBANK",
            "side": "LONG",
            "entry": 100,
            "sl": 98,
            "target": 104,
            "rr": 2,
            "score": 3.2,
            "decision": "TRUST",
            "confidence": "HIGH",
            "quality_tier": "ELITE",
            "daily_alert_rank": 1,
        }
        self.assertEqual(build_signal_message(packet), build_signal_message(dict(packet)))

    def test_runtime_bounded_for_30_synthetic_setups(self):
        setups = []
        for idx in range(30):
            setups.append(
                {
                    "symbol": f"SYM{idx}",
                    "side": "LONG" if idx % 2 == 0 else "SHORT",
                    "score": 3.0,
                    "rr": 2.0,
                    "decision": "TRUST",
                    "confidence": "HIGH",
                    "strategy_family": f"family{idx % 4}",
                    "raw": {"sector": f"sector{idx % 5}"},
                }
            )

        started = time.monotonic()
        result = phase9.build_cross_setup_intelligence_shadow(setups, sample_context(), {}, {})
        elapsed = time.monotonic() - started

        self.assertTrue(result["phase9_applied"])
        self.assertLessEqual(result["pairwise_comparisons"], phase9.MAX_PAIRWISE_COMPARISONS)
        self.assertLess(elapsed, 0.5)

    def test_refresh_report_writes_compact_artifacts(self):
        old_report = phase9.REPORT_PATH
        old_memory = phase9.MEMORY_PATH
        old_refresh = phase9.REPORT_REFRESH_SECONDS

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            phase9.REPORT_PATH = tmp_path / "reports" / "cross_setup_report.txt"
            phase9.MEMORY_PATH = tmp_path / "memory" / "cross_setup_memory.json"
            phase9.REPORT_REFRESH_SECONDS = -1

            result = phase9.refresh_cross_setup_report(
                sample_setups(),
                sample_context(),
                make_final_decisions(sample_setups(), sample_context()),
                {"risk_on_risk_off_state": "RISK_ON"},
            )

            self.assertTrue(result["phase9_applied"])
            self.assertTrue(phase9.REPORT_PATH.exists())
            self.assertTrue(phase9.MEMORY_PATH.exists())
            self.assertLess(phase9.REPORT_PATH.stat().st_size, 10000)

        phase9.REPORT_PATH = old_report
        phase9.MEMORY_PATH = old_memory
        phase9.REPORT_REFRESH_SECONDS = old_refresh

    def test_forbidden_imports_absent(self):
        source_path = PROJECT_ROOT / "engines" / "cross_setup_intelligence.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        forbidden = {
            "requests",
            "yfinance",
            "websocket",
            "supabase",
            "data.live_price",
            "scanners",
            "notifications",
            "alerts",
            "titan_master_brain.execution_engine",
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
