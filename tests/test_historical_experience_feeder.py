import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from research import historical_experience_feeder as feeder
from research.replay_realism_enrichment import build_replay_realism_fields
from research.semantic_replay_enrichment import build_semantic_replay_labels


def _record(symbol, year, setup, day):
    record = {
        **feeder.SAFETY_TAGS,
        "symbol": symbol,
        "date": f"{year}-01-{day:02d}",
        "signal_time": f"{year}-01-{day:02d}T00:00:00+00:00",
        "timeframe": "1440m",
        "setup_type": setup,
        "side": "LONG",
        "entry": 100.0,
        "sl": 99.0,
        "target": 102.0,
        "outcome": "WIN",
        "outcome_reason": "test",
        "pnl_points": 2.0,
        "rr": 2.0,
        "score": 70.0,
        "trend": "BULLISH",
        "volume_score": 1.5,
        "strength_score": 1.0,
        "compression_score": 2.0,
        "reason": "test",
        "lesson_learned": "test",
    }
    record["experience_hash"] = feeder.build_experience_hash(record)
    return record


class HistoricalExperienceFeederTests(unittest.TestCase):
    def test_semantic_fields_are_csv_additive(self):
        for field in [
            "semantic_labels",
            "trap_label",
            "fake_breakout_label",
            "liquidity_sweep_label",
            "regime_label",
            "volatility_state_label",
            "mtf_alignment_label",
            "gap_behavior_label",
            "panic_euphoria_label",
            "sector_rotation_label",
            "correlation_state_label",
            "news_reaction_label",
            "semantic_label_confidence",
            "semantic_label_reasons",
        ]:
            self.assertIn(field, feeder.CSV_FIELDS)

    def test_replay_realism_fields_are_csv_additive(self):
        for field in [
            "replay_realism",
            "signal_age_minutes",
            "holding_period_days",
            "session_context_label",
            "entry_timing_label",
            "exit_timing_label",
            "holding_time_label",
            "decay_risk_label",
            "replay_realism_confidence",
            "replay_realism_reasons",
        ]:
            self.assertIn(field, feeder.CSV_FIELDS)

    def test_experience_hash_includes_signal_time(self):
        first = _record("AAA", 2020, "trend_momentum_breakout", 1)
        second = dict(first)
        second["signal_time"] = "2020-01-01T12:00:00+00:00"
        second["experience_hash"] = feeder.build_experience_hash(second)

        self.assertNotEqual(first["experience_hash"], second["experience_hash"])

    def test_semantic_labels_are_not_in_experience_hash(self):
        first = _record("AAA", 2020, "trend_momentum_breakout", 1)
        second = dict(first)
        second["trap_label"] = "BULL_TRAP"
        second["semantic_labels"] = {"trap_label": "BULL_TRAP"}
        second["semantic_label_confidence"] = 0.5

        self.assertEqual(feeder.build_experience_hash(first), feeder.build_experience_hash(second))

    def test_replay_realism_fields_are_not_in_experience_hash(self):
        first = _record("AAA", 2020, "trend_momentum_breakout", 1)
        second = dict(first)
        second.update(
            {
                "replay_realism": {"advisory_only": True},
                "signal_age_minutes": 0.0,
                "holding_period_days": 3.0,
                "session_context_label": "DAILY_CANDLE_CONTEXT",
                "entry_timing_label": "MID_MOVE_ENTRY",
                "exit_timing_label": "NORMAL_EXIT",
                "holding_time_label": "SHORT_SWING",
                "decay_risk_label": "MODERATE_DECAY_RISK",
                "replay_realism_confidence": 1.0,
                "replay_realism_reasons": ["test"],
            }
        )

        self.assertEqual(feeder.build_experience_hash(first), feeder.build_experience_hash(second))

    def test_replay_realism_enrichment_uses_daily_context_and_exit_timing(self):
        history = pd.DataFrame(
            [
                {
                    "Datetime": f"2020-01-{day:02d}T00:00:00+00:00",
                    "Open": 100 + day * 0.1,
                    "High": 101 + day * 0.1,
                    "Low": 99 + day * 0.1,
                    "Close": 100 + day * 0.1,
                    "Volume": 1000,
                }
                for day in range(1, 25)
            ]
        )
        future = pd.DataFrame(
            [
                {"Datetime": "2020-01-25T00:00:00+00:00", "Open": 102, "High": 102.5, "Low": 101, "Close": 102, "Volume": 1000},
                {"Datetime": "2020-01-26T00:00:00+00:00", "Open": 102, "High": 103.5, "Low": 101, "Close": 103, "Volume": 1000},
            ]
        )
        record = _record("AAA", 2020, "trend_momentum_breakout", 24)
        record.update({"entry": 102.0, "sl": 100.0, "target": 103.0, "signal_time": "2020-01-24T00:00:00+00:00"})

        fields = build_replay_realism_fields(history, future, record)

        self.assertTrue(fields["replay_realism"]["advisory_only"])
        self.assertEqual(fields["replay_realism"]["source"], "HISTORICAL_OHLC_REPLAY")
        self.assertEqual(fields["session_context_label"], "DAILY_CANDLE_CONTEXT")
        self.assertEqual(fields["signal_age_minutes"], 0.0)
        self.assertEqual(fields["exit_timing_label"], "FAST_EXIT")
        self.assertEqual(fields["holding_period_days"], 2.0)
        self.assertEqual(fields["holding_time_label"], "SHORT_SWING")

    def test_replay_realism_marks_slow_failed_expansion_as_high_decay(self):
        history = pd.DataFrame(
            [
                {
                    "Datetime": f"2020-02-{day:02d}T00:00:00+00:00",
                    "Open": 100,
                    "High": 101,
                    "Low": 99,
                    "Close": 100 + day * 0.05,
                    "Volume": 1000,
                }
                for day in range(1, 25)
            ]
        )
        future = pd.DataFrame(
            [
                {
                    "Datetime": f"2020-03-{day:02d}T00:00:00+00:00",
                    "Open": 101,
                    "High": 101.5,
                    "Low": 100.5,
                    "Close": 100.8,
                    "Volume": 1000,
                }
                for day in range(1, 11)
            ]
        )
        record = _record("AAA", 2020, "trend_momentum_breakout", 24)
        record.update(
            {
                "entry": 101.0,
                "sl": 95.0,
                "target": 110.0,
                "outcome": "LOSS",
                "signal_time": "2020-02-24T00:00:00+00:00",
                "volatility_state_label": "EXPANSION",
            }
        )

        fields = build_replay_realism_fields(history, future, record)

        self.assertEqual(fields["exit_timing_label"], "SLOW_EXIT")
        self.assertEqual(fields["holding_time_label"], "MEDIUM_SWING")
        self.assertEqual(fields["decay_risk_label"], "HIGH_DECAY_RISK")

    def test_replay_realism_detects_intraday_context_and_signal_age(self):
        history = pd.DataFrame(
            [
                {
                    "Datetime": f"2020-01-01T{hour:02d}:{minute:02d}:00+00:00",
                    "Open": 100,
                    "High": 101,
                    "Low": 99,
                    "Close": 100 + index * 0.05,
                    "Volume": 1000,
                }
                for index, (hour, minute) in enumerate((divmod(step * 15, 60) for step in range(24)))
            ]
        )
        future = pd.DataFrame(
            [
                {"Datetime": "2020-01-01T06:00:00+00:00", "Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 1000},
            ]
        )
        record = _record("AAA", 2020, "trend_momentum_breakout", 1)
        record.update({"entry": 101.0, "sl": 99.0, "target": 102.0, "signal_time": "2020-01-01T04:15:00+00:00"})

        fields = build_replay_realism_fields(history, future, record)

        self.assertEqual(fields["session_context_label"], "INTRADAY_SESSION_CONTEXT")
        self.assertEqual(fields["signal_age_minutes"], 90.0)

    def test_replay_realism_stale_signal_age_contributes_to_decay_risk(self):
        history = pd.DataFrame(
            [
                {
                    "Datetime": f"2020-01-01T{hour:02d}:{minute:02d}:00+00:00",
                    "Open": 100,
                    "High": 101,
                    "Low": 99,
                    "Close": 100 + index * 0.02,
                    "Volume": 1000,
                }
                for index, (hour, minute) in enumerate((divmod(step * 15, 60) for step in range(28)))
            ]
        )
        future = pd.DataFrame(
            [
                {
                    "Datetime": "2020-01-01T07:00:00+00:00",
                    "Open": 101,
                    "High": 101.5,
                    "Low": 100.5,
                    "Close": 101,
                    "Volume": 1000,
                }
            ]
        )
        record = _record("AAA", 2020, "trend_momentum_breakout", 1)
        record.update(
            {
                "entry": 101.0,
                "sl": 95.0,
                "target": 110.0,
                "outcome": "LOSS",
                "signal_time": "2020-01-01T03:30:00+00:00",
            }
        )

        fields = build_replay_realism_fields(history, future, record)

        self.assertEqual(fields["signal_age_minutes"], 195.0)
        self.assertEqual(fields["decay_risk_label"], "HIGH_DECAY_RISK")

    def test_semantic_enrichment_detects_fake_breakout_and_liquidity_sweep(self):
        history = pd.DataFrame(
            [
                {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
                {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1000},
                {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 1000},
                {"Open": 102, "High": 104, "Low": 101, "Close": 103, "Volume": 1000},
                {"Open": 103, "High": 105, "Low": 102, "Close": 104, "Volume": 1000},
                {"Open": 104, "High": 106, "Low": 103, "Close": 105, "Volume": 1000},
                {"Open": 105, "High": 107, "Low": 104, "Close": 106, "Volume": 1000},
                {"Open": 106, "High": 108, "Low": 105, "Close": 107, "Volume": 1000},
                {"Open": 107, "High": 109, "Low": 106, "Close": 108, "Volume": 1000},
                {"Open": 108, "High": 112, "Low": 107, "Close": 108.5, "Volume": 1200},
            ]
        )

        labels = build_semantic_replay_labels(history, pd.DataFrame(), {"side": "LONG", "compression_score": 1})

        self.assertEqual(labels["fake_breakout_label"], "UPSIDE_FAKE_BREAKOUT")
        self.assertEqual(labels["liquidity_sweep_label"], "SWEEP_ABOVE_HIGH")
        self.assertEqual(labels["trap_label"], "BULL_TRAP")

    def test_semantic_enrichment_detects_gap_continuation_and_fade(self):
        base = [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
            {"Open": 102, "High": 104, "Low": 101, "Close": 103, "Volume": 1100},
        ]
        continuation = build_semantic_replay_labels(
            pd.DataFrame(base),
            pd.DataFrame([{"Open": 103, "High": 105, "Low": 102, "Close": 104, "Volume": 1000}]),
            {"side": "LONG", "compression_score": 1},
        )
        fade_rows = list(base)
        fade_rows[-1] = {"Open": 102, "High": 103, "Low": 99, "Close": 100, "Volume": 1100}
        fade = build_semantic_replay_labels(
            pd.DataFrame(fade_rows),
            pd.DataFrame([{"Open": 100, "High": 101, "Low": 98, "Close": 99, "Volume": 1000}]),
            {"side": "LONG", "compression_score": 1},
        )

        self.assertEqual(continuation["gap_behavior_label"], "GAP_UP_CONTINUATION")
        self.assertEqual(fade["gap_behavior_label"], "GAP_UP_FADE")

    def test_semantic_enrichment_detects_volatility_compression_and_expansion(self):
        compression = pd.DataFrame(
            [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000} for _ in range(20)]
            + [{"Open": 100, "High": 100.2, "Low": 99.8, "Close": 100, "Volume": 1000} for _ in range(5)]
        )
        expansion = pd.DataFrame(
            [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000} for _ in range(20)]
            + [{"Open": 100, "High": 104, "Low": 96, "Close": 101, "Volume": 1200} for _ in range(5)]
        )

        compressed = build_semantic_replay_labels(compression, pd.DataFrame(), {"side": "LONG", "compression_score": 1})
        expanded = build_semantic_replay_labels(expansion, pd.DataFrame(), {"side": "LONG", "compression_score": 1})

        self.assertEqual(compressed["volatility_state_label"], "COMPRESSION")
        self.assertEqual(expanded["volatility_state_label"], "EXPANSION")

    def test_semantic_enrichment_unknown_fallbacks_for_unavailable_inputs(self):
        labels = build_semantic_replay_labels(
            pd.DataFrame([{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000}]),
            pd.DataFrame(),
            {"side": "LONG"},
        )

        self.assertEqual(labels["regime_label"], "UNKNOWN")
        self.assertEqual(labels["volatility_state_label"], "UNKNOWN")
        self.assertEqual(labels["mtf_alignment_label"], "UNKNOWN")
        self.assertEqual(labels["sector_rotation_label"], "UNKNOWN")
        self.assertEqual(labels["correlation_state_label"], "UNKNOWN")
        self.assertEqual(labels["news_reaction_label"], "UNKNOWN")

    def test_parse_year_focus_ignores_bad_values(self):
        self.assertEqual(feeder.parse_year_focus("2008, bad,2020,2008"), [2008, 2020])

    def test_stratified_selection_respects_symbol_and_year_caps(self):
        old_simulate = feeder.simulate_symbol
        try:
            candidates = {
                "AAA": [
                    _record("AAA", 2008, "trend_momentum_breakout", 1),
                    _record("AAA", 2008, "compression_breakout_attempt", 2),
                    _record("AAA", 2020, "trend_continuation", 3),
                ],
                "BBB": [
                    _record("BBB", 2008, "trend_continuation", 1),
                    _record("BBB", 2020, "compression_breakout_attempt", 2),
                    _record("BBB", 2020, "trend_momentum_breakout", 3),
                ],
            }

            def fake_simulate(symbol, limit, lookahead, min_history, source_dir=None, year_focus=None):
                return candidates.get(symbol, [])[:limit]

            feeder.simulate_symbol = fake_simulate
            records, skipped = feeder._stratified_select_records(
                ["AAA", "BBB"],
                limit=4,
                lookahead=1,
                min_history=1,
                source_path=Path("."),
                emitted_hashes=set(),
                year_focus=[2008, 2020],
                max_per_symbol=2,
                max_per_year=2,
            )

            self.assertEqual(skipped, 0)
            self.assertEqual(len(records), 4)
            self.assertLessEqual(max(Counter(row["symbol"] for row in records).values()), 2)
            self.assertLessEqual(max(Counter(feeder.record_year(row) for row in records).values()), 2)
            self.assertGreaterEqual(len({row["setup_type"] for row in records}), 2)
        finally:
            feeder.simulate_symbol = old_simulate

    def test_dry_run_report_includes_sampling_options(self):
        old_simulate = feeder.simulate_symbol
        old_hashes = feeder.load_existing_hashes
        try:
            feeder.load_existing_hashes = lambda: set()
            feeder.simulate_symbol = lambda symbol, limit, lookahead, min_history, source_dir=None, year_focus=None: [
                _record(symbol, 2020, "trend_momentum_breakout", 1)
            ]

            with tempfile.TemporaryDirectory() as tmp:
                report = feeder.run_feeder(
                    symbols=["AAA", "BBB"],
                    limit=2,
                    dry_run=True,
                    source_dir=Path(tmp),
                    sampling_mode="stratified",
                    year_focus="2020",
                    max_per_symbol=1,
                    max_per_year=2,
                )

            self.assertEqual(report["status"], "DRY_RUN")
            self.assertEqual(report["sampling_mode"], "stratified")
            self.assertEqual(report["year_focus"], [2020])
            self.assertEqual(report["max_per_symbol"], 1)
            self.assertEqual(report["max_per_year"], 2)
            self.assertFalse(report["safety"]["live_mutation"])
        finally:
            feeder.simulate_symbol = old_simulate
            feeder.load_existing_hashes = old_hashes


if __name__ == "__main__":
    unittest.main()
