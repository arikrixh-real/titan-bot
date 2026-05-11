"""
TITAN Phase 28 - News Intelligence 2.0
--------------------------------------

News intelligence sidecar with sentiment, event, relevance, credibility,
panic/duplicate controls, narrative extraction, and reaction memory. It is
fail-open for TITAN and never enables live execution.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


REPORT_PATH = Path("data/news_intelligence/latest_news_intelligence_2_report.json")

POSITIVE_TERMS = {
    "beat", "beats", "growth", "profit", "profits", "record", "upgrade", "upgraded",
    "approval", "approved", "wins", "order win", "contract", "expansion", "buyback",
    "dividend", "strong", "surge", "rises", "rally", "bullish", "partnership",
}
NEGATIVE_TERMS = {
    "miss", "loss", "losses", "downgrade", "downgraded", "probe", "fraud",
    "default", "debt", "fire", "accident", "resigns", "resignation", "weak",
    "falls", "slumps", "selloff", "bearish", "penalty", "ban", "lawsuit",
}
PANIC_TERMS = {
    "crash", "panic", "plunge", "collapse", "fraud", "default", "bankruptcy",
    "raid", "ban", "scam", "massive loss", "emergency", "halted",
}
EARNINGS_TERMS = {"earnings", "results", "quarter", "q1", "q2", "q3", "q4", "revenue", "ebitda", "profit"}
EVENT_KEYWORDS = {
    "EARNINGS": EARNINGS_TERMS,
    "REGULATORY": {"rbi", "sebi", "regulator", "approval", "approved", "ban", "penalty", "policy"},
    "ORDER_CONTRACT": {"order", "contract", "deal", "wins", "tender", "project"},
    "MANAGEMENT": {"ceo", "cfo", "resigns", "resignation", "appoints", "management"},
    "M&A": {"merger", "acquisition", "stake", "buyout", "takeover"},
    "MACRO": {"inflation", "rate", "fed", "rbi", "gdp", "currency", "crude", "oil"},
}
HIGH_WEIGHT_SOURCES = {
    "reuters", "bloomberg", "exchange", "nse", "bse", "company filing",
    "economic times", "business standard", "moneycontrol", "livemint",
}
LOW_WEIGHT_SOURCES = {"twitter", "x.com", "telegram", "whatsapp", "reddit", "unknown", "blog"}


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


def safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def clamp(value: Any, min_value: float = 0.0, max_value: float = 100.0) -> float:
    low = safe_float(min_value, 0.0)
    high = safe_float(max_value, 100.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, safe_float(value, low)))


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _lower_blob(*values: Any) -> str:
    return " ".join(safe_text(value) for value in values if value is not None).lower()


def _first(data: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return default


def _hash_text(text: str) -> str:
    return hashlib.sha1(safe_text(text).lower().encode("utf-8", errors="ignore")).hexdigest()[:16]


def normalize_news_items(news_items: Any = None) -> List[Dict[str, Any]]:
    raw_items = []
    if isinstance(news_items, dict):
        for key in ("news", "news_items", "items", "data", "articles"):
            if isinstance(news_items.get(key), list):
                raw_items = news_items.get(key)
                break
        if not raw_items and (news_items.get("title") or news_items.get("headline")):
            raw_items = [news_items]
    else:
        raw_items = safe_list(news_items)

    normalized = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = safe_text(_first(item, ["title", "headline", "name"]))
        summary = safe_text(_first(item, ["summary", "description", "body", "content", "text"]))
        if not title and not summary:
            continue
        source = safe_text(_first(item, ["source", "publisher", "provider", "site"]), "unknown")
        symbols = [safe_text(x).upper() for x in safe_list(_first(item, ["symbols", "detected_symbols", "tickers"], [])) if safe_text(x)]
        sectors = [safe_text(x).lower() for x in safe_list(_first(item, ["sectors", "sector_tags"], [])) if safe_text(x)]
        url = safe_text(_first(item, ["url", "link"]))
        timestamp = safe_text(_first(item, ["timestamp", "published_at", "publishedAt", "date", "created_at"]))
        text_hash = safe_text(item.get("news_hash") or item.get("hash") or _hash_text(f"{title} {summary} {url}"))
        normalized.append({
            "title": title,
            "summary": summary,
            "source": source,
            "symbols": symbols,
            "sectors": sectors,
            "url": url,
            "timestamp": timestamp,
            "hash": text_hash,
            "raw": item,
        })
    return normalized


def calculate_source_weight(source: Any = None) -> float:
    text = safe_text(source, "unknown").lower()
    if any(name in text for name in HIGH_WEIGHT_SOURCES):
        return 85.0
    if any(name in text for name in LOW_WEIGHT_SOURCES):
        return 35.0
    if text and text != "unknown":
        return 62.0
    return 45.0


def calculate_news_credibility_score(news_item: Any = None) -> float:
    item = _dict(news_item)
    source_score = calculate_source_weight(item.get("source"))
    url = safe_text(item.get("url"))
    has_symbols = bool(safe_list(item.get("symbols")) or safe_list(item.get("detected_symbols")))
    has_summary = bool(safe_text(item.get("summary") or item.get("description")))
    score = source_score
    if url:
        score += 7.0
    if has_symbols:
        score += 5.0
    if has_summary:
        score += 5.0
    if "rumor" in _lower_blob(item.get("title"), item.get("summary")):
        score -= 20.0
    return round(clamp(score), 2)


def score_news_sentiment(news_item: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    item = _dict(news_item)
    text = _lower_blob(item.get("title"), item.get("summary"), item.get("description"))
    pos = sum(1 for term in POSITIVE_TERMS if term in text)
    neg = sum(1 for term in NEGATIVE_TERMS if term in text)
    raw = 50.0 + (pos - neg) * 12.0
    explicit = item.get("sentiment_score") or item.get("news_score")
    if explicit is not None:
        raw = (raw * 0.45) + (safe_float(explicit, 50.0) * 0.55)
    score = clamp(raw)
    return {
        "score": round(score, 2),
        "bias": "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL",
        "positive_hits": pos,
        "negative_hits": neg,
    }


def classify_news_event(news_item: Any = None) -> str:
    item = _dict(news_item)
    text = _lower_blob(item.get("title"), item.get("summary"), item.get("description"))
    for event, keywords in EVENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return event
    if any(term in text for term in PANIC_TERMS):
        return "PANIC_RISK"
    return "GENERAL_NEWS"


def _parse_time(value: Any) -> datetime | None:
    text = safe_text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def calculate_impact_half_life(news_item: Any = None, context: Any = None) -> Dict[str, Any]:
    event = classify_news_event(news_item)
    base_hours = {
        "EARNINGS": 18.0,
        "REGULATORY": 36.0,
        "ORDER_CONTRACT": 24.0,
        "MANAGEMENT": 18.0,
        "M&A": 48.0,
        "MACRO": 12.0,
        "PANIC_RISK": 8.0,
    }.get(event, 6.0)
    ctx = _dict(context)
    volatility = safe_float(ctx.get("volatility_score") or ctx.get("vix") or ctx.get("india_vix"), 0.0)
    if volatility >= 25.0:
        base_hours *= 0.75
    timestamp = _parse_time(_dict(news_item).get("timestamp") or _dict(news_item).get("published_at"))
    age_hours = 0.0
    if timestamp is not None:
        age_hours = max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds() / 3600.0)
    decay = clamp(100.0 * (0.5 ** (age_hours / max(base_hours, 1.0)))) if age_hours else 100.0
    return {"event_type": event, "half_life_hours": round(base_hours, 2), "age_hours": round(age_hours, 2), "impact_remaining_score": round(decay, 2)}


def calculate_stock_relevance(news_item: Any = None, setup: Any = None) -> float:
    item = _dict(news_item)
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    symbol = safe_text(setup_data.get("symbol") or raw.get("symbol") or setup_data.get("stock") or raw.get("stock")).upper()
    if not symbol:
        return 35.0
    symbols = [safe_text(x).upper() for x in safe_list(item.get("symbols") or item.get("detected_symbols"))]
    text = _lower_blob(item.get("title"), item.get("summary"), item.get("description"))
    if symbol in symbols:
        return 95.0
    if symbol.lower() in text:
        return 85.0
    return 25.0


def calculate_sector_relevance(news_item: Any = None, setup: Any = None, context: Any = None) -> float:
    item = _dict(news_item)
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    ctx = _dict(context)
    sector = safe_text(setup_data.get("sector") or raw.get("sector") or ctx.get("sector")).lower()
    if not sector:
        return 35.0
    sectors = [safe_text(x).lower() for x in safe_list(item.get("sectors") or item.get("sector_tags"))]
    text = _lower_blob(item.get("title"), item.get("summary"), item.get("description"))
    if sector in sectors:
        return 90.0
    if sector and sector in text:
        return 78.0
    return 30.0


def detect_fake_duplicate_news(news_items: Any = None) -> Dict[str, Any]:
    items = normalize_news_items(news_items)
    seen = set()
    duplicates = 0
    low_credibility = 0
    for item in items:
        key = item.get("hash") or _hash_text(f"{item.get('title')} {item.get('summary')}")
        if key in seen:
            duplicates += 1
        seen.add(key)
        if calculate_news_credibility_score(item) < 45.0:
            low_credibility += 1
    risk = clamp(duplicates * 18.0 + low_credibility * 12.0)
    return {"active": risk >= 35.0, "duplicate_count": duplicates, "low_credibility_count": low_credibility, "risk_score": round(risk, 2)}


def detect_panic_news(news_items: Any = None, context: Any = None) -> Dict[str, Any]:
    items = normalize_news_items(news_items)
    panic_hits = 0
    for item in items:
        text = _lower_blob(item.get("title"), item.get("summary"))
        if any(term in text for term in PANIC_TERMS):
            panic_hits += 1
    vix = safe_float(_dict(context).get("vix") or _dict(context).get("india_vix"), 0.0)
    score = clamp(panic_hits * 30.0 + max(0.0, vix - 22.0) * 3.0)
    return {"active": score >= 45.0, "panic_hits": panic_hits, "panic_score": round(score, 2)}


def detect_positive_news_exhaustion(news_items: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    items = normalize_news_items(news_items)
    positive_count = 0
    for item in items:
        sentiment = score_news_sentiment(item, setup, context)
        if sentiment.get("score", 50) >= 65 and calculate_stock_relevance(item, setup) >= 50:
            positive_count += 1
    gap_up = safe_float(_dict(context).get("gap_pct") or _dict(context).get("price_change_pct") or _dict(context).get("change_pct"), 0.0)
    risk = clamp(max(0, positive_count - 2) * 18.0 + max(0.0, gap_up - 3.0) * 12.0)
    return {"active": risk >= 35.0, "positive_news_count": positive_count, "risk_score": round(risk, 2)}


def tag_earnings_events(news_items: Any = None) -> List[Dict[str, Any]]:
    tags = []
    for item in normalize_news_items(news_items):
        text = _lower_blob(item.get("title"), item.get("summary"))
        if any(term in text for term in EARNINGS_TERMS):
            tags.append({
                "title": item.get("title"),
                "source": item.get("source"),
                "tag": "EARNINGS",
                "sentiment_score": score_news_sentiment(item).get("score"),
            })
    return tags[:10]


def build_news_reaction_memory(news_items: Any = None, trade_history: Any = None) -> Dict[str, Any]:
    items = normalize_news_items(news_items)
    trades = [row for row in safe_list(trade_history) if isinstance(row, dict)]
    sentiment_scores = [score_news_sentiment(item).get("score", 50.0) for item in items]
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 50.0
    related_wins = 0
    related_losses = 0
    for trade in trades[-100:]:
        reason = _lower_blob(trade.get("reason"), trade.get("notes"), trade.get("setup_type"))
        outcome = safe_text(trade.get("outcome") or trade.get("result") or trade.get("status")).upper()
        if "news" not in reason:
            continue
        if outcome in {"WIN", "TARGET", "PROFIT"}:
            related_wins += 1
        elif outcome in {"LOSS", "SL", "STOPLOSS"}:
            related_losses += 1
    total = related_wins + related_losses
    win_rate = related_wins / total * 100.0 if total else 0.0
    return {
        "news_items_observed": len(items),
        "average_recent_sentiment": round(avg_sentiment, 2),
        "historical_news_trade_count": total,
        "historical_news_win_rate": round(win_rate, 2),
        "memory_confidence": round(clamp(total * 8.0), 2),
    }


def extract_market_narrative(news_items: Any = None, context: Any = None) -> Dict[str, Any]:
    items = normalize_news_items(news_items)
    if not items:
        regime = safe_text(_dict(context).get("market_type") or _dict(context).get("market_regime"), "UNKNOWN")
        return {"narrative_type": "NO_REAL_NEWS", "dominant_event": "NONE", "headline_count": 0, "market_regime": regime}
    event_counts: Dict[str, int] = {}
    sentiment_scores = []
    for item in items:
        event = classify_news_event(item)
        event_counts[event] = event_counts.get(event, 0) + 1
        sentiment_scores.append(score_news_sentiment(item).get("score", 50.0))
    dominant = max(event_counts, key=event_counts.get) if event_counts else "GENERAL_NEWS"
    avg = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 50.0
    narrative = "RISK_ON_NEWS" if avg >= 60 else "RISK_OFF_NEWS" if avg <= 40 else "MIXED_NEWS"
    return {"narrative_type": narrative, "dominant_event": dominant, "headline_count": len(items), "event_counts": event_counts, "average_sentiment": round(avg, 2)}


def _real_news_report(setup: Dict[str, Any], items: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    scored = []
    for item in items:
        sentiment = score_news_sentiment(item, setup, context)
        stock_rel = calculate_stock_relevance(item, setup)
        sector_rel = calculate_sector_relevance(item, setup, context)
        credibility = calculate_news_credibility_score(item)
        half_life = calculate_impact_half_life(item, context)
        relevance = max(stock_rel, sector_rel * 0.75)
        weighted = (
            safe_float(sentiment.get("score"), 50.0) * 0.38
            + credibility * 0.22
            + relevance * 0.25
            + safe_float(half_life.get("impact_remaining_score"), 100.0) * 0.15
        )
        scored.append({
            "item": item,
            "sentiment": sentiment,
            "stock_relevance": stock_rel,
            "sector_relevance": sector_rel,
            "credibility": credibility,
            "half_life": half_life,
            "weighted_score": clamp(weighted),
        })
    if not scored:
        return {}
    best = max(scored, key=lambda row: row["weighted_score"])
    avg_sentiment = sum(row["sentiment"]["score"] for row in scored) / len(scored)
    avg_credibility = sum(row["credibility"] for row in scored) / len(scored)
    avg_source = sum(calculate_source_weight(row["item"].get("source")) for row in scored) / len(scored)
    duplicate = detect_fake_duplicate_news(items)
    panic = detect_panic_news(items, context)
    exhaustion = detect_positive_news_exhaustion(items, setup, context)
    earnings = tag_earnings_events(items)
    memory = build_news_reaction_memory(items, context.get("trade_history") or context.get("recent_trades") or [])
    narrative = extract_market_narrative(items, context)
    event = classify_news_event(best["item"])
    score = clamp(
        avg_sentiment * 0.34
        + best["weighted_score"] * 0.26
        + avg_credibility * 0.16
        + best["stock_relevance"] * 0.10
        + best["sector_relevance"] * 0.06
        + safe_float(memory.get("memory_confidence"), 0.0) * 0.03
        + 50.0 * 0.05
        - safe_float(duplicate.get("risk_score")) * 0.16
        - safe_float(panic.get("panic_score")) * 0.22
        - safe_float(exhaustion.get("risk_score")) * 0.14
    )
    warning = "NONE"
    if panic.get("panic_score", 0) >= 70 or duplicate.get("risk_score", 0) >= 80:
        warning = "SKIP"
    elif panic.get("active") or duplicate.get("active") or exhaustion.get("active"):
        warning = "REVIEW"
    elif event in {"MACRO", "REGULATORY"} and best["stock_relevance"] < 50:
        warning = "WAIT"
    return {
        "news_data_mode": "REAL_NEWS",
        "overall_news_sentiment_score": round(avg_sentiment, 2),
        "event_classification": event,
        "impact_half_life": best["half_life"],
        "stock_relevance_score": round(best["stock_relevance"], 2),
        "sector_relevance_score": round(best["sector_relevance"], 2),
        "duplicate_fake_news_control": duplicate,
        "panic_news_detection": panic,
        "positive_news_exhaustion": exhaustion,
        "earnings_event_tags": earnings,
        "news_reaction_memory": memory,
        "market_narrative": narrative,
        "credibility_score": round(avg_credibility, 2),
        "source_weight_score": round(avg_source, 2),
        "news_intelligence_score": round(score, 2),
        "news_bias": "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL",
        "news_warning": warning,
        "explanations": [
            "Real news items were analyzed for sentiment, relevance, credibility, and narrative.",
            f"Dominant event classification: {event}.",
            f"Market narrative: {narrative.get('narrative_type')}.",
        ],
    }


def _proxy_report(setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    score = safe_float(context.get("news_intelligence_score") or context.get("news_score") or context.get("news_sentiment_score"), 50.0)
    score = clamp(score)
    narrative = {"narrative_type": safe_text(context.get("news_narrative") or context.get("market_narrative"), "PROXY_NEWS"), "dominant_event": safe_text(context.get("event_classification"), "UNKNOWN")}
    return {
        "news_data_mode": "PROXY",
        "overall_news_sentiment_score": round(score, 2),
        "event_classification": safe_text(context.get("event_classification"), "PROXY_NEWS"),
        "impact_half_life": {"event_type": "PROXY_NEWS", "half_life_hours": 6.0, "impact_remaining_score": 50.0},
        "stock_relevance_score": clamp(context.get("news_relevance_score"), 50.0, 100.0),
        "sector_relevance_score": clamp(context.get("sector_news_relevance_score"), 45.0, 100.0),
        "duplicate_fake_news_control": {"active": False, "duplicate_count": 0, "risk_score": 0.0},
        "panic_news_detection": {"active": False, "panic_hits": 0, "panic_score": 0.0},
        "positive_news_exhaustion": {"active": False, "positive_news_count": 0, "risk_score": 0.0},
        "earnings_event_tags": [],
        "news_reaction_memory": {"news_items_observed": 0, "memory_confidence": 0.0},
        "market_narrative": narrative,
        "credibility_score": 50.0,
        "source_weight_score": 50.0,
        "news_intelligence_score": round(score, 2),
        "news_bias": "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL",
        "news_warning": "REVIEW" if safe_float(context.get("panic_news_score"), 0.0) >= 50 else "NONE",
        "explanations": ["No real news items found; using proxy news score/context."],
    }


def build_news_intelligence_report(setup: Any = None, news_items: Any = None, context: Any = None) -> Dict[str, Any]:
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    ctx = _dict(context)
    if news_items is None:
        news_items = setup_data.get("news_items") or raw.get("news_items") or ctx.get("news_items") or ctx.get("news")
    items = normalize_news_items(news_items)
    symbol = safe_text(setup_data.get("symbol") or raw.get("symbol") or setup_data.get("stock") or raw.get("stock"), "UNKNOWN").upper()

    if items:
        report = _real_news_report(setup_data, items, ctx)
    elif any(ctx.get(key) is not None for key in ("news_intelligence_score", "news_score", "news_sentiment_score", "news_bias", "news_narrative", "event_classification")):
        report = _proxy_report(setup_data, ctx)
    else:
        report = {
            "news_data_mode": "INSUFFICIENT",
            "overall_news_sentiment_score": 50.0,
            "event_classification": "NO_NEWS_DATA",
            "impact_half_life": {"event_type": "NO_NEWS_DATA", "half_life_hours": 0.0, "impact_remaining_score": 50.0},
            "stock_relevance_score": 50.0,
            "sector_relevance_score": 50.0,
            "duplicate_fake_news_control": {"active": False, "duplicate_count": 0, "risk_score": 0.0},
            "panic_news_detection": {"active": False, "panic_hits": 0, "panic_score": 0.0},
            "positive_news_exhaustion": {"active": False, "positive_news_count": 0, "risk_score": 0.0},
            "earnings_event_tags": [],
            "news_reaction_memory": {"news_items_observed": 0, "memory_confidence": 0.0},
            "market_narrative": {"narrative_type": "NO_REAL_NEWS", "dominant_event": "NONE", "headline_count": 0},
            "credibility_score": 50.0,
            "source_weight_score": 50.0,
            "news_intelligence_score": 50.0,
            "news_bias": "NEUTRAL",
            "news_warning": "REVIEW",
            "explanations": ["No useful real news or proxy news context available; score kept neutral."],
        }

    output = {
        "symbol": symbol,
        "news_data_mode": report.get("news_data_mode", "INSUFFICIENT"),
        "overall_news_sentiment_score": round(clamp(report.get("overall_news_sentiment_score", 50.0)), 2),
        "event_classification": report.get("event_classification", "UNKNOWN"),
        "impact_half_life": report.get("impact_half_life", {}),
        "stock_relevance_score": round(clamp(report.get("stock_relevance_score", 50.0)), 2),
        "sector_relevance_score": round(clamp(report.get("sector_relevance_score", 50.0)), 2),
        "duplicate_fake_news_control": report.get("duplicate_fake_news_control", {}),
        "panic_news_detection": report.get("panic_news_detection", {}),
        "positive_news_exhaustion": report.get("positive_news_exhaustion", {}),
        "earnings_event_tags": safe_list(report.get("earnings_event_tags"))[:10],
        "news_reaction_memory": report.get("news_reaction_memory", {}),
        "market_narrative": report.get("market_narrative", {}),
        "credibility_score": round(clamp(report.get("credibility_score", 50.0)), 2),
        "source_weight_score": round(clamp(report.get("source_weight_score", 50.0)), 2),
        "news_intelligence_score": round(clamp(report.get("news_intelligence_score", 50.0)), 2),
        "news_bias": report.get("news_bias", "NEUTRAL"),
        "news_warning": report.get("news_warning", "REVIEW"),
        "live_order_allowed": False,
        "explanations": safe_list(report.get("explanations"))[:8],
    }
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return output


if __name__ == "__main__":
    sample_news_items = [
        {
            "title": "Reliance beats quarterly profit estimates, announces expansion plan",
            "summary": "Company revenue growth and margin strength improved after new contract wins.",
            "source": "Reuters",
            "symbols": ["RELIANCE"],
            "sectors": ["energy"],
            "url": "https://example.com/reliance-results",
            "published_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "title": "Energy sector stocks rise after crude stabilizes",
            "summary": "Analysts cite better demand and stronger refining margins.",
            "source": "Business Standard",
            "sectors": ["energy"],
        },
    ]
    sample_setup = {"symbol": "RELIANCE", "side": "LONG", "sector": "energy"}
    sample_context = {"india_vix": 15.5, "change_pct": 1.2, "trade_history": [{"reason": "news breakout", "outcome": "WIN"}]}
    print(json.dumps(build_news_intelligence_report(sample_setup, sample_news_items, sample_context), indent=2, sort_keys=True))
