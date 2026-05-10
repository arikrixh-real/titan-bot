"""
Offline tests for TITAN Phase 6 multi-agent reasoning shadow layer.

These tests do not scan markets, send Telegram alerts, write trades, call
Supabase, place broker orders, or change alert ranking.
"""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import multi_agent_reasoning_engine as phase6
from engines import phase6_shadow_observer
from titan_master_brain.execution_engine import build_signal_message
from titan_master_brain.final_decision_engine import make_final_decisions


def sample_context():
    return {
        "trading_mode": "SELECTIVE",
        "risk_level": "MEDIUM",
        "learning_environment": "LEARNING_NOT_READY",
    }


def sample_setup():
    return {
        "symbol": "RELIANCE",
        "side": "LONG",
        "entry": 100.0,
        "sl": 98.0,
        "target": 104.0,
        "rr": 2.0,
        "score": 3.2,
        "decision": "TRUST",
        "confidence": "HIGH",
        "reasoning": ["Strong score", "Good RR"],
        "raw": {
            "symbol": "RELIANCE",
            "side": "LONG",
            "rr": 2.0,
            "score": 3.2,
            "setup_context": {"confirmations": 5},
            "market_context": {"trend": "BULLISH"},
            "professional_risk": {"risk_quality_score": 70, "risk_blocks": []},
            "execution_quality": {
                "execution_quality_score": 72,
                "slippage_risk_estimate": 25,
                "chase_entry_penalty": 0,
            },
            "advanced_regime": {
                "regime_type": "TRENDING",
                "panic_score": 10,
            },
        },
    }


class MultiAgentReasoningTests(unittest.TestCase):
    def test_phase6_adds_shadow_metadata_without_rank_adjustment(self):
        setup = sample_setup()
        result = phase6.evaluate_phase6_setup(setup, sample_context())

        self.assertTrue(result["phase6_applied"])
        self.assertTrue(result["phase6_shadow_mode"])
        self.assertEqual(result["phase6_rank_adjustment"], 0.0)
        self.assertIn("agent_opinions", result)
        self.assertEqual(len(result["agent_opinions"]), 7)
        self.assertIn("consensus_score", result)
        self.assertIn("conflict_score", result)
        self.assertIn("contradictions", result)
        self.assertIn("agreement_confidence", result)
        self.assertIn("scenario_reasoning", result)

    def test_phase6_preserves_original_trade_fields(self):
        setup = sample_setup()
        result = phase6.evaluate_phase6_setup(setup, sample_context())

        for key in ["symbol", "side", "entry", "sl", "target", "rr", "score", "decision", "confidence"]:
            self.assertEqual(result[key], setup[key])

    def test_missing_data_stays_bounded_and_neutral(self):
        result = phase6.evaluate_phase6_setup(
            {"symbol": "TCS", "side": "LONG", "score": 0.0, "rr": 0.0},
            {},
        )

        self.assertTrue(result["phase6_applied"])
        self.assertEqual(result["phase6_rank_adjustment"], 0.0)
        self.assertGreaterEqual(result["consensus_score"], 0.0)
        self.assertLessEqual(result["consensus_score"], 100.0)
        self.assertGreaterEqual(result["agreement_confidence"], 0.0)
        self.assertLessEqual(result["agreement_confidence"], 100.0)

    def test_contradiction_detection_flags_trend_conflict(self):
        setup = sample_setup()
        setup["raw"] = dict(setup["raw"])
        setup["raw"]["market_context"] = {"trend": "BEARISH"}

        result = phase6.evaluate_phase6_setup(setup, sample_context())

        self.assertIn("LONG setup conflicts with bearish trend", result["contradictions"])
        self.assertEqual(result["phase6_rank_adjustment"], 0.0)

    def test_apply_multi_agent_reasoning_fails_open_per_setup(self):
        old_agent = phase6.technical_agent

        def broken_agent(setup, context):
            raise RuntimeError("forced failure")

        phase6.technical_agent = broken_agent
        try:
            result = phase6.apply_multi_agent_reasoning([sample_setup()], sample_context())

            self.assertEqual(len(result), 1)
            self.assertFalse(result[0]["phase6_applied"])
            self.assertTrue(result[0]["phase6_shadow_mode"])
            self.assertEqual(result[0]["phase6_rank_adjustment"], 0.0)
        finally:
            phase6.technical_agent = old_agent

    def test_final_decision_selection_order_is_unchanged_by_phase6(self):
        base = [
            {**sample_setup(), "symbol": "AAA", "score": 3.4, "rr": 2.0},
            {**sample_setup(), "symbol": "BBB", "score": 3.1, "rr": 2.0},
        ]
        enriched = phase6.apply_multi_agent_reasoning(base, sample_context())

        before = make_final_decisions(base, sample_context())["selected"]
        after = make_final_decisions(enriched, sample_context())["selected"]

        self.assertEqual([item["symbol"] for item in before], [item["symbol"] for item in after])
        self.assertTrue(all(item.get("phase6_rank_adjustment") == 0.0 for item in after))

    def test_phase6_shadow_report_never_changes_setup_ranking(self):
        base = [
            {**sample_setup(), "symbol": "AAA", "score": 3.4, "rr": 2.0},
            {**sample_setup(), "symbol": "BBB", "score": 3.1, "rr": 2.0},
        ]
        enriched = phase6.apply_multi_agent_reasoning(base, sample_context())

        before = make_final_decisions(enriched, sample_context())["selected"]
        summary = phase6_shadow_observer.build_phase6_shadow_summary(enriched)
        after = make_final_decisions(enriched, sample_context())["selected"]

        self.assertGreaterEqual(summary["observed_setup_count"], 1)
        self.assertEqual([item["symbol"] for item in before], [item["symbol"] for item in after])
        self.assertEqual([item.get("score") for item in before], [item.get("score") for item in after])

    def test_phase6_metadata_does_not_change_telegram_formatting(self):
        packet = {
            "symbol": "RELIANCE",
            "side": "LONG",
            "entry": 100.0,
            "sl": 98.0,
            "target": 104.0,
            "rr": 2.0,
            "score": 3.2,
            "decision": "TRUST",
            "confidence": "HIGH",
            "quality_tier": "A",
            "daily_alert_rank": 1,
        }
        with_phase6 = dict(packet)
        with_phase6.update(
            {
                "phase6_applied": True,
                "consensus_score": 75.0,
                "conflict_score": 10.0,
                "phase6_rank_adjustment": 0.0,
            }
        )

        self.assertEqual(build_signal_message(packet), build_signal_message(with_phase6))

    def test_phase6_report_generation_fails_open(self):
        old_report_path = phase6_shadow_observer.REPORT_PATH
        old_memory_path = phase6_shadow_observer.MEMORY_PATH
        old_refresh_seconds = phase6_shadow_observer.PHASE6_REPORT_REFRESH_SECONDS

        phase6_shadow_observer.REPORT_PATH = PROJECT_ROOT
        phase6_shadow_observer.MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "phase6_shadow_memory.json"
        phase6_shadow_observer.PHASE6_REPORT_REFRESH_SECONDS = -1

        try:
            result = phase6_shadow_observer.refresh_phase6_shadow_report([sample_setup()])
        finally:
            phase6_shadow_observer.REPORT_PATH = old_report_path
            phase6_shadow_observer.MEMORY_PATH = old_memory_path
            phase6_shadow_observer.PHASE6_REPORT_REFRESH_SECONDS = old_refresh_seconds

        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
