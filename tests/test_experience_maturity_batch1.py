import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import advanced_regime_intelligence as regime
from engines import trap_memory_engine as trap_memory
from engines import volatility_memory_engine as volatility_memory


class ExperienceMaturityBatch1Tests(unittest.TestCase):
    def test_regime_transition_memory_is_bounded_and_advisory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_paths = (
                regime.HISTORICAL_REGIME_TRANSITION_MEMORY_PATH,
                regime.HISTORICAL_REGIME_TRANSITION_REPORT_PATH,
            )
            try:
                regime.HISTORICAL_REGIME_TRANSITION_MEMORY_PATH = tmp_path / "memory" / "historical_regime_transition_memory.json"
                regime.HISTORICAL_REGIME_TRANSITION_REPORT_PATH = tmp_path / "reports" / "historical_regime_transition_report.txt"
                active = {
                    "primary": "RISK_ON",
                    "previous_primary": "RISK_OFF",
                    "transition_detected": True,
                    "transition_confirmed": False,
                    "transition_strength": 0.42,
                }

                memory = regime.persist_regime_transition_memory(active, {})

                self.assertTrue(regime.HISTORICAL_REGIME_TRANSITION_MEMORY_PATH.exists())
                self.assertTrue(regime.HISTORICAL_REGIME_TRANSITION_REPORT_PATH.exists())
                self.assertEqual(memory["source_type"], "REGIME_TRANSITION_MEMORY")
                self.assertTrue(memory["advisory_only"])
                self.assertFalse(memory["safety"]["broker_api_changes"])
                self.assertIn("RISK_OFF->RISK_ON", memory["transition_buckets"])
                self.assertLessEqual(len(memory["recent_transitions"]), regime.MAX_TRANSITION_EVENTS)
            finally:
                (
                    regime.HISTORICAL_REGIME_TRANSITION_MEMORY_PATH,
                    regime.HISTORICAL_REGIME_TRANSITION_REPORT_PATH,
                ) = old_paths

    def test_volatility_memory_uses_existing_fields_only(self):
        records = [
            {"symbol": "INFY", "compression_score": 7, "outcome": "WIN", "score": 72, "reason": "compression breakout attempt"},
            {"symbol": "SBIN", "range_spike": 1.8, "outcome": "LOSS", "score": 64, "reason": "range expansion failed"},
            {"symbol": "TCS", "outcome": "WIN", "score": 61, "reason": "normal trend continuation"},
        ]

        memory = volatility_memory.build_volatility_memory(records)

        self.assertEqual(memory["source_type"], "VOLATILITY_EXPANSION_COMPRESSION_MEMORY")
        self.assertTrue(memory["advisory_only"])
        self.assertFalse(memory["safety"]["scanner_changes"])
        self.assertIn("COMPRESSION", memory["phase_buckets"])
        self.assertIn("EXPANSION", memory["phase_buckets"])
        self.assertIn("NORMAL", memory["phase_buckets"])

    def test_trap_memory_persists_fakeout_patterns(self):
        records = [
            {"symbol": "PNB", "outcome": "LOSS", "score": 67, "reason": "fake breakout trap avoidance failed"},
            {"symbol": "ICICIBANK", "outcome": "LOSS", "score": 71, "reason": "failed breakdown reversal bear trap"},
            {"symbol": "RELIANCE", "outcome": "WIN", "score": 82, "reason": "trend continuation"},
        ]

        memory = trap_memory.build_trap_memory(records)

        self.assertEqual(memory["source_type"], "TRAP_FAKEOUT_MEMORY")
        self.assertTrue(memory["advisory_only"])
        self.assertFalse(memory["safety"]["ranking_changes"])
        self.assertEqual(memory["matched_trap_records"], 2)
        self.assertIn("fake_breakout", memory["pattern_buckets"])
        self.assertIn("bear_trap", memory["pattern_buckets"])

    def test_new_memory_engines_avoid_forbidden_imports(self):
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
            "titan_master_brain.execution_engine",
            "titan_master_brain.input_aggregator",
            "engines.setup_engine",
        }
        for source_path in [
            PROJECT_ROOT / "engines" / "volatility_memory_engine.py",
            PROJECT_ROOT / "engines" / "trap_memory_engine.py",
        ]:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            self.assertTrue(forbidden.isdisjoint(imported), (source_path, imported & forbidden))

    def test_refresh_writes_memory_and_reports_to_configured_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_vol_paths = (volatility_memory.MEMORY_PATH, volatility_memory.REPORT_PATH)
            old_trap_paths = (trap_memory.MEMORY_PATH, trap_memory.REPORT_PATH)
            try:
                volatility_memory.MEMORY_PATH = tmp_path / "memory" / "volatility_expansion_compression_memory.json"
                volatility_memory.REPORT_PATH = tmp_path / "reports" / "volatility_memory_report.txt"
                trap_memory.MEMORY_PATH = tmp_path / "memory" / "trap_fakeout_memory.json"
                trap_memory.REPORT_PATH = tmp_path / "reports" / "trap_memory_report.txt"

                volatility_memory.refresh_volatility_memory(
                    [{"symbol": "INFY", "compression_score": 8, "outcome": "WIN", "reason": "compression"}]
                )
                trap_memory.refresh_trap_memory(
                    [{"symbol": "INFY", "outcome": "LOSS", "reason": "fakeout trap"}]
                )

                self.assertTrue(volatility_memory.MEMORY_PATH.exists())
                self.assertTrue(volatility_memory.REPORT_PATH.exists())
                self.assertTrue(trap_memory.MEMORY_PATH.exists())
                self.assertTrue(trap_memory.REPORT_PATH.exists())
                self.assertEqual(json.loads(volatility_memory.MEMORY_PATH.read_text(encoding="utf-8"))["advisory_only"], True)
                self.assertEqual(json.loads(trap_memory.MEMORY_PATH.read_text(encoding="utf-8"))["advisory_only"], True)
            finally:
                volatility_memory.MEMORY_PATH, volatility_memory.REPORT_PATH = old_vol_paths
                trap_memory.MEMORY_PATH, trap_memory.REPORT_PATH = old_trap_paths


if __name__ == "__main__":
    unittest.main()
