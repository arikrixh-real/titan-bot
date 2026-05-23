import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines import confidence_decay_memory_engine as confidence_decay
from engines import multi_timeframe_conflict_memory_engine as mtf_conflict
from engines import no_trade_refinement_memory_engine as no_trade_refinement
from engines import transition_instability_memory_engine as transition_instability


class ExperienceMaturityBatch2Tests(unittest.TestCase):
    def test_confidence_decay_memory_is_bounded_and_advisory_only(self):
        records = [
            {"symbol": "INFY", "outcome": "LOSS", "signal_age_minutes": 95, "confidence": 82, "volatility_score": 78, "setup_type": "breakout"},
            {"symbol": "TCS", "outcome": "WIN", "signal_age_minutes": 8, "confidence": 62, "volatility_score": 35, "setup_type": "pullback"},
        ]

        memory = confidence_decay.build_confidence_decay_memory(records)

        self.assertEqual(memory["source_type"], "CONFIDENCE_DECAY_MEMORY")
        self.assertTrue(memory["advisory_only"])
        self.assertFalse(memory["affects_live_execution_directly"])
        self.assertEqual(memory["rank_adjustment"], 0.0)
        self.assertEqual(memory["recommended_live_weight"], 0.0)
        self.assertFalse(memory["safety"]["ranking_changes"])
        self.assertLessEqual(memory["record_count"], confidence_decay.MAX_RECORDS)
        self.assertIn("STALE", memory["age_buckets"])

    def test_transition_instability_memory_tracks_unconfirmed_and_whipsaw(self):
        records = [
            {"from_regime": "RISK_OFF", "to_regime": "RISK_ON", "transition_confirmed": False, "transition_strength": 0.28, "outcome": "LOSS"},
            {"previous_primary": "RISK_ON", "primary": "RISK_OFF", "whipsaw": True, "outcome": "LOSS"},
            {"from_regime": "CHOPPY", "to_regime": "TREND", "transition_confirmed": True, "outcome": "WIN"},
        ]

        memory = transition_instability.build_transition_instability_memory(records)

        self.assertEqual(memory["source_type"], "TRANSITION_INSTABILITY_MEMORY")
        self.assertTrue(memory["advisory_only"])
        self.assertFalse(memory["safety"]["execution_changes"])
        self.assertIn("UNCONFIRMED", memory["instability_buckets"])
        self.assertIn("WHIPSAW", memory["instability_buckets"])
        self.assertLessEqual(len(memory["recent_transition_events"]), transition_instability.MAX_EVENTS)

    def test_multi_timeframe_conflict_memory_is_research_only(self):
        records = [
            {"symbol": "SBIN", "side": "LONG", "short_trend": "BULLISH", "medium_trend": "BEARISH", "long_trend": "BEARISH", "outcome": "LOSS"},
            {"symbol": "RELIANCE", "side": "SHORT", "short_trend": "BEARISH", "medium_trend": "BULLISH", "long_trend": "BULLISH", "outcome": "LOSS"},
            {"symbol": "TITAN", "side": "LONG", "short_trend": "BULLISH", "medium_trend": "BULLISH", "long_trend": "BULLISH", "outcome": "WIN"},
        ]

        memory = mtf_conflict.build_multi_timeframe_conflict_memory(records)

        self.assertEqual(memory["source_type"], "MULTI_TIMEFRAME_CONFLICT_MEMORY")
        self.assertTrue(memory["advisory_only"])
        self.assertFalse(memory["safety"]["strict_filter_changes"])
        self.assertFalse(memory["safety"]["multi_timeframe_engine_changes"])
        self.assertIn("HIGHER_TIMEFRAME_AGAINST_LONG", memory["conflict_buckets"])
        self.assertIn("ALIGNED", memory["conflict_buckets"])

    def test_no_trade_refinement_memory_does_not_create_gate(self):
        records = [
            {"symbol": "PNB", "outcome": "LOSS", "trade_permission": "ALLOW", "no_trade_warning": "NONE", "no_trade_score": 22, "reason": "choppy failed breakout"},
            {"symbol": "HDFCBANK", "outcome": "WIN", "trade_permission": "BLOCK", "no_trade_warning": "SKIP", "no_trade_score": 78, "reason": "blocked but later moved"},
            {"symbol": "INFY", "outcome": "LOSS", "trade_permission": "WAIT", "no_trade_warning": "WAIT", "no_trade_score": 55, "reason": "weak breadth"},
        ]

        memory = no_trade_refinement.build_no_trade_refinement_memory(records)

        self.assertEqual(memory["source_type"], "NO_TRADE_REFINEMENT_MEMORY")
        self.assertTrue(memory["advisory_only"])
        self.assertFalse(memory["safety"]["no_trade_engine_changes"])
        self.assertFalse(memory["safety"]["alert_filter_changes"])
        self.assertFalse(memory["safety"]["final_decision_changes"])
        self.assertIn("ALLOW_THEN_LOSS", memory["refinement_buckets"])
        self.assertIn("BLOCK_THEN_WIN", memory["refinement_buckets"])

    def test_batch2_refresh_writes_only_configured_memory_and_report_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_paths = {
                "confidence": (confidence_decay.MEMORY_PATH, confidence_decay.REPORT_PATH),
                "transition": (transition_instability.MEMORY_PATH, transition_instability.REPORT_PATH),
                "mtf": (mtf_conflict.MEMORY_PATH, mtf_conflict.REPORT_PATH),
                "no_trade": (no_trade_refinement.MEMORY_PATH, no_trade_refinement.REPORT_PATH),
            }
            try:
                confidence_decay.MEMORY_PATH = tmp_path / "memory" / "confidence_decay_memory.json"
                confidence_decay.REPORT_PATH = tmp_path / "reports" / "confidence_decay_memory_report.txt"
                transition_instability.MEMORY_PATH = tmp_path / "memory" / "transition_instability_memory.json"
                transition_instability.REPORT_PATH = tmp_path / "reports" / "transition_instability_memory_report.txt"
                mtf_conflict.MEMORY_PATH = tmp_path / "memory" / "multi_timeframe_conflict_memory.json"
                mtf_conflict.REPORT_PATH = tmp_path / "reports" / "multi_timeframe_conflict_memory_report.txt"
                no_trade_refinement.MEMORY_PATH = tmp_path / "memory" / "no_trade_refinement_memory.json"
                no_trade_refinement.REPORT_PATH = tmp_path / "reports" / "no_trade_refinement_memory_report.txt"

                confidence_decay.refresh_confidence_decay_memory([{"outcome": "LOSS", "signal_age_minutes": 90}])
                transition_instability.refresh_transition_instability_memory([{"from_regime": "A", "to_regime": "B", "transition_confirmed": False}])
                mtf_conflict.refresh_multi_timeframe_conflict_memory([{"side": "LONG", "medium_trend": "BEARISH", "long_trend": "BEARISH"}])
                no_trade_refinement.refresh_no_trade_refinement_memory([{"outcome": "LOSS", "trade_permission": "ALLOW"}])

                for memory_path, report_path in [
                    (confidence_decay.MEMORY_PATH, confidence_decay.REPORT_PATH),
                    (transition_instability.MEMORY_PATH, transition_instability.REPORT_PATH),
                    (mtf_conflict.MEMORY_PATH, mtf_conflict.REPORT_PATH),
                    (no_trade_refinement.MEMORY_PATH, no_trade_refinement.REPORT_PATH),
                ]:
                    self.assertTrue(memory_path.exists())
                    self.assertTrue(report_path.exists())
                    payload = json.loads(memory_path.read_text(encoding="utf-8"))
                    self.assertTrue(payload["advisory_only"])
                    self.assertFalse(payload["affects_live_execution_directly"])
            finally:
                confidence_decay.MEMORY_PATH, confidence_decay.REPORT_PATH = old_paths["confidence"]
                transition_instability.MEMORY_PATH, transition_instability.REPORT_PATH = old_paths["transition"]
                mtf_conflict.MEMORY_PATH, mtf_conflict.REPORT_PATH = old_paths["mtf"]
                no_trade_refinement.MEMORY_PATH, no_trade_refinement.REPORT_PATH = old_paths["no_trade"]

    def test_batch2_memory_engines_avoid_forbidden_imports(self):
        forbidden = {
            "requests",
            "yfinance",
            "websocket",
            "websockets",
            "supabase",
            "dashboard",
            "data.live_price",
            "scanners",
            "alerts",
            "notifications",
            "titan_master_brain.final_decision_engine",
            "titan_master_brain.alert_execution_filter",
            "titan_brain.strict_filter",
            "titan_brain.multi_timeframe_engine",
            "engines.no_trade_intelligence_engine",
            "engines.confidence_calibration_engine",
            "engines.setup_engine",
        }
        for source_path in [
            PROJECT_ROOT / "engines" / "confidence_decay_memory_engine.py",
            PROJECT_ROOT / "engines" / "transition_instability_memory_engine.py",
            PROJECT_ROOT / "engines" / "multi_timeframe_conflict_memory_engine.py",
            PROJECT_ROOT / "engines" / "no_trade_refinement_memory_engine.py",
        ]:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            self.assertTrue(forbidden.isdisjoint(imported), (source_path, imported & forbidden))


if __name__ == "__main__":
    unittest.main()
