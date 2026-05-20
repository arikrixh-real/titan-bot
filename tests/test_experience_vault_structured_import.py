import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experience_vault_runner.lesson_extractor import extract_structured_import_lessons


class ExperienceVaultStructuredImportTests(unittest.TestCase):
    def _csv_path(self, row):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "historical_experience_import.csv"
        with path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
        return path

    def _jsonl_path(self, row):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "historical_experience_import.jsonl"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        return path

    def test_csv_rows_parse_as_structured_records_without_concatenation(self):
        path = self._csv_path(
            {
                "experience_hash": "abc",
                "symbol": "RELIANCE",
                "setup_type": "trend_momentum_breakout",
                "side": "LONG",
                "outcome": "WIN",
                "outcome_reason": "Target touched at 2026-05-19T10:00:00Z",
                "rr": "2.0",
                "score": "84.5",
                "trend": "BULLISH",
                "reason": "trend_momentum_breakout simulated from cached candles: trend=BULLISH, side=LONG",
                "lesson_learned": "trend_momentum_breakout on RELIANCE worked in BULLISH conditions",
                "source_type": "HISTORICAL_SIMULATED",
                "validation_status": "UNVALIDATED",
            }
        )

        lessons = extract_structured_import_lessons(path, "data/experience_vault/imported_trade_logs/x.csv", "imported_trade_logs")

        self.assertGreaterEqual(len(lessons), 4)
        first = lessons[0]
        self.assertEqual(first["source_type"], "EXTERNAL_EXPERIENCE")
        self.assertEqual(first["validation_status"], "UNVALIDATED")
        self.assertEqual(first["symbol"], "RELIANCE")
        self.assertEqual(first["setup_type"], "trend_momentum_breakout")
        self.assertEqual(first["side"], "LONG")
        self.assertEqual(first["regime"], "BULLISH")
        self.assertEqual(first["outcome"], "WIN")
        self.assertEqual(first["trade_result"], "WIN")
        self.assertEqual(first["polarity"], "POSITIVE")
        self.assertEqual(first["score"], 84.5)
        self.assertEqual(first["rr"], 2.0)
        self.assertNotIn("experience_hash", first["setup_type"])
        self.assertNotIn("outcome_reason", first["regime"])

    def test_jsonl_loss_gets_negative_polarity_and_no_trade_lesson(self):
        path = self._jsonl_path(
            {
                "symbol": "INFY",
                "setup_type": "compression_breakout_attempt",
                "side": "SHORT",
                "regime": "CHOPPY",
                "outcome": "LOSS",
                "outcome_reason": "Stop loss touched after failed follow through",
                "score": 62,
                "rr": -1,
                "reason": "compression was present but follow through failed",
                "lesson_learned": "treat similar compression failures cautiously",
            }
        )

        lessons = extract_structured_import_lessons(path, "data/experience_vault/imported_trade_logs/x.jsonl", "imported_trade_logs")

        lesson_types = {lesson["lesson_type"] for lesson in lessons}
        self.assertIn("failure_success_reason", lesson_types)
        self.assertIn("confidence_lesson", lesson_types)
        self.assertIn("causal_lesson", lesson_types)
        self.assertIn("stock_behavior", lesson_types)
        self.assertIn("no_trade_lesson", lesson_types)
        self.assertTrue(all(lesson["polarity"] == "NEGATIVE" for lesson in lessons))
        self.assertTrue(all(lesson["trade_result"] == "LOSS" for lesson in lessons))


if __name__ == "__main__":
    unittest.main()
