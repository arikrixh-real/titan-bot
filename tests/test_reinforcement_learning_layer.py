import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import reinforcement_learning_layer as rl


def _record(symbol, outcome):
    return {
        "symbol": symbol,
        "setup_type": "trend_momentum_breakout",
        "side": "LONG",
        "entry": 100.0,
        "sl": 98.0,
        "target": 104.0,
        "outcome": outcome,
        "pnl_points": 4.0 if outcome == "WIN" else -2.0,
        "rr": 2.0,
        "score": 72.0,
        "trend": "BULLISH",
        "regime_label": "TRENDING",
        "source_type": "HISTORICAL_REPLAY",
    }


class ReinforcementLearningLayerTests(unittest.TestCase):
    def test_replay_memory_is_shadow_only_and_bounded(self):
        records = [_record(f"AAA{i}", "WIN") for i in range(rl.MAX_REPLAY_RECORDS + 25)]

        memory = rl.build_reinforcement_memory_from_replay(records)

        self.assertTrue(memory["research_only"])
        self.assertTrue(memory["advisory_only"])
        self.assertTrue(memory["shadow_mode"])
        self.assertEqual(memory["records_received"], rl.MAX_REPLAY_RECORDS + 25)
        self.assertEqual(memory["records_processed"], rl.MAX_REPLAY_RECORDS)
        self.assertLessEqual(memory["memory_priority"], 100.0)
        self.assertGreaterEqual(memory["memory_priority"], 0.0)
        safety = memory["safety"]
        self.assertFalse(safety["final_decision_engine_rank_mutation"])
        self.assertFalse(safety["scanner_mutation"])
        self.assertFalse(safety["execution_mutation"])
        self.assertFalse(safety["broker_mutation"])
        self.assertFalse(safety["telegram_mutation"])
        self.assertFalse(safety["supabase_mutation"])

    def test_refresh_writes_only_requested_local_files(self):
        records = [_record("AAA", "WIN"), _record("BBB", "LOSS")]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_path = root / "memory.json"
            report_path = root / "report.txt"
            status_path = root / "status.json"

            memory = rl.refresh_reinforcement_memory_from_replay(
                records,
                memory_path=memory_path,
                report_path=report_path,
                status_path=status_path,
            )

            self.assertEqual(memory["records_processed"], 2)
            self.assertTrue(memory_path.exists())
            self.assertTrue(report_path.exists())
            self.assertTrue(status_path.exists())
            self.assertIn("REINFORCEMENT LEARNING REPORT", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
