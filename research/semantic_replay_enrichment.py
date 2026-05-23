"""
Replay-only semantic enrichment for historical experience records.

Safety contract:
- Pure OHLC-derived labels for historical replay records only.
- No broker, Telegram, Supabase, dashboard, live-price, scanner, or runtime mutation.
- Defaults to UNKNOWN when replay evidence is weak or unavailable.
- Labels are advisory metadata and must not be included in experience hashes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


UNKNOWN = "UNKNOWN"

LABEL_FIELDS = [
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
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _len(df: Any) -> int:
    try:
        return len(df)
    except Exception:
        return 0


def _column(df: Any, name: str) -> Any:
    try:
        return df[name]
    except Exception:
        return None


def _iloc(df: Any, index: int) -> Dict[str, Any]:
    try:
        row = df.iloc[index]
        if hasattr(row, "to_dict"):
            return row.to_dict()
        return dict(row)
    except Exception:
        return {}


def _tail_mean(df: Any, column: str, count: int, end_offset: int = 0) -> float:
    series = _column(df, column)
    if series is None:
        return 0.0
    try:
        end = len(series) - end_offset if end_offset else len(series)
        start = max(0, end - count)
        values = series.iloc[start:end]
        return _safe_float(values.mean())
    except Exception:
        return 0.0


def _max_before_last(df: Any, column: str, lookback: int = 20) -> float:
    series = _column(df, column)
    if series is None or _len(df) < 2:
        return 0.0
    try:
        start = max(0, len(series) - lookback - 1)
        return _safe_float(series.iloc[start:-1].max())
    except Exception:
        return 0.0


def _min_before_last(df: Any, column: str, lookback: int = 20) -> float:
    series = _column(df, column)
    if series is None or _len(df) < 2:
        return 0.0
    try:
        start = max(0, len(series) - lookback - 1)
        return _safe_float(series.iloc[start:-1].min())
    except Exception:
        return 0.0


def _pct_change_from(df: Any, periods: int) -> float:
    if _len(df) <= periods:
        return 0.0
    latest = _safe_float(_iloc(df, -1).get("Close"))
    earlier = _safe_float(_iloc(df, -periods - 1).get("Close"))
    if earlier <= 0:
        return 0.0
    return ((latest - earlier) / earlier) * 100.0


def _range_ratio(history: Any) -> float:
    if _len(history) < 12:
        return 0.0
    recent = _tail_mean_range(history, 5)
    baseline = _tail_mean_range(history, 30) or _tail_mean_range(history, 12)
    return recent / baseline if baseline > 0 else 0.0


def _tail_mean_range(df: Any, count: int) -> float:
    try:
        ranges = _column(df, "High") - _column(df, "Low")
        return _safe_float(ranges.tail(count).mean())
    except Exception:
        return 0.0


def _volume_ratio(history: Any) -> float:
    if _len(history) < 10:
        return 1.0
    last_volume = _safe_float(_iloc(history, -1).get("Volume"))
    average = _tail_mean(history, "Volume", 20, end_offset=1) or _tail_mean(history, "Volume", 10, end_offset=1)
    return last_volume / average if average > 0 else 1.0


def _detect_sweeps(history: Any, side: str) -> Tuple[str, str, str, List[str]]:
    if _len(history) < 10:
        return UNKNOWN, UNKNOWN, UNKNOWN, ["insufficient_history_for_sweep_labels"]

    last = _iloc(history, -1)
    close = _safe_float(last.get("Close"))
    high = _safe_float(last.get("High"))
    low = _safe_float(last.get("Low"))
    previous_high = _max_before_last(history, "High")
    previous_low = _min_before_last(history, "Low")
    reasons: List[str] = []

    upside_sweep = previous_high > 0 and high > previous_high and close <= previous_high
    downside_sweep = previous_low > 0 and low < previous_low and close >= previous_low

    fake = "NONE"
    sweep = "NONE"
    trap = "NONE"

    if upside_sweep:
        fake = "UPSIDE_FAKE_BREAKOUT"
        sweep = "SWEEP_ABOVE_HIGH"
        trap = "BULL_TRAP" if side == "LONG" else "STOP_RUN"
        reasons.append("price_swept_above_recent_high_and_closed_back_inside")
    elif downside_sweep:
        fake = "DOWNSIDE_FAKE_BREAKOUT"
        sweep = "SWEEP_BELOW_LOW"
        trap = "BEAR_TRAP" if side == "SHORT" else "STOP_RUN"
        reasons.append("price_swept_below_recent_low_and_closed_back_inside")

    return trap, fake, sweep, reasons


def _volatility_state(history: Any, compression_score: Any) -> Tuple[str, List[str]]:
    if _len(history) < 12:
        return UNKNOWN, ["insufficient_history_for_volatility_state"]

    compression = _safe_float(compression_score, -1.0)
    ratio = _range_ratio(history)
    reasons: List[str] = []

    if compression >= 5.0 or (0 < ratio <= 0.72):
        reasons.append("range_compression_detected")
        return "COMPRESSION", reasons
    if ratio >= 1.35:
        reasons.append("range_expansion_detected")
        return "EXPANSION", reasons
    if ratio > 0:
        reasons.append("range_ratio_normal")
        return "NORMAL", reasons
    return UNKNOWN, ["volatility_ratio_unavailable"]


def _gap_behavior(history: Any, future: Any) -> Tuple[str, List[str]]:
    if _len(history) < 2:
        return UNKNOWN, ["insufficient_history_for_gap_behavior"]

    last = _iloc(history, -1)
    prev = _iloc(history, -2)
    open_price = _safe_float(last.get("Open"))
    close = _safe_float(last.get("Close"))
    prev_close = _safe_float(prev.get("Close"))
    if open_price <= 0 or prev_close <= 0:
        return UNKNOWN, ["gap_prices_unavailable"]

    gap_pct = ((open_price - prev_close) / prev_close) * 100.0
    avg_range_pct = 0.0
    average_range = _tail_mean_range(history, 20)
    if prev_close > 0:
        avg_range_pct = (average_range / prev_close) * 100.0
    threshold = max(0.35, min(1.25, avg_range_pct * 0.35 if avg_range_pct else 0.35))

    if abs(gap_pct) < threshold:
        return "NO_GAP", ["no_material_gap_detected"]

    follow_close = close
    if _len(future) > 0:
        follow_close = _safe_float(_iloc(future, min(2, _len(future) - 1)).get("Close"), close)

    if gap_pct > 0:
        if follow_close >= open_price:
            return "GAP_UP_CONTINUATION", ["gap_up_held_above_open"]
        return "GAP_UP_FADE", ["gap_up_faded_after_open"]

    if follow_close <= open_price:
        return "GAP_DOWN_CONTINUATION", ["gap_down_continued_below_open"]
    return "GAP_DOWN_FADE", ["gap_down_faded_after_open"]


def _regime_label(history: Any, volatility: str) -> Tuple[str, List[str]]:
    if _len(history) < 30:
        return UNKNOWN, ["insufficient_history_for_regime_label"]

    move_20 = abs(_pct_change_from(history, 20))
    move_5 = _pct_change_from(history, 5)
    ratio = _range_ratio(history)
    volume = _volume_ratio(history)

    if volatility == "EXPANSION" and (abs(move_5) >= 3.5 or volume >= 1.8):
        return "PANIC_VOLATILITY_SPIKE", ["expansion_with_large_recent_move_or_volume"]
    if move_20 >= 5.0:
        return "TRENDING", ["material_20_period_directional_move"]
    if ratio and ratio <= 0.85 and abs(move_20) <= 3.0:
        return "MEAN_REVERTING", ["compressed_range_with_limited_directional_progress"]
    return UNKNOWN, ["regime_evidence_not_decisive"]


def _panic_euphoria(history: Any, volatility: str) -> Tuple[str, List[str]]:
    if _len(history) < 8:
        return UNKNOWN, ["insufficient_history_for_panic_euphoria"]

    move_5 = _pct_change_from(history, 5)
    volume = _volume_ratio(history)
    if volatility == "EXPANSION" and move_5 <= -4.0 and volume >= 1.3:
        return "PANIC", ["sharp_negative_move_with_expansion_and_volume"]
    if volatility == "EXPANSION" and move_5 >= 4.0 and volume >= 1.3:
        return "EUPHORIA", ["sharp_positive_move_with_expansion_and_volume"]
    return "NEUTRAL", ["no_panic_or_euphoria_replay_signature"]


def build_semantic_replay_labels(history: Any, future: Any, record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build additive semantic labels for one replay record.

    The returned fields are intentionally independent of experience_hash.
    """

    side = str(record.get("side") or "").upper()
    reasons: List[str] = []

    trap, fake, sweep, sweep_reasons = _detect_sweeps(history, side)
    reasons.extend(sweep_reasons)

    volatility, volatility_reasons = _volatility_state(history, record.get("compression_score"))
    reasons.extend(volatility_reasons)

    gap, gap_reasons = _gap_behavior(history, future)
    reasons.extend(gap_reasons)

    regime, regime_reasons = _regime_label(history, volatility)
    reasons.extend(regime_reasons)

    panic_euphoria, panic_reasons = _panic_euphoria(history, volatility)
    reasons.extend(panic_reasons)

    labels = {
        "trap_label": trap,
        "fake_breakout_label": fake,
        "liquidity_sweep_label": sweep,
        "regime_label": regime,
        "volatility_state_label": volatility,
        "mtf_alignment_label": UNKNOWN,
        "gap_behavior_label": gap,
        "panic_euphoria_label": panic_euphoria,
        "sector_rotation_label": UNKNOWN,
        "correlation_state_label": UNKNOWN,
        "news_reaction_label": UNKNOWN,
    }

    known = sum(1 for value in labels.values() if value not in {UNKNOWN, "NONE"})
    confidence = round(known / float(len(labels)), 4)

    return {
        "semantic_labels": dict(labels),
        **labels,
        "semantic_label_confidence": confidence,
        "semantic_label_reasons": reasons[:12],
    }
