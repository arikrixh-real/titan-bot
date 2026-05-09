"""
TITAN Phase 4 - Data Advantage Layer
------------------------------------

Cached/local-data-only intelligence for market breadth, sector rotation,
event caution, options placeholders, and institutional-flow proxies.

This module is research-only:
- No broker execution.
- No paid/private data.
- No live network calls.
- No hard trade blocks.
- Fail-open neutral output on errors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd

try:
    from engines.pro_risk_engine import sector_for_symbol
except Exception:
    def sector_for_symbol(symbol: Any) -> str:
        return "UNKNOWN"


CACHE_DIR = Path("data/cache")
NEWS_MEMORY_FILE = Path("titan_brain/memory/news_batch_state.json")
MAX_SCORE_ADJUSTMENT = 0.20

BULLISH_WORDS = {
    "rise", "rises", "gain", "gains", "surge", "surges", "rally", "bullish",
    "beats", "growth", "strong", "upgrade", "record", "higher", "boost",
}
BEARISH_WORDS = {
    "fall", "falls", "drop", "drops", "slump", "weak", "bearish", "miss",
    "downgrade", "probe", "fraud", "loss", "lower", "inflation", "war",
}
EVENT_KEYWORDS = {
    "rbi", "mpc", "repo rate", "fed", "fomc", "rate decision", "cpi",
    "inflation", "budget", "election", "policy", "geopolitical",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").replace(".NS", "").strip().upper()


def _clean_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None

    clean = df.copy()
    clean.columns = [str(col).strip() for col in clean.columns]

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in clean.columns:
            clean[col] = pd.to_numeric(clean[col], errors="coerce")

    if "Close" not in clean.columns:
        return None

    clean = clean.dropna(subset=["Close"])
    if clean.empty:
        return None

    if "Volume" not in clean.columns:
        clean["Volume"] = 0.0
    clean["Volume"] = pd.to_numeric(clean["Volume"], errors="coerce").fillna(0.0)

    return clean


def _load_cached_df(symbol: str) -> pd.DataFrame | None:
    symbol_key = _normalize_symbol(symbol)
    candidates = [
        CACHE_DIR / f"{symbol_key}.csv",
        CACHE_DIR / f"{symbol_key}.NS.csv",
    ]

    if symbol_key == "^NSEI":
        candidates.insert(0, CACHE_DIR / "^NSEI.csv")
    if symbol_key == "^BSESN":
        candidates.insert(0, CACHE_DIR / "^BSESN.csv")

    for path in candidates:
        if not path.exists():
            continue
        try:
            return _clean_df(pd.read_csv(path))
        except Exception:
            return None

    return None


def _load_all_cached_data(limit: int = 140) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    if not CACHE_DIR.exists():
        return data

    for path in sorted(CACHE_DIR.glob("*.csv"))[:limit]:
        try:
            symbol = path.stem
            df = _clean_df(pd.read_csv(path))
            if df is not None and not df.empty:
                data[symbol] = df
        except Exception:
            continue

    return data


def _neutral_options_proxy() -> Dict[str, Any]:
    return {
        "available": False,
        "reason": "options_data_unavailable",
        "pcr_proxy": None,
        "oi_trend_proxy": "UNKNOWN",
        "derivatives_pressure_score": 50.0,
        "warnings": ["options_derivatives_proxy_neutral"],
    }


def _neutral_context(reason: str = "data_advantage_unavailable") -> Dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "market_ok": True,
        "direction": "NEUTRAL",
        "regime": "UNKNOWN",
        "status": "UNKNOWN",
        "volatility": "UNKNOWN",
        "risk_tone": "NEUTRAL",
        "risk_tone_score": 50.0,
        "nifty_trend": "UNKNOWN",
        "sensex_trend": "UNKNOWN",
        "index_breadth": {},
        "sector_strength": {},
        "sector_rankings": [],
        "sector_rotation": {},
        "sector_news_pressure": {},
        "sector_volatility": {},
        "options_derivatives_proxy": _neutral_options_proxy(),
        "event_calendar_proxy": {
            "available": False,
            "event_caution": False,
            "event_pressure_score": 0.0,
            "event_keywords": [],
            "warnings": ["event_news_proxy_unavailable"],
        },
        "data_advantage_score": 50.0,
        "warnings": [reason],
    }


def _pct_change(close: pd.Series, periods: int) -> float:
    if len(close) <= periods:
        return 0.0
    old = _safe_float(close.iloc[-periods - 1])
    latest = _safe_float(close.iloc[-1])
    if old <= 0:
        return 0.0
    return ((latest - old) / old) * 100.0


def _atr_percent(df: pd.DataFrame, window: int = 14) -> float:
    clean = _clean_df(df)
    if clean is None or len(clean) < 2 or not {"High", "Low", "Close"}.issubset(clean.columns):
        return 0.0

    prev_close = clean["Close"].shift(1)
    true_range = pd.concat(
        [
            clean["High"] - clean["Low"],
            (clean["High"] - prev_close).abs(),
            (clean["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = _safe_float(true_range.tail(window).mean())
    latest = _safe_float(clean["Close"].iloc[-1])
    return (atr / latest) * 100.0 if latest > 0 else 0.0


def _trend_from_df(df: pd.DataFrame | None) -> Dict[str, Any]:
    clean = _clean_df(df)
    if clean is None or len(clean) < 20:
        return {
            "available": False,
            "trend": "UNKNOWN",
            "return_1d": 0.0,
            "return_5d": 0.0,
            "return_20d": 0.0,
            "above_20dma": False,
            "above_50dma": False,
            "volatility_percent": 0.0,
        }

    close = clean["Close"]
    latest = _safe_float(close.iloc[-1])
    sma20 = _safe_float(close.tail(20).mean())
    sma50 = _safe_float(close.tail(50).mean()) if len(close) >= 50 else sma20

    if latest > sma20 >= sma50:
        trend = "BULLISH"
    elif latest < sma20 <= sma50:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return {
        "available": True,
        "trend": trend,
        "latest": round(latest, 4),
        "return_1d": round(_pct_change(close, 1), 4),
        "return_5d": round(_pct_change(close, 5), 4),
        "return_20d": round(_pct_change(close, 20), 4),
        "above_20dma": bool(latest > sma20),
        "above_50dma": bool(latest > sma50),
        "volatility_percent": round(_atr_percent(clean), 4),
    }


def _breadth_from_data(stock_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    advancers = decliners = above_20 = above_50 = usable = 0

    for symbol, df in stock_data.items():
        key = _normalize_symbol(symbol)
        if key.startswith("^") or key in {"NIFTYBEES"}:
            continue

        clean = _clean_df(df)
        if clean is None or len(clean) < 2:
            continue

        close = clean["Close"]
        latest = _safe_float(close.iloc[-1])
        prev = _safe_float(close.iloc[-2])
        if latest <= 0 or prev <= 0:
            continue

        usable += 1
        if latest > prev:
            advancers += 1
        elif latest < prev:
            decliners += 1

        if len(close) >= 20 and latest > _safe_float(close.tail(20).mean()):
            above_20 += 1
        if len(close) >= 50 and latest > _safe_float(close.tail(50).mean()):
            above_50 += 1

    advance_ratio = advancers / usable if usable else 0.5
    above_20_ratio = above_20 / usable if usable else 0.5
    above_50_ratio = above_50 / usable if usable else 0.5

    breadth_score = _clamp(
        (advance_ratio * 40.0)
        + (above_20_ratio * 35.0)
        + (above_50_ratio * 25.0)
    )

    if breadth_score >= 62:
        tone = "BULLISH"
    elif breadth_score <= 38:
        tone = "BEARISH"
    else:
        tone = "NEUTRAL"

    return {
        "available": usable > 0,
        "symbols_counted": usable,
        "advancers": advancers,
        "decliners": decliners,
        "advance_decline_ratio": round(advance_ratio, 4),
        "above_20dma_ratio": round(above_20_ratio, 4),
        "above_50dma_ratio": round(above_50_ratio, 4),
        "breadth_score": round(breadth_score, 2),
        "breadth_tone": tone,
    }


def _read_news_items() -> list[dict[str, Any]]:
    try:
        if not NEWS_MEMORY_FILE.exists():
            return []
        data = json.loads(NEWS_MEMORY_FILE.read_text(encoding="utf-8"))
        items = data.get("news", [])
        return items if isinstance(items, list) else []
    except Exception:
        return []


def _word_pressure(text: str) -> float:
    clean = str(text or "").lower()
    score = 0.0
    for word in BULLISH_WORDS:
        if word in clean:
            score += 1.0
    for word in BEARISH_WORDS:
        if word in clean:
            score -= 1.0
    return score


def _news_pressure(news_items: list[dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    pressure: Dict[str, Dict[str, Any]] = {}
    for item in news_items[-100:]:
        sectors = item.get("sectors") or []
        if not isinstance(sectors, list):
            continue
        raw_text = f"{item.get('title', '')} {item.get('summary', '')}"
        score = _word_pressure(raw_text)
        for sector in sectors:
            bucket = pressure.setdefault(
                str(sector),
                {"items": 0, "raw_score": 0.0, "pressure": "NEUTRAL", "pressure_score": 50.0},
            )
            bucket["items"] += 1
            bucket["raw_score"] += score

    for bucket in pressure.values():
        raw = _safe_float(bucket.get("raw_score"))
        items = max(int(bucket.get("items") or 0), 1)
        normalized = _clamp(50.0 + ((raw / items) * 12.0))
        bucket["pressure_score"] = round(normalized, 2)
        if normalized >= 58:
            bucket["pressure"] = "POSITIVE"
        elif normalized <= 42:
            bucket["pressure"] = "NEGATIVE"
        else:
            bucket["pressure"] = "NEUTRAL"
        bucket["raw_score"] = round(raw, 4)

    return pressure


def _event_calendar_proxy(news_items: list[dict[str, Any]]) -> Dict[str, Any]:
    found = set()
    headline_count = 0

    for item in news_items[-100:]:
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        matched = [keyword for keyword in EVENT_KEYWORDS if keyword in text]
        if matched:
            headline_count += 1
            found.update(matched)

    score = _clamp(headline_count * 18.0, 0.0, 100.0)
    event_caution = bool(headline_count >= 1)
    return {
        "available": bool(news_items),
        "event_caution": event_caution,
        "event_pressure_score": round(score, 2),
        "event_keywords": sorted(found),
        "warnings": ["high_impact_event_news_proxy"] if event_caution else [],
    }


def _sector_strength(stock_data: Dict[str, pd.DataFrame], news_pressure: Dict[str, Any]) -> Dict[str, Any]:
    buckets: Dict[str, list[dict[str, float]]] = {}

    for symbol, df in stock_data.items():
        key = _normalize_symbol(symbol)
        if key.startswith("^") or key in {"NIFTYBEES"}:
            continue
        sector = sector_for_symbol(key)
        if sector == "UNKNOWN":
            continue
        trend = _trend_from_df(df)
        if not trend.get("available"):
            continue
        clean = _clean_df(df)
        volume_ratio = 1.0
        if clean is not None and len(clean) >= 20:
            avg_volume = _safe_float(clean["Volume"].tail(20).mean())
            last_volume = _safe_float(clean["Volume"].iloc[-1])
            volume_ratio = last_volume / avg_volume if avg_volume > 0 else 1.0
        buckets.setdefault(sector, []).append({
            "return_5d": _safe_float(trend.get("return_5d")),
            "return_20d": _safe_float(trend.get("return_20d")),
            "above_20dma": 1.0 if trend.get("above_20dma") else 0.0,
            "above_50dma": 1.0 if trend.get("above_50dma") else 0.0,
            "volatility_percent": _safe_float(trend.get("volatility_percent")),
            "volume_ratio": volume_ratio,
        })

    sector_strength = {}
    for sector, rows in buckets.items():
        if not rows:
            continue
        count = len(rows)
        avg_5d = sum(row["return_5d"] for row in rows) / count
        avg_20d = sum(row["return_20d"] for row in rows) / count
        breadth = sum(row["above_20dma"] for row in rows) / count
        long_breadth = sum(row["above_50dma"] for row in rows) / count
        volatility = sum(row["volatility_percent"] for row in rows) / count
        volume_expansion = sum(row["volume_ratio"] for row in rows) / count
        pressure_score = _safe_float((news_pressure.get(sector) or {}).get("pressure_score"), 50.0)

        strength_score = _clamp(
            50.0
            + (avg_5d * 2.2)
            + (avg_20d * 0.9)
            + ((breadth - 0.5) * 30.0)
            + ((long_breadth - 0.5) * 20.0)
            + ((min(volume_expansion, 2.0) - 1.0) * 10.0)
            + ((pressure_score - 50.0) * 0.10)
        )

        sector_strength[sector] = {
            "symbols_counted": count,
            "avg_return_5d": round(avg_5d, 4),
            "avg_return_20d": round(avg_20d, 4),
            "breadth_20dma_ratio": round(breadth, 4),
            "breadth_50dma_ratio": round(long_breadth, 4),
            "volume_expansion_ratio": round(volume_expansion, 4),
            "sector_volatility": round(volatility, 4),
            "strength_score": round(strength_score, 2),
        }

    sorted_5d = sorted(
        sector_strength,
        key=lambda item: sector_strength[item]["avg_return_5d"],
        reverse=True,
    )
    sorted_20d = sorted(
        sector_strength,
        key=lambda item: sector_strength[item]["avg_return_20d"],
        reverse=True,
    )
    rank_5d = {sector: idx + 1 for idx, sector in enumerate(sorted_5d)}
    rank_20d = {sector: idx + 1 for idx, sector in enumerate(sorted_20d)}

    rankings = sorted(
        [
            {
                "sector": sector,
                "rank": idx + 1,
                "strength_score": values["strength_score"],
                "avg_return_5d": values["avg_return_5d"],
                "avg_return_20d": values["avg_return_20d"],
            }
            for idx, (sector, values) in enumerate(
                sorted(sector_strength.items(), key=lambda item: item[1]["strength_score"], reverse=True)
            )
        ],
        key=lambda item: item["rank"],
    )

    rotation = {}
    volatility = {}
    for sector, values in sector_strength.items():
        improvement = rank_20d.get(sector, len(rank_20d)) - rank_5d.get(sector, len(rank_5d))
        if improvement >= 3 and values["avg_return_5d"] > 0:
            state = "ROTATING_IN"
        elif improvement <= -3 and values["avg_return_5d"] < 0:
            state = "ROTATING_OUT"
        else:
            state = "STABLE"
        rotation[sector] = {
            "state": state,
            "rank_5d": rank_5d.get(sector),
            "rank_20d": rank_20d.get(sector),
            "rank_improvement": improvement,
        }
        vol_value = _safe_float(values.get("sector_volatility"))
        volatility[sector] = {
            "volatility_percent": round(vol_value, 4),
            "volatility_state": "HIGH" if vol_value >= 3.5 else "LOW" if vol_value <= 1.2 else "NORMAL",
        }

    return {
        "sector_strength": sector_strength,
        "sector_rankings": rankings,
        "sector_rotation": rotation,
        "sector_volatility": volatility,
    }


def _market_risk_tone(nifty: Dict[str, Any], sensex: Dict[str, Any], breadth: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    score = 50.0
    if nifty.get("trend") == "BULLISH":
        score += 12.0
    elif nifty.get("trend") == "BEARISH":
        score -= 12.0

    if sensex.get("available"):
        if sensex.get("trend") == "BULLISH":
            score += 6.0
        elif sensex.get("trend") == "BEARISH":
            score -= 6.0

    score += (_safe_float(breadth.get("breadth_score"), 50.0) - 50.0) * 0.45
    score -= _safe_float(event.get("event_pressure_score"), 0.0) * 0.12
    score = _clamp(score)

    if score >= 66:
        tone = "RISK_ON"
        direction = "BULLISH"
        regime = "BREADTH_CONFIRMED"
    elif score <= 34:
        tone = "RISK_OFF"
        direction = "BEARISH"
        regime = "BREADTH_WEAK"
    elif score <= 44:
        tone = "CAUTION"
        direction = "NEUTRAL"
        regime = "CAUTION"
    else:
        tone = "NEUTRAL"
        direction = "NEUTRAL"
        regime = "MIXED"

    volatility_value = max(
        _safe_float(nifty.get("volatility_percent")),
        _safe_float(sensex.get("volatility_percent")),
    )
    volatility = "HIGH" if volatility_value >= 2.5 else "LOW" if volatility_value <= 0.8 else "NORMAL"

    return {
        "risk_tone": tone,
        "risk_tone_score": round(score, 2),
        "direction": direction,
        "regime": regime,
        "status": regime,
        "volatility": volatility,
    }


def build_data_advantage_context(stock_data: Dict[str, pd.DataFrame] | None = None) -> Dict[str, Any]:
    """
    Build scan-level context from cached/local data only.
    """

    try:
        local_data = stock_data if isinstance(stock_data, dict) and stock_data else _load_all_cached_data()
        if not local_data:
            return _neutral_context("cached_market_data_unavailable")

        nifty_df = local_data.get("^NSEI")
        if nifty_df is None:
            nifty_df = _load_cached_df("^NSEI")
        if nifty_df is None:
            nifty_df = local_data.get("NIFTYBEES")
        nifty = _trend_from_df(nifty_df)

        sensex_df = local_data.get("^BSESN")
        if sensex_df is None:
            sensex_df = _load_cached_df("^BSESN")
        sensex = _trend_from_df(sensex_df)
        breadth = _breadth_from_data(local_data)
        news_items = _read_news_items()
        sector_news_pressure = _news_pressure(news_items)
        event_proxy = _event_calendar_proxy(news_items)
        sectors = _sector_strength(local_data, sector_news_pressure)
        tone = _market_risk_tone(nifty, sensex, breadth, event_proxy)

        score = _clamp(
            (_safe_float(breadth.get("breadth_score"), 50.0) * 0.45)
            + (_safe_float(tone.get("risk_tone_score"), 50.0) * 0.35)
            + (50.0 if not event_proxy.get("event_caution") else 42.0) * 0.20
        )

        warnings = []
        if not nifty.get("available"):
            warnings.append("nifty_proxy_unavailable")
        if not sensex.get("available"):
            warnings.append("sensex_proxy_unavailable")
        if event_proxy.get("event_caution"):
            warnings.append("event_day_caution_proxy")

        return {
            "available": True,
            "reason": "cached_data_advantage_active",
            "market_ok": True,
            "nifty_trend": nifty.get("trend", "UNKNOWN"),
            "sensex_trend": sensex.get("trend", "UNKNOWN"),
            "nifty_proxy": nifty,
            "sensex_proxy": sensex,
            "index_breadth": breadth,
            "sector_strength": sectors["sector_strength"],
            "sector_rankings": sectors["sector_rankings"],
            "sector_rotation": sectors["sector_rotation"],
            "sector_news_pressure": sector_news_pressure,
            "sector_volatility": sectors["sector_volatility"],
            "options_derivatives_proxy": _neutral_options_proxy(),
            "event_calendar_proxy": event_proxy,
            "data_advantage_score": round(score, 2),
            "warnings": warnings,
            **tone,
        }
    except Exception as exc:
        result = _neutral_context("data_advantage_context_error")
        result["error"] = str(exc)
        return result


def market_status_from_context(context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Backward-compatible market filter output.
    Always allows scanning; data layer never hard-blocks.
    """

    try:
        ctx = context if isinstance(context, dict) else build_data_advantage_context()
        return {
            "market_ok": True,
            "reason": "Phase 4 data advantage market filter active",
            "direction": ctx.get("direction", "NEUTRAL"),
            "regime": ctx.get("regime", "UNKNOWN"),
            "status": ctx.get("status", "UNKNOWN"),
            "volatility": ctx.get("volatility", "UNKNOWN"),
            "nifty_trend": ctx.get("nifty_trend", "UNKNOWN"),
            "sensex_trend": ctx.get("sensex_trend", "UNKNOWN"),
            "risk_tone": ctx.get("risk_tone", "NEUTRAL"),
            "risk_tone_score": ctx.get("risk_tone_score", 50.0),
            "breadth_score": (ctx.get("index_breadth") or {}).get("breadth_score", 50.0),
            "data_advantage_score": ctx.get("data_advantage_score", 50.0),
            "warnings": ctx.get("warnings", []),
        }
    except Exception as exc:
        return {
            "market_ok": True,
            "reason": "Phase 4 data advantage unavailable; fail-open",
            "direction": "NEUTRAL",
            "regime": "UNKNOWN",
            "status": "UNKNOWN",
            "volatility": "UNKNOWN",
            "nifty_trend": "UNKNOWN",
            "sensex_trend": "UNKNOWN",
            "risk_tone": "NEUTRAL",
            "risk_tone_score": 50.0,
            "breadth_score": 50.0,
            "data_advantage_score": 50.0,
            "warnings": ["data_advantage_market_status_error"],
            "error": str(exc),
        }


