"""
TITAN Phase 3 - Adaptive Intelligence Runtime Adapter
====================================================

Reads cached adaptive memory and applies conservative metadata-based
score adjustments.

Fail-open rule:
If anything fails, the original setup is returned unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADAPTIVE_STATE_PATH = PROJECT_ROOT / "data" / "memory" / "adaptive_intelligence_state.json"

MAX_SCORE_DELTA = 0.20
MAX_MULTIPLIER_DELTA = 0.06
MIN_CLOSED_TRADES_FOR_ACTIVE_ADJUSTMENT = 10


FALLBACK_STOCK_SECTORS = {
    "RELIANCE": "Energy / Telecom / Retail",
    "ONGC": "Oil & Gas",
    "COALINDIA": "Energy / Coal",
    "NTPC": "Power",
    "POWERGRID": "Power",
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "AXISBANK": "Banking",
    "KOTAKBANK": "Banking",
    "BAJFINANCE": "NBFC",
    "BAJAJFINSV": "Financial Services",
    "BHARTIARTL": "Telecom",
    "ADANIENT": "Conglomerate / Infrastructure",
    "ADANIPORTS": "Ports / Logistics",
    "LT": "Capital Goods / Infrastructure",
    "MARUTI": "Auto",
    "M&M": "Auto",
    "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto",
    "HEROMOTOCO": "Auto",
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "TATACONSUM": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "ULTRACEMCO": "Cement",
    "GRASIM": "Cement / Chemicals",
    "ASIANPAINT": "Paints / Consumer",
    "TITAN": "Consumer / Jewellery",
}

try:
    from intelligence.news_engine import STOCK_SECTORS as NEWS_STOCK_SECTORS
    STOCK_SECTORS = {**FALLBACK_STOCK_SECTORS, **NEWS_STOCK_SECTORS}
except Exception:
    STOCK_SECTORS = dict(FALLBACK_STOCK_SECTORS)


FEATURE_KEYWORDS: Dict[str, List[str]] = {
    "volume": ["volume", "vol spike", "volume spike"],
    "strength": ["strength", "relative strength", "stronger than market"],
    "compression": ["compression", "squeeze", "tight range"],
    "momentum": ["momentum", "rsi"],
    "trend": ["trend", "ema", "moving average"],
    "breakout": ["breakout", "range break", "resistance break"],
    "trap_avoidance": ["trap", "fakeout", "fake breakout"],
    "market_filter": ["market status", "market filter", "market regime", "nifty", "index"],
    "news": ["news", "event", "earnings", "result", "announcement"],
}


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _symbol(value: Any) -> str:
    text = str(value or "").upper().strip()
    return text.replace(".NS", "")


def _side(value: Any) -> str:
    side = str(value or "").upper().strip()
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side if side in {"LONG", "SHORT"} else "UNKNOWN"


def _load_state() -> Dict[str, Any]:
    if not ADAPTIVE_STATE_PATH.exists():
        return {}
    with ADAPTIVE_STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_features(setup: Dict[str, Any]) -> List[str]:
    reason = str(setup.get("reason") or setup.get("setup_reason") or "")
    confirmations = setup.get("confirmations", "")
    text = f"{reason} {confirmations}".lower()
    found = []
    for feature, words in FEATURE_KEYWORDS.items():
        if any(word in text for word in words):
            found.append(feature)
    return sorted(set(found)) or ["general"]


def _regime(setup: Dict[str, Any]) -> str:
    existing = str(setup.get("regime") or "").upper().strip()
    if existing:
        return existing

    text = str(setup.get("market_status") or "").lower()
    if "volatile" in text:
        return "VOLATILE"
    if "sideways" in text or "range" in text:
        return "SIDEWAYS"
    if "trend" in text:
        return "TRENDING"
    if "market_ok" in text or "level 1" in text:
        return "NEUTRAL_OK"
    return "NEUTRAL"


def _sector(symbol: str) -> str:
    return str(STOCK_SECTORS.get(_symbol(symbol)) or "UNKNOWN")


def _cluster_id(side: str, features: List[str], regime: str, sector: str) -> str:
    feature_part = "+".join(sorted(features[:5])) if features else "general"
    sector_part = re.sub(r"[^A-Z0-9]+", "_", str(sector).upper()).strip("_") or "UNKNOWN"
    return f"{side}|{regime}|{sector_part}|{feature_part}"


def _bucket(memory: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = memory.get(key)
    return value if isinstance(value, dict) else {}


def _weight_to_adjustment(bucket: Dict[str, Any], scale: float = 1.0) -> float:
    trades = _safe_int(bucket.get("trades"), 0)
    if trades <= 0:
        return 0.0
    sample_conf = _safe_float(bucket.get("sample_confidence"), min(1.0, trades / 30.0))
    weight = _safe_float(bucket.get("weight"), 1.0)
    return _clamp((weight - 1.0) * scale * sample_conf, -MAX_MULTIPLIER_DELTA, MAX_MULTIPLIER_DELTA)


def _feature_adjustment(state: Dict[str, Any], features: List[str]) -> float:
    memory = state.get("feature_memory", {}) or {}
    adjustments = []
    for feature in features:
        bucket = _bucket(memory, feature)
        if bucket:
            adjustments.append(_weight_to_adjustment(bucket, 0.75))
    if not adjustments:
        return 0.0
    return _clamp(sum(adjustments) / len(adjustments), -0.035, 0.035)


def _single_adjustment(state: Dict[str, Any], memory_key: str, key: str, scale: float) -> float:
    bucket = _bucket(state.get(memory_key, {}) or {}, key)
    if not bucket:
        return 0.0
    return _weight_to_adjustment(bucket, scale)


def _confidence_score(state: Dict[str, Any], buckets: List[Dict[str, Any]]) -> float:
    global_conf = state.get("global_confidence", {}) or {}
    base = _safe_float(global_conf.get("adaptive_confidence_score"), 50.0)
    points = [base]

    for bucket in buckets:
        if not bucket:
            continue
        posterior = _safe_float(bucket.get("posterior_win_rate"), 0.5)
        sample_conf = _safe_float(bucket.get("sample_confidence"), 0.0)
        points.append((0.5 + ((posterior - 0.5) * sample_conf)) * 100.0)

    score = sum(points) / len(points) if points else 50.0
    return round(_clamp(score, 35.0, 65.0), 2)


def _cluster_quality(bucket: Dict[str, Any]) -> float:
    if not bucket:
        return 50.0
    posterior = _safe_float(bucket.get("posterior_win_rate"), 0.5)
    sample_conf = _safe_float(bucket.get("sample_confidence"), 0.0)
    quality = 50.0 + ((posterior - 0.5) * 100.0 * sample_conf)
    return round(_clamp(quality, 35.0, 65.0), 2)


def _news_refinement(state: Dict[str, Any], symbol: str, sector: str) -> Dict[str, Any]:
    news_memory = state.get("news_reaction_memory", {}) or {}
    symbol_bucket = (news_memory.get("symbol_sentiment", {}) or {}).get(_symbol(symbol), {}) or {}
    sector_bucket = (news_memory.get("sector_sentiment", {}) or {}).get(sector, {}) or {}

    symbol_score = _safe_float(symbol_bucket.get("sentiment_score"), 0.0)
    sector_score = _safe_float(sector_bucket.get("sentiment_score"), 0.0)
    symbol_items = _safe_int(symbol_bucket.get("items"), 0)
    sector_items = _safe_int(sector_bucket.get("items"), 0)

    relevance = 0.0
    if symbol_items:
        relevance += 0.70
    if sector_items:
        relevance += 0.30
    relevance = _clamp(relevance, 0.0, 1.0)

    combined = (symbol_score * 0.70) + (sector_score * 0.30)
    combined = _clamp(combined, -1.0, 1.0)

    if combined > 0.10:
        sentiment = "POSITIVE"
    elif combined < -0.10:
        sentiment = "NEGATIVE"
    else:
        sentiment = "NEUTRAL"

    # Cap news influence hard to avoid repeated news overreaction.
    adjustment = _clamp(combined * relevance * 0.020, -0.020, 0.020)

    return {
        "sentiment": sentiment,
        "sentiment_score": round(combined, 4),
        "relevance_score": round(relevance, 4),
        "adjustment": round(adjustment, 4),
        "symbol_news_items": symbol_items,
        "sector_news_items": sector_items,
    }


def apply_adaptive_intelligence(setup: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies Phase 3 adaptive metadata and conservative score adjustment.

    This function must never reject a setup. Any failure returns the original
    setup unchanged.
    """

    if not isinstance(setup, dict):
        return setup

    original = setup

    try:
        state = _load_state()
        if not state:
            return original

        result = dict(setup)
        base_score = _safe_float(result.get("score"), 0.0)
        symbol = _symbol(result.get("symbol") or result.get("stock") or result.get("ticker"))
        side = _side(result.get("side") or result.get("direction") or result.get("trade_side"))
        features = _extract_features(result)
        regime = _regime(result)
        sector = _sector(symbol)
        cluster_id = _cluster_id(side, features, regime, sector)

        closed_trades = _safe_int(state.get("total_closed_trades"), 0)

        feature_adj = _feature_adjustment(state, features)
        regime_adj = _single_adjustment(state, "regime_memory", regime, 0.60)
        sector_adj = _single_adjustment(state, "sector_memory", sector, 0.50)
        side_adj = _single_adjustment(state, "side_memory", side, 0.40)
        symbol_adj = _single_adjustment(state, "symbol_memory", symbol, 0.30)

        cluster_bucket = _bucket(state.get("cluster_memory", {}) or {}, cluster_id)
        cluster_adj = _weight_to_adjustment(cluster_bucket, 0.55) if cluster_bucket else 0.0

        news = _news_refinement(state, symbol, sector)

        raw_adjustment_ratio = (
            feature_adj + regime_adj + sector_adj + side_adj + symbol_adj + cluster_adj + news["adjustment"]
        )

        if closed_trades < MIN_CLOSED_TRADES_FOR_ACTIVE_ADJUSTMENT:
            raw_adjustment_ratio = 0.0

        raw_adjustment_ratio = _clamp(raw_adjustment_ratio, -0.08, 0.08)
        score_delta = _clamp(base_score * raw_adjustment_ratio, -MAX_SCORE_DELTA, MAX_SCORE_DELTA)
        adjusted_score = _clamp(base_score + score_delta, 0.0, 100.0)

        confidence_buckets = [
            _bucket(state.get("regime_memory", {}) or {}, regime),
            _bucket(state.get("sector_memory", {}) or {}, sector),
            cluster_bucket,
            _bucket(state.get("side_memory", {}) or {}, side),
        ]

        result["phase3_base_score"] = round(base_score, 4)
        result["adaptive_confidence_score"] = _confidence_score(state, confidence_buckets)
        result["adaptive_feature_adjustment"] = round(feature_adj, 4)
        result["adaptive_regime_adjustment"] = round(regime_adj, 4)
        result["adaptive_sector_adjustment"] = round(sector_adj, 4)
        result["adaptive_symbol_adjustment"] = round(symbol_adj, 4)
        result["adaptive_side_adjustment"] = round(side_adj, 4)
        result["cluster_id"] = cluster_id
        result["cluster_quality_score"] = _cluster_quality(cluster_bucket)
        result["cluster_adjustment"] = round(cluster_adj, 4)
        result["news_sentiment_refined"] = news["sentiment"]
        result["news_sentiment_score"] = news["sentiment_score"]
        result["news_relevance_score"] = news["relevance_score"]
        result["news_reaction_adjustment"] = news["adjustment"]
        result["phase3_adjustment"] = round(score_delta, 4)
        result["phase3_adjustment_ratio"] = round(raw_adjustment_ratio, 4)
        result["phase3_memory_closed_trades"] = closed_trades
        result["phase3_applied"] = True
        result["phase3_active"] = closed_trades >= MIN_CLOSED_TRADES_FOR_ACTIVE_ADJUSTMENT
        result["score"] = round(adjusted_score, 2)

        return result

    except Exception as e:
        try:
            failed = dict(original)
            failed["phase3_applied"] = False
            failed["phase3_error"] = str(e)
            return failed
        except Exception:
            return original
