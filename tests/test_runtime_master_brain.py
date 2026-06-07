import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import runtime_master_brain


class RuntimeMasterBrainReadOnlyTests(unittest.TestCase):
    def test_missing_scanner_status_is_safe_no_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_dir = Path(temp_dir) / "data" / "runtime"
            scanner_path = runtime_dir / "scanner_status.json"
            master_path = runtime_dir / "master_brain_status.json"

            with patch.object(runtime_master_brain, "SCANNER_STATUS_PATH", scanner_path), patch.object(
                runtime_master_brain, "MASTER_BRAIN_STATUS_PATH", master_path
            ), patch.object(runtime_master_brain, "write_phase38_runtime_status"):
                payload = runtime_master_brain._run_read_only_master_brain()

            written = json.loads(master_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "READ_ONLY")
            self.assertEqual(payload["runtime_detail_status"], "MASTER_BRAIN_READ_ONLY_NO_CANDIDATES")
            self.assertEqual(written["status"], "READ_ONLY")
            self.assertEqual(written["runtime_detail_status"], "MASTER_BRAIN_READ_ONLY_NO_CANDIDATES")
            self.assertFalse(written["scanner_status_available"])
            self.assertEqual(written["scanner_status_error"], "missing_scanner_status")
            self.assertEqual(written["input_candidates"], 0)
            self.assertEqual(written["evaluated_count"], 0)
            self.assertNotEqual(written["status"], "MASTER_BRAIN_READ_ONLY_ERROR")
            self.assertTrue(written["observe_only"])
            self.assertFalse(written["trade_creation"])
            self.assertFalse(written["telegram_alerts"])
            self.assertFalse(written["supabase_writes"])
            self.assertFalse(written["journal_writes"])
            self.assertFalse(written["live_execution_enabled"])
            self.assertIn("phase38_runtime_guard", written)

    def test_invalid_scanner_status_remains_visible_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_dir = Path(temp_dir) / "data" / "runtime"
            runtime_dir.mkdir(parents=True)
            scanner_path = runtime_dir / "scanner_status.json"
            master_path = runtime_dir / "master_brain_status.json"
            scanner_path.write_text("{invalid", encoding="utf-8")

            with patch.object(runtime_master_brain, "SCANNER_STATUS_PATH", scanner_path), patch.object(
                runtime_master_brain, "MASTER_BRAIN_STATUS_PATH", master_path
            ), patch.object(runtime_master_brain, "write_phase38_runtime_status"):
                payload = runtime_master_brain._run_read_only_master_brain()

            self.assertEqual(payload["status"], "MASTER_BRAIN_READ_ONLY_ERROR")
            self.assertTrue(payload["scanner_status_available"])
            self.assertEqual(payload["scanner_status_error"], "invalid_scanner_status")
            self.assertEqual(payload["error_type"], "JSONDecodeError")

    def test_research_mode_missing_scanner_status_stays_read_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_dir = Path(temp_dir) / "data" / "runtime"
            scanner_path = runtime_dir / "scanner_status.json"
            master_path = runtime_dir / "master_brain_status.json"

            with patch.dict(os.environ, {runtime_master_brain.RUNTIME_MODE_ENV: "RESEARCH_ONLY"}), patch.object(
                runtime_master_brain, "SCANNER_STATUS_PATH", scanner_path
            ), patch.object(runtime_master_brain, "MASTER_BRAIN_STATUS_PATH", master_path), patch.object(
                runtime_master_brain, "write_phase38_runtime_status"
            ):
                payload = runtime_master_brain._run_read_only_master_brain()

            self.assertEqual(payload["runtime_mode"], "READ_ONLY")
            self.assertEqual(payload["status"], "READ_ONLY")
            self.assertEqual(payload["runtime_detail_status"], "MASTER_BRAIN_READ_ONLY_NO_CANDIDATES")
            self.assertFalse(payload["live_execution_enabled"])
            self.assertFalse(payload["telegram_enabled"])
            self.assertFalse(payload["lifecycle_mutation_enabled"])
            self.assertFalse(payload["journal_writes_enabled"])
            self.assertFalse(payload["outcome_tracking_enabled"])
            self.assertTrue(payload["phase38_runtime_guard"]["phase38_runtime_allowed"])


if __name__ == "__main__":
    unittest.main()