def _institutional_flow_proxy(df: pd.DataFrame | None, side: str = "LONG") -> Dict[str, Any]:
    clean = _clean_df(df)
    if clean is None or len(clean) < 20:
        return {
            "available": False,
            "volume_surge_ratio": 1.0,
            "accumulation_proxy_score": 50.0,
            "unusual_activity_score": 50.0,
            "price_volume_alignment": "UNKNOWN",
            "warnings": ["institutional_flow_proxy_unavailable"],
        }

    side = str(side or "").upper()
    last = clean.iloc[-1]
    close = clean["Close"]
    volume = clean["Volume"]
    latest = _safe_float(close.iloc[-1])
    prev = _safe_float(close.iloc[-2])
    avg_volume = _safe_float(volume.tail(20).mean())
    last_volume = _safe_float(volume.iloc[-1])
    volume_ratio = last_volume / avg_volume if avg_volume > 0 else 1.0

    high = _safe_float(last.get("High"), latest)
    low = _safe_float(last.get("Low"), latest)
    span = high - low
    close_location = ((latest - low) / span) if span > 0 else 0.5
    direction_unit = 1 if side in {"LONG", "BUY"} else -1 if side in {"SHORT", "SELL"} else 0
    price_change = latest - prev
    aligned = direction_unit == 0 or (price_change * direction_unit) >= 0

    recent_returns = close.pct_change().tail(5).dropna()
    aligned_days = sum(1 for value in recent_returns if value * (direction_unit or 1) > 0)
    directional_close = close_location if direction_unit >= 0 else 1.0 - close_location

    accumulation = _clamp(
        (directional_close * 45.0)
        + (min(volume_ratio, 2.5) / 2.5 * 35.0)
        + (aligned_days / max(len(recent_returns), 1) * 20.0)
    )
    unusual = _clamp(
        45.0
        + max(0.0, volume_ratio - 1.0) * 22.0
        + abs(_pct_change(close, 1)) * 4.0
        + abs(_pct_change(close, 5)) * 1.5
    )

    warnings = []
    if volume_ratio >= 1.8:
        warnings.append("volume_surge_detected")
    if unusual >= 75:
        warnings.append("unusual_activity_detected")

    return {
        "available": True,
        "volume_surge_ratio": round(volume_ratio, 4),
        "accumulation_proxy_score": round(accumulation, 2),
        "unusual_activity_score": round(unusual, 2),
        "price_volume_alignment": "ALIGNED" if aligned else "DIVERGENT",
        "close_location": round(close_location, 4),
        "warnings": warnings,
    }


