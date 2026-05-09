"""
Offline tests for TITAN Phase 2 portfolio and execution proxy engines.

These tests do not scan live markets, send Telegram alerts, write fake trades,
call Supabase, or place broker orders.
"""

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines.execution_quality_engine import analyze_execution_quality
from engines.portfolio_construction_engine import analyze_portfolio_construction
import engines.portfolio_construction_engine as portfolio_engine
import engines.setup_engine as setup_engine
from engines.setup_engine import apply_institutional_phase2
from titan_master_brain.setup_normalizer import normalize_setup


def make_stable_df(rows=80, start=100.0, step=0.25, volume_base=100000):
    data = []
    price = start

    for idx in range(rows):
        open_price = price
        close = price + step
        high = max(open_price, close) + 0.18
        low = min(open_price, close) - 0.16
        volume = volume_base + (idx * 500)
        data.append([open_price, high, low, close, volume])
        price = close

    return pd.DataFrame(data, columns=["Open", "High", "Low", "Close", "Volume"])


def make_extended_candle_df(rows=80):
    df = make_stable_df(rows)
    prior_close = float(df.iloc[-2]["Close"])
    df.loc[rows - 1, ["Open", "High", "Low", "Close", "Volume"]] = [
        prior_close,
        prior_close + 5.5,
        prior_close - 0.1,
        prior_close + 5.2,
        260000,
    ]
    return df


class InstitutionalPhase2Tests(unittest.TestCase):
    def test_portfolio_engine_returns_required_fields(self):
        result = analyze_portfolio_construction(
            setup={"symbol": "RELIANCE", "side": "LONG", "entry": 110},
            df=make_stable_df(),
            active_rows=[],
        )

        self.assertTrue(result["available"])
        self.assertIn("sector_exposure_score", result)
        self.assertIn("portfolio_concentration_risk", result)
        self.assertIn("correlation_proxy", result)
        self.assertIn("beta_like_market_sensitivity", result)
        self.assertIn("volatility_contribution_score", result)
        self.assertIn("portfolio_risk_warnings", result)

    def test_portfolio_engine_flags_sector_crowding(self):
        active_rows = [
            {"symbol": "ICICIBANK", "side": "LONG", "status": "OPEN"},
            {"symbol": "SBIN", "side": "LONG", "status": "OPEN"},
            {"symbol": "AXISBANK", "side": "SHORT", "status": "OPEN"},
        ]

        result = analyze_portfolio_construction(
            setup={"symbol": "HDFCBANK", "side": "LONG", "entry": 110},
            df=make_stable_df(),
            active_rows=active_rows,
        )

        self.assertGreaterEqual(result["same_sector_open_count"], 1)
        self.assertLess(result["sector_exposure_score"], 100)
        self.assertIn("sector_crowding", result["portfolio_risk_warnings"])

    def test_execution_quality_penalizes_extended_chase_entry(self):
        df = make_extended_candle_df()
        entry = float(df.iloc[-1]["Close"])

        result = analyze_execution_quality(
            df=df,
            setup={"symbol": "RELIANCE", "side": "LONG", "entry": entry},
            microstructure={"liquidity_quality_score": 55, "spread_behavior_proxy": 55},
            live_price=entry,
        )

        self.assertTrue(result["available"])
        self.assertTrue(result["extended_candle_risk"])
        self.assertGreater(result["chase_entry_penalty"], 0)
        self.assertIn("extended_candle_chase_risk", result["warnings"])

    def test_execution_quality_scores_better_near_recent_fair_value(self):
        df = make_stable_df()
        fair_entry = float(((df["High"] + df["Low"] + df["Close"]) / 3.0).tail(20).mean())
        chase_entry = fair_entry + 8.0

        fair = analyze_execution_quality(
            df=df,
            setup={"symbol": "RELIANCE", "side": "LONG", "entry": fair_entry},
            microstructure={"liquidity_quality_score": 75, "spread_behavior_proxy": 75},
        )
        chase = analyze_execution_quality(
            df=df,
            setup={"symbol": "RELIANCE", "side": "LONG", "entry": chase_entry},
            microstructure={"liquidity_quality_score": 75, "spread_behavior_proxy": 75},
        )

        self.assertGreater(
            fair["execution_quality_score"],
            chase["execution_quality_score"],
        )

    def test_phase2_integration_is_bounded_and_metadata_only(self):
        payload = {
            "symbol": "RELIANCE",
            "side": "LONG",
            "entry": 110.0,
            "score": 3.0,
            "rank_score": 3.0,
            "scores": {},
            "market_context": {},
            "setup_context": {},
            "microstructure": {"liquidity_quality_score": 70, "spread_behavior_proxy": 70},
        }

        result = apply_institutional_phase2(
            trade_payload=payload,
            data=make_stable_df(),
            side="LONG",
            live_price=110.0,
        )

        self.assertIn("portfolio_construction", result)
        self.assertIn("execution_quality", result)
        self.assertIn("phase2_score_adjustment", result)
        self.assertGreaterEqual(result["phase2_score_adjustment"], -0.25)
        self.assertLessEqual(result["phase2_score_adjustment"], 0.15)
        self.assertNotIn("phase2_blocked", result)

    def test_phase2_integration_fails_open_with_neutral_metadata(self):
        old_portfolio = setup_engine.analyze_portfolio_construction

        def boom(*args, **kwargs):
            raise RuntimeError("forced phase2 failure")

        setup_engine.analyze_portfolio_construction = boom

        try:
            payload = {
                "symbol": "RELIANCE",
                "side": "LONG",
                "entry": 110.0,
                "score": 3.0,
                "rank_score": 3.0,
            }
            result = apply_institutional_phase2(
                trade_payload=payload,
                data=make_stable_df(),
                side="LONG",
                live_price=110.0,
            )
        finally:
            setup_engine.analyze_portfolio_construction = old_portfolio

        self.assertIn("portfolio_construction", result)
        self.assertIn("execution_quality", result)
        self.assertGreaterEqual(result["score"], 0)

    def test_normalizer_preserves_phase2_metadata(self):
        normalized = normalize_setup({
            "symbol": "RELIANCE",
            "side": "LONG",
            "entry": 100,
            "score": 3.0,
            "portfolio_construction": {"portfolio_quality_score": 61},
            "execution_quality": {"execution_quality_score": 72},
            "phase2_score_adjustment": 0.08,
            "phase2_risk_warnings": ["example_warning"],
        })

        self.assertIn("portfolio_construction", normalized)
        self.assertIn("execution_quality", normalized)
        self.assertEqual(normalized["phase2_score_adjustment"], 0.08)

    def test_portfolio_engine_can_read_temp_active_file_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            active_path = Path(tmp) / "active.csv"
            active_path.write_text(
                "symbol,side,status\nRELIANCE,LONG,OPEN\nONGC,LONG,OPEN\n",
                encoding="utf-8",
            )

            old_files = portfolio_engine.ACTIVE_TRADE_FILES
            portfolio_engine.ACTIVE_TRADE_FILES = [active_path]

            try:
                result = analyze_portfolio_construction(
                    setup={"symbol": "RELIANCE", "side": "LONG", "entry": 110},
                    df=make_stable_df(),
                )
            finally:
                portfolio_engine.ACTIVE_TRADE_FILES = old_files

        self.assertTrue(result["available"])
        self.assertEqual(result["open_trade_count"], 2)


if __name__ == "__main__":
    unittest.main()
