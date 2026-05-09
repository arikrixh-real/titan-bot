"""
Offline tests for TITAN Phase 1 institutional proxy engines.

These tests do not send Telegram alerts, write fake trades, call Supabase,
or place broker orders.
"""

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines.advanced_regime_engine import detect_advanced_regime
from engines.institutional_microstructure import analyze_microstructure
from engines.pro_risk_engine import evaluate_professional_risk
import engines.pro_risk_engine as pro_risk_engine


def make_trending_df(rows=80):
    data = []
    price = 100.0

    for idx in range(rows):
        open_price = price
        close = price + 0.45
        high = close + 0.25
        low = open_price - 0.15
        volume = 100000 + (idx * 700)
        data.append([open_price, high, low, close, volume])
        price = close

    return pd.DataFrame(data, columns=["Open", "High", "Low", "Close", "Volume"])


def make_panic_df(rows=80):
    df = make_trending_df(rows)
    base = float(df.iloc[-2]["Close"])
    df.loc[rows - 1, ["Open", "High", "Low", "Close", "Volume"]] = [
        base,
        base * 1.09,
        base * 0.91,
        base * 1.07,
        900000,
    ]
    return df


def make_sweep_df(rows=60):
    df = make_trending_df(rows)
    recent_low = float(df["Low"].iloc[:-1].min())
    last_open = float(df.iloc[-2]["Close"])
    df.loc[rows - 1, ["Open", "High", "Low", "Close", "Volume"]] = [
        last_open,
        last_open * 1.01,
        recent_low * 0.995,
        last_open * 1.006,
        240000,
    ]
    return df


class InstitutionalPhase1Tests(unittest.TestCase):
    def test_microstructure_outputs_required_fields(self):
        result = analyze_microstructure(make_sweep_df(), side="LONG")

        self.assertTrue(result["available"])
        self.assertIn("order_imbalance_proxy", result)
        self.assertIn("bid_ask_pressure_proxy", result)
        self.assertIn("spread_behavior_proxy", result)
        self.assertIn("tick_behavior_proxy", result)
        self.assertIn("liquidity_quality_score", result)
        self.assertTrue(result["liquidity_sweep"])

    def test_advanced_regime_detects_trending_or_confident_regime(self):
        result = detect_advanced_regime(make_trending_df(), symbol="RELIANCE")

        self.assertTrue(result["available"])
        self.assertIn(result["regime_type"], {
            "TRENDING",
            "MEAN_REVERTING",
            "PANIC_VOLATILITY_SPIKE",
            "NEWS_DRIVEN",
            "LIQUIDITY_CRISIS",
        })
        self.assertGreaterEqual(result["regime_confidence"], 0)
        self.assertGreater(result["trending_score"], 20)

    def test_advanced_regime_detects_panic_spike(self):
        result = detect_advanced_regime(make_panic_df(), symbol="RELIANCE")

        self.assertTrue(result["available"])
        self.assertGreaterEqual(result["panic_score"], 60)

    def test_professional_risk_blocks_max_open_trades(self):
        with tempfile.TemporaryDirectory() as tmp:
            active_path = Path(tmp) / "active.csv"
            rows = ["symbol,side,status"]
            for idx in range(pro_risk_engine.MAX_OPEN_TRADES):
                rows.append(f"TEST{idx},LONG,OPEN")
            active_path.write_text("\n".join(rows), encoding="utf-8")

            old_active_files = pro_risk_engine.ACTIVE_TRADE_FILES
            old_outcome_files = pro_risk_engine.OUTCOME_FILES
            pro_risk_engine.ACTIVE_TRADE_FILES = [active_path]
            pro_risk_engine.OUTCOME_FILES = []

            try:
                result = evaluate_professional_risk(
                    setup={"symbol": "RELIANCE", "side": "LONG", "score": 3.5, "rr": 2.0},
                    microstructure={"liquidity_quality_score": 70, "spread_behavior_proxy": 75},
                    regime={"regime_type": "TRENDING", "panic_score": 10, "liquidity_crisis_score": 5},
                )
            finally:
                pro_risk_engine.ACTIVE_TRADE_FILES = old_active_files
                pro_risk_engine.OUTCOME_FILES = old_outcome_files

        self.assertFalse(result["risk_allowed"])
        self.assertIn("max_open_trades_guard", result["risk_blocks"])

    def test_professional_risk_blocks_bad_regime_weak_trade(self):
        result = evaluate_professional_risk(
            setup={"symbol": "RELIANCE", "side": "LONG", "score": 2.4, "rr": 2.0},
            microstructure={"liquidity_quality_score": 42, "spread_behavior_proxy": 40},
            regime={
                "regime_type": "PANIC_VOLATILITY_SPIKE",
                "panic_score": 80,
                "liquidity_crisis_score": 50,
            },
        )

        self.assertFalse(result["risk_allowed"])
        self.assertIn("bad_regime_weak_trade", result["risk_blocks"])


if __name__ == "__main__":
    unittest.main()