def apply_data_advantage_layer(
    trade_payload: Dict[str, Any],
    symbol: str,
    df: pd.DataFrame | None,
    side: str,
    market_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Attach Phase 4 metadata and bounded score adjustment. Never blocks trades.
    """

    result = dict(trade_payload or {})
    try:
        ctx = market_context if isinstance(market_context, dict) else build_data_advantage_context()
        sector = sector_for_symbol(symbol)
        sector_strength = (ctx.get("sector_strength") or {}).get(sector, {})
        sector_rotation = (ctx.get("sector_rotation") or {}).get(sector, {})
        sector_news = (ctx.get("sector_news_pressure") or {}).get(sector, {})
        sector_volatility = (ctx.get("sector_volatility") or {}).get(sector, {})
        flow = _institutional_flow_proxy(df, side=side)

        market_score = _safe_float(ctx.get("data_advantage_score"), 50.0)
        sector_score = _safe_float(sector_strength.get("strength_score"), 50.0)
        news_score = _safe_float(sector_news.get("pressure_score"), 50.0)
        flow_score = _safe_float(flow.get("accumulation_proxy_score"), 50.0)
        unusual_score = _safe_float(flow.get("unusual_activity_score"), 50.0)
        event_penalty = 6.0 if (ctx.get("event_calendar_proxy") or {}).get("event_caution") else 0.0

        composite = (
            (market_score * 0.28)
            + (sector_score * 0.27)
            + (news_score * 0.12)
            + (flow_score * 0.23)
            + (unusual_score * 0.10)
            - event_penalty
        )
        adjustment = (composite - 50.0) * 0.01
        adjustment = max(-MAX_SCORE_ADJUSTMENT, min(MAX_SCORE_ADJUSTMENT, adjustment))

        original_score = _safe_float(result.get("score"), 0.0)
        adjusted_score = max(0.0, original_score + adjustment)

        metadata = {
            "available": bool(ctx.get("available")),
            "sector": sector,
            "market_risk_tone": ctx.get("risk_tone", "NEUTRAL"),
            "market_risk_tone_score": ctx.get("risk_tone_score", 50.0),
            "sector_strength": sector_strength,
            "sector_rotation": sector_rotation,
            "sector_news_pressure": sector_news,
            "sector_volatility": sector_volatility,
            "options_derivatives_proxy": ctx.get("options_derivatives_proxy", _neutral_options_proxy()),
            "event_calendar_proxy": ctx.get("event_calendar_proxy", {}),
            "institutional_flow_proxy": flow,
            "composite_score": round(_clamp(composite), 2),
            "warnings": ctx.get("warnings", []),
        }

        result["score"] = round(adjusted_score, 2)
        result["rank_score"] = round(adjusted_score, 2)
        result["phase4_data_advantage"] = metadata
        result["phase4_score_adjustment"] = round(adjustment, 3)
        result["data_advantage_score"] = metadata["composite_score"]
        result["market_risk_tone"] = metadata["market_risk_tone"]
        result["sector_strength_score"] = sector_strength.get("strength_score", 50.0)
        result["unusual_activity_score"] = flow.get("unusual_activity_score", 50.0)

        if isinstance(result.get("scores"), dict):
            result["scores"] = dict(result["scores"])
            result["scores"]["phase4_score_adjustment"] = result["phase4_score_adjustment"]
            result["scores"]["phase4_adjusted_score"] = result["score"]
            result["scores"]["data_advantage_score"] = result["data_advantage_score"]

        if isinstance(result.get("market_context"), dict):
            result["market_context"] = dict(result["market_context"])
            result["market_context"]["data_advantage"] = {
                "risk_tone": metadata["market_risk_tone"],
                "risk_tone_score": metadata["market_risk_tone_score"],
                "breadth": ctx.get("index_breadth", {}),
                "event_calendar_proxy": metadata["event_calendar_proxy"],
            }

        if isinstance(result.get("setup_context"), dict):
            result["setup_context"] = dict(result["setup_context"])
            result["setup_context"]["phase4_data_advantage"] = metadata

        return result

    except Exception as exc:
        result["phase4_data_advantage"] = {
            "available": False,
            "sector": sector_for_symbol(symbol),
            "composite_score": 50.0,
            "warnings": ["phase4_data_advantage_error"],
            "error": str(exc),
        }
        result["phase4_score_adjustment"] = 0.0
        result["data_advantage_score"] = 50.0
        return result
