"""
Replay-only realism enrichment for historical experience records.

Safety contract:
- Pure OHLC-derived labels for historical replay records only.
- No broker, Telegram, Supabase, dashboard, live-price, scanner, ranking, or runtime mutation.
- Defaults to UNKNOWN when replay evidence is weak or unavailable.
- Fields are advisory metadata and must not be included in experience hashes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


UNKNOWN = "UNKNOWN"

REPLAY_REALISM_FIELDS = [
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


def _iloc(df: Any, index: int) -> Dict[str, Any]:
    try:
        row = df.iloc[index]
        if hasattr(row, "to_dict"):
            return row.to_dict()
        return dict(row)
    except Exception:
        return {}


def _column(df: Any, name: str) -> Any:
    try:
        return df[name]
    except Exception:
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime()
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _range_average(df: Any, count: int) -> float:
    try:
        ranges = _column(df, "High") - _column(df, "Low")
        return _safe_float(ranges.tail(count).mean())
    except Exception:
        return 0.0


def _close_mean(df: Any, count: int) -> float:
    series = _column(df, "Close")
    if series is None:
        return 0.0
    try:
        return _safe_float(series.tail(count).mean())
    except Exception:
        return 0.0


def _session_context_label(history: Any) -> Tuple[str, List[str]]:
    if _len(history) < 2:
        return UNKNOWN, ["insufficient_history_for_session_context"]

    latest = _iloc(history, -1)
    stamp = _parse_datetime(latest.get("Datetime"))
    if stamp is None:
        return UNKNOWN, ["signal_timestamp_unavailable_for_session_context"]

    return "DAILY_CANDLE_CONTEXT", ["historical_feeder_uses_daily_or_coarse_cached_candles"]


def _entry_timing_label(history: Any, side: str) -> Tuple[str, List[str]]:
    if _len(history) < 20:
        return UNKNOWN, ["insufficient_history_for_entry_timing"]

    latest = _iloc(history, -1)
    close = _safe_float(latest.get("Close"))
    mean_close = _close_mean(history, 20)
    avg_range = _range_average(history, 20)
    if close <= 0 or mean_close <= 0 or avg_range <= 0:
        return UNKNOWN, ["entry_timing_inputs_unavailable"]

    extension = abs(close - mean_close) / avg_range
    direction_ok = (side == "LONG" and close >= mean_close) or (side == "SHORT" and close <= mean_close)

    if extension >= 3.0:
        return "EXTENDED_ENTRY", ["close_extended_more_than_three_average_ranges_from_rolling_mean"]
    if extension >= 1.8 and direction_ok:
        return "LATE_ENTRY", ["close_extended_in_trade_direction_from_rolling_mean"]
    if extension >= 0.75:
        return "MID_MOVE_ENTRY", ["close_moderately_displaced_from_rolling_mean"]
    return "EARLY_ENTRY", ["close_near_rolling_mean_at_signal"]


def _resolve_exit_index(future: Any, record: Dict[str, Any]) -> Tuple[Optional[int], str, List[str]]:
    if _len(future) <= 0:
        return None, UNKNOWN, ["future_candles_unavailable_for_exit_timing"]

    side = str(record.get("side") or "").upper()
    entry = _safe_float(record.get("entry"))
    sl = _safe_float(record.get("sl"))
    target = _safe_float(record.get("target"))
    if side not in {"LONG", "SHORT"} or entry <= 0 or sl <= 0 or target <= 0:
        return None, UNKNOWN, ["trade_level_inputs_unavailable_for_exit_timing"]

    for index in range(_len(future)):
        candle = _iloc(future, index)
        high = _safe_float(candle.get("High"))
        low = _safe_float(candle.get("Low"))
        if side == "LONG":
            stopped = low <= sl
            targeted = high >= target
        else:
            stopped = high >= sl
            targeted = low <= target
        if stopped or targeted:
            candle_number = index + 1
            if candle_number <= 2:
                return index, "FAST_EXIT", ["tp_or_sl_resolved_within_two_future_candles"]
            if candle_number <= 8:
                return index, "NORMAL_EXIT", ["tp_or_sl_resolved_within_normal_replay_window"]
            return index, "SLOW_EXIT", ["tp_or_sl_resolved_late_in_replay_window"]

    return _len(future) - 1, "SLOW_EXIT", ["tp_or_sl_not_touched_marked_by_final_lookahead_close"]


def _holding_period_days(history: Any, future: Any, record: Dict[str, Any], exit_index: Optional[int]) -> Tuple[Optional[float], List[str]]:
    signal_time = _parse_datetime(record.get("signal_time"))
    if signal_time is None and _len(history) > 0:
        signal_time = _parse_datetime(_iloc(history, -1).get("Datetime"))
    if signal_time is None:
        return None, ["signal_time_unavailable_for_holding_period"]

    if exit_index is None or _len(future) <= 0:
        return None, ["exit_time_unavailable_for_holding_period"]

    exit_time = _parse_datetime(_iloc(future, exit_index).get("Datetime"))
    if exit_time is None:
        return None, ["exit_timestamp_unavailable_for_holding_period"]

    seconds = max(0.0, (exit_time - signal_time).total_seconds())
    return round(seconds / 86400.0, 4), ["holding_period_derived_from_signal_and_replay_exit_timestamps"]


def _holding_time_label(days: Optional[float]) -> Tuple[str, List[str]]:
    if days is None:
        return UNKNOWN, ["holding_period_unavailable_for_holding_time_label"]
    if days < 1.0:
        return "INTRADAY_SIMULATED", ["holding_period_less_than_one_day"]
    if days <= 5.0:
        return "SHORT_SWING", ["holding_period_up_to_five_days"]
    if days <= 20.0:
        return "MEDIUM_SWING", ["holding_period_up_to_twenty_days"]
    return "LONG_HOLD", ["holding_period_above_twenty_days"]


def _decay_risk_label(holding_days: Optional[float], volatility: str, outcome: str, exit_label: str) -> Tuple[str, List[str]]:
    if holding_days is None:
        return UNKNOWN, ["holding_period_unavailable_for_decay_risk"]

    outcome = str(outcome or "").upper()
    volatility = str(volatility or UNKNOWN).upper()
    reasons: List[str] = []
    risk_score = 0

    if holding_days > 8:
        risk_score += 2
        reasons.append("holding_period_above_eight_days")
    elif holding_days > 3:
        risk_score += 1
        reasons.append("holding_period_above_three_days")
    else:
        reasons.append("short_holding_period")

    if volatility == "EXPANSION":
        risk_score += 1
        reasons.append("expansion_volatility_state")
    elif volatility == "COMPRESSION":
        reasons.append("compression_volatility_state")

    if outcome in {"LOSS", "FLAT", "NO_FOLLOWUP", "INVALID_LEVELS"} and exit_label == "SLOW_EXIT":
        risk_score += 2
        reasons.append("setup_failed_after_delayed_exit")
    elif outcome == "LOSS":
        risk_score += 1
        reasons.append("setup_failed_in_replay")

    if risk_score >= 3:
        return "HIGH_DECAY_RISK", reasons
    if risk_score >= 1:
        return "MODERATE_DECAY_RISK", reasons
    return "LOW_DECAY_RISK", reasons


def build_replay_realism_fields(history: Any, future: Any, record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build additive advisory replay realism fields for one historical replay record.

    The returned fields are intentionally independent of experience_hash.
    """

    reasons: List[str] = ["advisory_research_only_ohlc_replay"]
    side = str(record.get("side") or "").upper()

    session_label, session_reasons = _session_context_label(history)
    reasons.extend(session_reasons)

    entry_label, entry_reasons = _entry_timing_label(history, side)
    reasons.extend(entry_reasons)

    exit_index, exit_label, exit_reasons = _resolve_exit_index(future, record)
    reasons.extend(exit_reasons)

    holding_days, holding_reasons = _holding_period_days(history, future, record, exit_index)
    reasons.extend(holding_reasons)

    holding_label, holding_label_reasons = _holding_time_label(holding_days)
    reasons.extend(holding_label_reasons)

    decay_label, decay_reasons = _decay_risk_label(
        holding_days,
        str(record.get("volatility_state_label") or UNKNOWN),
        str(record.get("outcome") or UNKNOWN),
        exit_label,
    )
    reasons.extend(decay_reasons)

    labels = {
        "session_context_label": session_label,
        "entry_timing_label": entry_label,
        "exit_timing_label": exit_label,
        "holding_time_label": holding_label,
        "decay_risk_label": decay_label,
    }
    known = sum(1 for value in labels.values() if value != UNKNOWN)
    confidence = round(known / float(len(labels)), 4)

    replay_realism = {
        "advisory_only": True,
        "research_only": True,
        "source": "HISTORICAL_OHLC_REPLAY",
        "labels": dict(labels),
    }

    return {
        "replay_realism": replay_realism,
        "signal_age_minutes": 0.0,
        "holding_period_days": holding_days if holding_days is not None else UNKNOWN,
        **labels,
        "replay_realism_confidence": confidence,
        "replay_realism_reasons": reasons[:14],
    }
