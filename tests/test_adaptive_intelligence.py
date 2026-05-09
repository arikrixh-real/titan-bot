"""
Offline tests for TITAN Phase 3 adaptive intelligence.

These tests do not scan live markets, send Telegram alerts, or create trades.
"""

from pathlib import Path
import json
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import adaptive_intelligence as ai
from engines import adaptive_memory_builder as builder


def sample_state():
    return {
        "version": "3.0",
        "last_updated": "2026-05-10 00:00:00",
        "total_closed_trades": 30,
        "total_wins": 20,
        "total_losses": 10,
        "global_confidence": {
            "trades": 30,
            "wins": 20,
            "losses": 10,
            "posterior_win_rate": 0.6471,
            "adaptive_confidence_score": 64.7,
            "sample_confidence": 1.0,
            "weight": 1.0735,
        },
        "feature_memory": {
            "breakout": {
                "trades": 30,
                "wins": 20,
                "losses": 10,
                "posterior_win_rate": 0.6471,
                "sample_confidence": 1.0,
                "weight": 1.0735,
            },
            "volume": {
                "trades": 30,
                "wins": 20,
                "losses": 10,
                "posterior_win_rate": 0.6471,
                "sample_confidence": 1.0,
                "weight": 1.0735,
            },
        },
        "regime_memory": {
            "NEUTRAL_OK": {
                "trades": 30,
                "wins": 20,
                "losses": 10,
                "posterior_win_rate": 0.6471,
                "sample_confidence": 1.0,
                "weight": 1.0735,
            }
        },
        "sector_memory": {
            "Energy / Telecom / Retail": {
                "trades": 30,
                "wins": 20,
                "losses": 10,
                "posterior_win_rate": 0.6471,
                "sample_confidence": 1.0,
                "weight": 1.0735,
            }
        },
        "side_memory": {
            "LONG": {
                "trades": 30,
                "wins": 20,
                "losses": 10,
                "posterior_win_rate": 0.6471,
                "sample_confidence": 1.0,
                "weight": 1.0735,
            }
        },
        "symbol_memory": {},
        "cluster_memory": {
            "LONG|NEUTRAL_OK|ENERGY_TELECOM_RETAIL|breakout+volume": {
                "trades": 30,
                "wins": 20,
                "losses": 10,
                "posterior_win_rate": 0.6471,
                "sample_confidence": 1.0,
                "weight": 1.0735,
            }
        },
        "news_reaction_memory": {
            "seen_news_hashes": ["abc"],
            "symbol_sentiment": {
                "RELIANCE": {"items": 1, "sentiment_score": 0.6}
            },
            "sector_sentiment": {},
        },
    }


