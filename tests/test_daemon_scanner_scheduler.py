import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import titan_daemon
from utils.market_hours import IST


class DaemonScannerSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.status_path = self.root / "runtime" / "scanner_scheduler_status.json"
        self.market_time = datetime(2026, 5, 25, 10, 15, tzinfo=IST)
        self.off_hours = datetime(2026, 5, 25, 16, 15, tzinfo=IST)

    def tearDown(self):
        self.tmp.cleanup()

    def _read_status(self):
        return json.loads(self.status_path.read_text(encoding="utf-8"))

    def test_daemon_scheduler_invokes_scanner_when_enabled_in_trade_window(self):
        calls = []

        def scanner_runner():
            calls.append("scan")

        with patch.object(titan_daemon, "acquire_lock", return_value=True), patch.object(titan_daemon, "release_lock"):
            status = titan_daemon.run_scanner_scheduler_tick(
                now=self.market_time,
                scanner_runner=scanner_runner,
                status_path=self.status_path,
                scheduler_mode="TEST_DAEMON",
            )

        self.assertEqual(calls, ["scan"])
        self.assertTrue(status["scheduler_active"])
        self.assertTrue(status["scanner_invocation_enabled"])
        self.assertEqual(status["invocation_count"], 1)
        self.assertEqual(status["failed_invocation_count"], 0)
        self.assertIsNone(status["last_scanner_exception"])
        self.assertIsNone(status["last_skip_reason"])

    def test_skipped_scanner_writes_reason_when_disabled(self):
        calls = []
        with patch.dict(os.environ, {titan_daemon.SCANNER_SCHEDULER_ENABLED_ENV: "0"}):
            status = titan_daemon.run_scanner_scheduler_tick(
                now=self.market_time,
                scanner_runner=lambda: calls.append("scan"),
                status_path=self.status_path,
                scheduler_mode="TEST_DAEMON",
            )

        self.assertEqual(calls, [])
        self.assertFalse(status["scanner_invocation_enabled"])
        self.assertEqual(status["last_skip_reason"], "scanner_scheduler_disabled_by_env")

    def test_scanner_exception_captured_and_daemon_can_continue(self):
        def scanner_runner():
            raise RuntimeError("scanner failed")

        with patch.object(titan_daemon, "acquire_lock", return_value=True), \
            patch.object(titan_daemon, "release_lock"), \
            patch.object(titan_daemon, "log_runtime_error"):
            status = titan_daemon.run_scanner_scheduler_tick(
                now=self.market_time,
                scanner_runner=scanner_runner,
                status_path=self.status_path,
                scheduler_mode="TEST_DAEMON",
            )
            after = titan_daemon.run_scanner_scheduler_tick(
                now=self.market_time,
                scanner_runner=lambda: None,
                status_path=self.status_path,
                scheduler_mode="TEST_DAEMON",
                force=True,
            )

        self.assertIn("RuntimeError:scanner failed", status["last_scanner_exception"])
        self.assertEqual(status["failed_invocation_count"], 1)
        self.assertIsNone(after["last_scanner_exception"])
        self.assertEqual(after["invocation_count"], 2)

    def test_trade_window_protection_preserved_off_hours(self):
        calls = []
        status = titan_daemon.run_scanner_scheduler_tick(
            now=self.off_hours,
            scanner_runner=lambda: calls.append("scan"),
            status_path=self.status_path,
            scheduler_mode="TEST_DAEMON",
        )

        self.assertEqual(calls, [])
        self.assertFalse(status["trade_window"])
        self.assertTrue(status["research_mode"])
        self.assertEqual(status["last_skip_reason"], "outside_trade_window_standby")

    def test_locked_scanner_does_not_double_invoke_and_writes_reason(self):
        calls = []
        with patch.object(titan_daemon, "acquire_lock", return_value=False):
            status = titan_daemon.run_scanner_scheduler_tick(
                now=self.market_time,
                scanner_runner=lambda: calls.append("scan"),
                status_path=self.status_path,
                scheduler_mode="TEST_DAEMON",
            )

        self.assertEqual(calls, [])
        self.assertEqual(status["last_skip_reason"], "scanner_task_lock_active")

    def test_safety_flags_keep_mutations_disabled(self):
        status = titan_daemon.run_scanner_scheduler_tick(
            now=self.off_hours,
            scanner_runner=lambda: None,
            status_path=self.status_path,
            scheduler_mode="TEST_DAEMON",
        )
        flags = status["safety_flags"]
        self.assertFalse(flags["affects_live_ranking"])
        self.assertFalse(flags["affects_execution"])
        self.assertFalse(flags["broker_mutation"])
        self.assertFalse(flags["telegram_mutation"])
        self.assertFalse(flags["supabase_mutation"])


if __name__ == "__main__":
    unittest.main()
