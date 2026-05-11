"""
TITAN Phase 32 - Multi-Agent Debate Engine

Internal deterministic debate layer for final candidate review.
This engine never places orders and always fails closed for live execution.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List


REPORT_PATH = os.path.join("data", "multi_agent_debate", "latest_multi_agent_debate_report.json")


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


def _symbol(setup):
    setup = _as_dict(setup)
    raw = _raw(setup)
    return safe_text(setup.get("symbol") or setup.get("stock") or raw.get("symbol") or raw.get("stock") or "UNKNOWN")


def _field(setup, key, default=None):
    setup = _as_dict(setup)
    raw = _raw(setup)
    return setup.get(key, raw.get(key, default))


def _score_field(setup, key, default=50.0):
    return clamp(_field(setup, key, default))


def _contains_any(text, words):
    text = safe_text(text).lower()
    return any(word in text for word in words)


def _warning_points(value):
    warning = safe_text(value).upper()
    if warning == "SKIP":
        return 30.0
    if warning == "WAIT":
        return 18.0
    if warning == "REVIEW":
        return 10.0
    return 0.0


def _bias_points(value, bearish_words=None, bullish_words=None):
    text = safe_text(value).upper()
    bearish_words = bearish_words or {"BEARISH", "REJECT", "NEGATIVE", "RISK_OFF"}
    bullish_words = bullish_words or {"BULLISH", "APPROVE", "POSITIVE", "RISK_ON"}
    if text in bearish_words:
        return -12.0
    if text in bullish_words:
        return 12.0
    return 0.0


def _rank_score(setup):
    keys = [
        "final_scenario_rank",
        "final_liquidity_rank",
        "final_calendar_rank",
        "final_news_intelligence_rank",
        "final_options_rank",
        "new_blended_rank_score",
        "blended_rank_score",
        "final_score",
        "score",
    ]
    for key in keys:
        value = _field(setup, key)
        if value is not None:
            return clamp(value)
    return 50.0


def _data_mode(setup, context):
    setup = _as_dict(setup)
    context = _as_dict(context)
    if not setup and not context:
        return "INSUFFICIENT"

    rich_keys = {
        "final_scenario_rank",
        "final_liquidity_rank",
        "final_calendar_rank",
        "final_news_intelligence_rank",
        "final_options_rank",
        "scenario_score",
        "liquidity_map_score",
        "calendar_intelligence_score",
        "news_intelligence_score",
        "options_flow_score",
        "portfolio_safety_score",
        "microstructure_score",
        "probability_score",
        "rr",
        "confidence",
        "decision",
    }
    present = sum(1 for key in rich_keys if _field(setup, key) not in (None, "", [], {}))
    context_present = sum(1 for key, value in context.items() if value not in (None, "", [], {}))
    if present >= 5 or (present >= 3 and context_present >= 2):
        return "REAL_CONTEXT"
    if present >= 1 or context_present >= 1:
        return "PROXY"
    return "INSUFFICIENT"


def run_bullish_agent(setup=None, context=None):
    setup = _as_dict(setup)
    scores = [
        _rank_score(setup),
        _score_field(setup, "probability_score", 50.0),
        _score_field(setup, "scenario_score", 50.0),
        _score_field(setup, "liquidity_map_score", 50.0),
        _score_field(setup, "news_intelligence_score", 50.0),
        _score_field(setup, "options_flow_score", 50.0),
    ]
    support = sum(scores) / float(len(scores))
    rr = safe_float(_field(setup, "rr"), 0.0)
    if rr >= 2.0:
        support += 8.0
    elif rr >= 1.5:
        support += 4.0
    if safe_text(_field(setup, "decision")).upper() == "TRUST":
        support += 8.0
    if safe_text(_field(setup, "confidence")).upper() == "HIGH":
        support += 6.0
    support += _bias_points(_field(setup, "scenario_bias"))
    support += _bias_points(_field(setup, "liquidity_bias"))
    support = clamp(support)
    arguments = []
    if support >= 65:
        arguments.append("Strong confluence across rank and intelligence scores.")
    if rr >= 1.5:
        arguments.append("Reward-risk is acceptable for debate support.")
    if not arguments:
        arguments.append("Bullish case is present but not decisive.")
    return {
        "stance": "SUPPORT" if support >= 65 else "WEAK_SUPPORT" if support >= 52 else "NEUTRAL",
        "support_score": round(support, 2),
        "arguments": arguments,
    }


def run_bearish_agent(setup=None, context=None):
    setup = _as_dict(setup)
    objection = 100.0 - _rank_score(setup)
    rr = safe_float(_field(setup, "rr"), 0.0)
    if rr and rr < 1.2:
        objection += 18.0
    if safe_text(_field(setup, "decision")).upper() == "REJECT":
        objection += 22.0
    for key in ["scenario_bias", "liquidity_bias", "news_bias", "calendar_bias", "options_flow_bias"]:
        if safe_text(_field(setup, key)).upper() in {"BEARISH", "REJECT"}:
            objection += 8.0
    objection = clamp(objection)
    arguments = []
    if objection >= 60:
        arguments.append("Bearish case sees weak score, poor bias, or rejected setup state.")
    else:
        arguments.append("Bearish objection is limited.")
    return {
        "stance": "OBJECT" if objection >= 65 else "CHALLENGE" if objection >= 45 else "LOW_OBJECTION",
        "objection_score": round(objection, 2),
        "arguments": arguments,
    }


def run_risk_objection_agent(setup=None, context=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    rr = safe_float(_field(setup, "rr"), 0.0)
    heat = max(safe_float(_field(setup, "portfolio_heat_score"), 0.0), safe_float(context.get("portfolio_heat_score"), 0.0))
    drawdown = max(safe_float(_field(setup, "drawdown_pct"), 0.0), safe_float(context.get("drawdown_pct"), 0.0))
    event_risk = _score_field(setup, "event_risk_score", safe_float(context.get("event_risk_score"), 0.0))
    objection = 20.0
    if rr and rr < 1.3:
        objection += 24.0
    if heat >= 70.0:
        objection += 22.0
    if drawdown >= 5.0:
        objection += 18.0
    if event_risk >= 70.0:
        objection += 16.0
    objection = clamp(objection)
    return {
        "stance": "OBJECT" if objection >= 65 else "REVIEW" if objection >= 45 else "CLEAR",
        "objection_score": round(objection, 2),
        "risk_factors": {"rr": rr, "portfolio_heat_score": heat, "drawdown_pct": drawdown, "event_risk_score": event_risk},
    }


def run_execution_objection_agent(setup=None, context=None):
    setup = _as_dict(setup)
    spread = safe_float(_field(setup, "spread_pct"), safe_float(_as_dict(context).get("spread_pct"), 0.0))
    slippage = safe_float(_field(setup, "slippage_pct"), safe_float(_as_dict(context).get("slippage_pct"), 0.0))
    chase = safe_float(_field(setup, "chase_risk_score"), 0.0)
    objection = 12.0 + _warning_points(_field(setup, "liquidity_warning")) + _warning_points(_field(setup, "microstructure_warning"))
    if spread >= 0.35:
        objection += 18.0
    if slippage >= 0.25:
        objection += 16.0
    if chase >= 65.0:
        objection += 18.0
    objection = clamp(objection)
    return {
        "stance": "OBJECT" if objection >= 65 else "REVIEW" if objection >= 40 else "CLEAR",
        "objection_score": round(objection, 2),
        "execution_risks": {"spread_pct": spread, "slippage_pct": slippage, "chase_risk_score": chase},
    }


def run_news_objection_agent(setup=None, context=None):
    setup = _as_dict(setup)
    credibility = _score_field(setup, "news_credibility_score", 50.0)
    sentiment = _score_field(setup, "news_sentiment_score", _score_field(setup, "news_intelligence_score", 50.0))
    objection = 15.0 + _warning_points(_field(setup, "news_warning"))
    if safe_text(_field(setup, "news_bias")).upper() == "BEARISH":
        objection += 16.0
    if credibility < 35.0:
        objection += 16.0
    if sentiment < 40.0:
        objection += 12.0
    objection = clamp(objection)
    return {
        "stance": "OBJECT" if objection >= 65 else "REVIEW" if objection >= 40 else "CLEAR",
        "objection_score": round(objection, 2),
        "news_state": {"sentiment_score": sentiment, "credibility_score": credibility, "warning": safe_text(_field(setup, "news_warning") or "NONE")},
    }


def run_portfolio_objection_agent(setup=None, context=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    heat = max(safe_float(_field(setup, "portfolio_heat_score"), 0.0), safe_float(context.get("portfolio_heat_score"), 0.0))
    concentration = max(safe_float(_field(setup, "concentration_score"), 0.0), safe_float(context.get("concentration_score"), 0.0))
    crowding = safe_float(_field(setup, "crowding_score"), safe_float(context.get("crowding_score"), 0.0))
    objection = 12.0 + _warning_points(_field(setup, "portfolio_warning"))
    if heat >= 70.0:
        objection += 22.0
    if concentration >= 65.0:
        objection += 18.0
    if crowding >= 65.0:
        objection += 16.0
    objection = clamp(objection)
    return {
        "stance": "OBJECT" if objection >= 65 else "REVIEW" if objection >= 40 else "CLEAR",
        "objection_score": round(objection, 2),
        "portfolio_state": {"portfolio_heat_score": heat, "concentration_score": concentration, "crowding_score": crowding},
    }


def run_regime_objection_agent(setup=None, context=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    regime_text = " ".join(
        [
            safe_text(_field(setup, "regime")),
            safe_text(_field(setup, "market_regime")),
            safe_text(context.get("regime")),
            safe_text(context.get("market_regime")),
            safe_text(context.get("setup_environment")),
        ]
    )
    objection = 12.0 + _warning_points(_field(setup, "scenario_warning")) + _warning_points(_field(setup, "calendar_warning"))
    if _contains_any(regime_text, ["chop", "range", "no edge", "volatile", "uncertain", "risk off"]):
        objection += 20.0
    stress = _field(setup, "scenario_stress_risk", {})
    if isinstance(stress, dict) and safe_float(stress.get("stress_risk_score"), 0.0) >= 65.0:
        objection += 18.0
    objection = clamp(objection)
    return {
        "stance": "OBJECT" if objection >= 65 else "REVIEW" if objection >= 40 else "CLEAR",
        "objection_score": round(objection, 2),
        "regime_state": {"regime_text": regime_text.strip() or "UNKNOWN"},
    }


def resolve_agent_contradictions(agent_outputs=None):
    outputs = _as_dict(agent_outputs)
    bullish = safe_float(_as_dict(outputs.get("bullish_agent")).get("support_score"), 50.0)
    objection_scores = [
        safe_float(_as_dict(outputs.get(name)).get("objection_score"), 0.0)
        for name in [
            "bearish_agent",
            "risk_objection_agent",
            "execution_objection_agent",
            "news_objection_agent",
            "portfolio_objection_agent",
            "regime_objection_agent",
        ]
    ]
    avg_objection = sum(objection_scores) / float(len(objection_scores) or 1)
    max_objection = max(objection_scores or [0.0])
    contradictions = []
    if bullish >= 65.0 and avg_objection >= 50.0:
        contradictions.append("Strong bullish support conflicts with broad objection pressure.")
    if bullish >= 70.0 and max_objection >= 70.0:
        contradictions.append("High-conviction upside conflicts with at least one severe objection.")
    net_support = clamp(bullish - (avg_objection * 0.55) + 35.0)
    return {
        "contradictions_found": bool(contradictions),
        "contradiction_count": len(contradictions),
        "net_support_score": round(net_support, 2),
        "average_objection_score": round(avg_objection, 2),
        "max_objection_score": round(max_objection, 2),
        "notes": contradictions or ["No major contradiction detected."],
    }


def run_final_judge_agent(setup=None, agent_outputs=None, context=None):
    outputs = _as_dict(agent_outputs)
    resolution = resolve_agent_contradictions(outputs)
    net = safe_float(resolution.get("net_support_score"), 50.0)
    avg_objection = safe_float(resolution.get("average_objection_score"), 0.0)
    max_objection = safe_float(resolution.get("max_objection_score"), 0.0)
    if max_objection >= 78.0 or (net < 38.0 and avg_objection >= 55.0):
        decision = "REJECT"
        warning = "SKIP"
    elif max_objection >= 65.0 or avg_objection >= 48.0 or net < 52.0:
        decision = "REVIEW"
        warning = "REVIEW"
    else:
        decision = "APPROVE"
        warning = "NONE"
    judge_score = clamp((net * 0.7) + ((100.0 - avg_objection) * 0.3))
    return {
        "decision": decision,
        "warning": warning,
        "judge_score": round(judge_score, 2),
        "rationale": "Approve only when support survives bearish, risk, execution, news, portfolio, and regime objections.",
    }


def calculate_confidence_after_debate(agent_outputs=None, judge_output=None):
    outputs = _as_dict(agent_outputs)
    judge = _as_dict(judge_output)
    resolution = resolve_agent_contradictions(outputs)
    judge_score = safe_float(judge.get("judge_score"), 50.0)
    net = safe_float(resolution.get("net_support_score"), 50.0)
    confidence = (judge_score * 0.65) + (net * 0.35)
    confidence -= safe_float(resolution.get("contradiction_count"), 0.0) * 6.0
    if safe_text(judge.get("decision")).upper() == "REJECT":
        confidence -= 12.0
    return round(clamp(confidence), 2)


def run_adversarial_reasoning(setup=None, context=None):
    agents = {
        "risk": run_risk_objection_agent(setup, context),
        "execution": run_execution_objection_agent(setup, context),
        "news": run_news_objection_agent(setup, context),
        "portfolio": run_portfolio_objection_agent(setup, context),
        "regime": run_regime_objection_agent(setup, context),
    }
    risks = []
    for name, output in agents.items():
        score = safe_float(output.get("objection_score"), 0.0)
        if score >= 45.0:
            risks.append({"area": name, "risk_score": round(score, 2), "stance": output.get("stance")})
    top_score = max([safe_float(item.get("risk_score"), 0.0) for item in risks] or [0.0])
    return {
        "adversarial_risk_score": round(clamp(top_score), 2),
        "failure_modes": risks or [{"area": "none", "risk_score": 0.0, "stance": "LOW"}],
        "summary": "Adversarial pass checks how the setup can fail before ranking blend.",
    }


def _save_report(report):
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)
    except Exception:
        pass


def build_multi_agent_debate_report(setup=None, context=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    mode = _data_mode(setup, context)
    explanations: List[str] = []

    bullish = run_bullish_agent(setup, context)
    bearish = run_bearish_agent(setup, context)
    risk = run_risk_objection_agent(setup, context)
    execution = run_execution_objection_agent(setup, context)
    news = run_news_objection_agent(setup, context)
    portfolio = run_portfolio_objection_agent(setup, context)
    regime = run_regime_objection_agent(setup, context)
    outputs = {
        "bullish_agent": bullish,
        "bearish_agent": bearish,
        "risk_objection_agent": risk,
        "execution_objection_agent": execution,
        "news_objection_agent": news,
        "portfolio_objection_agent": portfolio,
        "regime_objection_agent": regime,
    }
    resolution = resolve_agent_contradictions(outputs)
    judge = run_final_judge_agent(setup, outputs, context)
    adversarial = run_adversarial_reasoning(setup, context)
    confidence = calculate_confidence_after_debate(outputs, judge)

    judge_score = safe_float(judge.get("judge_score"), 50.0)
    debate_score = (judge_score * 0.6) + (confidence * 0.4)
    warning = safe_text(judge.get("warning") or "REVIEW").upper()
    bias = safe_text(judge.get("decision") or "REVIEW").upper()

    if mode == "INSUFFICIENT":
        debate_score = 50.0
        bias = "REVIEW"
        warning = "REVIEW"
        explanations.append("Insufficient setup/context data; debate remains neutral and non-blocking.")
    elif mode == "PROXY":
        explanations.append("Proxy debate used partial setup/context fields.")
    else:
        explanations.append("Real context debate used rich candidate intelligence fields.")

    if warning == "SKIP":
        debate_score -= 20.0
        explanations.append("Final judge rejected the setup; ranking blend receives safe reduction.")
    elif warning in {"WAIT", "REVIEW"} and mode != "INSUFFICIENT":
        debate_score -= 6.0
        explanations.append("Final judge requested review/wait; small ranking penalty applied.")

    debate_score = round(clamp(debate_score), 2)
    explanations.extend(safe_list(resolution.get("notes")))

    report = {
        "symbol": _symbol(setup),
        "debate_data_mode": mode,
        "bullish_agent": bullish,
        "bearish_agent": bearish,
        "risk_objection_agent": risk,
        "execution_objection_agent": execution,
        "news_objection_agent": news,
        "portfolio_objection_agent": portfolio,
        "regime_objection_agent": regime,
        "contradiction_resolution": resolution,
        "final_judge": judge,
        "adversarial_reasoning": adversarial,
        "confidence_after_debate": confidence,
        "debate_score": debate_score,
        "debate_bias": bias if bias in {"APPROVE", "REJECT", "REVIEW"} else "REVIEW",
        "debate_warning": warning if warning in {"NONE", "WAIT", "SKIP", "REVIEW"} else "REVIEW",
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
        "rr": 2.1,
        "scenario_score": 68,
        "liquidity_map_score": 63,
        "news_intelligence_score": 61,
        "news_credibility_score": 74,
        "calendar_intelligence_score": 58,
        "portfolio_heat_score": 35,
        "scenario_warning": "NONE",
        "liquidity_warning": "REVIEW",
    }
    sample_context = {
        "market_regime": "trend",
        "trading_mode": "SELECTIVE",
        "portfolio_heat_score": 32,
    }
    print(json.dumps(build_multi_agent_debate_report(sample_setup, sample_context), indent=2, sort_keys=True))