class AdaptiveIntelligenceTests(unittest.TestCase):
    def test_missing_memory_fails_open_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = ai.ADAPTIVE_STATE_PATH
            ai.ADAPTIVE_STATE_PATH = Path(tmp) / "missing.json"
            try:
                setup = {"symbol": "RELIANCE", "side": "LONG", "score": 3.0}
                result = ai.apply_adaptive_intelligence(setup)
                self.assertEqual(result, setup)
            finally:
                ai.ADAPTIVE_STATE_PATH = old_path

    def test_runtime_adjustment_is_bounded_and_metadata_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = ai.ADAPTIVE_STATE_PATH
            state_path = Path(tmp) / "adaptive_intelligence_state.json"
            state_path.write_text(json.dumps(sample_state()), encoding="utf-8")
            ai.ADAPTIVE_STATE_PATH = state_path
            try:
                setup = {
                    "symbol": "RELIANCE",
                    "side": "LONG",
                    "score": 3.0,
                    "reason": "Breakout with volume",
                    "market_status": {"market_ok": True, "reason": "Level 1 market filter active"},
                }
                result = ai.apply_adaptive_intelligence(setup)
                self.assertTrue(result["phase3_applied"])
                self.assertTrue(result["phase3_active"])
                self.assertLessEqual(abs(result["phase3_adjustment"]), 0.20)
                self.assertIn("adaptive_confidence_score", result)
                self.assertIn("cluster_quality_score", result)
                self.assertEqual(result["news_sentiment_refined"], "POSITIVE")
            finally:
                ai.ADAPTIVE_STATE_PATH = old_path

    def test_low_sample_memory_adds_metadata_but_keeps_score_neutral(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = ai.ADAPTIVE_STATE_PATH
            state = sample_state()
            state["total_closed_trades"] = 2
            state_path = Path(tmp) / "adaptive_intelligence_state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            ai.ADAPTIVE_STATE_PATH = state_path
            try:
                setup = {
                    "symbol": "RELIANCE",
                    "side": "LONG",
                    "score": 3.0,
                    "reason": "Breakout with volume",
                }
                result = ai.apply_adaptive_intelligence(setup)
                self.assertEqual(result["score"], 3.0)
                self.assertFalse(result["phase3_active"])
            finally:
                ai.ADAPTIVE_STATE_PATH = old_path


class AdaptiveMemoryBuilderTests(unittest.TestCase):
    def test_builder_creates_memory_from_fake_journal_and_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_paths = (
                builder.TRADE_JOURNAL_CSV,
                builder.TRADE_OUTCOMES_JSONL,
                builder.TRADE_OUTCOMES_OLD_CSV,
                builder.ADAPTIVE_STATE_PATH,
                builder.ADAPTIVE_REPORT_PATH,
                builder.MEMORY_DIR,
                builder.REPORTS_DIR,
            )
            try:
                journal_dir = root / "data" / "journals"
                memory_dir = root / "data" / "memory"
                reports_dir = root / "reports"
                journal_dir.mkdir(parents=True)
                memory_dir.mkdir(parents=True)
                reports_dir.mkdir(parents=True)

                builder.TRADE_JOURNAL_CSV = journal_dir / "trade_journal.csv"
                builder.TRADE_OUTCOMES_JSONL = journal_dir / "trade_outcomes.jsonl"
                builder.TRADE_OUTCOMES_OLD_CSV = journal_dir / "trade_outcomes_old.csv"
                builder.ADAPTIVE_STATE_PATH = memory_dir / "adaptive_intelligence_state.json"
                builder.ADAPTIVE_REPORT_PATH = reports_dir / "adaptive_intelligence_report.txt"
                builder.MEMORY_DIR = memory_dir
                builder.REPORTS_DIR = reports_dir

                builder.TRADE_JOURNAL_CSV.write_text(
                    "timestamp,scan_id,symbol,side,entry,sl,target,rr,score,rank_score,confirmations,reason,alert_sent,market_status\n"
                    "2026-05-05 09:20:00,S1,RELIANCE,LONG,100,99,102,2,3,20,Volume Breakout,RELIANCE breakout with volume,YES,\"{'market_ok': True, 'reason': 'Level 1 market filter active'}\"\n",
                    encoding="utf-8",
                )
                builder.TRADE_OUTCOMES_JSONL.write_text(
                    json.dumps({
                        "trade_id": "S1|RELIANCE|LONG|100",
                        "scan_id": "S1",
                        "symbol": "RELIANCE",
                        "side": "LONG",
                        "entry": "100",
                        "outcome": "TARGET_HIT",
                    }) + "\n",
                    encoding="utf-8",
                )

                state = builder.build_adaptive_memory(write_files=True)
                self.assertEqual(state["total_closed_trades"], 1)
                self.assertIn("breakout", state["feature_memory"])
                self.assertTrue(builder.ADAPTIVE_STATE_PATH.exists())
                self.assertTrue(builder.ADAPTIVE_REPORT_PATH.exists())
            finally:
                (
                    builder.TRADE_JOURNAL_CSV,
                    builder.TRADE_OUTCOMES_JSONL,
                    builder.TRADE_OUTCOMES_OLD_CSV,
                    builder.ADAPTIVE_STATE_PATH,
                    builder.ADAPTIVE_REPORT_PATH,
                    builder.MEMORY_DIR,
                    builder.REPORTS_DIR,
                ) = old_paths


if __name__ == "__main__":
    unittest.main()
