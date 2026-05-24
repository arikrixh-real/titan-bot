"""
Offline tests for TITAN Phase 38 test-mode guard.

These tests do not scan live markets, send Telegram alerts, write trades,
call Supabase, deploy, restart daemons, or place broker orders.
"""

from copy import deepcopy
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import phase38_test_mode_guard as phase38


class Phase38TestModeGuardTests(unittest.TestCase):
    def test_phase38_is_metadata_only_and_never_enables_live_execution(self):
        setup = {"symbol": "RELIANCE", "score": 72}
        result = phase38.apply_phase38_test_mode(setup, {"execution_mode": "dry_run"})

        self.assertTrue(result["phase38_applied"])
        self.assertTrue(result["phase38_test_mode"])
        self.assertFalse(result["phase38_live_execution_enabled"])
        self.assertEqual(result["phase38_rank_adjustment"], 0.0)
        self.assertEqual(result["score"], 72)

    def test_blocked_intents_make_dry_run_not_ready(self):
        result = phase38.evaluate_phase38_test_mode(
            {"requested_actions": ["place_order"]},
            {"requested_actions": ["vps_deploy", "telegram_send"]},
        )

        self.assertFalse(result["phase38_dry_run_ready"])
        self.assertIn("place_order", result["phase38_blocked_intents"])
        self.assertIn("vps_deploy", result["phase38_blocked_intents"])
        self.assertIn("telegram_send", result["phase38_blocked_intents"])

    def test_inputs_are_not_mutated(self):
        setup = {"symbol": "TCS", "requested_actions": ["dry_run_only"], "nested": {"a": 1}}
        context = {"execution_mode": "dry_run", "requested_actions": []}
        before = (deepcopy(setup), deepcopy(context))

        phase38.apply_phase38_test_mode(setup, context)

        self.assertEqual(setup, before[0])
        self.assertEqual(context, before[1])

    def test_invalid_inputs_fail_safe(self):
        result = phase38.evaluate_phase38_test_mode(None, None)

        self.assertTrue(result["phase38_applied"])
        self.assertTrue(result["phase38_test_mode"])
        self.assertFalse(result["phase38_live_execution_enabled"])
        self.assertTrue(result["phase38_dry_run_ready"])

    def test_protected_runtime_modes_block_live_capability(self):
        for mode in ("TEST", "RESEARCH_ONLY", "SHADOW", "PAPER"):
            with self.subTest(mode=mode):
                result = phase38.evaluate_phase38_runtime_guard(
                    {
                        "runtime_mode": mode,
                        "live_execution_enabled": True,
                        "telegram_enabled": True,
                        "broker_enabled": True,
                    }
                )

                self.assertFalse(result["phase38_runtime_allowed"])
                self.assertTrue(result["phase38_fail_closed"])

    def test_replay_cannot_run_under_live_runtime(self):
        result = phase38.evaluate_phase38_runtime_guard(
            {
                "runtime_mode": "REAL",
                "replay_active": True,
                "research_only": True,
                "live_execution_enabled": False,
                "telegram_enabled": False,
                "broker_enabled": False,
            }
        )

        self.assertFalse(result["phase38_runtime_allowed"])
        self.assertIn("REPLAY_WITH_LIVE_CAPABILITY", result["phase38_unsafe_states"])

    def test_real_runtime_without_protected_mode_is_validated_not_enabled_by_phase38(self):
        result = phase38.evaluate_phase38_runtime_guard(
            {
                "runtime_mode": "REAL",
                "live_execution_enabled": True,
                "telegram_enabled": True,
                "broker_enabled": False,
            }
        )

        self.assertTrue(result["phase38_runtime_allowed"])
        self.assertTrue(result["phase38_live_ready"])


if __name__ == "__main__":
    unittest.main()
