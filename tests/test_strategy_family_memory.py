"""
Offline tests for TITAN Phase 5 strategy family memory.

These tests use temporary files only and do not scan, send alerts, call
Supabase, or place broker orders.
"""

from pathlib import Path
import json
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import strategy_family_memory as memory


class StrategyFamilyMemoryTests(unittest.TestCase):
    def test_builder_creates_family_memory_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal_dir = root / "data" / "journals"
            memory_dir = root / "data" / "memory"
            reports_dir = root / "reports"
            journal_dir.mkdir(parents=True)
            memory_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)

            old_paths = (
                memory.TRADE_JOURNAL_CSV,
                memory.TRADE_OUTCOMES_JSONL,
                memory.TRADE_OUTCOMES_OLD_CSV,
                memory.FAMILY_MEMORY_PATH,
                memory.SELF_EVALUATION_REPORT_PATH,
                memory.MEMORY_DIR,
                memory.REPORTS_DIR,
            )

            try:
                memory.TRADE_JOURNAL_CSV = journal_dir / "trade_journal.csv"
                memory.TRADE_OUTCOMES_JSONL = journal_dir / "trade_outcomes.jsonl"
                memory.TRADE_OUTCOMES_OLD_CSV = journal_dir / "trade_outcomes_old.csv"
                memory.FAMILY_MEMORY_PATH = memory_dir / "strategy_family_memory.json"
                memory.SELF_EVALUATION_REPORT_PATH = reports_dir / "self_evaluation_report.txt"
                memory.MEMORY_DIR = memory_dir
                memory.REPORTS_DIR = reports_dir

                memory.TRADE_JOURNAL_CSV.write_text(
                    "timestamp,scan_id,symbol,side,entry,sl,target,rr,score,rank_score,confirmations,reason,alert_sent,market_status\n"
                    "2026-05-05 09:20:00,S1,RELIANCE,LONG,100,99,102,2,3,20,5,Breakout with volume,NO,TRENDING\n",
                    encoding="utf-8",
                )
                memory.TRADE_OUTCOMES_JSONL.write_text(
                    json.dumps({
                        "trade_id": "S1|RELIANCE|LONG|100",
                        "scan_id": "S1",
                        "symbol": "RELIANCE",
                        "side": "LONG",
                        "entry": "100",
                        "outcome": "TP",
                    }) + "\n",
                    encoding="utf-8",
                )

                state = memory.build_strategy_family_memory(write_files=True)

                self.assertEqual(state["total_closed_trades"], 1)
                self.assertIn("BREAKOUT", state["families"])
                self.assertTrue(memory.FAMILY_MEMORY_PATH.exists())
                self.assertTrue(memory.SELF_EVALUATION_REPORT_PATH.exists())
                self.assertIn("overfitting_controls", state)
            finally:
                (
                    memory.TRADE_JOURNAL_CSV,
                    memory.TRADE_OUTCOMES_JSONL,
                    memory.TRADE_OUTCOMES_OLD_CSV,
                    memory.FAMILY_MEMORY_PATH,
                    memory.SELF_EVALUATION_REPORT_PATH,
                    memory.MEMORY_DIR,
                    memory.REPORTS_DIR,
                ) = old_paths

    def test_bucket_uses_shrinkage_and_caps(self):
        bucket = {"trades": 30, "wins": 30, "losses": 0}
        finalized = memory._finalize_bucket(bucket)

        self.assertLessEqual(finalized["family_quality_score"], 65.0)
        self.assertGreaterEqual(finalized["family_quality_score"], 35.0)
        self.assertLessEqual(finalized["weight"], 1.06)


if __name__ == "__main__":
    unittest.main()
