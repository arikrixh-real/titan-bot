"""
Focused tests for Phase 39 runtime visibility.

These tests only exercise status summarization. They do not scan markets, send
Telegram alerts, touch Supabase, mutate rankings, change execution packets, or
place broker orders.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import runtime_status


class Phase39RuntimeObservatoryTests(unittest.TestCase):
    def _patch_phase39_paths(self, root):
        runtime_dir = root / "data" / "runtime"
        import_dir = root / "data" / "experience_vault" / "imported_trade_logs"
        memory_dir = root / "data" / "memory"
        reports_dir = root / "reports"
        paths = {
            "status": runtime_dir / "historical_replay_status.json",
            "progress": runtime_dir / "historical_replay_progress.json",
            "import_report": import_dir / "historical_experience_import_report.json",
            "csv": import_dir / "historical_experience_import.csv",
            "jsonl": import_dir / "historical_experience_import.jsonl",
        }
        artifacts = {
            "adaptive_memory": {
                "path": memory_dir / "historical_adaptive_intelligence_state.json",
                "report_path": reports_dir / "historical_adaptive_intelligence_report.txt",
                "progress_key": "adaptive_memory",
            },
            "rl_shadow_refresh": {
                "path": memory_dir / "reinforcement_learning_memory.json",
                "report_path": reports_dir / "phase20_reinforcement_learning_report.txt",
                "runtime_path": runtime_dir / "reinforcement_learning_status.json",
                "progress_key": "reinforcement_learning",
            },
            "volatility_memory": {
                "path": memory_dir / "volatility_expansion_compression_memory.json",
                "report_path": reports_dir / "volatility_memory_report.txt",
            },
            "trap_memory": {
                "path": memory_dir / "trap_fakeout_memory.json",
                "report_path": reports_dir / "trap_memory_report.txt",
            },
            "confidence_decay_memory": {
                "path": memory_dir / "confidence_decay_memory.json",
                "report_path": reports_dir / "confidence_decay_memory_report.txt",
            },
            "transition_instability_memory": {
                "path": memory_dir / "transition_instability_memory.json",
                "report_path": reports_dir / "transition_instability_memory_report.txt",
            },
            "multi_timeframe_conflict_memory": {
                "path": memory_dir / "multi_timeframe_conflict_memory.json",
                "report_path": reports_dir / "multi_timeframe_conflict_memory_report.txt",
            },
            "no_trade_refinement_memory": {
                "path": memory_dir / "no_trade_refinement_memory.json",
                "report_path": reports_dir / "no_trade_refinement_memory_report.txt",
            },
        }
        return paths, artifacts

    def test_phase39_summary_uses_existing_artifacts_and_stays_non_mutating(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths, artifacts = self._patch_phase39_paths(root)
            for path in paths.values():
                path.parent.mkdir(parents=True, exist_ok=True)

            now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
            replay_time = (now - timedelta(minutes=30)).isoformat()
            paths["status"].write_text(json.dumps({"status": "COMPLETED", "timestamp_ist": replay_time}), encoding="utf-8")
            paths["progress"].write_text(
                json.dumps(
                    {
                        "status": "COMPLETED",
                        "last_completed_at_ist": replay_time,
                        "last_records_generated": 12,
                        "adaptive_memory": {"records_loaded": 12},
                        "reinforcement_learning": {"records_processed": 12},
                        "research_memory_refresh": {
                            "volatility_memory": {"record_count": 12},
                            "trap_memory": {"record_count": 12},
                        },
                    }
                ),
                encoding="utf-8",
            )
            paths["import_report"].write_text(json.dumps({"records_generated": 12}), encoding="utf-8")
            paths["csv"].write_text("symbol,score\n", encoding="utf-8")
            paths["jsonl"].write_text(
                "\n".join(
                    [
                        json.dumps({"symbol": "OLD", "score": 70}),
                        "not-json",
                        json.dumps(
                            {
                                "symbol": "AAA",
                                "replay_realism": {},
                                "semantic_labels": {},
                                "interpreted_outcome_label": "WEAK_WIN",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(runtime_status, "HISTORICAL_REPLAY_STATUS_PATH", paths["status"]), patch.object(
                runtime_status, "HISTORICAL_REPLAY_PROGRESS_PATH", paths["progress"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_REPORT_PATH", paths["import_report"]), patch.object(
                runtime_status, "HISTORICAL_EXPERIENCE_CSV_PATH", paths["csv"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_JSONL_PATH", paths["jsonl"]), patch.object(
                runtime_status, "PHASE39_MEMORY_ARTIFACTS", artifacts
            ):
                summary = runtime_status._phase39_research_memory_observatory(now)

        self.assertEqual(summary["status"], "OK")
        self.assertEqual(summary["latest_replay_record_count"], 12)
        self.assertFalse(summary["stale_replay"])
        self.assertTrue(summary["replay_realism_active"])
        self.assertTrue(summary["semantic_replay_labels_active"])
        self.assertTrue(summary["interpretation_engine_active"])
        self.assertEqual(summary["latest_jsonl_record_status"]["reason"], "ok")
        self.assertEqual(summary["latest_jsonl_record_status"]["line_number"], 3)
        self.assertTrue(summary["adaptive_memory_refreshed"])
        self.assertTrue(summary["research_memory_refresh_active"])
        self.assertTrue(summary["rl_shadow_refresh_active"])
        self.assertTrue(summary["experience_maturity_memory_engines_active"])
        safety = summary["runtime_safety_summary"]
        self.assertTrue(safety["visibility_only"])
        self.assertFalse(safety["live_rank_mutation_allowed"])
        self.assertFalse(safety["scanner_changes"])
        self.assertFalse(safety["broker_orders"])
        self.assertFalse(safety["telegram_changes"])
        self.assertFalse(safety["supabase_writes"])
        self.assertFalse(safety["execution_packet_changes"])
        self.assertFalse(safety["alert_filter_changes"])
        self.assertFalse(summary["affects_live_ranking_or_execution"])

    def test_phase39_warns_when_replay_artifacts_are_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths, artifacts = self._patch_phase39_paths(root)
            paths["progress"].parent.mkdir(parents=True, exist_ok=True)
            paths["csv"].parent.mkdir(parents=True, exist_ok=True)

            now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
            stale_time = (now - timedelta(seconds=runtime_status.PHASE39_STALE_REPLAY_SECONDS + 1)).isoformat()
            paths["progress"].write_text(
                json.dumps({"status": "COMPLETED", "last_completed_at_ist": stale_time, "last_records_generated": 0}),
                encoding="utf-8",
            )
            paths["csv"].write_text("symbol,score\n", encoding="utf-8")

            with patch.object(runtime_status, "HISTORICAL_REPLAY_STATUS_PATH", paths["status"]), patch.object(
                runtime_status, "HISTORICAL_REPLAY_PROGRESS_PATH", paths["progress"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_REPORT_PATH", paths["import_report"]), patch.object(
                runtime_status, "HISTORICAL_EXPERIENCE_CSV_PATH", paths["csv"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_JSONL_PATH", paths["jsonl"]), patch.object(
                runtime_status, "PHASE39_MEMORY_ARTIFACTS", artifacts
            ):
                summary = runtime_status._phase39_research_memory_observatory(now)

        self.assertEqual(summary["status"], "WARNING")
        self.assertTrue(summary["stale_replay"])
        self.assertIn("phase39_replay_artifacts_stale", summary["warnings"])
        self.assertFalse(summary["replay_realism_active"])
        self.assertFalse(summary["semantic_replay_labels_active"])
        self.assertFalse(summary["interpretation_engine_active"])

    def test_phase39_warns_when_jsonl_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths, artifacts = self._patch_phase39_paths(root)
            paths["progress"].parent.mkdir(parents=True, exist_ok=True)

            now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
            replay_time = (now - timedelta(minutes=30)).isoformat()
            paths["progress"].write_text(
                json.dumps({"status": "COMPLETED", "last_completed_at_ist": replay_time, "last_records_generated": 0}),
                encoding="utf-8",
            )

            with patch.object(runtime_status, "HISTORICAL_REPLAY_STATUS_PATH", paths["status"]), patch.object(
                runtime_status, "HISTORICAL_REPLAY_PROGRESS_PATH", paths["progress"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_REPORT_PATH", paths["import_report"]), patch.object(
                runtime_status, "HISTORICAL_EXPERIENCE_CSV_PATH", paths["csv"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_JSONL_PATH", paths["jsonl"]), patch.object(
                runtime_status, "PHASE39_MEMORY_ARTIFACTS", artifacts
            ):
                summary = runtime_status._phase39_research_memory_observatory(now)

        self.assertEqual(summary["status"], "WARNING")
        self.assertEqual(summary["latest_jsonl_record_status"]["reason"], "missing")
        self.assertIn("phase39_latest_jsonl_record_missing", summary["warnings"])
        self.assertFalse(summary["replay_realism_active"])
        self.assertFalse(summary["semantic_replay_labels_active"])
        self.assertFalse(summary["interpretation_engine_active"])

    def test_phase39_warns_when_jsonl_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths, artifacts = self._patch_phase39_paths(root)
            paths["progress"].parent.mkdir(parents=True, exist_ok=True)
            paths["jsonl"].parent.mkdir(parents=True, exist_ok=True)

            now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
            replay_time = (now - timedelta(minutes=30)).isoformat()
            paths["progress"].write_text(
                json.dumps({"status": "COMPLETED", "last_completed_at_ist": replay_time, "last_records_generated": 0}),
                encoding="utf-8",
            )
            paths["jsonl"].write_text("\n  \n", encoding="utf-8")

            with patch.object(runtime_status, "HISTORICAL_REPLAY_STATUS_PATH", paths["status"]), patch.object(
                runtime_status, "HISTORICAL_REPLAY_PROGRESS_PATH", paths["progress"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_REPORT_PATH", paths["import_report"]), patch.object(
                runtime_status, "HISTORICAL_EXPERIENCE_CSV_PATH", paths["csv"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_JSONL_PATH", paths["jsonl"]), patch.object(
                runtime_status, "PHASE39_MEMORY_ARTIFACTS", artifacts
            ):
                summary = runtime_status._phase39_research_memory_observatory(now)

        self.assertEqual(summary["status"], "WARNING")
        self.assertEqual(summary["latest_jsonl_record_status"]["reason"], "empty")
        self.assertIn("phase39_latest_jsonl_record_empty", summary["warnings"])
        self.assertFalse(summary["replay_realism_active"])
        self.assertFalse(summary["semantic_replay_labels_active"])
        self.assertFalse(summary["interpretation_engine_active"])

    def test_phase39_warns_when_jsonl_has_no_valid_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths, artifacts = self._patch_phase39_paths(root)
            paths["progress"].parent.mkdir(parents=True, exist_ok=True)
            paths["jsonl"].parent.mkdir(parents=True, exist_ok=True)

            now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
            replay_time = (now - timedelta(minutes=30)).isoformat()
            paths["progress"].write_text(
                json.dumps({"status": "COMPLETED", "last_completed_at_ist": replay_time, "last_records_generated": 0}),
                encoding="utf-8",
            )
            paths["jsonl"].write_text("not-json\n[]\n", encoding="utf-8")

            with patch.object(runtime_status, "HISTORICAL_REPLAY_STATUS_PATH", paths["status"]), patch.object(
                runtime_status, "HISTORICAL_REPLAY_PROGRESS_PATH", paths["progress"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_REPORT_PATH", paths["import_report"]), patch.object(
                runtime_status, "HISTORICAL_EXPERIENCE_CSV_PATH", paths["csv"]
            ), patch.object(runtime_status, "HISTORICAL_EXPERIENCE_JSONL_PATH", paths["jsonl"]), patch.object(
                runtime_status, "PHASE39_MEMORY_ARTIFACTS", artifacts
            ):
                summary = runtime_status._phase39_research_memory_observatory(now)

        self.assertEqual(summary["status"], "WARNING")
        self.assertEqual(summary["latest_jsonl_record_status"]["reason"], "no_valid_json_object")
        self.assertEqual(summary["latest_jsonl_record_status"]["invalid_line_count"], 2)
        self.assertIn("phase39_latest_jsonl_record_no_valid_json_object", summary["warnings"])
        self.assertFalse(summary["replay_realism_active"])
        self.assertFalse(summary["semantic_replay_labels_active"])
        self.assertFalse(summary["interpretation_engine_active"])


if __name__ == "__main__":
    unittest.main()
