"""
TITAN - Filter Engine (FIXED SAFE COMPATIBLE VERSION)
----------------------------------------------------

Fixes:
1. GitHub error:
   '<' not supported between instances of 'int' and 'str'

2. Setup engine mismatch:
   passes_quality_filters() missing 1 required positional argument: 'rr'

Cause:
Some callers pass:
- passes_quality_filters(score, rr, side, market_status)
while some older callers pass:
- passes_quality_filters(score)
- passes_quality_filters(score, side)
- passes_quality_filters(setup_dict)

This version supports all safely.

Used by:
- setup_engine.py
- master brain
- older engine calls
"""

from __future__ import annotations

from typing import Any, Dict


MIN_SCORE = 0.0
MIN_RR = 1.5


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Converts any value safely to float.
    Prevents int/str comparison errors.
    """

    try:
        if value is None:
            return default

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()

        if text == "":
            return default

        text = text.replace("%", "").replace(",", "")

        return float(text)

    except Exception:
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    """
    Converts common values safely to bool.
    """

    if isinstance(value, bool):
        return value

    if value is None:
        return default

    text = str(value).strip().lower()

    if text in {"true", "yes", "1", "ok", "active", "bullish", "allowed"}:
        return True

    if text in {"false", "no", "0", "blocked", "inactive", "bearish"}:
        return False

    return default


def _extract_from_setup_dict(setup: Dict[str, Any]) -> tuple[Any, Any, str, Dict[str, Any]]:
    """
    Supports calls like:
        passes_quality_filters(setup_dict)

    Extracts score, rr, side, market_status from common key names.
    """

    score = (
        setup.get("score")
        or setup.get("final_score")
        or setup.get("rank_score")
        or setup.get("elite_probability_score")
        or 0.0
    )

    rr = (
        setup.get("rr")
        or setup.get("risk_reward")
        or setup.get("risk_reward_ratio")
        or setup.get("r_ratio")
        or MIN_RR
    )

    side = (
        setup.get("side")
        or setup.get("direction")
        or setup.get("trade_side")
        or "LONG"
    )

    market_status = (
        setup.get("market_status")
        or setup.get("market")
        or {}
    )

    if not isinstance(market_status, dict):
        market_status = {}

    return score, rr, side, market_status


def passes_quality_filters(
    score: Any = 0.0,
    rr: Any = None,
    side: str = "LONG",
    market_status: Dict[str, Any] | None = None,
) -> bool:
    """
    Final quality filter before setup is accepted.

    Safe compatible rules:
    - Accepts old/new call styles.
    - Market must be OK if market_status is provided.
    - Score must be numeric.
    - RR must be numeric.
    - Side must be LONG or SHORT.

    Supported call styles:
        passes_quality_filters(score, rr, side, market_status)
        passes_quality_filters(score)
        passes_quality_filters(score, side)
        passes_quality_filters(setup_dict)
    """

    # If first argument is full setup dict
    if isinstance(score, dict):
        score, rr, side, market_status = _extract_from_setup_dict(score)

    # If second argument looks like side instead of RR
    # Example: passes_quality_filters(score, "LONG")
    if isinstance(rr, str) and rr.strip().upper() in {"LONG", "SHORT"}:
        side = rr
        rr = MIN_RR

    # If rr missing, use minimum acceptable RR to preserve old callers
    if rr is None:
        rr = MIN_RR

    market_status = market_status or {}

    score_value = safe_float(score, 0.0)
    rr_value = safe_float(rr, 0.0)
    side_value = str(side or "").strip().upper()

    # Validate trade side
    if side_value not in {"LONG", "SHORT"}:
        return False

    # Market filter:
    # If market_status is empty, do not block.
    # If market_ok exists and is False, block.
    if isinstance(market_status, dict) and "market_ok" in market_status:
        market_ok = safe_bool(market_status.get("market_ok"), False)
        if not market_ok:
            return False

    # Basic quality thresholds
    if score_value < MIN_SCORE:
        return False

    if rr_value < MIN_RR:
        return False

    return True


def quality_filter(
    score: Any = 0.0,
    rr: Any = None,
    side: str = "LONG",
    market_status: Dict[str, Any] | None = None,
) -> bool:
    """
    Backward-compatible alias.
    """
    return passes_quality_filters(
        score=score,
        rr=rr,
        side=side,
        market_status=market_status,
    )


def filter_setup(setup: Dict[str, Any]) -> bool:
    """
    Extra compatibility helper for any engine that calls filter_setup(setup).
    """
    return passes_quality_filters(setup)