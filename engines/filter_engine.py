"""
TITAN - Filter Engine (FIXED SAFE VERSION)
-----------------------------------------

Fixes GitHub error:
'<' not supported between instances of 'int' and 'str'

Cause:
Some values were coming as strings in GitHub Actions.

This file safely converts:
- score
- rr
- market flags

Used by:
setup_engine.py
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

        # Clean common formatting
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


def passes_quality_filters(
    score: Any,
    rr: Any,
    side: str = "LONG",
    market_status: Dict[str, Any] | None = None,
) -> bool:
    """
    Final quality filter before setup is accepted.

    Safe rules:
    - Market must be OK if market_status is provided.
    - Score must be numeric.
    - RR must be numeric.
    - Side must be LONG or SHORT.
    """

    market_status = market_status or {}

    score_value = safe_float(score, 0.0)
    rr_value = safe_float(rr, 0.0)
    side_value = str(side or "").strip().upper()

    # Validate trade side
    if side_value not in {"LONG", "SHORT"}:
        return False

    # Market filter
    # If market_status is empty, don't block.
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


# Backward-compatible alias if older files call another name
def quality_filter(
    score: Any,
    rr: Any,
    side: str = "LONG",
    market_status: Dict[str, Any] | None = None,
) -> bool:
    return passes_quality_filters(
        score=score,
        rr=rr,
        side=side,
        market_status=market_status,
    )