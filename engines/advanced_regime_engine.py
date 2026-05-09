"""
TITAN Phase 1 - Advanced Regime Detection
-----------------------------------------

Uses proxy signals from OHLCV, volume, cached index data, and local news memory.
This module does not fetch network data and does not affect Telegram formatting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd


NEWS_MEMORY_FILE = Path("titan_brain/memory/news_batch_state.json")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _clean_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None

    clean = df.copy()
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in clean.columns:
            clean[col] = pd.to_numeric(clean[col], errors="coerce")

    required = [col for col in ["High", "Low", "Close"] if col in clean.columns]
    if len(required) < 3:
        return None

    clean = clean.dropna(subset=required)
    if clean.empty:
        return None

    if "Volume" not in clean.columns:
        clean["Volume"] = 0.0
    clean["Volume"] = pd.to_numeric(clean["Volume"], errors="coerce").fillna(0.0)

    return clean


def _atr_proxy(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return true_range.rolling(window).mean()


def _recent_news_score(symbol: str | None = None) -> tuple[float, list[str]]:
    if not NEWS_MEMORY_FILE.exists():
        return 0.0, []

    try:
        with open(NEWS_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data.get("news", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            return 0.0, []

        symbol_key = str(symbol or "").replace(".NS", "").upper()
        matched = []

        for item in items[:100]:
            if not isinstance(item, dict):
                continue

            detected = [str(x).upper() for x in item.get("detected_symbols", []) or []]
            sectors = item.get("sectors", []) or []

            if symbol_key and symbol_key in detected:
                matched.append("symbol_news")
            elif sectors:
                matched.append("sector_or_macro_news")

        symbol_hits = matched.count("symbol_news")
        sector_hits = matched.count("sector_or_macro_news")
        score = _clamp((symbol_hits * 25.0) + min(sector_hits, 4) * 8.0)
        return score, matched[:5]

    except Exception:
        return 0.0, []


def detect_advanced_regime(
    df: pd.DataFrame | None,
    symbol: str | None = None,
    market_status: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Classifies the local setup regime using available proxy data.
    """

    clean = _clean_df(df)
    if clean is None or len(clean) < 30:
        return {
            "available": False,
            "regime_type": "UNKNOWN",
            "trending_score": 0.0,
            "mean_reversion_score": 0.0,
            "panic_score": 0.0,
            "news_driven_score": 0.0,
            "liquidity_crisis_score": 0.0,
            "regime_confidence": 0.0,
            "warnings": ["regime_data_unavailable"],
        }

    close = clean["Close"]
    volume = clean["Volume"]
    ranges = clean["High"] - clean["Low"]
    atr = _atr_proxy(clean)

    last_close = _safe_float(close.iloc[-1])
    close_5 = _safe_float(close.iloc[-6], last_close)
    close_20 = _safe_float(close.iloc[-21], last_close)

    move_5 = abs((last_close - close_5) / close_5) if close_5 else 0.0
    move_20 = abs((last_close - close_20) / close_20) if close_20 else 0.0

    ema_fast = close.ewm(span=8, adjust=False).mean()
    ema_slow = close.ewm(span=21, adjust=False).mean()
    ema_gap = abs(_safe_float(ema_fast.iloc[-1] - ema_slow.iloc[-1])) / last_close if last_close else 0.0

    returns = close.pct_change().tail(12).dropna()
    same_direction = 0
    prior_sign = 0
    for value in returns:
        sign = 1 if value > 0 else -1 if value < 0 else 0
        if sign and sign == prior_sign:
            same_direction += 1
        if sign:
            prior_sign = sign
    persistence = same_direction / max(len(returns) - 1, 1)

    recent_range = _safe_float(ranges.tail(5).mean())
    normal_range = _safe_float(ranges.tail(30).mean())
    current_atr = _safe_float(atr.iloc[-1])
    normal_atr = _safe_float(atr.tail(30).mean())
    range_spike = recent_range / normal_range if normal_range > 0 else 1.0
    atr_spike = current_atr / normal_atr if normal_atr > 0 else 1.0

    avg_volume = _safe_float(volume.tail(30).mean())
    recent_volume = _safe_float(volume.tail(3).mean())
    volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0

    trending_score = _clamp((move_20 * 1200.0) + (ema_gap * 2800.0) + (persistence * 35.0))
    panic_score = _clamp(((range_spike - 1.0) * 45.0) + ((atr_spike - 1.0) * 40.0) + ((volume_ratio - 1.0) * 22.0))

    compression = 1.0 - min(range_spike, 1.0)
    choppiness = 1.0 - persistence
    mean_reversion_score = _clamp((choppiness * 45.0) + (compression * 35.0) + max(0.0, 1.0 - move_5 * 150.0) * 20.0)

    news_score, news_matches = _recent_news_score(symbol)
    news_driven_score = _clamp(news_score + max(0.0, volume_ratio - 1.0) * 18.0 + max(0.0, range_spike - 1.0) * 12.0)

    low_volume = _clamp((1.0 - min(volume_ratio, 1.0)) * 70.0)
    unstable_range = _clamp(max(0.0, range_spike - 1.6) * 45.0)
    liquidity_crisis_score = _clamp(low_volume + unstable_range)

    scores = {
        "TRENDING": trending_score,
        "MEAN_REVERTING": mean_reversion_score,
        "PANIC_VOLATILITY_SPIKE": panic_score,
        "NEWS_DRIVEN": news_driven_score,
        "LIQUIDITY_CRISIS": liquidity_crisis_score,
    }
    regime_type = max(scores, key=scores.get)

    top_score = scores[regime_type]
    sorted_scores = sorted(scores.values(), reverse=True)
    separation = top_score - sorted_scores[1] if len(sorted_scores) > 1 else top_score
    data_depth_score = _clamp(len(clean) / 60.0 * 100.0)
    regime_confidence = _clamp((top_score * 0.55) + (separation * 0.30) + (data_depth_score * 0.15))

    warnings = []
    if panic_score >= 65:
        warnings.append("panic_volatility_spike")
    if liquidity_crisis_score >= 60:
        warnings.append("liquidity_crisis_risk")
    if news_driven_score >= 60:
        warnings.append("news_driven_regime")

    market_reason = ""
    if isinstance(market_status, dict):
        market_reason = str(market_status.get("reason", ""))

    return {
        "available": True,
        "regime_type": regime_type,
        "trending_score": round(trending_score, 2),
        "mean_reversion_score": round(mean_reversion_score, 2),
        "panic_score": round(panic_score, 2),
        "news_driven_score": round(news_driven_score, 2),
        "liquidity_crisis_score": round(liquidity_crisis_score, 2),
        "regime_confidence": round(regime_confidence, 2),
        "volume_ratio": round(volume_ratio, 3),
        "range_spike": round(range_spike, 3),
        "atr_spike": round(atr_spike, 3),
        "market_filter_reason": market_reason,
        "news_matches": news_matches,
        "warnings": warnings,
    }
