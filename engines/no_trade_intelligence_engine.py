"""
TITAN Phase 35 - No-Trade Intelligence Engine

Protective market-condition layer. High no_trade_score means higher danger.
This engine never places orders and always keeps live execution disabled.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List


REPORT_PATH = os.path.join("data", "no_trade", "latest_no_trade_intelligence_report.json")


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


def _warning_score(value):
    text = safe_text(value).upper()
    if text == "SKIP":
        return 35.0
    if text == "WAIT":
        return 24.0
    if text == "REVIEW":
        return 14.0
    return 0.0


def _contains_any(text, words):
    text = safe_text(text).lower()
    return any(word in text for word in words)


def normalize_no_trade_inputs(setup=None, context=None, recent_setups=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    recent = [item for item in safe_list(recent_setups or context.get("recent_setups")) if isinstance(item, dict)]
    return {
        "setup": dict(setup),
        "context": dict(context),
        "recent_setups": recent,
        "symbol": _symbol(setup),
    }


def _data_mode(setup, context, recent_setups):
    setup = _as_dict(setup)
    context = _as_dict(context)
    recent = safe_list(recent_setups)
    rich_keys = [
        "market_regime",
        "setup_environment",
        "breadth_score",
        "advance_decline_ratio",
        "news_chaos_score",
        "vix",
        "volatility_score",
        "liquidity_score",
        "market_toxicity_score",
        "trading_mode",
    ]
    setup_keys = [
        "debate_warning",
        "reflection_warning",
        "calibration_warning",
        "liquidity_warning",
        "news_warning",
        "scenario_warning",
        "calendar_warning",
        "no_trade_score",
    ]
    context_count = sum(1 for key in rich_keys if context.get(key) not in (None, "", [], {}))
    setup_count = sum(1 for key in setup_keys if _field(setup, key) not in (None, "", [], {}))
    if context_count >= 4 or len(recent) >= 3 or (context_count >= 2 and setup_count >= 2):
        return "REAL_CONTEXT"
    if context_count >= 1 or setup_count >= 1 or recent:
        return "PROXY"
    return "INSUFFICIENT"


def detect_low_edge_day(context=None, recent_setups=None):
    context = _as_dict(context)
    recent = [item for item in safe_list(recent_setups) if isinstance(item, dict)]
    avg_score = 50.0
    if recent:
        scores = [safe_float(item.get("score") or item.get("final_score") or item.get("final_calibration_rank"), 0.0) for item in recent]
        scores = [score for score in scores if score > 0.0]
        if scores:
            avg_score = sum(scores) / len(scores)
    trading_mode = safe_text(context.get("trading_mode")).upper()
    edge_score = safe_float(context.get("edge_score"), avg_score)
    no_edge = edge_score < 42.0 or trading_mode in {"NO_TRADE", "OBSERVE_ONLY"} or _contains_any(context.get("setup_environment"), ["no edge", "degraded"])
    danger = clamp(100.0 - edge_score + (18.0 if no_edge else 0.0))
    return {
        "is_low_edge_day": bool(no_edge),
        "edge_score": round(clamp(edge_score), 2),
        "average_recent_setup_score": round(clamp(avg_score), 2),
        "danger_score": round(danger, 2),
    }


def detect_choppy_market(context=None):
    context = _as_dict(context)
    regime_text = " ".join(
        [
            safe_text(context.get("market_regime")),
            safe_text(context.get("regime")),
            safe_text(context.get("setup_environment")),
        ]
    )
    volatility = safe_float(context.get("volatility_score") or context.get("vix"), 0.0)
    chop = _contains_any(regime_text, ["chop", "range", "sideways", "no edge", "uncertain"]) or volatility >= 75.0
    danger = 25.0 + (35.0 if chop else 0.0) + (10.0 if volatility >= 75.0 else 0.0)
    return {"is_choppy": bool(chop), "regime_text": regime_text.strip() or "UNKNOWN", "volatility_score": volatility, "danger_score": round(clamp(danger), 2)}


def detect_news_chaos(context=None):
    context = _as_dict(context)
    chaos = safe_float(context.get("news_chaos_score"), 0.0)
    panic = safe_float(context.get("panic_news_score"), 0.0)
    count = len(safe_list(context.get("news_items") or context.get("news")))
    warning = safe_text(context.get("news_warning")).upper()
    danger = max(chaos, panic)
    if count >= 12:
        danger += 12.0
    danger += _warning_score(warning)
    return {"is_news_chaos": clamp(danger) >= 55.0, "news_item_count": count, "danger_score": round(clamp(danger), 2)}


def detect_liquidity_danger(setup=None, context=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    liquidity_score = safe_float(_field(setup, "liquidity_map_score", context.get("liquidity_score")), 50.0)
    spread = safe_float(_field(setup, "spread_pct", context.get("spread_pct")), 0.0)
    danger = (100.0 - liquidity_score) * 0.55 + _warning_score(_field(setup, "liquidity_warning"))
    if spread >= 0.35:
        danger += 18.0
    return {"is_liquidity_danger": clamp(danger) >= 55.0, "liquidity_score": round(clamp(liquidity_score), 2), "spread_pct": spread, "danger_score": round(clamp(danger), 2)}


def detect_contradiction_overload(setup=None, context=None):
    setup = _as_dict(setup)
    contradiction = _field(setup, "debate_contradiction_resolution", {})
    count = safe_float(_as_dict(contradiction).get("contradiction_count"), 0.0)
    avg_objection = safe_float(_as_dict(contradiction).get("average_objection_score"), 0.0)
    warnings = sum(
        1
        for key in ["debate_warning", "reflection_warning", "calibration_warning", "scenario_warning", "calendar_warning", "news_warning"]
        if safe_text(_field(setup, key)).upper() in {"SKIP", "WAIT", "REVIEW"}
    )
    danger = count * 18.0 + avg_objection * 0.45 + warnings * 8.0
    return {"is_contradiction_overload": clamp(danger) >= 55.0, "contradiction_count": int(count), "warning_count": warnings, "danger_score": round(clamp(danger), 2)}


def detect_weak_breadth(context=None):
    context = _as_dict(context)
    breadth = safe_float(context.get("breadth_score"), 50.0)
    adr = safe_float(context.get("advance_decline_ratio"), 1.0)
    weak = breadth < 40.0 or adr < 0.75
    danger = (100.0 - breadth) * 0.55 + (18.0 if adr < 0.75 else 0.0)
    return {"is_weak_breadth": bool(weak), "breadth_score": round(clamp(breadth), 2), "advance_decline_ratio": adr, "danger_score": round(clamp(danger), 2)}


def apply_uncertainty_no_trade_rules(setup=None, context=None):
    setup = _as_dict(setup)
    uncertainty = max(
        safe_float(_field(setup, "probability_uncertainty"), 0.0),
        safe_float(_field(setup, "uncertainty_score"), 0.0),
        safe_float(context.get("uncertainty_score") if isinstance(context, dict) else 0.0, 0.0),
    )
    calibration = safe_text(_field(setup, "calibration_warning")).upper()
    danger = uncertainty * 0.75 + _warning_score(calibration)
    return {"uncertainty_score": round(clamp(uncertainty), 2), "rule_triggered": clamp(danger) >= 55.0, "danger_score": round(clamp(danger), 2)}


def calculate_wait_mode_intelligence(setup=None, context=None):
    setup = _as_dict(setup)
    wait_reasons = []
    for key in ["calendar_warning", "scenario_warning", "debate_warning", "reflection_warning", "calibration_warning"]:
        warning = safe_text(_field(setup, key)).upper()
        if warning == "WAIT":
            wait_reasons.append(key)
    if safe_text(_as_dict(context).get("trading_mode")).upper() in {"SELECTIVE", "OBSERVE_ONLY"}:
        wait_reasons.append("trading_mode")
    wait_score = clamp(len(wait_reasons) * 20.0 + _warning_score(_field(setup, "no_trade_warning")))
    return {"wait_recommended": wait_score >= 35.0, "wait_score": round(wait_score, 2), "wait_reasons": wait_reasons}


def detect_overtrading_risk(recent_setups=None, context=None):
    context = _as_dict(context)
    recent = [item for item in safe_list(recent_setups or context.get("recent_setups")) if isinstance(item, dict)]
    trades_today = safe_float(context.get("trades_today") or context.get("alerts_sent_today"), len(recent))
    rejected_count = sum(1 for item in recent if safe_text(item.get("decision")).upper() == "REJECT")
    danger = trades_today * 8.0 + rejected_count * 3.0
    if trades_today >= 5.0:
        danger += 20.0
    return {"is_overtrading_risk": clamp(danger) >= 55.0, "trades_today": trades_today, "recent_setup_count": len(recent), "danger_score": round(clamp(danger), 2)}


def detect_market_toxicity(context=None):
    context = _as_dict(context)
    toxicity = safe_float(context.get("market_toxicity_score"), 0.0)
    vix = safe_float(context.get("vix") or context.get("volatility_score"), 0.0)
    gap = abs(safe_float(context.get("gap_pct"), 0.0))
    danger = max(toxicity, vix)
    if gap >= 1.5:
        danger += 16.0
    if _contains_any(context.get("market_regime"), ["panic", "crash", "risk off"]):
        danger += 25.0
    return {"is_toxic": clamp(danger) >= 60.0, "market_toxicity_score": round(clamp(toxicity), 2), "vix_or_volatility": vix, "danger_score": round(clamp(danger), 2)}


def _save_report(report):
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    except Exception:
        pass


def build_no_trade_intelligence_report(setup=None, context=None, recent_setups=None):
    setup = _as_dict(setup)
    context = _as_dict(context)
    recent = safe_list(recent_setups or context.get("recent_setups"))
    mode = _data_mode(setup, context, recent)
    explanations: List[str] = []

    low_edge = detect_low_edge_day(context, recent)
    choppy = detect_choppy_market(context)
    news = detect_news_chaos(context)
    liquidity = detect_liquidity_danger(setup, context)
    contradiction = detect_contradiction_overload(setup, context)
    breadth = detect_weak_breadth(context)
    uncertainty = apply_uncertainty_no_trade_rules(setup, context)
    wait_mode = calculate_wait_mode_intelligence(setup, context)
    overtrading = detect_overtrading_risk(recent, context)
    toxicity = detect_market_toxicity(context)

    danger_scores = [
        low_edge.get("danger_score", 0.0),
        choppy.get("danger_score", 0.0),
        news.get("danger_score", 0.0),
        liquidity.get("danger_score", 0.0),
        contradiction.get("danger_score", 0.0),
        breadth.get("danger_score", 0.0),
        uncertainty.get("danger_score", 0.0),
        wait_mode.get("wait_score", 0.0),
        overtrading.get("danger_score", 0.0),
        toxicity.get("danger_score", 0.0),
    ]
    no_trade_score = sum(safe_float(score) for score in danger_scores) / float(len(danger_scores))
    severe = any(
        [
            low_edge.get("is_low_edge_day"),
            choppy.get("is_choppy") and toxicity.get("is_toxic"),
            contradiction.get("is_contradiction_overload"),
            liquidity.get("is_liquidity_danger") and breadth.get("is_weak_breadth"),
        ]
    )

    if mode == "INSUFFICIENT":
        no_trade_score = 20.0
        permission = "REVIEW"
        warning = "REVIEW"
        explanations.append("Insufficient no-trade data; neutral review state applied without aggressive blocking.")
    else:
        if no_trade_score >= 70.0 or severe:
            permission = "BLOCK"
            warning = "SKIP"
        elif no_trade_score >= 50.0 or wait_mode.get("wait_recommended") or overtrading.get("is_overtrading_risk"):
            permission = "WAIT"
            warning = "WAIT"
        elif no_trade_score >= 35.0 or news.get("is_news_chaos") or breadth.get("is_weak_breadth"):
            permission = "REVIEW"
            warning = "REVIEW"
        else:
            permission = "ALLOW"
            warning = "NONE"
        explanations.append(f"{mode} no-trade scan evaluated market safety and setup contradiction risk.")
        if low_edge.get("is_low_edge_day"):
            explanations.append("Low-edge day detected; alerts should be blocked while research continues.")
        if toxicity.get("is_toxic"):
            explanations.append("Market toxicity elevated.")
        if choppy.get("is_choppy"):
            explanations.append("Choppy or uncertain market regime detected.")

    report = {
        "symbol": _symbol(setup),
        "no_trade_data_mode": mode,
        "low_edge_day": low_edge,
        "choppy_market": choppy,
        "news_chaos": news,
        "liquidity_danger": liquidity,
        "contradiction_overload": contradiction,
        "weak_breadth": breadth,
        "uncertainty_rules": uncertainty,
        "wait_mode": wait_mode,
        "overtrading_risk": overtrading,
        "market_toxicity": toxicity,
        "no_trade_score": round(clamp(no_trade_score), 2),
        "trade_permission": permission,
        "no_trade_warning": warning,
        "live_order_allowed": False,
        "explanations": explanations,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_report(report)
    return report


if __name__ == "__main__":
    sample_setup = {
        "symbol": "TITAN",
        "liquidity_map_score": 42,
        "liquidity_warning": "REVIEW",
        "debate_warning": "REVIEW",
        "calibration_warning": "NONE",
    }
    sample_context = {
        "market_regime": "choppy range",
        "breadth_score": 36,
        "advance_decline_ratio": 0.68,
        "news_chaos_score": 58,
        "trading_mode": "SELECTIVE",
        "volatility_score": 64,
        "trades_today": 4,
    }
    sample_recent_setups = [
        {"symbol": "A", "score": 38, "decision": "REJECT"},
        {"symbol": "B", "score": 44, "decision": "DOWNGRADE"},
        {"symbol": "C", "score": 41, "decision": "REJECT"},
    ]
    print(json.dumps(build_no_trade_intelligence_report(sample_setup, sample_context, sample_recent_setups), indent=2, sort_keys=True))
