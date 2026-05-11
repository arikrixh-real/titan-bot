"""
TITAN Phase 33 - Self-Reflection & Meta-Cognition Engine

Deterministic self-review layer for confidence calibration, reasoning quality,
mistake patterns, and overconfidence checks. This engine never places orders.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List


REPORT_PATH = os.path.join("data", "self_reflection", "latest_self_reflection_report.json")


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return float(value)
    except Exception:
        return float(default)


def safe_text(value, default=""):
    try:
        if value is None:
            return str(default)
        return str(value).strip()
    except Exception:
        return str(default)


def safe_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def clamp(value, min_value=0.0, max_value=100.0):
    try:
        value = safe_float(value, min_value)
        return max(float(min_value), min(float(max_value), value))
    except Exception:
        return float(min_value)


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _raw(setup):
    setup = _as_dict(setup)
    return setup.get("raw") if isinstance(setup.get("raw"), dict) else {}


def _field(setup, key, default=None):
    setup = _as_dict(setup)
    raw = _raw(setup)
    return setup.get(key, raw.get(key, default))


def _symbol(setup):
    setup = _as_dict(setup)
    raw = _raw(setup)
    return safe_text(setup.get("symbol") or setup.get("stock") or raw.get("symbol") or raw.get("stock") or "UNKNOWN")


def _score_field(setup, key, default=50.0):
    return clamp(_field(setup, key, default))


def _rank_score(setup):
    for key in [
        "final_debate_rank",
        "final_scenario_rank",
        "final_liquidity_rank",
        "final_calendar_rank",
        "final_news_intelligence_rank",
        "final_options_rank",
        "new_blended_rank_score",
        "blended_rank_score",
        "final_score",
        "score",
    ]:
        value = _field(setup, key)
        if value is not None:
            return clamp(value)
    return 50.0


def _confidence_numeric(value):
    text = safe_text(value).upper()
    if text == "HIGH":
        return 80.0
    if text == "MEDIUM":
        return 60.0
    if text == "LOW":
        return 35.0
    return clamp(value, 0.0, 100.0) if value not in (None, "") else 50.0


def _is_loss(trade):
    trade = _as_dict(trade)
    result = safe_text(trade.get("result") or trade.get("outcome") or trade.get("status")).upper()
    pnl = safe_float(trade.get("pnl") or trade.get("pnl_pct") or trade.get("profit"), 0.0)
    return result in {"LOSS", "STOP", "STOP_LOSS", "FAILED"} or pnl < 0.0


def normalize_reflection_inputs(setup=None, context=None, trade_result=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    trade_result = _as_dict(trade_result)
    payload = {
        "setup": dict(setup),
        "context": dict(context),
        "trade_result": dict(trade_result),
        "symbol": _symbol(setup),
        "rank_score": _rank_score(setup),
        "confidence_score": _confidence_numeric(_field(setup, "confidence", _field(setup, "confidence_score"))),
    }
    return payload


def _data_mode(setup, context, trade_result, trade_history):
    setup = _as_dict(setup)
    context = _as_dict(context)
    trade_result = _as_dict(trade_result)
    history = safe_list(trade_history)
    rich_keys = [
        "final_debate_rank",
        "debate_score",
        "scenario_score",
        "liquidity_map_score",
        "news_intelligence_score",
        "calendar_intelligence_score",
        "options_flow_score",
        "probability_score",
        "confidence_after_debate",
        "debate_final_judge",
        "reasoning",
        "explanations",
        "rr",
        "decision",
        "confidence",
    ]
    present = sum(1 for key in rich_keys if _field(setup, key) not in (None, "", [], {}))
    context_present = sum(1 for _, value in context.items() if value not in (None, "", [], {}))
    if present >= 5 or trade_result or len(history) >= 3 or (present >= 3 and context_present >= 2):
        return "REAL_REFLECTION"
    if present >= 1 or context_present >= 1 or history:
        return "PROXY"
    return "INSUFFICIENT"


def run_self_critique(setup=None, context=None, trade_result=None):
    setup = _as_dict(setup)
    weaknesses = []
    strengths = []
    score = _rank_score(setup)
    rr = safe_float(_field(setup, "rr"), 0.0)
    if score >= 65.0:
        strengths.append("Candidate has acceptable blended intelligence score.")
    elif score < 45.0:
        weaknesses.append("Candidate score is below the preferred quality zone.")
    if rr >= 1.8:
        strengths.append("Reward-risk supports the decision.")
    elif rr and rr < 1.3:
        weaknesses.append("Reward-risk is weak and needs caution.")
    for key in ["debate_warning", "scenario_warning", "liquidity_warning", "news_warning", "calendar_warning"]:
        warning = safe_text(_field(setup, key)).upper()
        if warning in {"SKIP", "WAIT", "REVIEW"}:
            weaknesses.append(f"{key} is {warning}.")
    if _is_loss(trade_result):
        weaknesses.append("Latest trade result was adverse.")
    critique_score = clamp(70.0 + len(strengths) * 6.0 - len(weaknesses) * 8.0)
    return {
        "critique_score": round(critique_score, 2),
        "strengths": strengths or ["No decisive strengths detected."],
        "weaknesses": weaknesses or ["No major weakness detected."],
    }


def run_decision_regret_analysis(setup=None, context=None, trade_result=None):
    setup = _as_dict(setup)
    trade_result = _as_dict(trade_result)
    confidence = _confidence_numeric(_field(setup, "confidence", _field(setup, "confidence_after_debate")))
    score = _rank_score(setup)
    loss = _is_loss(trade_result)
    regret = 15.0
    if confidence >= 75.0 and score < 55.0:
        regret += 28.0
    if loss and confidence >= 70.0:
        regret += 24.0
    elif loss:
        regret += 12.0
    if safe_text(_field(setup, "decision")).upper() == "TRUST" and score < 50.0:
        regret += 18.0
    regret = clamp(regret)
    return {
        "regret_risk_score": round(regret, 2),
        "regret_level": "HIGH" if regret >= 65.0 else "MEDIUM" if regret >= 40.0 else "LOW",
        "notes": ["Regret risk rises when confidence exceeds evidence or recent outcome is adverse."],
    }


def run_confidence_calibration(setup=None, context=None, trade_result=None):
    setup = _as_dict(setup)
    confidence = _confidence_numeric(_field(setup, "confidence", _field(setup, "confidence_after_debate")))
    evidence = sum(
        [
            _rank_score(setup),
            _score_field(setup, "debate_score", 50.0),
            _score_field(setup, "scenario_score", 50.0),
            _score_field(setup, "liquidity_map_score", 50.0),
            _score_field(setup, "news_intelligence_score", 50.0),
        ]
    ) / 5.0
    gap = confidence - evidence
    calibration = clamp(100.0 - abs(gap) * 1.25)
    label = "CALIBRATED"
    if gap >= 18.0:
        label = "OVERCONFIDENT"
    elif gap <= -18.0:
        label = "UNDERCONFIDENT"
    return {
        "confidence_score": round(confidence, 2),
        "evidence_score": round(evidence, 2),
        "calibration_gap": round(gap, 2),
        "calibration_score": round(calibration, 2),
        "calibration_label": label,
    }


def analyze_reasoning_quality(setup=None, context=None):
    setup = _as_dict(setup)
    evidence_fields = [
        "probability_explanations",
        "causal_explanations",
        "options_explanations",
        "news_explanations",
        "calendar_explanations",
        "liquidity_explanations",
        "scenario_explanations",
        "debate_explanations",
        "reasoning",
        "explanations",
    ]
    evidence_count = 0
    for key in evidence_fields:
        value = _field(setup, key)
        if isinstance(value, list):
            evidence_count += len([item for item in value if safe_text(item)])
        elif safe_text(value):
            evidence_count += 1
    warning_count = sum(
        1
        for key in ["debate_warning", "scenario_warning", "liquidity_warning", "news_warning", "calendar_warning"]
        if safe_text(_field(setup, key)).upper() in {"SKIP", "WAIT", "REVIEW"}
    )
    quality = clamp(45.0 + min(evidence_count, 8) * 6.0 - warning_count * 7.0)
    return {
        "reasoning_quality_score": round(quality, 2),
        "evidence_count": evidence_count,
        "warning_count": warning_count,
        "quality_label": "STRONG" if quality >= 70.0 else "WEAK" if quality < 45.0 else "ADEQUATE",
    }


def detect_hallucination_or_overconfidence(setup=None, context=None):
    setup = _as_dict(setup)
    calibration = run_confidence_calibration(setup, context)
    reasoning = analyze_reasoning_quality(setup, context)
    risk = 10.0
    if calibration.get("calibration_label") == "OVERCONFIDENT":
        risk += 34.0
    if safe_float(reasoning.get("evidence_count"), 0.0) <= 1.0 and safe_float(calibration.get("confidence_score"), 50.0) >= 70.0:
        risk += 28.0
    if safe_float(reasoning.get("reasoning_quality_score"), 50.0) < 45.0:
        risk += 18.0
    risk = clamp(risk)
    return {
        "hallucination_risk_score": round(risk, 2),
        "overconfidence_detected": calibration.get("calibration_label") == "OVERCONFIDENT",
        "evidence_gap_detected": safe_float(reasoning.get("evidence_count"), 0.0) <= 1.0,
        "risk_label": "HIGH" if risk >= 65.0 else "MEDIUM" if risk >= 40.0 else "LOW",
    }


def detect_mistake_patterns(trade_history=None, context=None):
    history = [item for item in safe_list(trade_history) if isinstance(item, dict)]
    if not history:
        return {
            "history_count": 0,
            "loss_count": 0,
            "repeat_mistake_score": 0.0,
            "patterns": [],
        }
    losses = [item for item in history if _is_loss(item)]
    pattern_counts: Dict[str, int] = {}
    for item in losses:
        for key in ["mistake", "reason", "tag", "setup_type", "strategy", "exit_reason"]:
            text = safe_text(item.get(key))
            if text:
                pattern_counts[text.upper()] = pattern_counts.get(text.upper(), 0) + 1
    repeated = [{"pattern": key, "count": count} for key, count in pattern_counts.items() if count >= 2]
    loss_rate = (len(losses) / float(len(history))) * 100.0
    repeat_score = clamp(loss_rate * 0.7 + len(repeated) * 12.0)
    return {
        "history_count": len(history),
        "loss_count": len(losses),
        "loss_rate": round(loss_rate, 2),
        "repeat_mistake_score": round(repeat_score, 2),
        "patterns": repeated,
    }


def generate_self_improvement_suggestions(setup=None, context=None, trade_history=None):
    suggestions = []
    calibration = run_confidence_calibration(setup, context)
    hallucination = detect_hallucination_or_overconfidence(setup, context)
    mistakes = detect_mistake_patterns(trade_history, context)
    reasoning = analyze_reasoning_quality(setup, context)
    if calibration.get("calibration_label") == "OVERCONFIDENT":
        suggestions.append("Reduce confidence unless evidence score confirms the setup.")
    if hallucination.get("risk_label") in {"MEDIUM", "HIGH"}:
        suggestions.append("Require explicit evidence from multiple engines before trusting the setup.")
    if safe_float(mistakes.get("repeat_mistake_score"), 0.0) >= 45.0:
        suggestions.append("Review repeated losing patterns before increasing rank.")
    if safe_float(reasoning.get("reasoning_quality_score"), 50.0) < 50.0:
        suggestions.append("Improve reasoning trace quality before treating the decision as high confidence.")
    if not suggestions:
        suggestions.append("Maintain current calibration discipline and continue monitoring outcomes.")
    return suggestions


def calculate_thought_quality_score(setup=None, context=None):
    reasoning = analyze_reasoning_quality(setup, context)
    calibration = run_confidence_calibration(setup, context)
    hallucination = detect_hallucination_or_overconfidence(setup, context)
    score = (
        safe_float(reasoning.get("reasoning_quality_score"), 50.0) * 0.45
        + safe_float(calibration.get("calibration_score"), 50.0) * 0.40
        + (100.0 - safe_float(hallucination.get("hallucination_risk_score"), 50.0)) * 0.15
    )
    return round(clamp(score), 2)


def _save_report(report):
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    except Exception:
        pass


def build_self_reflection_report(setup=None, context=None, trade_result=None, trade_history=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    trade_result = _as_dict(trade_result)
    history = safe_list(trade_history)
    mode = _data_mode(setup, context, trade_result, history)
    explanations: List[str] = []

    self_critique = run_self_critique(setup, context, trade_result)
    regret = run_decision_regret_analysis(setup, context, trade_result)
    calibration = run_confidence_calibration(setup, context, trade_result)
    reasoning = analyze_reasoning_quality(setup, context)
    hallucination = detect_hallucination_or_overconfidence(setup, context)
    mistakes = detect_mistake_patterns(history, context)
    suggestions = generate_self_improvement_suggestions(setup, context, history)
    thought_quality = calculate_thought_quality_score(setup, context)

    reflection_score = (
        thought_quality * 0.35
        + safe_float(self_critique.get("critique_score"), 50.0) * 0.20
        + safe_float(calibration.get("calibration_score"), 50.0) * 0.20
        + (100.0 - safe_float(regret.get("regret_risk_score"), 50.0)) * 0.15
        + (100.0 - safe_float(mistakes.get("repeat_mistake_score"), 0.0)) * 0.10
    )

    warning = "NONE"
    if safe_float(hallucination.get("hallucination_risk_score"), 0.0) >= 75.0:
        warning = "SKIP"
    elif (
        safe_float(mistakes.get("repeat_mistake_score"), 0.0) >= 45.0
        or safe_float(reasoning.get("reasoning_quality_score"), 50.0) < 45.0
        or calibration.get("calibration_label") == "OVERCONFIDENT"
    ):
        warning = "REVIEW"

    if mode == "INSUFFICIENT":
        reflection_score = 50.0
        bias = "REVIEW"
        warning = "REVIEW"
        explanations.append("Insufficient reflection data; neutral non-blocking reflection applied.")
    else:
        if warning == "SKIP":
            reflection_score -= 22.0
            explanations.append("High hallucination or overconfidence risk reduced reflection score.")
        elif warning in {"REVIEW", "WAIT"}:
            reflection_score -= 6.0
            explanations.append("Reflection requested review; small ranking penalty applied.")
        bias = "CONFIDENT" if reflection_score >= 65.0 and warning == "NONE" else "UNCERTAIN" if reflection_score >= 48.0 else "REVIEW"
        explanations.append(f"{mode} self-reflection used available setup/context/outcome evidence.")

    reflection_score = round(clamp(reflection_score), 2)
    report = {
        "symbol": _symbol(setup),
        "reflection_data_mode": mode,
        "self_critique": self_critique,
        "decision_regret_analysis": regret,
        "confidence_calibration": calibration,
        "reasoning_quality": reasoning,
        "hallucination_detection": hallucination,
        "mistake_patterns": mistakes,
        "self_improvement_suggestions": suggestions,
        "thought_quality_score": thought_quality,
        "reflection_score": reflection_score,
        "reflection_bias": bias,
        "reflection_warning": warning if warning in {"NONE", "WAIT", "SKIP", "REVIEW"} else "REVIEW",
        "live_order_allowed": False,
        "explanations": explanations,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_report(report)
    return report


if __name__ == "__main__":
    sample_setup = {
        "symbol": "TITAN",
        "decision": "TRUST",
        "confidence": "HIGH",
        "score": 72,
        "rr": 2.0,
        "debate_score": 74,
        "scenario_score": 69,
        "liquidity_map_score": 64,
        "news_intelligence_score": 62,
        "debate_explanations": ["Debate approved with low objection pressure."],
        "scenario_explanations": ["Bullish expected value with contained stress risk."],
    }
    sample_context = {"market_regime": "trend", "trading_mode": "SELECTIVE"}
    sample_trade_result = {"result": "WIN", "pnl_pct": 1.4}
    sample_trade_history = [
        {"result": "WIN", "setup_type": "breakout", "pnl_pct": 1.2},
        {"result": "LOSS", "setup_type": "reversal", "mistake": "CHASE", "pnl_pct": -0.8},
        {"result": "LOSS", "setup_type": "reversal", "mistake": "CHASE", "pnl_pct": -0.6},
    ]
    print(
        json.dumps(
            build_self_reflection_report(sample_setup, sample_context, sample_trade_result, sample_trade_history),
            indent=2,
            sort_keys=True,
        )
    )
