"""
TITAN - Setup Pattern Intelligence Engine
----------------------------------------

Purpose:
- Detects setup pattern tags from each trade setup.
- Learns which patterns perform best from Evolution memory.
- Adds pattern confidence and pattern multiplier.
- Safe during learning phase.
- Does NOT send Telegram alerts.
- Does NOT change Telegram cap.
- Does NOT write journal/outcome files.

Used by:
setup_engine.py
"""

from __future__ import annotations

from typing import Any, Dict, List


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if text == "":
            return default
        return float(text)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def detect_setup_patterns(setup: Dict[str, Any]) -> List[str]:
    """
    Detects pattern tags from reason text + setup values.
    """

    reason = str(setup.get("reason", "")).lower()
    rr = _safe_float(setup.get("rr"), 0.0)
    score = _safe_float(setup.get("score"), 0.0)
    side = str(setup.get("side", "")).upper()

    patterns: List[str] = []

    keyword_map = {
        "breakout": ["breakout", "resistance break", "range break"],
        "volume_expansion": ["volume", "volume spike", "vol spike"],
        "momentum_continuation": ["momentum", "strong momentum", "rsi", "strength"],
        "trend_following": ["trend", "ema", "moving average"],
        "relative_strength": ["relative strength", "stronger than market"],
        "trap_safe": ["trap", "fakeout", "fake breakout"],
        "compression_break": ["compression", "squeeze", "tight range"],
        "news_backed": ["news", "event", "result", "earnings", "announcement"],
        "market_supported": ["market regime", "market filter", "nifty", "index"],
    }

    for tag, words in keyword_map.items():
        if any(word in reason for word in words):
            patterns.append(tag)

    if rr >= 2:
        patterns.append("high_rr")

    if score >= 80:
        patterns.append("high_score")

    if side == "LONG":
        patterns.append("long_setup")
    elif side == "SHORT":
        patterns.append("short_setup")

    return sorted(set(patterns)) or ["general_setup"]


def apply_pattern_intelligence(setup: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adds:
    - pattern_tags
    - pattern_multiplier
    - pattern_confidence
    - pattern_adjusted_score
    - pattern_intelligence_applied

    Learning phase:
    - multiplier remains 1.0 until enough closed trades exist.
    """

    if not isinstance(setup, dict):
        return setup

    result = dict(setup)

    patterns = detect_setup_patterns(result)
    base_score = _safe_float(
        result.get("adaptive_score", result.get("score", result.get("evolved_score", 0))),
        0.0,
    )

    try:
        from engines.evolution_engine import get_evolution_state
        state = get_evolution_state()
    except Exception as e:
        result["pattern_tags"] = patterns
        result["pattern_multiplier"] = 1.0
        result["pattern_confidence"] = 0.0
        result["pattern_adjusted_score"] = round(base_score, 2)
        result["pattern_intelligence_applied"] = False
        result["pattern_error"] = str(e)
        return result

    closed_trades = int(state.get("total_closed_trades", 0) or 0)
    reason_memory = state.get("reason_memory", {}) or {}

    if closed_trades < 10:
        multiplier = 1.0
        confidence = 0.0
    else:
        weights = []
        confidence_points = []

        # Map our pattern names to existing evolution reason memory names
        pattern_to_memory = {
            "breakout": "breakout",
            "volume_expansion": "volume",
            "momentum_continuation": "momentum",
            "trend_following": "trend",
            "relative_strength": "relative_strength",
            "trap_safe": "trap_avoidance",
            "compression_break": "compression",
            "news_backed": "news",
            "market_supported": "market_regime",
        }

        for pattern in patterns:
            memory_key = pattern_to_memory.get(pattern)
            if not memory_key:
                continue

            bucket = reason_memory.get(memory_key)
            if not bucket:
                continue

            trades = int(bucket.get("trades", 0) or 0)
            weight = _safe_float(bucket.get("weight"), 1.0)

            weights.append(weight)
            confidence_points.append(min(1.0, trades / 30.0))

        if weights:
            multiplier = sum(weights) / len(weights)
            confidence = sum(confidence_points) / len(confidence_points)
        else:
            multiplier = 1.0
            confidence = 0.0

    multiplier = _clamp(multiplier, 0.80, 1.20)
    pattern_score = _clamp(base_score * multiplier, 0.0, 100.0)

    result["pattern_tags"] = patterns
    result["pattern_multiplier"] = round(multiplier, 4)
    result["pattern_confidence"] = round(confidence, 4)
    result["pattern_adjusted_score"] = round(pattern_score, 2)
    result["pattern_intelligence_applied"] = True

    # Final main score becomes pattern-adjusted score.
    result["score"] = round(pattern_score, 2)

    return result