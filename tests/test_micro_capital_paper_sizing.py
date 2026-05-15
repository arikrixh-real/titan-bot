"""
Focused paper-sizing tests for ADAPTIVE_1K mode.

These tests do not scan markets, create trades, call brokers, or send alerts.
"""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines.paper_trading_engine import calculate_paper_trade_sizing


def micro_account(balance=1000.0):
    return {
        "capital_mode": "ADAPTIVE_1K",
        "current_balance": balance,
        "risk_rules": {"max_risk_per_trade_pct": 1.0},
    }


class MicroCapitalPaperSizingTests(unittest.TestCase):
    def test_affordable_stock_is_capped_to_cash_not_rejected(self):
        sizing = calculate_paper_trade_sizing(
            micro_account(),
            {"symbol": "BANKBARODA", "entry": 200.0, "sl": 199.5},
        )

        self.assertTrue(sizing["sizing_valid"])
        self.assertEqual(sizing["computed_qty"], 20)
        self.assertEqual(sizing["quantity"], 5)
        self.assertEqual(sizing["required_capital"], 1000.0)
        self.assertLessEqual(sizing["quantity"] * sizing["risk_per_share"], sizing["risk_amount"])
        self.assertEqual(sizing["rejection_reason"], "")

    def test_one_share_is_allowed_when_risk_and_cash_are_valid(self):
        sizing = calculate_paper_trade_sizing(
            micro_account(),
            {"symbol": "PFC", "entry": 450.0, "sl": 445.0},
        )

        self.assertTrue(sizing["sizing_valid"])
        self.assertEqual(sizing["quantity"], 2)
        self.assertLessEqual(sizing["required_capital"], sizing["account_balance"])

    def test_extremely_wide_stop_is_still_rejected(self):
        sizing = calculate_paper_trade_sizing(
            micro_account(),
            {"symbol": "TATAMOTORS", "entry": 200.0, "sl": 180.0},
        )

        self.assertFalse(sizing["sizing_valid"])
        self.assertEqual(sizing["quantity"], 0)
        self.assertEqual(sizing["rejection_reason"], "MICRO_CAPITAL_SL_TOO_WIDE")

    def test_price_above_cash_is_still_rejected(self):
        sizing = calculate_paper_trade_sizing(
            micro_account(),
            {"symbol": "ADANIENT", "entry": 1200.0, "sl": 1199.0},
        )

        self.assertFalse(sizing["sizing_valid"])
        self.assertEqual(sizing["quantity"], 0)
        self.assertEqual(sizing["rejection_reason"], "MICRO_CAPITAL_PRICE_SKIP")


if __name__ == "__main__":
    unittest.main()
