"""
TITAN Phase 6 - Multi-Agent Reasoning Shadow Layer
--------------------------------------------------

Deterministic advisory layer for evaluated Master Brain setups.

Safety:
- Shadow mode only.
- Does not scan markets, fetch data, write files, send alerts, or create trades.
- Does not block setups.
- Does not change ranking: phase6_rank_adjustment is always 0.
- Fails open by returning original setups unchanged on unexpected errors.
"""

from __future__ import annotations

from typing import Any, Dict, List


PHASE6_SHADOW_MODE = True
PHASE6_RANK_ADJUSTMENT = 0.0
MAX_SETUPS_TO_STUDY = 15

SUPPORT = "SUPPORT"
CAUTION = "CAUTION"
OPPOSE = "OPPOSE"
NEUTRAL = "NEUTRAL"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _raw_setup(setup: Dict[str, Any]) -> Dict[str, Any]:
    raw = setup.get("raw")
    return raw if isinstance(raw, dict) else setup


def _nested_dict(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _stance_from_score(score: float) -> str:
    if score >= 0.35:
        return SUPPORT
    if score <= -0.35:
        return OPPOSE
    if score < 0:
        return CAUTION
    return NEUTRAL


def _opinion(agent: str, score: float, confidence: float, evidence: List[str], warnings: List[str] | None = None) -> Dict[str, Any]:
    return {
        "agent": agent,
        "stance": _stance_from_score(score),
        "score": round(max(-1.0, min(1.0, score)), 4),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "evidence": evidence[:4],
        "warnings": (warnings or [])[:4],
    }


def technical_agent(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    raw = _raw_setup(setup)
    score = _safe_float(setup.get("score") or raw.get("score") or raw.get("rank_score"), 0.0)
    rr = _safe_float(setup.get("rr") or raw.get("rr"), 0.0)
    setup_context = _nested_dict(raw, "setup_context")
    confirmations = _safe_int(setup_context.get("confirmations") or setup.get("confirmations"), 0)

    points = 0.0
    evidence = []
    warnings = []

    if score >= 3.0:
        points += 0.35
        evidence.append("setup score is strong")
    elif score >= 2.0:
        points += 0.10
        evidence.append("setup score is moderate")
    else:
        points -= 0.25
        warnings.append("setup score is weak")

    if rr >= 2.0:
        points += 0.25
        evidence.append("risk reward is supportive")
    elif rr < 1.5:
        points -= 0.30
        warnings.append("risk reward is below preferred threshold")

    if confirmations >= 5:
        points += 0.25
        evidence.append("confirmation count is high")
    elif confirmations < 3:
        points -= 0.20
        warnings.append("confirmation count is low")

    return _opinion("technical_agent", points, 0.75 if evidence or warnings else 0.35, evidence, warnings)


def risk_agent(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    raw = _raw_setup(setup)
    professional_risk = _nested_dict(raw, "professional_risk")
    risk_quality = _safe_float(
        raw.get("risk_quality_score") or professional_risk.get("risk_quality_score"),
        50.0,
    )
    risk_blocks = professional_risk.get("risk_blocks") or []
    rr = _safe_float(setup.get("rr") or raw.get("rr"), 0.0)

    points = 0.0
    evidence = []
    warnings = []

    if risk_blocks:
        points -= 0.70
        warnings.append("professional risk blocks are present")
    elif risk_quality >= 65:
        points += 0.30
        evidence.append("risk quality is supportive")
    elif risk_quality <= 40:
        points -= 0.35
        warnings.append("risk quality is weak")

    if rr >= 2.0:
        points += 0.15
        evidence.append("trade offers acceptable reward for risk")
    elif rr < 1.5:
        points -= 0.25
        warnings.append("reward for risk is thin")

    return _opinion("risk_agent", points, 0.70, evidence, warnings)


def regime_agent(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    raw = _raw_setup(setup)
    market_context = _nested_dict(raw, "market_context")
    advanced_regime = _nested_dict(raw, "advanced_regime")
    side = str(setup.get("side") or raw.get("side") or "").upper()
    trend = str(market_context.get("trend") or raw.get("trend") or "").upper()
    trading_mode = str(context.get("trading_mode") or "").upper()
    risk_level = str(context.get("risk_level") or "").upper()
    regime_type = str(advanced_regime.get("regime_type") or "").upper()
    panic_score = _safe_float(advanced_regime.get("panic_score"), 0.0)

    points = 0.0
    evidence = []
    warnings = []

    if side == "LONG" and trend == "BULLISH":
        points += 0.35
        evidence.append("LONG setup aligns with bullish trend")
    elif side == "SHORT" and trend == "BEARISH":
        points += 0.35
        evidence.append("SHORT setup aligns with bearish trend")
    elif trend:
        points -= 0.35
        warnings.append("setup side conflicts with trend")

    if trading_mode in {"SELECTIVE", "AGGRESSIVE"} and risk_level != "HIGH":
        points += 0.15
        evidence.append("context allows selective participation")
    elif risk_level == "HIGH":
        points -= 0.25
        warnings.append("context risk level is high")

    if regime_type == "TRENDING":
        points += 0.15
        evidence.append("advanced regime is trending")

    if panic_score >= 60:
        points -= 0.35
        warnings.append("panic score is elevated")

    return _opinion("regime_agent", points, 0.70, evidence, warnings)


def execution_agent(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    raw = _raw_setup(setup)
    execution = _nested_dict(raw, "execution_quality")
    execution_score = _safe_float(raw.get("execution_quality_score") or execution.get("execution_quality_score"), 50.0)
    slippage = _safe_float(raw.get("slippage_risk_estimate") or execution.get("slippage_risk_estimate"), 50.0)
    chase_penalty = _safe_float(raw.get("chase_entry_penalty") or execution.get("chase_entry_penalty"), 0.0)

    points = 0.0
    evidence = []
    warnings = []

    if execution_score >= 65:
        points += 0.35
        evidence.append("execution quality is supportive")
    elif execution_score <= 40:
        points -= 0.30
        warnings.append("execution quality is weak")

    if slippage <= 35:
        points += 0.15
        evidence.append("slippage risk appears contained")
    elif slippage >= 65:
        points -= 0.30
        warnings.append("slippage risk is elevated")

    if chase_penalty >= 40:
        points -= 0.25
        warnings.append("entry may be chase-sensitive")

    return _opinion("execution_agent", points, 0.60, evidence, warnings)


def memory_agent(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    raw = _raw_setup(setup)
    family_strength = setup.get("strategy_family_strength") or raw.get("strategy_family_strength") or {}
    memory_active = bool(family_strength.get("memory_active")) if isinstance(family_strength, dict) else False
    family_quality = _safe_float(family_strength.get("family_quality_score") if isinstance(family_strength, dict) else None, 50.0)
    learning_env = str(context.get("learning_environment") or "").upper()

    points = 0.0
    evidence = []
    warnings = []

    if memory_active and family_quality >= 58:
        points += 0.25
        evidence.append("strategy family memory is supportive")
    elif memory_active and family_quality <= 42:
        points -= 0.25
        warnings.append("strategy family memory is weak")
    else:
        evidence.append("memory kept neutral due to sample rules")

    if learning_env == "RECENT_MEMORY_FAVORABLE":
        points += 0.10
        evidence.append("recent memory environment is favorable")
    elif learning_env == "RECENT_MEMORY_WEAK":
        points -= 0.15
        warnings.append("recent memory environment is weak")

    return _opinion("memory_agent", points, 0.45 if not memory_active else 0.65, evidence, warnings)


def news_agent(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    raw = _raw_setup(setup)
    side = str(setup.get("side") or raw.get("side") or "").upper()
    sentiment = str(
        raw.get("news_sentiment_refined")
        or raw.get("news_sentiment")
        or raw.get("news_sentiment_score")
        or ""
    ).upper()
    relevance = _safe_float(raw.get("news_relevance_score"), 0.0)

    points = 0.0
    evidence = []
    warnings = []

    if not sentiment:
        evidence.append("no decisive news signal available")
        return _opinion("news_agent", 0.0, 0.30, evidence, warnings)

    bullish = "BULL" in sentiment or _safe_float(sentiment, 0.0) > 0
    bearish = "BEAR" in sentiment or _safe_float(sentiment, 0.0) < 0
    strength = 0.25 if relevance >= 50 else 0.12

    if side == "LONG" and bullish:
        points += strength
        evidence.append("news tone supports LONG setup")
    elif side == "SHORT" and bearish:
        points += strength
        evidence.append("news tone supports SHORT setup")
    elif bullish or bearish:
        points -= strength
        warnings.append("news tone conflicts with setup side")

    return _opinion("news_agent", points, 0.45 if relevance < 50 else 0.60, evidence, warnings)


def scenario_agent(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    scenario = build_scenario_reasoning(setup, context)
    failure_mode = scenario.get("failure_mode", "")
    confidence = _safe_float(scenario.get("scenario_confidence"), 50.0) / 100.0
    score = (confidence - 0.5) * 0.8
    warnings = [failure_mode] if failure_mode else []
    evidence = [scenario.get("base_case", "scenario built from available setup context")]
    return _opinion("scenario_agent", score, 0.55, evidence, warnings)


def build_scenario_reasoning(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    raw = _raw_setup(setup)
    side = str(setup.get("side") or raw.get("side") or "UNKNOWN").upper()
    symbol = setup.get("symbol") or raw.get("symbol") or "UNKNOWN"
    rr = _safe_float(setup.get("rr") or raw.get("rr"), 0.0)
    score = _safe_float(setup.get("score") or raw.get("score"), 0.0)

    if side == "SHORT":
        base_case = f"{symbol} follows through lower without reclaiming entry."
        bull_case = "Bearish momentum expands and target is reached cleanly."
        bear_case = "Price reclaims entry and invalidates the short setup."
    elif side == "LONG":
        base_case = f"{symbol} follows through higher while holding entry."
        bull_case = "Buying pressure expands and target is reached cleanly."
        bear_case = "Price loses entry and invalidates the long setup."
    else:
        base_case = f"{symbol} requires clearer directional confirmation."
        bull_case = "Directional confirmation improves before action."
        bear_case = "Unclear side keeps setup unreliable."

    if rr < 1.5:
        failure_mode = "thin reward-to-risk leaves little room for execution error"
    elif score < 2.0:
        failure_mode = "weak setup score may not attract follow-through"
    elif str(context.get("risk_level") or "").upper() == "HIGH":
        failure_mode = "high market-context risk can overwhelm setup quality"
    else:
        failure_mode = "normal follow-through failure after entry"

    confidence = 50.0
    confidence += 12.0 if rr >= 2.0 else -10.0 if rr < 1.5 else 0.0
    confidence += 12.0 if score >= 3.0 else -8.0 if score < 2.0 else 0.0
    confidence -= 10.0 if str(context.get("risk_level") or "").upper() == "HIGH" else 0.0

    return {
        "base_case": base_case,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "failure_mode": failure_mode,
        "required_confirmation": "price must respect entry and move toward target with continued confirmation",
        "scenario_confidence": round(_clamp(confidence), 2),
    }


def detect_contradictions(setup: Dict[str, Any], context: Dict[str, Any], opinions: List[Dict[str, Any]]) -> List[str]:
    raw = _raw_setup(setup)
    market_context = _nested_dict(raw, "market_context")
    execution = _nested_dict(raw, "execution_quality")
    side = str(setup.get("side") or raw.get("side") or "").upper()
    trend = str(market_context.get("trend") or raw.get("trend") or "").upper()
    rr = _safe_float(setup.get("rr") or raw.get("rr"), 0.0)
    confidence = str(setup.get("confidence") or "").upper()
    score = _safe_float(setup.get("score") or raw.get("score"), 0.0)
    slippage = _safe_float(raw.get("slippage_risk_estimate") or execution.get("slippage_risk_estimate"), 50.0)
    sentiment = str(raw.get("news_sentiment_refined") or raw.get("news_sentiment") or "").upper()

    contradictions = []

    if side == "LONG" and trend == "BEARISH":
        contradictions.append("LONG setup conflicts with bearish trend")
    if side == "SHORT" and trend == "BULLISH":
        contradictions.append("SHORT setup conflicts with bullish trend")
    if confidence == "HIGH" and rr < 1.5:
        contradictions.append("high confidence conflicts with low reward-to-risk")
    if score >= 3.0 and slippage >= 65:
        contradictions.append("strong setup score conflicts with elevated slippage risk")
    if side == "LONG" and "BEAR" in sentiment:
        contradictions.append("LONG setup conflicts with bearish news tone")
    if side == "SHORT" and "BULL" in sentiment:
        contradictions.append("SHORT setup conflicts with bullish news tone")

    support_count = sum(1 for item in opinions if item.get("stance") == SUPPORT)
    oppose_count = sum(1 for item in opinions if item.get("stance") == OPPOSE)
    if support_count >= 2 and oppose_count >= 2:
        contradictions.append("specialist agents are materially split")

    return contradictions


def _consensus_score(opinions: List[Dict[str, Any]]) -> float:
    if not opinions:
        return 50.0

    weighted_sum = 0.0
    weight_total = 0.0

    for item in opinions:
        confidence = _safe_float(item.get("confidence"), 0.0)
        weighted_sum += _safe_float(item.get("score"), 0.0) * confidence
        weight_total += confidence

    if weight_total <= 0:
        return 50.0

    normalized = (weighted_sum / weight_total + 1.0) * 50.0
    return round(_clamp(normalized), 2)


def _conflict_score(opinions: List[Dict[str, Any]]) -> float:
    if len(opinions) < 2:
        return 0.0

    scores = [_safe_float(item.get("score"), 0.0) for item in opinions]
    mean = sum(scores) / len(scores)
    variance = sum((score - mean) ** 2 for score in scores) / len(scores)
    return round(_clamp((variance ** 0.5) * 100.0), 2)


def _agreement_confidence(consensus: float, conflict: float, contradictions: List[str]) -> float:
    agreement = consensus
    agreement -= conflict * 0.35
    agreement -= min(25.0, len(contradictions) * 7.0)
    return round(_clamp(agreement), 2)


def evaluate_phase6_setup(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(setup)

    opinions = [
        technical_agent(result, context),
        risk_agent(result, context),
        regime_agent(result, context),
        execution_agent(result, context),
        memory_agent(result, context),
        news_agent(result, context),
        scenario_agent(result, context),
    ]
    scenario = build_scenario_reasoning(result, context)
    contradictions = detect_contradictions(result, context, opinions)
    consensus = _consensus_score(opinions)
    conflict = _conflict_score(opinions)
    agreement = _agreement_confidence(consensus, conflict, contradictions)

    result["phase6_applied"] = True
    result["phase6_shadow_mode"] = PHASE6_SHADOW_MODE
    result["agent_opinions"] = opinions
    result["consensus_score"] = consensus
    result["conflict_score"] = conflict
    result["contradictions"] = contradictions
    result["agreement_confidence"] = agreement
    result["scenario_reasoning"] = scenario
    result["phase6_rank_adjustment"] = PHASE6_RANK_ADJUSTMENT

    return result


def apply_multi_agent_reasoning(evaluated_setups: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Attach Phase 6 metadata to evaluated setups.
    Returns original setup list unchanged if the layer itself fails.
    """

    if not evaluated_setups:
        return evaluated_setups or []

    try:
        enriched = []

        for index, setup in enumerate(evaluated_setups):
            if index >= MAX_SETUPS_TO_STUDY:
                enriched.append(setup)
                continue

            if not isinstance(setup, dict):
                enriched.append(setup)
                continue

            try:
                enriched.append(evaluate_phase6_setup(setup, context or {}))
            except Exception as exc:
                failed = dict(setup)
                failed["phase6_applied"] = False
                failed["phase6_shadow_mode"] = PHASE6_SHADOW_MODE
                failed["phase6_error"] = str(exc)
                failed["phase6_rank_adjustment"] = PHASE6_RANK_ADJUSTMENT
                enriched.append(failed)

        return enriched

    except Exception:
        return evaluated_setups
