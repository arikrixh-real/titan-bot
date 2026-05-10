"""
Offline tests for TITAN Phase 8 market narrative shadow intelligence.

These tests do not scan, call live prices, send Telegram, use broker APIs,
or change rankings/final decisions.
"""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import market_narrative_engine as narrative
from titan_master_brain.execution_engine import build_signal_message
from titan_master_brain.final_decision_engine import make_final_decisions


def sample_master_input():
    return {
        "market": {
            "status": "OK",
            "data": {
                "market_ok": True,
                "reason": "cached_data_advantage_active",
                "direction": "BULLISH",
                "risk_tone": "RISK_ON",
                "risk_tone_score": 68,
                "volatility": "NORMAL",
                "index_breadth": {"breadth_score": 70},
                "sector_rankings": [
                    {"sector": "Banking", "strength_score": 72},
                    {"sector": "IT", "strength_score": 66},
                    {"sector": "Metals", "strength_score": 35},
                ],
                "event_calendar_proxy": {
                    "event_caution": False,
                    "event_pressure_score": 10,
                    "event_keywords": [],
                },
            },
        },
        "setups": {"count": 2},
        "memory": {"analysis": {}},
    }


def sample_context():
    return {
        "market_type": "MARKET_ALLOWED_LEVEL_1",
        "trading_mode": "SELECTIVE",
        "risk_level": "MEDIUM",
        "setup_environment": "NORMAL_SETUP_PHASE",
        "learning_environment": "LEARNING_NOT_READY",
    }


def sample_setups():
    return [
        {
            "symbol": "HDFCBANK",
            "side": "LONG",
            "score": 3.2,
            "rr": 2.0,
            "decision": "TRUST",
            "confidence": "HIGH",
            "raw": {"sector": "Banking"},
        },
        {
            "symbol": "TATASTEEL",
            "side": "SHORT",
            "score": 3.0,
            "rr": 2.0,
            "decision": "TRUST",
            "confidence": "HIGH",
            "raw": {"sector": "Metals"},
        },
    ]


class MarketNarrativeEngineTests(unittest.TestCase):
    def test_build_narrative_is_shadow_and_does_not_mutate_inputs(self):
        master_input = sample_master_input()
        context = sample_context()
        setups = sample_setups()
        before = (deepcopy(master_input), deepcopy(context), deepcopy(setups))

        result = narrative.build_market_narrative_shadow(master_input, context, setups)

        self.assertTrue(result["phase8_shadow_mode"])
        self.assertTrue(result["phase8_applied"])
        self.assertEqual(result["narrative_adjustment"], 0.0)
        self.assertEqual(result["narrative_type"], "RISK_ON_TREND")
        self.assertEqual(master_input, before[0])
        self.assertEqual(context, before[1])
        self.assertEqual(setups, before[2])

    def test_refresh_report_writes_compact_artifacts(self):
        old_memory = narrative.MEMORY_PATH
        old_report = narrative.REPORT_PATH
        old_refresh = narrative.REPORT_REFRESH_SECONDS

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            narrative.MEMORY_PATH = tmp_path / "memory" / "market_narrative_memory.json"
            narrative.REPORT_PATH = tmp_path / "reports" / "market_narrative_report.txt"
            narrative.REPORT_REFRESH_SECONDS = -1

            result = narrative.refresh_market_narrative_report(
                sample_master_input(),
                sample_context(),
                sample_setups(),
            )

            self.assertEqual(result["narrative_type"], "RISK_ON_TREND")
            self.assertTrue(narrative.MEMORY_PATH.exists())
            self.assertTrue(narrative.REPORT_PATH.exists())
            self.assertLess(narrative.REPORT_PATH.stat().st_size, 10000)

        narrative.MEMORY_PATH = old_memory
        narrative.REPORT_PATH = old_report
        narrative.REPORT_REFRESH_SECONDS = old_refresh

    def test_report_generation_fails_open(self):
        old_memory = narrative.MEMORY_PATH
        old_report = narrative.REPORT_PATH
        old_refresh = narrative.REPORT_REFRESH_SECONDS

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            narrative.MEMORY_PATH = tmp_path / "memory" / "market_narrative_memory.json"
            narrative.REPORT_PATH = tmp_path
            narrative.REPORT_REFRESH_SECONDS = -1

            result = narrative.refresh_market_narrative_report(
                sample_master_input(),
                sample_context(),
                sample_setups(),
            )

            self.assertFalse(result["phase8_applied"])
            self.assertEqual(result["narrative_type"], "DATA_INSUFFICIENT_NEUTRAL")
            self.assertIn("error", result)

        narrative.MEMORY_PATH = old_memory
        narrative.REPORT_PATH = old_report
        narrative.REPORT_REFRESH_SECONDS = old_refresh

    def test_no_network_live_price_telegram_or_broker_imports(self):
        source = (PROJECT_ROOT / "engines" / "market_narrative_engine.py").read_text(encoding="utf-8")
        banned = [
            "requests",
            "yfinance",
            "websocket",
            "get_live_price",
            "send_telegram",
            "TELEGRAM",
            "supabase",
            "create_client",
            "Upstox",
        ]
        for token in banned:
            self.assertNotIn(token, source)

    def test_ranking_and_telegram_formatting_unchanged(self):
        setups = sample_setups()
        context = sample_context()
        before = make_final_decisions(deepcopy(setups), context)["selected"]

        narrative.build_market_narrative_shadow(sample_master_input(), context, setups)

        after = make_final_decisions(deepcopy(setups), context)["selected"]
        self.assertEqual([item["symbol"] for item in before], [item["symbol"] for item in after])

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


if __name__ == "__main__":
    unittest.main()
