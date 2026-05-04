"""
TITAN - Market Regime Intelligence
---------------------------------

Adjusts behavior based on market condition.
Safe during learning phase.
"""

from typing import Dict, Any


def classify_market_regime(market_status: dict) -> str:
    """
    Simple regime classification based on existing market filter output.
    """
    reason = str(market_status.get("reason", "")).lower()

    if "trend" in reason:
        return "TRENDING"
    elif "sideways" in reason or "range" in reason:
        return "SIDEWAYS"
    elif "volatile" in reason:
        return "VOLATILE"
    else:
        return "NEUTRAL"


def regime_score_adjustment(setup: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adjust score based on market regime.
    """

    result = dict(setup)

    base_score = float(result.get("score", 0))
    side = result.get("side", "LONG")
    market_status = result.get("market_status", {})

    regime = classify_market_regime(market_status)

    multiplier = 1.0

    # 🧠 Regime logic
    if regime == "TRENDING":
        # Favor trend-following trades
        multiplier = 1.05

    elif regime == "SIDEWAYS":
        # Reduce breakout confidence
        multiplier = 0.95

    elif regime == "VOLATILE":
        # Be cautious
        multiplier = 0.92

    else:
        multiplier = 1.0

    adjusted_score = base_score * multiplier

    result["regime"] = regime
    result["regime_multiplier"] = round(multiplier, 3)
    result["regime_adjusted_score"] = round(adjusted_score, 2)

    # Final override
    result["score"] = round(adjusted_score, 2)

    return result