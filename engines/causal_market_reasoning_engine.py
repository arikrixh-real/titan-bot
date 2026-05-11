"""
TITAN Phase 16 Step 1 - Causal Market Reasoning Engine
------------------------------------------------------

Standalone, rule-based engine for explaining why a setup may move.
This module does not change scanning, Telegram, dashboard, execution,
broker behavior, or alert caps. Every function fails open and returns
safe neutral structures for missing or invalid inputs.
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


def safe_text(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def clamp(value: Any, min_value: float = 0.0, max_value: float = 1.0) -> float:
    value = safe_float(value, min_value)
    low = safe_float(min_value, 0.0)
    high = safe_float(max_value, 1.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, value))


POSITIVE_WORDS = {
    "rise", "rises", "gain", "gains", "surge", "surges", "beats", "strong",
    "growth", "upgrade", "order", "deal", "approval", "record", "boost",
}

NEGATIVE_WORDS = {
    "fall", "falls", "drop", "drops", "weak", "loss", "miss", "cuts",
    "downgrade", "probe", "fraud", "penalty", "debt", "pressure", "war",
}

FALSE_NEWS_WORDS = {
    "rumour", "rumor", "unverified", "sources", "may", "could", "likely",
    "speculation", "denies", "clarifies", "fake",
}

MACRO_WORDS = {
    "rbi", "fed", "inflation", "rate", "rates", "bond", "yield", "crude",
    "dollar", "rupee", "budget", "policy", "geopolitical",
}

EVENT_WORDS = {
    "earnings": "EARNINGS",
    "result": "EARNINGS",
    "order": "ORDER_DEAL",
    "deal": "ORDER_DEAL",
    "approval": "REGULATORY",
    "rbi": "POLICY",
    "fed": "GLOBAL_MACRO",
    "merger": "CORPORATE_ACTION",
    "acquisition": "CORPORATE_ACTION",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _lower_blob(*values: Any) -> str:
    return " ".join(safe_text(value).lower() for value in values if safe_text(value))


def _setup_symbol(setup: Dict[str, Any]) -> str:
    return safe_text(setup.get("symbol") or setup.get("stock") or setup.get("ticker"), "UNKNOWN").upper()


def _setup_sector(setup: Dict[str, Any], context: Dict[str, Any]) -> str:
    for source in [setup, context, _as_dict(setup.get("raw"))]:
        sector = source.get("sector") or source.get("industry") or source.get("sector_name")
        if sector:
            return safe_text(sector, "UNKNOWN")
    return "UNKNOWN"


def _score_words(text: str) -> Dict[str, int]:
    words = set(text.lower().replace("/", " ").replace("-", " ").split())
    positive = sum(1 for word in POSITIVE_WORDS if word in words)
    negative = sum(1 for word in NEGATIVE_WORDS if word in words)
    macro = sum(1 for word in MACRO_WORDS if word in words)
    caution = sum(1 for word in FALSE_NEWS_WORDS if word in words)
    return {"positive": positive, "negative": negative, "macro": macro, "caution": caution}


def _news_matches(news: Dict[str, Any], symbol: str, sector: str) -> Dict[str, bool]:
    title = safe_text(news.get("title"))
    summary = safe_text(news.get("summary"))
    text = _lower_blob(title, summary)
    symbols = [safe_text(item).upper() for item in _as_list(news.get("detected_symbols"))]
    sectors = [safe_text(item).lower() for item in _as_list(news.get("sectors"))]
    return {
        "symbol": symbol != "UNKNOWN" and (symbol in symbols or symbol.lower() in text),
        "sector": sector != "UNKNOWN" and (sector.lower() in text or any(sector.lower() in item for item in sectors)),
        "macro": bool(_score_words(text)["macro"]),
    }


def detect_news_to_sector_stock_chain(news_items: Any, setup: Any, context: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    symbol = _setup_symbol(setup)
    sector = _setup_sector(setup, context)
    matched = []

    for item in _as_list(news_items):
        if not isinstance(item, dict):
            continue
        match = _news_matches(item, symbol, sector)
        if not any(match.values()):
            continue
        text = _lower_blob(item.get("title"), item.get("summary"))
        word_scores = _score_words(text)
        matched.append({
            "title": safe_text(item.get("title"), "Untitled"),
            "link": safe_text(item.get("link")),
            "match_type": [key for key, active in match.items() if active],
            "sentiment_bias": "BULLISH" if word_scores["positive"] > word_scores["negative"] else "BEARISH" if word_scores["negative"] > word_scores["positive"] else "NEUTRAL",
        })

    strength = min(100.0, len(matched) * 25.0)
    return {
        "active": bool(matched),
        "symbol": symbol,
        "sector": sector,
        "matched_news_count": len(matched),
        "chain_strength": round(strength, 2),
        "chain": matched[:5],
    }


def detect_index_sector_stock_causality(setup: Any, context: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    side = safe_text(setup.get("side"), "UNKNOWN").upper()
    market_bias = safe_text(context.get("market_bias") or context.get("market_type") or context.get("market_regime"), "NEUTRAL").upper()
    index_strength = safe_float(context.get("index_strength") or context.get("nifty_strength"), 50.0)
    sector_strength = safe_float(context.get("sector_strength") or context.get("sector_strength_score"), 50.0)
    stock_strength = safe_float(setup.get("relative_strength") or setup.get("score"), 50.0)

    bullish_alignment = side == "LONG" and index_strength >= 55 and sector_strength >= 55
    bearish_alignment = side == "SHORT" and index_strength <= 45 and sector_strength <= 45
    aligned = bullish_alignment or bearish_alignment
    causal_score = (abs(index_strength - 50.0) + abs(sector_strength - 50.0) + abs(stock_strength - 50.0)) / 1.5

    return {
        "active": aligned,
        "market_bias": market_bias,
        "index_strength": round(index_strength, 2),
        "sector_strength": round(sector_strength, 2),
        "stock_strength": round(stock_strength, 2),
        "causal_alignment": "ALIGNED" if aligned else "MIXED",
        "causal_score": round(clamp(causal_score, 0.0, 100.0), 2),
    }


def detect_sector_leadership_cause(setup: Any, context: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    sector = _setup_sector(setup, context)
    sector_rank = safe_float(context.get("sector_rank"), 50.0)
    sector_strength = safe_float(context.get("sector_strength") or context.get("sector_strength_score"), 50.0)
    relative_strength = safe_float(setup.get("relative_strength") or setup.get("score"), 50.0)
    leadership_score = (sector_strength * 0.55) + (relative_strength * 0.35) + ((100.0 - sector_rank) * 0.10)

    return {
        "active": leadership_score >= 60.0,
        "sector": sector,
        "sector_rank": round(sector_rank, 2),
        "sector_strength": round(sector_strength, 2),
        "relative_strength": round(relative_strength, 2),
        "leadership_score": round(clamp(leadership_score, 0.0, 100.0), 2),
    }


def explain_market_wide_pressure(setup: Any, context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    pressure_sources = []
    vix = safe_float(context.get("vix"), 18.0)
    breadth = safe_float(context.get("breadth"), 50.0)
    volatility = safe_float(context.get("volatility"), 50.0)
    global_bias = safe_text(context.get("global_bias") or context.get("risk_tone"), "NEUTRAL").upper()

    if vix >= 20:
        pressure_sources.append("High VIX")
    if breadth <= 40:
        pressure_sources.append("Weak breadth")
    if volatility >= 65:
        pressure_sources.append("Volatility expansion")
    if "RISK_OFF" in global_bias or "BEAR" in global_bias:
        pressure_sources.append("Risk-off global tone")

    pressure_score = min(100.0, (max(vix - 12.0, 0.0) * 2.0) + max(50.0 - breadth, 0.0) + (volatility * 0.35))
    return {
        "active": bool(pressure_sources),
        "pressure_score": round(pressure_score, 2),
        "pressure_sources": pressure_sources,
        "market_tone": global_bias,
    }


def classify_event_driven_move(news_items: Any, setup: Any, context: Any) -> str:
    del setup, context
    for item in _as_list(news_items):
        if not isinstance(item, dict):
            continue
        text = _lower_blob(item.get("title"), item.get("summary"))
        for word, event_type in EVENT_WORDS.items():
            if word in text:
                return event_type
    return "NO_CLEAR_EVENT"


def detect_false_news_caution(news_items: Any) -> Dict[str, Any]:
    caution_items = []
    for item in _as_list(news_items):
        if not isinstance(item, dict):
            continue
        text = _lower_blob(item.get("title"), item.get("summary"))
        caution_score = _score_words(text)["caution"]
        if caution_score:
            caution_items.append({
                "title": safe_text(item.get("title"), "Untitled"),
                "caution_terms": caution_score,
            })

    return {
        "active": bool(caution_items),
        "caution_score": round(min(100.0, len(caution_items) * 30.0), 2),
        "items": caution_items[:5],
    }


def calculate_cause_confidence(causal_factors: Any) -> float:
    factors = _as_list(causal_factors)
    if not factors:
        return 0.0

    scores = []
    for factor in factors:
        if not isinstance(factor, dict):
            continue
        for key in ["chain_strength", "causal_score", "leadership_score", "confidence", "pressure_score"]:
            if key in factor:
                scores.append(clamp(safe_float(factor.get(key)), 0.0, 100.0))
                break
        if factor.get("active") is True and not any(key in factor for key in ["chain_strength", "causal_score", "leadership_score", "confidence", "pressure_score"]):
            scores.append(55.0)

    if not scores:
        return 0.0
    return round(clamp(sum(scores) / len(scores), 0.0, 100.0), 2)


def build_cause_effect_map(news_items: Any, setup: Any, context: Any) -> List[Dict[str, Any]]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    symbol = _setup_symbol(setup)
    sector = _setup_sector(setup, context)
    items = []

    for news in _as_list(news_items):
        if not isinstance(news, dict):
            continue
        match = _news_matches(news, symbol, sector)
        if not any(match.values()):
            continue
        text = _lower_blob(news.get("title"), news.get("summary"))
        word_scores = _score_words(text)
        effect = "UPWARD_PRESSURE" if word_scores["positive"] > word_scores["negative"] else "DOWNWARD_PRESSURE" if word_scores["negative"] > word_scores["positive"] else "ATTENTION_ONLY"
        items.append({
            "cause": safe_text(news.get("title"), "Matched news"),
            "transmission": "news -> sector -> stock" if match["sector"] else "news -> stock" if match["symbol"] else "macro news -> market",
            "expected_effect": effect,
            "affected_symbol": symbol,
            "affected_sector": sector,
        })

    if not items:
        items.append({
            "cause": "Index/sector context",
            "transmission": "market context -> sector/stock risk appetite",
            "expected_effect": "CONTEXTUAL_PRESSURE",
            "affected_symbol": symbol,
            "affected_sector": sector,
        })

    return items[:10]


def track_delayed_effect_potential(news_items: Any, setup: Any, context: Any) -> Dict[str, Any]:
    event_type = classify_event_driven_move(news_items, setup, context)
    delayed_events = {"POLICY", "GLOBAL_MACRO", "REGULATORY", "ORDER_DEAL"}
    count = len(_as_list(news_items))
    potential = event_type in delayed_events or count >= 3
    return {
        "active": potential,
        "event_type": event_type,
        "watch_window": "1-3 sessions" if potential else "intraday only",
        "reason": "Policy, macro, regulatory, or repeated news can transmit with delay." if potential else "No delayed catalyst detected.",
    }


def detect_secondary_impacts(news_items: Any, setup: Any, context: Any) -> List[Dict[str, Any]]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    sector = _setup_sector(setup, context)
    impacts = []
    text = _lower_blob(*[f"{item.get('title', '')} {item.get('summary', '')}" for item in _as_list(news_items) if isinstance(item, dict)])

    if "crude" in text or "oil" in text:
        impacts.append({"source": "Crude/oil move", "possible_impact": "Affects energy, paints, aviation, and inflation-sensitive sectors."})
    if "rate" in text or "rbi" in text or "fed" in text:
        impacts.append({"source": "Rate/policy move", "possible_impact": "Affects banks, NBFCs, real estate, autos, and market multiples."})
    if sector != "UNKNOWN":
        impacts.append({"source": f"{sector} move", "possible_impact": "Peer stocks may react through sector sympathy."})

    return impacts[:6]


def detect_cascading_event_risk(news_items: Any, setup: Any, context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    false_news = detect_false_news_caution(news_items)
    market_pressure = explain_market_wide_pressure(setup, context)
    event_type = classify_event_driven_move(news_items, setup, context)
    risk_score = 0.0
    reasons = []

    if false_news.get("active"):
        risk_score += 25.0
        reasons.append("News reliability caution")
    if market_pressure.get("pressure_score", 0) >= 55:
        risk_score += 30.0
        reasons.append("Market-wide pressure can spread")
    if event_type in {"GLOBAL_MACRO", "POLICY", "REGULATORY"}:
        risk_score += 25.0
        reasons.append("Event type can cascade across sectors")

    return {
        "active": risk_score >= 30.0,
        "risk_score": round(clamp(risk_score, 0.0, 100.0), 2),
        "reasons": reasons,
    }


def build_macro_to_micro_chain(setup: Any, context: Any) -> List[str]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    sector = _setup_sector(setup, context)
    symbol = _setup_symbol(setup)
    regime = safe_text(context.get("market_regime") or context.get("market_type"), "neutral market")
    side = safe_text(setup.get("side"), "UNKNOWN")
    return [
        f"Macro/regime backdrop: {regime}",
        f"Index and breadth influence sector appetite for {sector}",
        f"Sector flow influences {symbol}",
        f"Setup side under evaluation: {side}",
    ]


def build_narrative_causality_graph(news_items: Any, setup: Any, context: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    symbol = _setup_symbol(setup)
    sector = _setup_sector(setup, context)
    nodes = [
        {"id": "macro", "label": "Macro/market context"},
        {"id": "index", "label": "Index pressure"},
        {"id": "sector", "label": sector},
        {"id": "stock", "label": symbol},
    ]
    edges = [
        {"from": "macro", "to": "index", "reason": "Risk appetite transmission"},
        {"from": "index", "to": "sector", "reason": "Market breadth and sector rotation"},
        {"from": "sector", "to": "stock", "reason": "Sector sympathy and relative strength"},
    ]

    if _as_list(news_items):
        nodes.insert(0, {"id": "news", "label": "News catalyst"})
        edges.insert(0, {"from": "news", "to": "sector", "reason": "News affects sector/stock narrative"})

    return {"nodes": nodes, "edges": edges}


def _primary_cause(*factors: Dict[str, Any]) -> str:
    best_name = "Context-only setup"
    best_score = 0.0
    for name, factor in factors:
        if not isinstance(factor, dict):
            continue
        score = max(
            safe_float(factor.get("chain_strength"), 0.0),
            safe_float(factor.get("causal_score"), 0.0),
            safe_float(factor.get("leadership_score"), 0.0),
            safe_float(factor.get("pressure_score"), 0.0),
        )
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


def build_causal_reasoning_report(setup: Any, context: Any, news_items: Any = None) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    news_items = _as_list(news_items)
    symbol = _setup_symbol(setup)
    sector = _setup_sector(setup, context)

    news_chain = detect_news_to_sector_stock_chain(news_items, setup, context)
    index_chain = detect_index_sector_stock_causality(setup, context)
    leadership = detect_sector_leadership_cause(setup, context)
    pressure = explain_market_wide_pressure(setup, context)
    event_classification = classify_event_driven_move(news_items, setup, context)
    false_news = detect_false_news_caution(news_items)
    cause_effect_map = build_cause_effect_map(news_items, setup, context)
    delayed = track_delayed_effect_potential(news_items, setup, context)
    secondary = detect_secondary_impacts(news_items, setup, context)
    cascade = detect_cascading_event_risk(news_items, setup, context)
    macro_chain = build_macro_to_micro_chain(setup, context)
    graph = build_narrative_causality_graph(news_items, setup, context)

    confidence = calculate_cause_confidence([news_chain, index_chain, leadership, pressure])
    primary = _primary_cause(
        ("News-to-sector-stock catalyst", news_chain),
        ("Index-sector-stock alignment", index_chain),
        ("Sector leadership", leadership),
        ("Market-wide pressure", pressure),
    )

    explanations = []
    if news_chain.get("active"):
        explanations.append("Relevant news is linked to the setup symbol, sector, or macro backdrop.")
    if index_chain.get("active"):
        explanations.append("Index and sector conditions align with the setup direction.")
    if leadership.get("active"):
        explanations.append("Sector leadership may be driving stock-level demand.")
    if pressure.get("active"):
        explanations.append("Market-wide pressure can dominate individual setup quality.")
    if not explanations:
        explanations.append("No strong external cause detected; report uses neutral context-based reasoning.")

    return {
        "symbol": symbol,
        "sector": sector,
        "primary_cause": primary,
        "cause_confidence_score": confidence,
        "news_to_sector_stock_chain": news_chain,
        "index_sector_stock_causality": index_chain,
        "sector_leadership_cause": leadership,
        "market_wide_pressure": pressure,
        "event_classification": event_classification,
        "false_news_caution": false_news,
        "cause_effect_map": cause_effect_map,
        "delayed_effect_tracking": delayed,
        "secondary_impacts": secondary,
        "cascading_event_risk": cascade,
        "macro_to_micro_chain": macro_chain,
        "narrative_causality_graph": graph,
        "explanations": explanations,
    }


if __name__ == "__main__":
    sample_setup = {
        "symbol": "RELIANCE",
        "side": "LONG",
        "sector": "Energy / Telecom / Retail",
        "score": 72,
        "relative_strength": 68,
    }
    sample_context = {
        "market_regime": "bullish_trending",
        "index_strength": 64,
        "sector_strength": 70,
        "breadth": 62,
        "vix": 15.5,
        "volatility": 42,
        "risk_tone": "RISK_ON",
        "sector_rank": 12,
    }
    sample_news_items = [
        {
            "title": "Reliance gains after strong retail growth and Jio subscriber additions",
            "summary": "Energy and telecom sentiment improves as broader market stays firm.",
            "detected_symbols": ["RELIANCE"],
            "sectors": ["Energy / Telecom / Retail", "Telecom"],
            "link": "https://example.com/reliance",
        },
        {
            "title": "Crude oil rises as OPEC signals supply cuts",
            "summary": "Energy companies may see margin and sentiment impact.",
            "detected_symbols": [],
            "sectors": ["Oil & Gas"],
            "link": "https://example.com/crude",
        },
    ]

    report = build_causal_reasoning_report(sample_setup, sample_context, sample_news_items)
    print(json.dumps(report, indent=2, ensure_ascii=False))
