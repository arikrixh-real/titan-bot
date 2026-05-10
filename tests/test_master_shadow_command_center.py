"""
Offline tests for TITAN Phase 10 Master Shadow Intelligence Command Center.

These tests do not scan, call live prices, send Telegram, use broker APIs,
write Supabase state, or change rankings/final decisions.
"""

from copy import deepcopy
import ast
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import master_shadow_command_center as phase10


def sample_setups():
    return [
        {
            "symbol": "HDFCBANK",
            "side": "LONG",
            "score": 3.4,
            "rr": 2.1,
            "decision": "TRUST",
            "confidence": "HIGH",
        }
    ]


def sample_decisions():
    return {
        "action_mode": "TRADE_CANDIDATES_FOUND",
        "selected": [{"symbol": "HDFCBANK", "side": "LONG"}],
        "rejected": [],
        "summary": ["sample"],
    }


def sample_context():
    return {
        "trading_mode": "SELECTIVE",
        "risk_level": "MEDIUM",
        "setup_environment": "NORMAL_SETUP_PHASE",
    }


class MasterShadowCommandCenterTests(unittest.TestCase):
    def setUp(self):
        self.old_paths = {
            "PHASE5_MEMORY_PATH": phase10.PHASE5_MEMORY_PATH,
            "PHASE6_MEMORY_PATH": phase10.PHASE6_MEMORY_PATH,
            "PHASE7_MEMORY_PATH": phase10.PHASE7_MEMORY_PATH,
            "PHASE8_MEMORY_PATH": phase10.PHASE8_MEMORY_PATH,
            "PHASE9_MEMORY_PATH": phase10.PHASE9_MEMORY_PATH,
            "MEMORY_PATH": phase10.MEMORY_PATH,
            "REPORT_PATH": phase10.REPORT_PATH,
            "REPORT_REFRESH_SECONDS": phase10.REPORT_REFRESH_SECONDS,
            "RUNTIME_BUDGET_SECONDS": phase10.RUNTIME_BUDGET_SECONDS,
            "MAX_FILE_BYTES": phase10.MAX_FILE_BYTES,
        }

    def tearDown(self):
        for name, value in self.old_paths.items():
            setattr(phase10, name, value)

    def _point_all_memory_paths(self, tmp_path):
        phase10.PHASE5_MEMORY_PATH = tmp_path / "missing_phase5.json"
        phase10.PHASE6_MEMORY_PATH = tmp_path / "missing_phase6.json"
        phase10.PHASE7_MEMORY_PATH = tmp_path / "missing_phase7.json"
        phase10.PHASE8_MEMORY_PATH = tmp_path / "missing_phase8.json"
        phase10.PHASE9_MEMORY_PATH = tmp_path / "missing_phase9.json"
        phase10.MEMORY_PATH = tmp_path / "memory" / "master_shadow_memory.json"
        phase10.REPORT_PATH = tmp_path / "reports" / "master_shadow_command_center.txt"

    def test_missing_memory_files_return_neutral_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_all_memory_paths(tmp_path)

            result = phase10.build_master_shadow_snapshot()

            self.assertTrue(result["phase10_shadow_mode"])
            self.assertEqual(result["command_status"]["overall_state"], "NEUTRAL_OBSERVING")
            self.assertTrue(result["command_status"]["failed_open"])
            self.assertEqual(result["phase10_rank_adjustment"], 0.0)
            self.assertIn("phase5_memory_missing", result["risk_observations"]["data_quality_flags"])

    def test_corrupted_json_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_all_memory_paths(tmp_path)
            phase10.PHASE8_MEMORY_PATH = tmp_path / "phase8.json"
            phase10.PHASE8_MEMORY_PATH.write_text("{bad json", encoding="utf-8")

            result = phase10.build_master_shadow_snapshot()

            self.assertTrue(result["phase10_shadow_mode"])
            self.assertIn("phase8_memory_read_error", result["risk_observations"]["data_quality_flags"])
            self.assertIn(result["command_status"]["overall_state"], {"NEUTRAL_OBSERVING", "DEGRADED_OBSERVING"})

    def test_oversized_json_skipped_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_all_memory_paths(tmp_path)
            phase10.MAX_FILE_BYTES = 10
            phase10.PHASE9_MEMORY_PATH = tmp_path / "phase9.json"
            phase10.PHASE9_MEMORY_PATH.write_text('{"current_snapshot":{"portfolio_heat_score":80}}', encoding="utf-8")

            result = phase10.build_master_shadow_snapshot()

            self.assertIn("phase9_memory_oversized", result["risk_observations"]["data_quality_flags"])
            self.assertFalse(result["layer_freshness"]["phase9"]["available"])
            self.assertEqual(result["layer_freshness"]["phase9"]["status"], "OVERSIZED_SKIPPED")

    def test_runtime_budget_flags_work(self):
        old_reader = phase10._read_json_limited

        def slow_reader(path, layer_name):
            time.sleep(0.02)
            return {}, {"available": False, "age_seconds": None, "path": str(path), "status": "MISSING"}, []

        phase10._read_json_limited = slow_reader
        phase10.RUNTIME_BUDGET_SECONDS = 0.001
        try:
            result = phase10.build_master_shadow_snapshot()
        finally:
            phase10._read_json_limited = old_reader

        self.assertFalse(result["runtime_bounded"])
        self.assertIn("phase10_runtime_budget_exceeded", result["risk_observations"]["data_quality_flags"])

    def test_input_objects_not_mutated(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_all_memory_paths(tmp_path)
            phase10.PHASE8_MEMORY_PATH = tmp_path / "phase8.json"
            phase10.PHASE8_MEMORY_PATH.write_text(
                json.dumps(
                    {
                        "current_narrative": {
                            "narrative_type": "RISK_ON_TREND",
                            "risk_on_risk_off_state": "RISK_ON",
                            "narrative_confidence": 0.75,
                        }
                    }
                ),
                encoding="utf-8",
            )

            setups = sample_setups()
            decisions = sample_decisions()
            context = sample_context()
            before = (deepcopy(setups), deepcopy(decisions), deepcopy(context))

            phase10.build_master_shadow_snapshot(setups, decisions, context, {"phase8": "sample"})

            self.assertEqual(setups, before[0])
            self.assertEqual(decisions, before[1])
            self.assertEqual(context, before[2])

    def test_safety_block_generated_correctly(self):
        result = phase10.build_master_shadow_snapshot([], {}, {})
        safety = result["safety"]

        self.assertEqual(safety["phase10_rank_adjustment"], 0.0)
        self.assertFalse(safety["ranking_changes"])
        self.assertFalse(safety["execution_changes"])
        self.assertFalse(safety["telegram_changes"])
        self.assertFalse(safety["broker_api_changes"])
        self.assertFalse(safety["live_price_calls"])
        self.assertFalse(safety["network_calls"])
        self.assertFalse(safety["evaluated_setups_mutated"])
        self.assertFalse(safety["final_decisions_mutated"])
        self.assertFalse(safety["context_mutated"])
        self.assertTrue(safety["no_forbidden_imports_detected"])

    def test_refresh_writes_compact_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._point_all_memory_paths(tmp_path)
            phase10.REPORT_REFRESH_SECONDS = -1
            phase10.PHASE7_MEMORY_PATH = tmp_path / "phase7.json"
            phase10.PHASE7_MEMORY_PATH.write_text(
                json.dumps({"trade_lifecycle": {"T1": {"symbol": "HDFCBANK"}}}),
                encoding="utf-8",
            )

            result = phase10.refresh_master_shadow_command_center(force=True)

            self.assertTrue(result["phase10_shadow_mode"])
            self.assertTrue(phase10.MEMORY_PATH.exists())
            self.assertTrue(phase10.REPORT_PATH.exists())
            self.assertLess(phase10.REPORT_PATH.stat().st_size, 10000)

    def test_forbidden_imports_absent(self):
        source_path = PROJECT_ROOT / "engines" / "master_shadow_command_center.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        forbidden = {
            "requests",
            "yfinance",
            "websocket",
            "websockets",
            "supabase",
            "data.live_price",
            "scanners",
            "alerts",
            "notifications",
            "titan_master_brain.input_aggregator",
            "engines.setup_engine",
        }

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        self.assertTrue(forbidden.isdisjoint(imported), imported & forbidden)


if __name__ == "__main__":
    unittest.main()
