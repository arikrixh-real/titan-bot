import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard_truth
import master_brain_activation_guard as guard
import runtime_master_brain
import runtime_truth


def clean_runtime_truth():
    return {
        "summary": {
            "overall_status": "LIVE",
            "restart_blockers": [],
        },
        "components": {
            "master_brain": {"status": "LIVE"},
        },
    }


def clean_journal_truth():
    return {
        "canonical_open_trade_count": 0,
        "legacy_open_rows_warning": False,
        "restart_blocker": False,
    }


class MasterBrainActivationGuardTests(unittest.TestCase):
    def test_missing_env_cannot_enter_real(self):
        payload = guard.build_master_brain_activation_guard(
            env={},
            authoritative_truth=clean_runtime_truth(),
            journal_truth=clean_journal_truth(),
        )

        self.assertEqual(payload["effective_mode"], "READ_ONLY")
        self.assertFalse(payload["real_mode_allowed"])
        self.assertFalse(payload["can_call_broker"])

    def test_invalid_env_cannot_enter_real(self):
        payload = guard.build_master_brain_activation_guard(
            env={"TITAN_RUNTIME_MASTER_BRAIN_MODE": "LIVE"},
            authoritative_truth=clean_runtime_truth(),
            journal_truth=clean_journal_truth(),
        )

        self.assertEqual(payload["effective_mode"], "READ_ONLY")
        self.assertEqual(payload["reason"], "invalid_or_ambiguous_mode_forced_read_only")

    def test_real_requested_without_approval_becomes_real_blocked(self):
        payload = guard.build_master_brain_activation_guard(
            env={"TITAN_RUNTIME_MASTER_BRAIN_MODE": "REAL"},
            authoritative_truth=clean_runtime_truth(),
            journal_truth=clean_journal_truth(),
        )

        self.assertEqual(payload["status"], "REAL_BLOCKED")
        self.assertFalse(payload["real_mode_allowed"])
        self.assertIn("missing_real_master_brain_approval_token", payload["real_mode_blockers"])

    def test_read_only_cannot_mutate_or_execute(self):
        payload = guard.build_master_brain_activation_guard(
            env={"TITAN_RUNTIME_MASTER_BRAIN_MODE": "READ_ONLY"},
            authoritative_truth=clean_runtime_truth(),
            journal_truth=clean_journal_truth(),
        )

        self.assertFalse(payload["can_send_telegram"])
        self.assertFalse(payload["can_mutate_journal"])
        self.assertFalse(payload["can_call_broker"])
        self.assertFalse(payload["can_execute_orders"])

    def test_advisory_only_cannot_execute_orders(self):
        payload = guard.build_master_brain_activation_guard(
            env={"TITAN_RUNTIME_MASTER_BRAIN_MODE": "ADVISORY_ONLY"},
            authoritative_truth=clean_runtime_truth(),
            journal_truth=clean_journal_truth(),
        )

        self.assertEqual(payload["status"], "ADVISORY_ONLY")
        self.assertFalse(payload["can_execute_orders"])

    def test_paper_only_cannot_call_live_broker_execution(self):
        payload = guard.build_master_brain_activation_guard(
            env={"TITAN_RUNTIME_MASTER_BRAIN_MODE": "PAPER_ONLY"},
            authoritative_truth=clean_runtime_truth(),
            journal_truth=clean_journal_truth(),
        )

        self.assertEqual(payload["status"], "PAPER_ONLY")
        self.assertFalse(payload["can_call_broker"])

    def test_real_mode_requires_explicit_approval_token(self):
        env = {
            "TITAN_RUNTIME_MASTER_BRAIN_MODE": "REAL",
            "TITAN_MASTER_BRAIN_ALLOW_REAL": guard.REAL_APPROVAL_TOKEN,
            "TITAN_RUNTIME_OWNER": "VPS",
            "TITAN_MARKET_SESSION_PERMISSION": guard.MARKET_PERMISSION_TOKEN,
            "TITAN_BROKER_LIVE_EXECUTION": guard.BROKER_APPROVAL_TOKEN,
            "TITAN_TELEGRAM_ALERTS": guard.TELEGRAM_APPROVAL_TOKEN,
            "TITAN_SUPABASE_TRADE_WRITES": guard.SUPABASE_APPROVAL_TOKEN,
        }
        with patch.object(guard, "is_trade_window", return_value=True):
            payload = guard.build_master_brain_activation_guard(
                env=env,
                authoritative_truth=clean_runtime_truth(),
                journal_truth=clean_journal_truth(),
            )

        self.assertEqual(payload["status"], "LIVE")
        self.assertTrue(payload["real_mode_allowed"])
        self.assertTrue(payload["can_execute_orders"])

    def test_runtime_status_shows_real_blocked_not_active(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_dir = Path(temp_dir) / "data" / "runtime"
            master_path = runtime_dir / "master_brain_status.json"
            scanner_path = runtime_dir / "scanner_status.json"
            guard_path = runtime_dir / "master_brain_activation_guard.json"
            with patch.dict("os.environ", {"TITAN_RUNTIME_MASTER_BRAIN_MODE": "REAL"}, clear=True), patch.object(
                runtime_master_brain, "MASTER_BRAIN_STATUS_PATH", master_path
            ), patch.object(runtime_master_brain, "SCANNER_STATUS_PATH", scanner_path), patch.object(
                guard, "MASTER_BRAIN_ACTIVATION_GUARD_PATH", guard_path
            ), patch.object(runtime_master_brain, "write_phase38_runtime_status"):
                payload = runtime_master_brain.run_master_brain()

            self.assertEqual(payload["status"], "REAL_BLOCKED")
            self.assertFalse(payload["can_execute_orders"])
            self.assertTrue(master_path.exists())
            written = json.loads(master_path.read_text(encoding="utf-8"))
            self.assertEqual(written["status"], "REAL_BLOCKED")

    def test_dashboard_does_not_show_active_when_guard_blocks_real(self):
        truth = {
            "summary": {"overall_status": "LIVE", "restart_blockers": ["master_brain"]},
            "components": {
                "master_brain": {"status": "REAL_BLOCKED", "reason": "real_mode_blocked_by_activation_guard"}
            },
        }
        payload = dashboard_truth.build_dashboard_truth_consolidation(
            truth,
            {"canonical_open_trade_count": 0, "legacy_open_rows_warning": False},
        )

        self.assertEqual(payload["master_brain_display_status"], "REAL_BLOCKED")
        self.assertNotEqual(payload["master_brain_display_status"], "ACTIVE")


if __name__ == "__main__":
    unittest.main()
