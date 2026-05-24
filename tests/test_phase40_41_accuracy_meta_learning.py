import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import accuracy_validation_framework as phase40
from engines import meta_learning_engine as phase41
import runtime_status


class Phase40Phase41Tests(unittest.TestCase):
    def _write_csv(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row.keys()}))
            writer.writeheader()
            writer.writerows(rows)

    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_phase40_builds_accuracy_from_existing_artifacts_and_stays_shadow_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            journal = root / "trade_outcomes.csv"
            replay = root / "replay.jsonl"
            self._write_csv(
                journal,
                [
                    {"trade_id": "1", "symbol": "AAA", "strategy": "Breakout", "sector": "IT", "regime": "TRENDING", "prediction": "TRADE", "outcome": "WIN"},
                    {"trade_id": "2", "symbol": "BBB", "strategy": "Momentum", "sector": "BANKING", "regime": "CHOPPY", "prediction": "TRADE", "outcome": "LOSS"},
                    {"trade_id": "3", "symbol": "CCC", "strategy": "MeanRev", "sector": "AUTO", "regime": "SIDEWAYS", "prediction": "NO_TRADE", "outcome": "WIN"},
                ],
            )
            replay.parent.mkdir(parents=True, exist_ok=True)
            replay.write_text(
                json.dumps({"trade_id": "r1", "symbol": "AAA", "setup_type": "Breakout", "sector": "IT", "regime_label": "TRENDING", "outcome": "LOSS"})
                + "\n",
                encoding="utf-8",
            )
            sources = [
                ("test_journal", journal, "csv", "paper"),
                ("test_replay", replay, "jsonl", "replay"),
            ]
            with patch.object(phase40, "ARTIFACT_SOURCES", sources):
                state = phase40.build_accuracy_validation_state(previous={})

        self.assertEqual(state["closed_records_this_run"], 4)
        self.assertEqual(state["overall_accuracy"]["false_positive"], 2)
        self.assertEqual(state["overall_accuracy"]["false_negative"], 1)
        self.assertIn("BREAKOUT", state["strategy_accuracy"])
        self.assertTrue(state["advisory_only"])
        self.assertTrue(state["research_only"])
        self.assertTrue(state["shadow_mode"])
        self.assertFalse(state["affects_live_ranking"])
        self.assertFalse(state["affects_execution"])
        self.assertFalse(state["broker_mutation"])
        self.assertFalse(state["telegram_mutation"])
        self.assertFalse(state["supabase_mutation"])

    def test_phase40_and_phase41_continue_from_previous_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            journal = root / "trade_outcomes.csv"
            self._write_csv(
                journal,
                [
                    {"trade_id": "1", "symbol": "AAA", "strategy": "Breakout", "sector": "IT", "regime": "TRENDING", "prediction": "TRADE", "outcome": "WIN"},
                    {"trade_id": "2", "symbol": "BBB", "strategy": "Momentum", "sector": "BANKING", "regime": "CHOPPY", "prediction": "TRADE", "outcome": "LOSS"},
                ],
            )
            phase40_memory = root / "accuracy_validation_state.json"
            phase40_runtime = root / "accuracy_validation_status.json"
            phase40_report = root / "accuracy_validation_report.txt"
            phase41_memory = root / "meta_learning_state.json"
            phase41_runtime = root / "meta_learning_status.json"
            phase41_report = root / "meta_learning_report.txt"
            rl_memory = root / "reinforcement_learning_memory.json"
            self._write_json(rl_memory, {"records_processed": 12, "total_trades": 12})

            with patch.object(phase40, "ARTIFACT_SOURCES", [("test_journal", journal, "csv", "paper")]), patch.object(
                phase40, "MEMORY_PATH", phase40_memory
            ), patch.object(phase40, "RUNTIME_STATUS_PATH", phase40_runtime), patch.object(phase40, "REPORT_PATH", phase40_report), patch.object(
                phase41, "ACCURACY_STATE_PATH", phase40_memory
            ), patch.object(phase41, "META_STATE_PATH", phase41_memory), patch.object(
                phase41, "RUNTIME_STATUS_PATH", phase41_runtime
            ), patch.object(phase41, "REPORT_PATH", phase41_report), patch.object(
                phase41, "MEMORY_INPUTS", {"reinforcement_learning": rl_memory}
            ):
                first40 = phase40.run_accuracy_validation(write_files=True)
                first41 = phase41.run_meta_learning(accuracy_state=first40, write_files=True)
                second40 = phase40.run_accuracy_validation(write_files=True)
                second41 = phase41.run_meta_learning(accuracy_state=second40, write_files=True)

                phase_specs = {
                    "phase40_accuracy_validation": {
                        "path": phase40_runtime,
                        "fallback_path": phase40_memory,
                        "placement": "master_controller_accuracy_validation_sidecar",
                        "mode": "advisory_only",
                        "fields": ("status", "run_count", "closed_records_this_run", "new_record_ids_this_run"),
                    },
                    "phase41_meta_learning": {
                        "path": phase41_runtime,
                        "fallback_path": phase41_memory,
                        "placement": "master_controller_meta_learning_sidecar",
                        "mode": "advisory_only",
                        "fields": ("status", "run_count", "priority_count", "phase40_run_count_seen"),
                    },
                }
                with patch.object(runtime_status, "PHASE_STATUS_ARTIFACTS", phase_specs):
                    visibility = runtime_status._phase_status_summaries()
                artifacts_written = all(
                    path.exists()
                    for path in (
                        phase40_memory,
                        phase40_runtime,
                        phase40_report,
                        phase41_memory,
                        phase41_runtime,
                        phase41_report,
                    )
                )

        self.assertEqual(first40["run_count"], 1)
        self.assertEqual(second40["run_count"], 2)
        self.assertTrue(second40["continued_from_previous_state"])
        self.assertEqual(second40["previous_run_count"], 1)
        self.assertEqual(first41["run_count"], 1)
        self.assertEqual(second41["run_count"], 2)
        self.assertTrue(second41["continued_from_previous_state"])
        self.assertEqual(second41["phase40_run_count_seen"], 2)
        self.assertTrue(second41["learning_priorities"])
        self.assertFalse(second41["affects_live_ranking"])
        self.assertFalse(second41["affects_execution"])
        self.assertTrue(callable(phase40.run_accuracy_validation))
        self.assertTrue(callable(phase41.run_meta_learning))
        self.assertTrue(artifacts_written)
        self.assertTrue(visibility["phase40_accuracy_validation"]["connected"])
        self.assertTrue(visibility["phase41_meta_learning"]["connected"])
        self.assertEqual(visibility["phase40_accuracy_validation"]["values"]["run_count"], 2)
        self.assertEqual(visibility["phase41_meta_learning"]["values"]["run_count"], 2)
        self.assertEqual(visibility["phase41_meta_learning"]["values"]["phase40_run_count_seen"], 2)
        self.assertTrue(visibility["phase40_accuracy_validation"]["values"])
        self.assertTrue(visibility["phase41_meta_learning"]["values"])


if __name__ == "__main__":
    unittest.main()
