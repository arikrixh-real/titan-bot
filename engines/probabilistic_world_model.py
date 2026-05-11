"""
TITAN Phase 15 Step 1 - Probabilistic World Model Engine
--------------------------------------------------------

Standalone probability model for explaining setup quality in terms of odds.
This module does not alter scanning, dashboard, Telegram, or execution flow.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        result = int(float(value))
        return result
    except Exception:
        return default


def clamp(value: Any, min_value: float = 0.0, max_value: float = 1.0) -> float:
    value = safe_float(value, min_value)
    low = safe_float(min_value, 0.0)
    high = safe_float(max_value, 1.0)

    if low > high:
        low, high = high, low

    return max(low, min(high, value))


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get_number(data: Dict[str, Any], keys: Iterable[str], default: float = 0.0) -> float:
    for key in keys:
        if key in data:
            return safe_float(data.get(key), default)
    return default


def _get_text(data: Dict[str, Any], key: str, default: str = "") -> str:
    try:
        value = data.get(key, default)
        return str(value or default).strip()
    except Exception:
        return default


def _normal_score(value: Any, default: float = 50.0) -> float:
    value = safe_float(value, default)
    if value <= 1.0:
        return clamp(value) * 100.0
    return clamp(value, 0.0, 100.0)


def _prob_from_score(value: Any, default: float = 50.0) -> float:
    return clamp(_normal_score(value, default) / 100.0)


def _regime_bias(context: Dict[str, Any]) -> float:
    regime = _get_text(context, "market_regime", "neutral").lower()

    if any(word in regime for word in ["bull", "uptrend", "risk_on", "trending_up"]):
        return 0.70
    if any(word in regime for word in ["bear", "downtrend", "risk_off", "trending_down"]):
        return 0.30
    if any(word in regime for word in ["side", "range", "chop", "flat"]):
        return 0.42
    return 0.50


def _regime_alignment(setup: Dict[str, Any], context: Dict[str, Any]) -> float:
    side = _get_text(setup, "side", "").lower()
    bias = _regime_bias(context)

    if side in {"short", "sell"}:
        return 1.0 - bias
    if side in {"long", "buy"}:
        return bias
    return 0.50


def _volatility_risk(context: Dict[str, Any]) -> float:
    volatility = _prob_from_score(context.get("volatility"), 50.0)
    vix = _get_number(context, ["vix"], 18.0)
    vix_risk = clamp((vix - 12.0) / 28.0)
    return clamp((volatility * 0.55) + (vix_risk * 0.45))


def _rr_score(setup: Dict[str, Any]) -> float:
    rr = _get_number(setup, ["rr"], 0.0)
    if rr > 0:
        return clamp(rr / 3.0)

    entry = _get_number(setup, ["entry"], 0.0)
    stop = _get_number(setup, ["stop_loss", "sl"], 0.0)
    target = _get_number(setup, ["target", "tp"], 0.0)
    risk = abs(entry - stop)
    reward = abs(target - entry)

    if risk <= 0 or reward <= 0:
        return 0.50

    return clamp((reward / risk) / 3.0)


def _setup_quality(setup: Dict[str, Any], context: Dict[str, Any]) -> float:
    momentum = _prob_from_score(setup.get("momentum_score"), 50.0)
    trend = _prob_from_score(setup.get("trend_score"), 50.0)
    structure = _prob_from_score(setup.get("structure_score"), 50.0)
    volume = _prob_from_score(setup.get("volume_score"), 50.0)
    relative_strength = _prob_from_score(setup.get("relative_strength"), 50.0)
    setup_score = _prob_from_score(setup.get("score"), 50.0)
    sector = _prob_from_score(context.get("sector_strength"), 50.0)
    breadth = _prob_from_score(context.get("breadth"), 50.0)
    regime = _regime_alignment(setup, context)
    rr = _rr_score(setup)

    return clamp(
        (momentum * 0.17)
        + (trend * 0.13)
        + (structure * 0.15)
        + (volume * 0.10)
        + (relative_strength * 0.12)
        + (setup_score * 0.10)
        + (sector * 0.08)
        + (breadth * 0.06)
        + (regime * 0.05)
        + (rr * 0.04)
    )


def calculate_regime_continuation_probability(context: Any) -> float:
    context = _safe_dict(context)
    trend_strength = _prob_from_score(context.get("trend_strength"), 50.0)
    breadth = _prob_from_score(context.get("breadth"), 50.0)
    sentiment = _prob_from_score(context.get("market_sentiment"), 50.0)
    index_strength = _prob_from_score(context.get("index_strength"), 50.0)
    volatility_risk = _volatility_risk(context)
    sideways_penalty = 0.12 if "side" in _get_text(context, "market_regime").lower() else 0.0

    probability = (
        0.20
        + (trend_strength * 0.28)
        + (breadth * 0.18)
        + (sentiment * 0.14)
        + (index_strength * 0.14)
        - (volatility_risk * 0.12)
        - sideways_penalty
    )
    return clamp(probability)


def calculate_regime_transition_probability(context: Any) -> float:
    context = _safe_dict(context)
    trend_strength = _prob_from_score(context.get("trend_strength"), 50.0)
    breadth = _prob_from_score(context.get("breadth"), 50.0)
    sentiment = _prob_from_score(context.get("market_sentiment"), 50.0)
    volatility_risk = _volatility_risk(context)
    sideways_bonus = 0.10 if "side" in _get_text(context, "market_regime").lower() else 0.0

    weakness = (1.0 - trend_strength) * 0.25 + (1.0 - breadth) * 0.22
    contradiction = abs(sentiment - trend_strength) * 0.18
    probability = 0.15 + weakness + contradiction + (volatility_risk * 0.20) + sideways_bonus
    return clamp(probability)


def calculate_setup_survival_probability(setup: Any, context: Any) -> float:
    setup = _safe_dict(setup)
    context = _safe_dict(context)
    quality = _setup_quality(setup, context)
    volatility_risk = _volatility_risk(context)
    poor_structure = 1.0 - _prob_from_score(setup.get("structure_score"), 50.0)

    probability = (quality * 0.76) + ((1.0 - volatility_risk) * 0.16) - (poor_structure * 0.08)
    return clamp(probability)


def calculate_tp_before_sl_probability(setup: Any, context: Any) -> float:
    setup = _safe_dict(setup)
    context = _safe_dict(context)
    quality = _setup_quality(setup, context)
    rr = _rr_score(setup)
    continuation = calculate_regime_continuation_probability(context)
    false_breakout = calculate_false_breakout_probability(setup, context)
    momentum_decay = calculate_momentum_decay_probability(setup, context)

    probability = (
        (quality * 0.45)
        + (rr * 0.16)
        + (continuation * 0.18)
        + ((1.0 - false_breakout) * 0.12)
        + ((1.0 - momentum_decay) * 0.09)
    )
    return clamp(probability)


def calculate_false_breakout_probability(setup: Any, context: Any) -> float:
    setup = _safe_dict(setup)
    context = _safe_dict(context)
    volume = _prob_from_score(setup.get("volume_score"), 50.0)
    structure = _prob_from_score(setup.get("structure_score"), 50.0)
    breadth = _prob_from_score(context.get("breadth"), 50.0)
    volatility_risk = _volatility_risk(context)
    regime_alignment = _regime_alignment(setup, context)

    probability = (
        0.12
        + ((1.0 - volume) * 0.24)
        + ((1.0 - structure) * 0.22)
        + ((1.0 - breadth) * 0.15)
        + (volatility_risk * 0.17)
        + ((1.0 - regime_alignment) * 0.10)
    )
    return clamp(probability)


def calculate_momentum_decay_probability(setup: Any, context: Any) -> float:
    setup = _safe_dict(setup)
    context = _safe_dict(context)
    momentum = _prob_from_score(setup.get("momentum_score"), 50.0)
    trend = _prob_from_score(setup.get("trend_score"), 50.0)
    relative_strength = _prob_from_score(setup.get("relative_strength"), 50.0)
    volatility_risk = _volatility_risk(context)
    breadth = _prob_from_score(context.get("breadth"), 50.0)

    probability = (
        0.10
        + ((1.0 - momentum) * 0.32)
        + ((1.0 - trend) * 0.18)
        + ((1.0 - relative_strength) * 0.18)
        + (volatility_risk * 0.12)
        + ((1.0 - breadth) * 0.10)
    )
    return clamp(probability)


def calculate_volatility_expansion_probability(setup: Any, context: Any) -> float:
    setup = _safe_dict(setup)
    context = _safe_dict(context)
    current_volatility = _prob_from_score(context.get("volatility"), 50.0)
    vix_risk = clamp((_get_number(context, ["vix"], 18.0) - 12.0) / 28.0)
    weak_structure = 1.0 - _prob_from_score(setup.get("structure_score"), 50.0)
    transition = calculate_regime_transition_probability(context)

    probability = (
        0.08
        + (current_volatility * 0.30)
        + (vix_risk * 0.24)
        + (weak_structure * 0.16)
        + (transition * 0.22)
    )
    return clamp(probability)


def calculate_narrative_failure_probability(setup: Any, context: Any) -> float:
    setup = _safe_dict(setup)
    context = _safe_dict(context)
    news = _prob_from_score(setup.get("news_score"), 50.0)
    sector = _prob_from_score(context.get("sector_strength"), 50.0)
    sentiment = _prob_from_score(context.get("market_sentiment"), 50.0)
    index_strength = _prob_from_score(context.get("index_strength"), 50.0)
    regime_alignment = _regime_alignment(setup, context)

    probability = (
        0.10
        + ((1.0 - news) * 0.22)
        + ((1.0 - sector) * 0.20)
        + ((1.0 - sentiment) * 0.18)
        + ((1.0 - index_strength) * 0.14)
        + ((1.0 - regime_alignment) * 0.16)
    )
    return clamp(probability)


def calculate_uncertainty_score(probabilities: Any) -> float:
    probabilities = _safe_dict(probabilities)
    if not probabilities:
        return 1.0

    values = [clamp(value) for value in probabilities.values()]
    if not values:
        return 1.0

    average_distance_from_neutral = sum(abs(value - 0.5) for value in values) / len(values)
    dispersion = max(values) - min(values)
    uncertainty = 1.0 - (average_distance_from_neutral * 1.35) + (dispersion * 0.15)
    return clamp(uncertainty)


def calculate_probability_confidence(probabilities: Any) -> float:
    probabilities = _safe_dict(probabilities)
    uncertainty = calculate_uncertainty_score(probabilities)
    values = [clamp(value) for value in probabilities.values()]
    if not values:
        return 0.0

    favorable = [
        probabilities.get("regime_continuation_probability", 0.5),
        probabilities.get("setup_survival_probability", 0.5),
        probabilities.get("tp_before_sl_probability", 0.5),
    ]
    adverse = [
        probabilities.get("false_breakout_probability", 0.5),
        probabilities.get("momentum_decay_probability", 0.5),
        probabilities.get("volatility_expansion_probability", 0.5),
        probabilities.get("narrative_failure_probability", 0.5),
    ]

    signal_strength = (sum(clamp(value) for value in favorable) / len(favorable)) * 0.55
    risk_control = (1.0 - (sum(clamp(value) for value in adverse) / len(adverse))) * 0.45
    confidence = ((signal_strength + risk_control) * 0.70) + ((1.0 - uncertainty) * 0.30)
    return clamp(confidence)


def calculate_expected_value(setup: Any, probabilities: Any) -> float:
    setup = _safe_dict(setup)
    probabilities = _safe_dict(probabilities)

    entry = _get_number(setup, ["entry"], 0.0)
    stop = _get_number(setup, ["stop_loss", "sl"], 0.0)
    target = _get_number(setup, ["target", "tp"], 0.0)
    risk = abs(entry - stop)
    reward = abs(target - entry)

    if risk <= 0 or reward <= 0:
        rr = _get_number(setup, ["rr"], 1.0)
        risk = 1.0
        reward = max(0.0, rr)

    win_probability = clamp(probabilities.get("tp_before_sl_probability", 0.5))
    loss_probability = 1.0 - win_probability
    return round((win_probability * reward) - (loss_probability * risk), 4)


def _build_explanations(setup: Dict[str, Any], context: Dict[str, Any], probabilities: Dict[str, float]) -> List[str]:
    explanations: List[str] = []

    if _prob_from_score(setup.get("trend_score"), 50.0) >= 0.65:
        explanations.append("Trend strength supports continuation.")
    elif _prob_from_score(setup.get("trend_score"), 50.0) <= 0.40:
        explanations.append("Weak trend score reduces setup durability.")

    if _prob_from_score(setup.get("momentum_score"), 50.0) >= 0.65:
        explanations.append("Momentum confirmation improves TP-before-SL odds.")
    elif probabilities.get("momentum_decay_probability", 0.0) >= 0.55:
        explanations.append("Momentum decay risk is elevated.")

    if _prob_from_score(setup.get("structure_score"), 50.0) >= 0.65:
        explanations.append("Structure quality lowers false-breakout risk.")
    elif probabilities.get("false_breakout_probability", 0.0) >= 0.55:
        explanations.append("Low structure or confirmation raises false-breakout risk.")

    if _volatility_risk(context) >= 0.60:
        explanations.append("Volatility and VIX conditions increase uncertainty.")

    if _prob_from_score(context.get("breadth"), 50.0) <= 0.40:
        explanations.append("Weak market breadth reduces probability quality.")
    elif _prob_from_score(context.get("breadth"), 50.0) >= 0.65:
        explanations.append("Healthy breadth supports setup survival.")

    if _rr_score(setup) <= 0.35:
        explanations.append("Risk-reward profile is poor or unavailable.")
    elif _rr_score(setup) >= 0.65:
        explanations.append("Risk-reward profile supports positive expected value.")

    if not explanations:
        explanations.append("Probabilities are neutral because available inputs are limited or mixed.")

    return explanations


def _recommendation(final_probability_score: float) -> str:
    if final_probability_score >= 80.0:
        return "STRONG"
    if final_probability_score >= 65.0:
        return "GOOD"
    if final_probability_score >= 45.0:
        return "WEAK"
    return "REJECT"


def build_probability_report(setup: Any, context: Any) -> Dict[str, Any]:
    setup = _safe_dict(setup)
    context = _safe_dict(context)

    probabilities = {
        "regime_continuation_probability": calculate_regime_continuation_probability(context),
        "regime_transition_probability": calculate_regime_transition_probability(context),
        "setup_survival_probability": calculate_setup_survival_probability(setup, context),
        "tp_before_sl_probability": calculate_tp_before_sl_probability(setup, context),
        "false_breakout_probability": calculate_false_breakout_probability(setup, context),
        "momentum_decay_probability": calculate_momentum_decay_probability(setup, context),
        "volatility_expansion_probability": calculate_volatility_expansion_probability(setup, context),
        "narrative_failure_probability": calculate_narrative_failure_probability(setup, context),
    }
    uncertainty = calculate_uncertainty_score(probabilities)
    confidence = calculate_probability_confidence(probabilities)
    expected_value = calculate_expected_value(setup, probabilities)

    favorable_score = (
        probabilities["regime_continuation_probability"] * 0.14
        + probabilities["setup_survival_probability"] * 0.24
        + probabilities["tp_before_sl_probability"] * 0.34
        + confidence * 0.10
    )
    risk_penalty = (
        probabilities["regime_transition_probability"] * 0.04
        + probabilities["false_breakout_probability"] * 0.08
        + probabilities["momentum_decay_probability"] * 0.06
        + probabilities["volatility_expansion_probability"] * 0.05
        + probabilities["narrative_failure_probability"] * 0.05
    )
    final_probability_score = clamp(favorable_score - risk_penalty + 0.15) * 100.0
    final_probability_score = round(clamp(final_probability_score, 0.0, 100.0), 2)

    report = {
        "symbol": _get_text(setup, "symbol", "UNKNOWN") or "UNKNOWN",
        "side": _get_text(setup, "side", "UNKNOWN") or "UNKNOWN",
        "regime_continuation_probability": round(probabilities["regime_continuation_probability"], 4),
        "regime_transition_probability": round(probabilities["regime_transition_probability"], 4),
        "setup_survival_probability": round(probabilities["setup_survival_probability"], 4),
        "tp_before_sl_probability": round(probabilities["tp_before_sl_probability"], 4),
        "false_breakout_probability": round(probabilities["false_breakout_probability"], 4),
        "momentum_decay_probability": round(probabilities["momentum_decay_probability"], 4),
        "volatility_expansion_probability": round(probabilities["volatility_expansion_probability"], 4),
        "narrative_failure_probability": round(probabilities["narrative_failure_probability"], 4),
        "uncertainty_score": round(uncertainty, 4),
        "probability_confidence_score": round(confidence, 4),
        "expected_value": expected_value,
        "final_probability_score": final_probability_score,
        "recommendation": _recommendation(final_probability_score),
        "explanations": _build_explanations(setup, context, probabilities),
    }
    return report


def rank_setups_by_probability(setups: Any, context: Any) -> List[Dict[str, Any]]:
    if not isinstance(setups, list):
        setups = []

    reports = [build_probability_report(setup, context) for setup in setups]
    return sorted(
        reports,
        key=lambda report: safe_float(report.get("final_probability_score"), 0.0),
        reverse=True,
    )


if __name__ == "__main__":
    sample_setup = {
        "symbol": "RELIANCE",
        "side": "LONG",
        "entry": 2850,
        "stop_loss": 2800,
        "target": 2960,
        "rr": 2.2,
        "score": 78,
        "volume_score": 72,
        "momentum_score": 76,
        "trend_score": 74,
        "structure_score": 81,
        "relative_strength": 69,
        "news_score": 62,
    }
    sample_context = {
        "market_regime": "bullish_trending",
        "volatility": 38,
        "trend_strength": 73,
        "breadth": 68,
        "vix": 15.4,
        "market_sentiment": 66,
        "sector_strength": 71,
        "index_strength": 70,
    }
    sample_ranked_setups = [
        sample_setup,
        {
            "symbol": "TCS",
            "side": "LONG",
            "entry": "3900",
            "sl": "3840",
            "tp": "4040",
            "rr": "2.33",
            "score": 69,
            "volume_score": 58,
            "momentum_score": 64,
            "trend_score": 67,
            "structure_score": 63,
            "relative_strength": 61,
            "news_score": 55,
        },
        {
            "symbol": "WEAK_SAMPLE",
            "side": "LONG",
            "entry": "bad",
            "stop_loss": None,
            "target": "",
            "rr": 0.8,
            "score": 39,
            "volume_score": 35,
            "momentum_score": 31,
            "trend_score": 42,
            "structure_score": 37,
            "relative_strength": 34,
            "news_score": 45,
        },
    ]

    output = {
        "single_report": build_probability_report(sample_setup, sample_context),
        "ranked_setups": rank_setups_by_probability(sample_ranked_setups, sample_context),
    }
    print(json.dumps(output, indent=2))
