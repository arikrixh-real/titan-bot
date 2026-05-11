"""
TITAN Phase 17 Step 1 - Cross-Asset Intelligence Engine
-------------------------------------------------------

Standalone, rule-based intelligence layer for intermarket and cross-asset
pressure. This module does not integrate with Telegram, dashboard, scanner,
broker/execution, ranking, or alert-cap logic. All functions fail open and
return bounded neutral structures when inputs are missing or invalid.
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


def clamp(value: Any, min_value: float = -1.0, max_value: float = 1.0) -> float:
    low = safe_float(min_value, -1.0)
    high = safe_float(max_value, 1.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, safe_float(value, 0.0)))


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _upper(value: Any, default: str = "NEUTRAL") -> str:
    return safe_text(value, default).upper()


def _setup_symbol(setup: Dict[str, Any]) -> str:
    return _upper(setup.get("symbol") or setup.get("stock") or setup.get("ticker"), "UNKNOWN")


def _setup_sector(setup: Dict[str, Any], context: Dict[str, Any]) -> str:
    for source in (setup, _as_dict(setup.get("raw")), context):
        sector = source.get("sector") or source.get("industry") or source.get("sector_name")
        if sector:
            return safe_text(sector, "UNKNOWN")
    return "UNKNOWN"


def _first_float(source: Dict[str, Any], keys: Iterable[str], default: float = 0.0) -> float:
    for key in keys:
        if key in source:
            return safe_float(source.get(key), default)
    return default


def _market(context: Dict[str, Any]) -> Dict[str, Any]:
    market = context.get("market")
    if isinstance(market, dict):
        data = market.get("data")
        return data if isinstance(data, dict) else market
    return context


def _bias_from_score(score: float, bullish_at: float = 0.15, bearish_at: float = -0.15) -> str:
    if score >= bullish_at:
        return "BULLISH"
    if score <= bearish_at:
        return "BEARISH"
    return "NEUTRAL"


def _trend_score(value: Any, fallback_change: float = 0.0) -> float:
    text = _upper(value, "")
    if text in {"BULLISH", "UP", "UPTREND", "RISK_ON", "STRONG", "POSITIVE"}:
        return 0.65
    if text in {"BEARISH", "DOWN", "DOWNTREND", "RISK_OFF", "WEAK", "NEGATIVE"}:
        return -0.65
    change = safe_float(fallback_change, 0.0)
    if abs(change) < 0.1:
        return 0.0
    return clamp(change / 2.0)


def _extract_asset(context: Dict[str, Any], names: Iterable[str]) -> Dict[str, Any]:
    market = _market(context)
    containers = [
        market,
        _as_dict(market.get("indices")),
        _as_dict(market.get("global_markets")),
        _as_dict(market.get("cross_asset")),
        _as_dict(market.get("commodities")),
        _as_dict(market.get("currency")),
        _as_dict(context.get("cross_asset")),
    ]
    for container in containers:
        for name in names:
            value = container.get(name)
            if isinstance(value, dict):
                return value
    return {}


def detect_nifty_banknifty_relationship(context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    market = _market(context)
    nifty = _extract_asset(context, ("nifty", "NIFTY", "nifty50", "NIFTY50"))
    banknifty = _extract_asset(context, ("banknifty", "BANKNIFTY", "bank_nifty", "BANK_NIFTY"))

    nifty_change = _first_float(nifty, ("change_pct", "pct_change", "change", "return_pct"), _first_float(market, ("nifty_change", "nifty_pct_change"), 0.0))
    bank_change = _first_float(banknifty, ("change_pct", "pct_change", "change", "return_pct"), _first_float(market, ("banknifty_change", "bank_nifty_change"), 0.0))
    nifty_score = _trend_score(nifty.get("trend") or market.get("nifty_trend"), nifty_change)
    bank_score = _trend_score(banknifty.get("trend") or market.get("banknifty_trend"), bank_change)

    spread = bank_change - nifty_change
    alignment = clamp((nifty_score + bank_score) / 2.0)
    aligned = (nifty_score > 0 and bank_score > 0) or (nifty_score < 0 and bank_score < 0)
    if not aligned and abs(nifty_score - bank_score) >= 0.6:
        alignment *= 0.35

    return {
        "nifty_change_pct": round(nifty_change, 2),
        "banknifty_change_pct": round(bank_change, 2),
        "spread_pct": round(spread, 2),
        "relationship": "ALIGNED" if aligned else "DIVERGENT" if abs(nifty_score - bank_score) >= 0.35 else "MIXED",
        "leader": "BANKNIFTY" if spread > 0.25 else "NIFTY" if spread < -0.25 else "BALANCED",
        "score": round(alignment, 4),
        "bias": _bias_from_score(alignment),
    }


def analyze_india_vix_pressure(context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    market = _market(context)
    vix_data = _extract_asset(context, ("india_vix", "INDIA_VIX", "vix", "VIX"))
    raw_vix = None
    for key in ("value", "last", "price", "vix"):
        if key in vix_data:
            raw_vix = vix_data.get(key)
            break
    if raw_vix is None:
        raw_vix = market.get("india_vix") if "india_vix" in market else market.get("vix")
    has_valid_vix = raw_vix is not None and safe_float(raw_vix, None) is not None
    if not has_valid_vix:
        return {
            "value": 0.0,
            "change_pct": 0.0,
            "state": "UNKNOWN",
            "score": 0.0,
            "bias": "NEUTRAL",
        }

    vix = safe_float(raw_vix, 15.0)
    change = _first_float(vix_data, ("change_pct", "pct_change", "change"), _first_float(market, ("vix_change", "india_vix_change"), 0.0))

    score = 0.35
    state = "LOW_STABLE"
    if vix >= 22 or change >= 8:
        score = -0.8
        state = "SPIKING"
    elif vix >= 18 or change >= 4:
        score = -0.45
        state = "ELEVATED"
    elif vix <= 13 and change <= 2:
        score = 0.45
        state = "LOW_STABLE"
    elif change <= -4:
        score = 0.35
        state = "COOLING"

    return {
        "value": round(vix, 2),
        "change_pct": round(change, 2),
        "state": state,
        "score": round(clamp(score), 4),
        "bias": _bias_from_score(score),
    }


def analyze_usdinr_impact(setup: Any, context: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    sector = _setup_sector(setup, context).lower()
    fx = _extract_asset(context, ("usdinr", "USDINR", "usd_inr", "USD_INR"))
    change = _first_float(fx, ("change_pct", "pct_change", "change"), _first_float(_market(context), ("usdinr_change", "usd_inr_change"), 0.0))
    level = _first_float(fx, ("value", "last", "price", "level"), _first_float(_market(context), ("usdinr", "usd_inr"), 0.0))

    exporters = ("it", "technology", "pharma", "export", "textile", "chemicals")
    importers = ("airline", "aviation", "oil marketing", "paint", "consumer durables", "import")
    is_exporter = any(term in sector for term in exporters)
    is_importer = any(term in sector for term in importers)

    instability = abs(change) >= 0.55
    score = -0.1 if instability else 0.0
    sector_effect = "BROAD_NEUTRAL"
    if is_exporter and change > 0:
        score += 0.45
        sector_effect = "EXPORTER_TAILWIND"
    elif is_exporter and change < -0.25:
        score -= 0.25
        sector_effect = "EXPORTER_HEADWIND"
    elif is_importer and change > 0:
        score -= 0.4
        sector_effect = "IMPORT_COST_HEADWIND"
    elif is_importer and change < -0.25:
        score += 0.25
        sector_effect = "IMPORT_COST_RELIEF"

    return {
        "level": round(level, 4),
        "change_pct": round(change, 2),
        "sector_effect": sector_effect,
        "instability": instability,
        "score": round(clamp(score), 4),
        "bias": _bias_from_score(score),
    }


def analyze_crude_oil_impact(setup: Any, context: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    sector = _setup_sector(setup, context).lower()
    crude = _extract_asset(context, ("crude", "CRUDE", "brent", "BRENT", "wti", "WTI"))
    change = _first_float(crude, ("change_pct", "pct_change", "change"), _first_float(_market(context), ("crude_change", "brent_change"), 0.0))
    level = _first_float(crude, ("value", "last", "price", "level"), _first_float(_market(context), ("crude", "brent"), 0.0))

    beneficiaries = ("oil", "gas", "energy", "upstream", "exploration")
    sensitive = ("airline", "aviation", "paint", "tyre", "cement", "chemical", "logistics", "omc")
    is_beneficiary = any(term in sector for term in beneficiaries) and "paint" not in sector
    is_sensitive = any(term in sector for term in sensitive)

    score = 0.0
    sector_effect = "BROAD_NEUTRAL"
    if is_beneficiary and change > 0:
        score = 0.45
        sector_effect = "ENERGY_TAILWIND"
    elif is_beneficiary and change < 0:
        score = -0.2
        sector_effect = "ENERGY_PRICE_HEADWIND"
    elif is_sensitive and change > 0:
        score = -0.45
        sector_effect = "INPUT_COST_HEADWIND"
    elif is_sensitive and change < -0.5:
        score = 0.3
        sector_effect = "INPUT_COST_RELIEF"
    elif change > 2.0:
        score = -0.2
        sector_effect = "INFLATION_PRESSURE"

    return {
        "level": round(level, 4),
        "change_pct": round(change, 2),
        "sector_effect": sector_effect,
        "score": round(clamp(score), 4),
        "bias": _bias_from_score(score),
    }


def analyze_gold_safe_haven_pressure(context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    gold = _extract_asset(context, ("gold", "GOLD", "xauusd", "XAUUSD"))
    change = _first_float(gold, ("change_pct", "pct_change", "change"), _first_float(_market(context), ("gold_change", "xauusd_change"), 0.0))
    level = _first_float(gold, ("value", "last", "price", "level"), _first_float(_market(context), ("gold", "xauusd"), 0.0))

    score = 0.0
    state = "NEUTRAL"
    if change >= 1.0:
        score = -0.45
        state = "SAFE_HAVEN_BID"
    elif change >= 0.35:
        score = -0.2
        state = "MILD_FEAR_FLOW"
    elif change <= -0.6:
        score = 0.25
        state = "RISK_APPETITE_SUPPORT"

    return {
        "level": round(level, 4),
        "change_pct": round(change, 2),
        "state": state,
        "score": round(clamp(score), 4),
        "bias": _bias_from_score(score),
    }


def detect_global_risk_mode(context: Any) -> str:
    context = _as_dict(context)
    market = _market(context)
    explicit = _upper(market.get("global_risk_mode") or market.get("risk_mode") or context.get("global_risk_mode"), "")
    if explicit in {"RISK_ON", "RISK_OFF", "NEUTRAL"}:
        return explicit

    components = [
        analyze_us_market_pressure(context).get("score", 0.0),
        analyze_asian_market_influence(context).get("score", 0.0),
        analyze_european_market_influence(context).get("score", 0.0),
        analyze_gold_safe_haven_pressure(context).get("score", 0.0),
        analyze_india_vix_pressure(context).get("score", 0.0),
    ]
    score = sum(safe_float(item) for item in components) / max(1, len(components))
    if score >= 0.18:
        return "RISK_ON"
    if score <= -0.18:
        return "RISK_OFF"
    return "NEUTRAL"


def analyze_us_market_pressure(context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    us = _extract_asset(context, ("us", "US", "spx", "SPX", "s&p500", "nasdaq", "NASDAQ", "dow", "DOW"))
    market = _market(context)
    change = _first_float(us, ("change_pct", "pct_change", "change"), _first_float(market, ("us_change", "spx_change", "nasdaq_change"), 0.0))
    futures = _first_float(us, ("futures_change_pct", "futures_change"), _first_float(market, ("us_futures_change", "gift_nifty_change"), 0.0))
    score = clamp((change + futures) / 2.5)

    if score >= 0.25:
        state = "STRONG_US_SUPPORT"
    elif score <= -0.25:
        state = "US_MARKET_PRESSURE"
    else:
        state = "MIXED_US_CUES"

    return {
        "change_pct": round(change, 2),
        "futures_change_pct": round(futures, 2),
        "state": state,
        "score": round(score, 4),
        "bias": _bias_from_score(score),
    }


def analyze_asian_market_influence(context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    asia = _extract_asset(context, ("asia", "ASIA", "asian_markets"))
    market = _market(context)
    change = _first_float(asia, ("change_pct", "pct_change", "avg_change"), _first_float(market, ("asia_change", "asian_change"), 0.0))
    gift = _first_float(market, ("gift_nifty_change", "sgx_nifty_change"), _first_float(asia, ("gift_nifty_change", "sgx_nifty_change"), 0.0))
    score = clamp((change * 0.55 + gift * 0.45) / 1.8)

    return {
        "avg_change_pct": round(change, 2),
        "gift_nifty_change_pct": round(gift, 2),
        "state": "ASIA_SUPPORTIVE" if score >= 0.2 else "ASIA_PRESSURE" if score <= -0.2 else "ASIA_MIXED",
        "score": round(score, 4),
        "bias": _bias_from_score(score),
    }


def analyze_european_market_influence(context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    europe = _extract_asset(context, ("europe", "EUROPE", "european_markets", "dax", "DAX", "ftse", "FTSE"))
    market = _market(context)
    change = _first_float(europe, ("change_pct", "pct_change", "avg_change"), _first_float(market, ("europe_change", "european_change"), 0.0))
    score = clamp(change / 1.7)

    return {
        "avg_change_pct": round(change, 2),
        "state": "EUROPE_SUPPORTIVE" if score >= 0.2 else "EUROPE_PRESSURE" if score <= -0.2 else "EUROPE_MIXED",
        "score": round(score, 4),
        "bias": _bias_from_score(score),
    }


def build_intermarket_correlation_model(setup: Any, context: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)
    side = _upper(setup.get("side") or setup.get("direction"), "LONG")
    sector = _setup_sector(setup, context)
    components = {
        "index_relationship": detect_nifty_banknifty_relationship(context).get("score", 0.0),
        "us_market": analyze_us_market_pressure(context).get("score", 0.0),
        "asia": analyze_asian_market_influence(context).get("score", 0.0),
        "europe": analyze_european_market_influence(context).get("score", 0.0),
        "vix": analyze_india_vix_pressure(context).get("score", 0.0),
        "usdinr": analyze_usdinr_impact(setup, context).get("score", 0.0),
        "crude": analyze_crude_oil_impact(setup, context).get("score", 0.0),
        "gold": analyze_gold_safe_haven_pressure(context).get("score", 0.0),
    }
    raw_score = sum(safe_float(value) for value in components.values()) / max(1, len(components))
    setup_adjusted_score = -raw_score if side in {"SHORT", "SELL", "BEARISH"} else raw_score

    supportive = [name for name, value in components.items() if safe_float(value) >= 0.2]
    adverse = [name for name, value in components.items() if safe_float(value) <= -0.2]

    return {
        "sector": sector,
        "setup_side": side,
        "components": {key: round(safe_float(value), 4) for key, value in components.items()},
        "supportive_factors": supportive,
        "adverse_factors": adverse,
        "raw_score": round(clamp(raw_score), 4),
        "setup_adjusted_score": round(clamp(setup_adjusted_score), 4),
        "structure": "POSITIVE_INTERMARKET" if raw_score >= 0.2 else "NEGATIVE_INTERMARKET" if raw_score <= -0.2 else "MIXED_INTERMARKET",
    }


def detect_cross_asset_volatility_transmission(context: Any) -> Dict[str, Any]:
    context = _as_dict(context)
    vix = analyze_india_vix_pressure(context)
    gold = analyze_gold_safe_haven_pressure(context)
    us = analyze_us_market_pressure(context)
    crude = _extract_asset(context, ("crude", "CRUDE", "brent", "BRENT", "wti", "WTI"))
    fx = _extract_asset(context, ("usdinr", "USDINR", "usd_inr", "USD_INR"))
    crude_change = abs(_first_float(crude, ("change_pct", "pct_change", "change"), _first_float(_market(context), ("crude_change", "brent_change"), 0.0)))
    fx_change = abs(_first_float(fx, ("change_pct", "pct_change", "change"), _first_float(_market(context), ("usdinr_change", "usd_inr_change"), 0.0)))

    shock_points = 0.0
    triggers = []
    if safe_text(vix.get("state")) in {"SPIKING", "ELEVATED"}:
        shock_points += 0.35
        triggers.append("india_vix")
    if gold.get("state") == "SAFE_HAVEN_BID":
        shock_points += 0.2
        triggers.append("gold_safe_haven")
    if safe_float(us.get("score")) <= -0.35:
        shock_points += 0.2
        triggers.append("us_market_selloff")
    if crude_change >= 2.0:
        shock_points += 0.15
        triggers.append("crude_shock")
    if fx_change >= 0.55:
        shock_points += 0.15
        triggers.append("usdinr_instability")

    shock_score = clamp(shock_points, 0.0, 1.0)
    return {
        "active": shock_score >= 0.35,
        "shock_score": round(shock_score, 4),
        "transmission_risk": "HIGH" if shock_score >= 0.65 else "MEDIUM" if shock_score >= 0.35 else "LOW",
        "triggers": triggers,
        "alignment_impact": round(-shock_score, 4),
    }


def calculate_cross_asset_alignment_score(components: Any) -> float:
    items = _as_list(components)
    if isinstance(components, dict):
        items = list(components.values())
    if not items:
        return 50.0

    values = [clamp(item) for item in items]
    avg = sum(values) / max(1, len(values))
    return round(clamp((avg + 1.0) * 50.0, 0.0, 100.0), 2)


def build_cross_asset_report(setup: Any, context: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    context = _as_dict(context)

    nifty_banknifty = detect_nifty_banknifty_relationship(context)
    vix = analyze_india_vix_pressure(context)
    usdinr = analyze_usdinr_impact(setup, context)
    crude = analyze_crude_oil_impact(setup, context)
    gold = analyze_gold_safe_haven_pressure(context)
    global_mode = detect_global_risk_mode(context)
    us = analyze_us_market_pressure(context)
    asia = analyze_asian_market_influence(context)
    europe = analyze_european_market_influence(context)
    correlation = build_intermarket_correlation_model(setup, context)
    volatility = detect_cross_asset_volatility_transmission(context)

    global_score = 0.35 if global_mode == "RISK_ON" else -0.35 if global_mode == "RISK_OFF" else 0.0
    components = {
        "nifty_banknifty": nifty_banknifty.get("score", 0.0),
        "india_vix": vix.get("score", 0.0),
        "usdinr": usdinr.get("score", 0.0),
        "crude": crude.get("score", 0.0),
        "gold": gold.get("score", 0.0),
        "global_risk_mode": global_score,
        "us_market": us.get("score", 0.0),
        "asia": asia.get("score", 0.0),
        "europe": europe.get("score", 0.0),
        "intermarket": correlation.get("raw_score", 0.0),
        "volatility_transmission": volatility.get("alignment_impact", 0.0),
    }
    alignment = calculate_cross_asset_alignment_score(components)
    bias = "BULLISH" if alignment >= 58 else "BEARISH" if alignment <= 42 else "NEUTRAL"

    explanations = []
    if nifty_banknifty.get("relationship") == "ALIGNED":
        explanations.append(f"NIFTY/BANKNIFTY aligned with {nifty_banknifty.get('bias')} pressure.")
    if vix.get("state") in {"SPIKING", "ELEVATED"}:
        explanations.append("India VIX is adding volatility pressure.")
    elif vix.get("bias") == "BULLISH":
        explanations.append("India VIX is stable enough to support risk appetite.")
    if global_mode != "NEUTRAL":
        explanations.append(f"Global mode is {global_mode}.")
    for label, item in (("USDINR", usdinr), ("Crude", crude), ("Gold", gold)):
        if item.get("bias") != "NEUTRAL":
            explanations.append(f"{label} impact is {item.get('bias')} via {item.get('sector_effect') or item.get('state')}.")
    if volatility.get("active"):
        explanations.append(f"Cross-asset volatility transmission risk is {volatility.get('transmission_risk')}.")
    if not explanations:
        explanations.append("Cross-asset inputs are mixed and do not create a strong directional edge.")

    return {
        "symbol": _setup_symbol(setup),
        "sector": _setup_sector(setup, context),
        "nifty_banknifty_relationship": nifty_banknifty,
        "india_vix_pressure": vix,
        "usdinr_impact": usdinr,
        "crude_oil_impact": crude,
        "gold_safe_haven_pressure": gold,
        "global_risk_mode": global_mode,
        "us_market_pressure": us,
        "asian_market_influence": asia,
        "european_market_influence": europe,
        "intermarket_correlation_model": correlation,
        "cross_asset_volatility_transmission": volatility,
        "cross_asset_alignment_score": alignment,
        "cross_asset_bias": bias,
        "explanations": explanations[:8],
    }


if __name__ == "__main__":
    sample_setup = {
        "symbol": "INFY",
        "sector": "IT",
        "side": "LONG",
        "score": 72,
    }
    sample_context = {
        "market": {
            "data": {
                "nifty": {"change_pct": 0.62, "trend": "BULLISH"},
                "banknifty": {"change_pct": 0.48, "trend": "BULLISH"},
                "india_vix": {"value": 12.8, "change_pct": -2.1},
                "usdinr": {"level": 83.42, "change_pct": 0.22},
                "brent": {"level": 84.3, "change_pct": -0.4},
                "gold": {"level": 2310.0, "change_pct": -0.35},
                "us": {"change_pct": 0.45, "futures_change_pct": 0.28},
                "asia": {"avg_change": 0.32},
                "europe": {"avg_change": 0.12},
                "gift_nifty_change": 0.3,
            }
        }
    }
    print(json.dumps(build_cross_asset_report(sample_setup, sample_context), indent=2, sort_keys=True))
