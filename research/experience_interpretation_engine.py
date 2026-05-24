"""
Replay-only experience interpretation for historical experience records.

Safety contract:
- Pure OHLC/replay-derived interpretation for historical records only.
- No broker, Telegram, Supabase, dashboard, live-price, scanner, ranking, or runtime mutation.
- Defaults to UNKNOWN when replay evidence is weak or unavailable.
- Fields are advisory metadata and must not be included in experience hashes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


UNKNOWN = "UNKNOWN"

EXPERIENCE_INTERPRETATION_FIELDS = [
    "interpreted_outcome_label",
    "failure_reason_label",
    "success_reason_label",
    "behavioral_pattern_label",
    "emotional_market_proxy",
    "market_context_label",
    "conviction_quality_label",
    "reflection_summary",
    "experience_weight",
    "replay_interpretation_confidence",
    "replay_interpretation_reasons",
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "" or value == UNKNOWN:
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


def _tail_mean_range(df: Any, count: int) -> float:
    try:
        ranges = _column(df, "High") - _column(df, "Low")
        return _safe_float(ranges.tail(count).mean())
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


def _volume_ratio(history: Any) -> float:
    if _len(history) < 10:
        return 1.0
    volume = _column(history, "Volume")
    if volume is None:
        return 1.0
    try:
        latest = _safe_float(volume.iloc[-1])
        baseline = _safe_float(volume.iloc[-21:-1].mean()) or _safe_float(volume.iloc[-11:-1].mean())
        return latest / baseline if baseline > 0 else 1.0
    except Exception:
        return 1.0


def _entry_extension(history: Any, side: str) -> Tuple[float, List[str]]:
    if _len(history) < 20:
        return 0.0, ["insufficient_history_for_entry_extension"]
    close = _safe_float(_iloc(history, -1).get("Close"))
    closes = _column(history, "Close")
    avg_range = _tail_mean_range(history, 20)
    if closes is None or close <= 0 or avg_range <= 0:
        return 0.0, ["entry_extension_inputs_unavailable"]
    try:
        mean_close = _safe_float(closes.tail(20).mean())
    except Exception:
        mean_close = 0.0
    if mean_close <= 0:
        return 0.0, ["entry_extension_mean_unavailable"]
    signed_extension = (close - mean_close) / avg_range
    if side == "SHORT":
        signed_extension *= -1.0
    return signed_extension, ["entry_extension_from_rolling_mean"]


def _future_direction(future: Any, side: str, entry: float) -> Tuple[float, List[str]]:
    if _len(future) <= 0 or entry <= 0:
        return 0.0, ["future_direction_inputs_unavailable"]
    final_close = _safe_float(_iloc(future, -1).get("Close"))
    if final_close <= 0:
        return 0.0, ["future_final_close_unavailable"]
    direction = (final_close - entry) / entry
    if side == "SHORT":
        direction *= -1.0
    return direction * 100.0, ["future_direction_from_final_replay_close"]


def _is_low_confirmation(record: Dict[str, Any]) -> bool:
    score = _safe_float(record.get("score"))
    semantic_confidence = _safe_float(record.get("semantic_label_confidence"), 0.0)
    realism_confidence = _safe_float(record.get("replay_realism_confidence"), 0.0)
    return score < 55.0 or (semantic_confidence < 0.2 and realism_confidence < 0.5)


def _market_context(record: Dict[str, Any], range_ratio: float, move_20: float) -> Tuple[str, List[str]]:
    regime = str(record.get("regime_label") or UNKNOWN).upper()
    volatility = str(record.get("volatility_state_label") or UNKNOWN).upper()
    setup_type = str(record.get("setup_type") or "").lower()
    fake = str(record.get("fake_breakout_label") or UNKNOWN).upper()
    reasons: List[str] = []

    if volatility == "EXPANSION" or range_ratio >= 1.45:
        reasons.append("expanded_replay_range")
        return "VOLATILE_MARKET", reasons
    if "breakout" in setup_type or fake not in {UNKNOWN, "NONE"}:
        reasons.append("breakout_or_failed_breakout_replay_context")
        return "BREAKOUT_ENVIRONMENT", reasons
    if regime == "TRENDING" or abs(move_20) >= 5.0:
        reasons.append("directional_twenty_period_move")
        return "TRENDING_MARKET", reasons
    if regime == "MEAN_REVERTING" or volatility == "COMPRESSION" or (0 < range_ratio <= 0.85):
        reasons.append("compressed_or_mean_reverting_replay_context")
        return "CHOPPY_MARKET", reasons
    return UNKNOWN, ["market_context_evidence_not_decisive"]


def _interpreted_outcome(
    record: Dict[str, Any],
    market_context: str,
    entry_extension: float,
    future_direction: float,
) -> Tuple[str, List[str]]:
    outcome = str(record.get("outcome") or UNKNOWN).upper()
    rr = _safe_float(record.get("rr"))
    exit_label = str(record.get("exit_timing_label") or UNKNOWN).upper()
    fake = str(record.get("fake_breakout_label") or UNKNOWN).upper()
    reasons: List[str] = []

    if outcome == "WIN":
        if rr >= 1.3 and exit_label in {"FAST_EXIT", "NORMAL_EXIT"} and market_context != "CHOPPY_MARKET":
            return "CLEAN_WIN", ["winning_replay_resolved_with_confirmed_rr"]
        return "WEAK_WIN", ["winning_replay_but_confirmation_or_rr_was_limited"]

    if outcome == "LOSS":
        if fake not in {UNKNOWN, "NONE"} or entry_extension >= 1.8:
            return "AVOIDABLE_LOSS", ["loss_followed_late_or_failed_breakout_evidence"]
        if market_context == "CHOPPY_MARKET" or abs(future_direction) < 0.15:
            return "CHOP_EXIT", ["loss_in_choppy_or_directionless_replay"]
        return "CLEAN_LOSS", ["loss_without_clear_avoidable_replay_signature"]

    if outcome == "FLAT" or market_context == "CHOPPY_MARKET":
        reasons.append("flat_or_choppy_replay_resolution")
        return "CHOP_EXIT", reasons
    return UNKNOWN, ["outcome_evidence_not_decisive"]


def _failure_reason(record: Dict[str, Any], entry_extension: float, future_direction: float, range_ratio: float) -> Tuple[str, List[str]]:
    outcome = str(record.get("outcome") or UNKNOWN).upper()
    if outcome not in {"LOSS", "FLAT"}:
        return UNKNOWN, ["failure_reason_not_applicable_to_non_loss"]

    fake = str(record.get("fake_breakout_label") or UNKNOWN).upper()
    volatility = str(record.get("volatility_state_label") or UNKNOWN).upper()
    entry_label = str(record.get("entry_timing_label") or UNKNOWN).upper()
    move_5 = _safe_float(record.get("_move_5_proxy"))

    if fake not in {UNKNOWN, "NONE"}:
        return "FAKE_BREAKOUT", ["fake_breakout_label_present"]
    if entry_label in {"LATE_ENTRY", "EXTENDED_ENTRY"} or entry_extension >= 1.8:
        return "LATE_ENTRY", ["late_or_extended_entry_replay_signature"]
    if volatility == "EXPANSION" or range_ratio >= 1.6:
        return "HIGH_VOLATILITY_FAILURE", ["loss_during_expanded_volatility"]
    if future_direction <= -0.5:
        return "TREND_REVERSAL", ["future_replay_closed_against_entry_direction"]
    if abs(move_5) < 0.75:
        return "WEAK_MOMENTUM", ["weak_recent_directional_move_before_failure"]
    if _is_low_confirmation(record):
        return "LOW_CONFIRMATION", ["low_score_or_low_replay_confirmation"]
    return UNKNOWN, ["failure_reason_evidence_not_decisive"]


def _success_reason(record: Dict[str, Any], entry_extension: float, future_direction: float, range_ratio: float, volume_ratio: float) -> Tuple[str, List[str]]:
    outcome = str(record.get("outcome") or UNKNOWN).upper()
    if outcome != "WIN":
        return UNKNOWN, ["success_reason_not_applicable_to_non_win"]

    setup_type = str(record.get("setup_type") or "").lower()
    volatility = str(record.get("volatility_state_label") or UNKNOWN).upper()
    rr = _safe_float(record.get("rr"))

    if entry_extension <= 0.8 and future_direction >= 0.5:
        return "EARLY_TREND_CAPTURE", ["entry_was_not_extended_before_directional_followthrough"]
    if "breakout" in setup_type and (volume_ratio >= 1.3 or rr >= 1.5):
        return "STRONG_BREAKOUT", ["breakout_setup_confirmed_by_volume_or_rr"]
    if volatility == "EXPANSION" or range_ratio >= 1.35:
        return "VOLATILITY_EXPANSION", ["win_resolved_during_range_expansion"]
    if rr >= 1.2 and not _is_low_confirmation(record):
        return "HIGH_CONFIRMATION", ["winning_replay_had_sufficient_score_and_confirmation"]
    return "CLEAN_CONTINUATION", ["winning_replay_followed_trade_direction"]


def _behavioral_pattern(record: Dict[str, Any], interpreted: str, failure: str, success: str, entry_extension: float) -> Tuple[str, List[str]]:
    entry_label = str(record.get("entry_timing_label") or UNKNOWN).upper()
    if entry_label in {"LATE_ENTRY", "EXTENDED_ENTRY"} or entry_extension >= 1.8:
        return "CHASING", ["late_or_extended_entry_behavior_proxy"]
    if failure in {"LOW_CONFIRMATION", "WEAK_MOMENTUM"} and _safe_float(record.get("score")) >= 65.0:
        return "OVERCONFIDENCE_SETUP", ["high_score_but_replay_confirmation_was_weak"]
    if failure in {"TREND_REVERSAL", "HIGH_VOLATILITY_FAILURE"}:
        return "PANIC_REVERSAL", ["failure_occurred_during_reversal_or_high_volatility"]
    if success in {"HIGH_CONFIRMATION", "STRONG_BREAKOUT"}:
        return "PATIENT_CONFIRMATION", ["success_had_confirmation_evidence"]
    if interpreted == "CLEAN_WIN":
        return "DISCIPLINED_ENTRY", ["clean_win_without_late_entry_signature"]
    if interpreted in {"WEAK_WIN", "CHOP_EXIT", "CLEAN_LOSS"}:
        return "NEUTRAL", ["behavioral_signature_not_extreme"]
    return UNKNOWN, ["behavioral_pattern_evidence_not_decisive"]


def _emotional_proxy(record: Dict[str, Any], behavioral: str, market_context: str, failure: str) -> Tuple[str, List[str]]:
    panic_euphoria = str(record.get("panic_euphoria_label") or UNKNOWN).upper()
    trend = str(record.get("trend") or UNKNOWN).upper()
    if panic_euphoria == "PANIC" or failure == "HIGH_VOLATILITY_FAILURE":
        return "PANIC", ["panic_or_high_volatility_failure_proxy"]
    if panic_euphoria == "EUPHORIA" or behavioral == "CHASING":
        return "EUPHORIC", ["euphoria_or_chasing_proxy"]
    if "BEAR" in trend and market_context == "VOLATILE_MARKET":
        return "FEARFUL", ["bearish_volatile_replay_context"]
    if market_context == "TRENDING_MARKET":
        return "TREND_CONFIDENT", ["trending_replay_context"]
    if market_context in {"CHOPPY_MARKET", UNKNOWN}:
        return "CALM", ["no_extreme_emotional_replay_proxy"]
    return UNKNOWN, ["emotional_proxy_evidence_not_decisive"]


def _conviction_quality(record: Dict[str, Any], interpreted: str) -> Tuple[str, List[str]]:
    score = _safe_float(record.get("score"))
    semantic_confidence = _safe_float(record.get("semantic_label_confidence"), 0.0)
    realism_confidence = _safe_float(record.get("replay_realism_confidence"), 0.0)
    combined = (semantic_confidence + realism_confidence) / 2.0
    if score >= 70.0 and combined >= 0.45 and interpreted in {"CLEAN_WIN", "CLEAN_LOSS"}:
        return "HIGH_CONVICTION", ["score_and_replay_confidence_were_high"]
    if score >= 55.0 and combined >= 0.25:
        return "MEDIUM_CONVICTION", ["score_or_replay_confidence_was_moderate"]
    if score > 0:
        return "LOW_CONVICTION", ["score_or_replay_confidence_was_limited"]
    return UNKNOWN, ["conviction_inputs_unavailable"]


def _experience_weight(interpreted: str, market_context: str, conviction: str, confidence: float) -> float:
    base = {
        "CLEAN_WIN": 0.82,
        "CLEAN_LOSS": 0.72,
        "AVOIDABLE_LOSS": 0.62,
        "WEAK_WIN": 0.48,
        "CHOP_EXIT": 0.34,
        UNKNOWN: 0.2,
    }.get(interpreted, 0.2)
    if conviction == "HIGH_CONVICTION":
        base += 0.08
    elif conviction == "LOW_CONVICTION":
        base -= 0.08
    if market_context == "CHOPPY_MARKET":
        base -= 0.1
    return round(max(0.05, min(1.0, base * max(0.35, confidence))), 4)


def _reflection_summary(interpreted: str, failure: str, success: str, market_context: str) -> str:
    if interpreted in {"CLEAN_WIN", "WEAK_WIN"}:
        if success == "EARLY_TREND_CAPTURE":
            return "Early continuation entry succeeded with directional followthrough."
        if success == "STRONG_BREAKOUT":
            return "Breakout replay succeeded with confirming expansion."
        if success == "VOLATILITY_EXPANSION":
            return "Winning replay benefited from volatility expansion."
        return "Replay win had supportive but limited confirmation."
    if interpreted in {"CLEAN_LOSS", "AVOIDABLE_LOSS", "CHOP_EXIT"}:
        if failure == "LATE_ENTRY":
            return "Late extended entry failed in replay."
        if failure == "FAKE_BREAKOUT":
            return "Failed breakout replay showed trap risk."
        if failure == "HIGH_VOLATILITY_FAILURE":
            return "Setup failed during volatile replay regime."
        if market_context == "CHOPPY_MARKET":
            return "Replay outcome was noisy in choppy conditions."
        return "Replay loss lacked enough confirmation to generalize strongly."
    return "Replay evidence was insufficient for a strong interpretation."


def build_experience_interpretation_fields(history: Any, future: Any, record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build additive advisory interpretation fields for one historical replay record.

    The returned fields are intentionally independent of experience_hash.
    """

    reasons: List[str] = ["advisory_research_only_ohlc_replay"]
    side = str(record.get("side") or "").upper()
    entry = _safe_float(record.get("entry"))
    move_5 = _pct_change_from(history, 5)
    move_20 = _pct_change_from(history, 20)
    range_ratio = _range_ratio(history)
    volume_ratio = _volume_ratio(history)
    entry_extension, extension_reasons = _entry_extension(history, side)
    future_direction, future_reasons = _future_direction(future, side, entry)
    reasons.extend(extension_reasons)
    reasons.extend(future_reasons)

    working_record = dict(record)
    working_record["_move_5_proxy"] = move_5

    market_context, market_reasons = _market_context(working_record, range_ratio, move_20)
    reasons.extend(market_reasons)
    interpreted, interpreted_reasons = _interpreted_outcome(working_record, market_context, entry_extension, future_direction)
    reasons.extend(interpreted_reasons)
    failure, failure_reasons = _failure_reason(working_record, entry_extension, future_direction, range_ratio)
    reasons.extend(failure_reasons)
    success, success_reasons = _success_reason(working_record, entry_extension, future_direction, range_ratio, volume_ratio)
    reasons.extend(success_reasons)
    behavioral, behavioral_reasons = _behavioral_pattern(working_record, interpreted, failure, success, entry_extension)
    reasons.extend(behavioral_reasons)
    emotional, emotional_reasons = _emotional_proxy(working_record, behavioral, market_context, failure)
    reasons.extend(emotional_reasons)
    conviction, conviction_reasons = _conviction_quality(working_record, interpreted)
    reasons.extend(conviction_reasons)

    labels = {
        "interpreted_outcome_label": interpreted,
        "failure_reason_label": failure,
        "success_reason_label": success,
        "behavioral_pattern_label": behavioral,
        "emotional_market_proxy": emotional,
        "market_context_label": market_context,
        "conviction_quality_label": conviction,
    }
    known = sum(1 for value in labels.values() if value != UNKNOWN)
    evidence_available = 1 if _len(history) >= 20 and _len(future) > 0 else 0
    confidence = round((known / float(len(labels))) * (0.75 + 0.25 * evidence_available), 4)
    reflection = _reflection_summary(interpreted, failure, success, market_context)

    return {
        **labels,
        "reflection_summary": reflection,
        "experience_weight": _experience_weight(interpreted, market_context, conviction, confidence),
        "replay_interpretation_confidence": confidence,
        "replay_interpretation_reasons": reasons[:16],
    }
