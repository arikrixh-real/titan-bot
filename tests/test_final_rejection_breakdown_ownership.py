from datetime import datetime
import unittest

import runtime_scanner
from utils.market_hours import IST


class FinalRejectionBreakdownOwnershipTests(unittest.TestCase):
    def test_final_rejection_breakdown_cannot_override_final_validated_setups(self):
        final_count = runtime_scanner._resolve_final_count(
            {"final_passed": 99, "timestamp_ist": datetime.now(IST).isoformat()},
            {"final_passed": 88, "timestamp_ist": datetime.now(IST).isoformat()},
            final_validated_payload={
                "timestamp_ist": datetime.now(IST).isoformat(),
                "setups": [{"symbol": "A"}, {"symbol": "B"}],
            },
            current_entry_passed=7,
        )

        self.assertEqual(final_count["final_passed"], 2)
        self.assertEqual(final_count["entry_passed"], 7)
        self.assertEqual(final_count["final_count_source"], "runtime_scanner.final_validated_setups")

    def test_final_rejection_diagnostics_are_marked_stale_when_old(self):
        diagnostics = runtime_scanner._final_rejection_diagnostics(
            {
                "timestamp_ist": "2000-01-01T00:00:00+05:30",
                "breakdown": {"QUALITY_FAIL": 5},
                "symbols_by_reason": {"QUALITY_FAIL": ["ABC"]},
                "total_final_rejections_after_entry": 5,
                "final_passed": 123,
            }
        )

        self.assertTrue(diagnostics["diagnostic_only"])
        self.assertFalse(diagnostics["authoritative_for_final_passed"])
        self.assertFalse(diagnostics["fresh"])
        self.assertTrue(diagnostics["stale"])

        reasons, examples, rejected = runtime_scanner._setup_engine_rejections_from_debug(
            diagnostics,
            entry_passed=10,
            final_passed=1,
        )

        self.assertFalse(reasons)
        self.assertEqual(examples, {})
        self.assertIsNone(rejected)


if __name__ == "__main__":
    unittest.main()
