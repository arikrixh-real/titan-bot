"""
TITAN - Setup Reasoning Engine
Preserves full setup data for execution.
"""

from typing import List, Dict, Any


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def evaluate_single_setup(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    raw = setup if isinstance(setup, dict) else {}

    score = _safe_float(raw.get("score") or raw.get("final_score") or raw.get("rank_score"))
    rr = _safe_float(raw.get("rr") or raw.get("risk_reward"), 0.0)

    setup_context = raw.get("setup_context", {})
    if not isinstance(setup_context, dict):
        setup_context = {}

    market_context = raw.get("market_context", {})
    if not isinstance(market_context, dict):
        market_context = {}

    confirmations = int(setup_context.get("confirmations") or raw.get("confirmations") or 0)

    side = raw.get("side") or raw.get("direction")
    trend = market_context.get("trend") or raw.get("trend") or "UNKNOWN"

    reasoning = []
    strong_factors = 0

    if score >= 3:
        reasoning.append("Strong score")
        strong_factors += 1
    elif score >= 2:
        reasoning.append("Moderate score")
    else:
        reasoning.append("Weak score")

    if rr >= 2:
        reasoning.append("Good RR")
        strong_factors += 1
    else:
        reasoning.append("Low RR")

    if confirmations >= 5:
        reasoning.append("High confirmations")
        strong_factors += 1
    elif confirmations >= 3:
        reasoning.append("Moderate confirmations")
    else:
        reasoning.append("Low confirmations")

    if side == "LONG" and trend == "BULLISH":
        reasoning.append("Trend aligned LONG")
        strong_factors += 1
    elif side == "SHORT" and trend == "BEARISH":
        reasoning.append("Trend aligned SHORT")
        strong_factors += 1
    else:
        reasoning.append("Trend mismatch")

    if strong_factors >= 4:
        decision = "TRUST"
        confidence = "HIGH"
    elif strong_factors >= 2:
        decision = "DOWNGRADE"
        confidence = "MEDIUM"
    else:
        decision = "REJECT"
        confidence = "LOW"

    evaluated = {
        "symbol": raw.get("symbol") or raw.get("stock"),
        "side": side,
        "entry": raw.get("entry") or raw.get("entry_price"),
        "sl": raw.get("sl") or raw.get("stop_loss") or raw.get("stoploss"),
        "target": raw.get("target") or raw.get("tp") or raw.get("t1"),
        "rr": rr,
        "score": score,
        "decision": decision,
        "confidence": confidence,
        "reasoning": reasoning,
        "raw": raw,
    }

    for key in [
        "strategy_family",
        "strategy_family_strength",
        "meta_layer_scores",
        "meta_quality_score",
        "meta_rank_adjustment",
        "meta_adjustment_bounded",
        "meta_positive_factors",
        "meta_negative_factors",
        "meta_explanation",
        "phase5_applied",
        "phase5_blocked",
        "phase5_error",
        "probability_score",
        "probability_recommendation",
        "probability_expected_value",
        "probability_confidence",
        "probability_uncertainty",
        "probability_explanations",
        "blended_rank_score",
        "causal_primary_cause",
        "causal_confidence_score",
        "causal_event_classification",
        "causal_market_pressure",
        "causal_sector_leadership",
        "causal_delayed_effect",
        "causal_cascading_risk",
        "causal_explanations",
        "new_blended_rank_score",
    ]:
        if key in raw:
            evaluated[key] = raw.get(key)

    return evaluated


def evaluate_setups(setups: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    evaluated = []

    for setup in setups or []:
        try:
            evaluated.append(evaluate_single_setup(setup, context))
        except Exception as e:
            print(f"[Reasoning ERROR] {e}")

    return evaluated
