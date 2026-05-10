"""
Offline tests for TITAN Phase 5 meta intelligence.

These tests do not scan live markets, send Telegram alerts, write trades,
call Supabase, or place broker orders.
"""

from pathlib import Path
import json
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import meta_intelligence_engine as meta
from titan_master_brain.setup_normalizer import normalize_setup
from titan_master_brain.daily_alert_manager import calculate_daily_alert_rank


def sample_setup():
    return {
        "symbol": "RELIANCE",
        "side": "LONG",
        "entry": 100.0,
        "sl": 98.0,
        "target": 104.0,
        "rr": 2.0,
        "score": 3.0,
        "rank_score": 3.0,
        "reason": "Breakout with volume compression",
        "microstructure": {"liquidity_quality_score": 72, "spread_behavior_proxy": 70},
        "advanced_regime": {
            "regime_type": "TRENDING",
            "regime_confidence": 68,
            "panic_score": 10,
            "liquidity_crisis_score": 5,
        },
        "professional_risk": {"risk_quality_score": 74, "risk_blocks": []},
        "portfolio_construction": {"portfolio_quality_score": 63},
        "execution_quality": {"execution_quality_score": 70, "slippage_risk_estimate": 35},
        "adaptive_confidence_score": 58,
        "cluster_quality_score": 57,
        "data_advantage_score": 62,
        "scores": {},
        "setup_context": {},
    }


class MetaIntelligenceTests(unittest.TestCase):
    def test_meta_layer_is_bounded_and_does_not_block(self):
        setup = sample_setup()
        result = meta.apply_meta_intelligence(setup)

        self.assertTrue(result["phase5_applied"])
        self.assertFalse(result["phase5_blocked"])
        self.assertIn("meta_quality_score", result)
        self.assertIn("meta_layer_scores", result)
        self.assertIn("strategy_family", result)
        self.assertGreaterEqual(result["meta_rank_adjustment"], -0.30)
        self.assertLessEqual(result["meta_rank_adjustment"], 0.20)
        self.assertEqual(result["score"], setup["score"])

    def test_missing_layers_fail_open_with_neutral_metadata(self):
        setup = {"symbol": "TCS", "side": "LONG", "score": 2.5, "rank_score": 2.5}
        result = meta.apply_meta_intelligence(setup)

        self.assertTrue(result["phase5_applied"])
        self.assertFalse(result["phase5_blocked"])
        self.assertGreaterEqual(result["meta_quality_score"], 0)
        self.assertLessEqual(result["meta_quality_score"], 100)

    def test_family_memory_small_sample_stays_neutral(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = meta.FAMILY_MEMORY_PATH
            memory_path = Path(tmp) / "family.json"
            memory_path.write_text(
                json.dumps({
                    "total_closed_trades": 4,
                    "families": {
                        "COMPRESSION_BREAKOUT": {
                            "trades": 4,
                            "wins": 4,
                            "losses": 0,
                            "family_quality_score": 65,
                            "posterior_win_rate": 0.75,
                            "sample_confidence": 0.2,
                        }
                    },
                }),
                encoding="utf-8",
            )
            meta.FAMILY_MEMORY_PATH = memory_path
            try:
                result = meta.apply_meta_intelligence(sample_setup())
                self.assertFalse(result["strategy_family_strength"]["memory_active"])
                self.assertEqual(result["meta_layer_scores"]["family_score"], 50.0)
            finally:
                meta.FAMILY_MEMORY_PATH = old_path

    def test_normalizer_preserves_phase5_metadata(self):
        result = meta.apply_meta_intelligence(sample_setup())
        normalized = normalize_setup(result)

        self.assertIn("meta_quality_score", normalized)
        self.assertIn("strategy_family", normalized)
        self.assertIn("phase5_applied", normalized)

    def test_daily_alert_rank_meta_effect_is_tiny(self):
        base = {
            "symbol": "RELIANCE",
            "side": "LONG",
            "score": 3.0,
            "rr": 2.0,
            "decision": "TRUST",
            "confidence": "HIGH",
            "raw": {"setup_context": {"confirmations": 5}},
        }
        low = calculate_daily_alert_rank({**base, "meta_quality_score": 25})
        high = calculate_daily_alert_rank({**base, "meta_quality_score": 75})
        self.assertLessEqual(high - low, 4.0)


if __name__ == "__main__":
    unittest.main()
