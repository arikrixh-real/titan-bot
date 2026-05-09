"""
Offline tests for TITAN Phase 4 data advantage layer.

These tests use synthetic local data only. They do not scan live markets,
send Telegram alerts, write trades, call Supabase, or place broker orders.
"""

from pathlib import Path
import json
import sys
import tempfile
import unittest

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines.data_advantage_engine import (  # noqa: E402
    apply_data_advantage_layer,
    build_data_advantage_context,
    market_status_from_context,
)
import engines.data_advantage_engine as data_advantage_engine  # noqa: E402
from titan_master_brain.setup_normalizer import normalize_setup  # noqa: E402


def make_df(rows=80, start=100.0, step=0.3, volume_base=100000, volume_step=500):
    data = []
    price = start
    for idx in range(rows):
        open_price = price
        close = price + step
        high = max(open_price, close) + 0.2
        low = min(open_price, close) - 0.2
        volume = volume_base + (idx * volume_step)
        data.append([open_price, high, low, close, volume])
        price = close
    return pd.DataFrame(data, columns=["Open", "High", "Low", "Close", "Volume"])


class DataAdvantageEngineTests(unittest.TestCase):
    def test_context_returns_market_breadth_and_neutral_options_proxy(self):
        stock_data = {
            "^NSEI": make_df(step=0.4),
            "RELIANCE": make_df(step=0.5),
            "TCS": make_df(step=0.35),
            "INFY": make_df(step=-0.1),
            "HDFCBANK": make_df(step=0.2),
        }

        context = build_data_advantage_context(stock_data)

        self.assertTrue(context["available"])
        self.assertTrue(context["market_ok"])
        self.assertIn("index_breadth", context)
        self.assertIn("breadth_score", context["index_breadth"])
        self.assertIn("sector_rankings", context)
        self.assertFalse(context["options_derivatives_proxy"]["available"])
        self.assertEqual(context["options_derivatives_proxy"]["derivatives_pressure_score"], 50.0)

    def test_sector_rotation_and_volatility_metadata_present(self):
        stock_data = {
            "^NSEI": make_df(step=0.2),
            "TCS": make_df(step=0.6),
            "INFY": make_df(step=0.5),
            "HDFCBANK": make_df(step=-0.05),
            "ICICIBANK": make_df(step=-0.02),
        }

        context = build_data_advantage_context(stock_data)

        self.assertIn("IT", context["sector_strength"])
        self.assertIn("IT", context["sector_rotation"])
        self.assertIn("IT", context["sector_volatility"])
        self.assertIn(context["sector_rotation"]["IT"]["state"], {"ROTATING_IN", "ROTATING_OUT", "STABLE"})

    def test_event_caution_proxy_reads_local_news_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            news_path = Path(tmp) / "news_batch_state.json"
            news_path.write_text(
                json.dumps({
                    "news": [
                        {
                            "title": "RBI MPC rate decision due as inflation stays high",
                            "summary": "Markets watch policy commentary",
                            "sectors": ["Banking", "Market Index"],
                        }
                    ]
                }),
                encoding="utf-8",
            )
            old_path = data_advantage_engine.NEWS_MEMORY_FILE
            data_advantage_engine.NEWS_MEMORY_FILE = news_path
            try:
                context = build_data_advantage_context({
                    "^NSEI": make_df(step=0.2),
                    "HDFCBANK": make_df(step=0.2),
                    "ICICIBANK": make_df(step=0.2),
                })
            finally:
                data_advantage_engine.NEWS_MEMORY_FILE = old_path

        event_proxy = context["event_calendar_proxy"]
        self.assertTrue(event_proxy["available"])
        self.assertTrue(event_proxy["event_caution"])
        self.assertIn("rbi", event_proxy["event_keywords"])

    def test_apply_layer_is_bounded_and_does_not_block(self):
        context = build_data_advantage_context({
            "^NSEI": make_df(step=0.4),
            "RELIANCE": make_df(step=0.7, volume_step=1500),
            "ONGC": make_df(step=0.3),
        })
        payload = {
            "symbol": "RELIANCE",
            "side": "LONG",
            "entry": 120.0,
            "score": 3.0,
            "rank_score": 3.0,
            "scores": {},
            "market_context": {},
            "setup_context": {},
        }

        result = apply_data_advantage_layer(
            trade_payload=payload,
            symbol="RELIANCE",
            df=make_df(step=0.7, volume_step=1500),
            side="LONG",
            market_context=context,
        )

        self.assertIn("phase4_data_advantage", result)
        self.assertIn("phase4_score_adjustment", result)
        self.assertGreaterEqual(result["phase4_score_adjustment"], -0.20)
        self.assertLessEqual(result["phase4_score_adjustment"], 0.20)
        self.assertNotIn("phase4_blocked", result)

    def test_apply_layer_fails_open_with_neutral_adjustment(self):
        old_flow = data_advantage_engine._institutional_flow_proxy

        def boom(*args, **kwargs):
            raise RuntimeError("forced phase4 failure")

        data_advantage_engine._institutional_flow_proxy = boom
        try:
            result = apply_data_advantage_layer(
                trade_payload={"symbol": "RELIANCE", "side": "LONG", "score": 3.0, "rank_score": 3.0},
                symbol="RELIANCE",
                df=make_df(),
                side="LONG",
                market_context={"available": True},
            )
        finally:
            data_advantage_engine._institutional_flow_proxy = old_flow

        self.assertEqual(result["phase4_score_adjustment"], 0.0)
        self.assertEqual(result["data_advantage_score"], 50.0)
        self.assertEqual(result["score"], 3.0)

    def test_market_status_is_backward_compatible_and_fail_open(self):
        status = market_status_from_context({"available": False, "index_breadth": {}})

        self.assertTrue(status["market_ok"])
        self.assertIn("reason", status)
        self.assertIn("direction", status)
        self.assertIn("regime", status)

    def test_normalizer_preserves_phase4_metadata(self):
        normalized = normalize_setup({
            "symbol": "RELIANCE",
            "side": "LONG",
            "entry": 100,
            "score": 3.0,
            "phase4_data_advantage": {"composite_score": 62},
            "phase4_score_adjustment": 0.12,
            "data_advantage_score": 62,
            "market_risk_tone": "RISK_ON",
            "sector_strength_score": 66,
            "unusual_activity_score": 72,
        })

        self.assertIn("phase4_data_advantage", normalized)
        self.assertEqual(normalized["phase4_score_adjustment"], 0.12)
        self.assertEqual(normalized["market_risk_tone"], "RISK_ON")


if __name__ == "__main__":
    unittest.main()

