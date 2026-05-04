"""
TITAN - Self-Adaptive Scoring Engine
-----------------------------------

Purpose:
- Adjusts setup score using Evolution memory.
- Boosts factors that historically win.
- Reduces factors that historically lose.
- Safe during learning phase.
- Does NOT send Telegram alerts.
- Does NOT change alert cap.
- Does NOT write to journal/outcome files.

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


def _reason_tags(reason: str) -> List[str]:
    reason_l = str(reason or "").lower()

    tag_map = {
        "breakout": ["breakout", "resistance break", "range break"],
        "volume": ["volume", "volume spike", "vol spike"],
        "momentum": ["momentum", "rsi", "strength"],
        "trend": ["trend", "ema", "moving average"],
        "relative_strength": ["relative strength", "rs", "stronger than market"],
        "trap_avoidance": ["trap", "fakeout", "fake breakout"],
        "compression": ["compression", "squeeze", "tight range"],
        "news": ["news", "event", "result", "earnings", "announcement"],
        "market_regime": ["market regime", "nifty", "index", "market filter"],
    }

    tags = []

    for tag, words in tag_map.items():
        if any(word in reason_l for word in words):
            tags.append(tag)

    return tags or ["general"]


def adaptive_score_adjustment(setup: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns setup with adaptive score fields added.

    Adds:
    - raw_score
    - adaptive_score
    - adaptive_multiplier
    - adaptive_tags
    - adaptive_applied

    During early learning phase, score remains mostly unchanged.
    """

    if not isinstance(setup, dict):
        return setup

    result = dict(setup)

    raw_score = _safe_float(
        result.get("base_score", result.get("score", result.get("final_score", 0))),
        0.0,
    )

    reason = str(result.get("reason", ""))
    tags = _reason_tags(reason)

    try:
        from engines.evolution_engine import get_evolution_state

        state = get_evolution_state()
    except Exception as e:
        result["raw_score"] = round(raw_score, 2)
        result["adaptive_score"] = round(raw_score, 2)
        result["adaptive_multiplier"] = 1.0
        result["adaptive_tags"] = tags
        result["adaptive_applied"] = False
        result["adaptive_error"] = str(e)
        return result

    closed_trades = int(state.get("total_closed_trades", 0) or 0)

    # Learning phase protection:
    # Before enough closed trades, don't aggressively change scores.
    if closed_trades < 10:
        multiplier = 1.0
    else:
        multiplier = _safe_float(state.get("score_boost"), 1.0)

        reason_memory = state.get("reason_memory", {}) or {}
        tag_weights = []

        for tag in tags:
            bucket = reason_memory.get(tag)
            if bucket:
                tag_weights.append(_safe_float(bucket.get("weight"), 1.0))

        if tag_weights:
            avg_tag_weight = sum(tag_weights) / len(tag_weights)
            multiplier *= avg_tag_weight

    multiplier = _clamp(multiplier, 0.80, 1.20)
    adaptive_score = _clamp(raw_score * multiplier, 0.0, 100.0)

    result["raw_score"] = round(raw_score, 2)
    result["adaptive_score"] = round(adaptive_score, 2)
    result["adaptive_multiplier"] = round(multiplier, 4)
    result["adaptive_tags"] = tags
    result["adaptive_applied"] = True

    # Main score becomes adaptive score.
    result["score"] = round(adaptive_score, 2)

    return result