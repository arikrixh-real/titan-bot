"""
TITAN Phase 1 - Institutional Microstructure Proxies
----------------------------------------------------

Proxy-only intelligence from OHLCV/live price data.
No order book, bid/ask feed, tick tape, or broker execution is used here.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd


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

    required = [col for col in ["Open", "High", "Low", "Close"] if col in clean.columns]
    if len(required) < 4:
        return None

    clean = clean.dropna(subset=required)
    if clean.empty:
        return None

    if "Volume" not in clean.columns:
        clean["Volume"] = 0.0
    clean["Volume"] = pd.to_numeric(clean["Volume"], errors="coerce").fillna(0.0)

    return clean


def _atr_proxy(df: pd.DataFrame, window: int = 14) -> float:
    if len(df) < 2:
        return 0.0

    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return _safe_float(true_range.tail(window).mean())


def _close_location(row: pd.Series) -> float:
    high = _safe_float(row.get("High"))
    low = _safe_float(row.get("Low"))
    close = _safe_float(row.get("Close"))
    span = high - low

    if span <= 0:
        return 0.5

    return _clamp((close - low) / span, 0.0, 1.0)


def analyze_microstructure(
    df: pd.DataFrame | None,
    side: str = "LONG",
    live_price: float | None = None,
) -> Dict[str, Any]:
    """
    Returns institutional-style microstructure proxies.

    All scores are 0-100 where higher is better except boolean flags.
    """

    clean = _clean_df(df)
    side = str(side or "").upper()

    neutral = {
        "available": False,
        "order_imbalance_proxy": 50.0,
        "liquidity_sweep": False,
        "liquidity_sweep_direction": "NONE",
        "bid_ask_pressure_proxy": 50.0,
        "spread_behavior_proxy": 50.0,
        "tick_behavior_proxy": 50.0,
        "liquidity_quality_score": 50.0,
        "warnings": ["microstructure_data_unavailable"],
    }

    if clean is None or len(clean) < 20:
        return neutral

    last = clean.iloc[-1]
    prev = clean.iloc[-2]
    recent = clean.tail(20)
    prior = clean.iloc[:-1].tail(20)

    close = clean["Close"]
    volume = clean["Volume"]

    last_close = _safe_float(live_price, _safe_float(last.get("Close")))
    prev_close = _safe_float(prev.get("Close"))
    last_open = _safe_float(last.get("Open"))
    last_high = _safe_float(last.get("High"))
    last_low = _safe_float(last.get("Low"))
    last_volume = _safe_float(last.get("Volume"))
    avg_volume = _safe_float(volume.tail(20).mean())
    atr = _atr_proxy(clean)
    avg_range = _safe_float((recent["High"] - recent["Low"]).mean())

    body = abs(last_close - last_open)
    candle_range = max(last_high - last_low, 0.0)
    body_strength = body / candle_range if candle_range > 0 else 0.0
    close_location = _close_location(last)
    volume_ratio = last_volume / avg_volume if avg_volume > 0 else 1.0

    directional_pressure = close_location if side == "LONG" else 1.0 - close_location
    order_imbalance = _clamp((directional_pressure * 60.0) + (body_strength * 25.0) + (min(volume_ratio, 2.0) * 7.5))

    recent_high = _safe_float(prior["High"].max(), last_high)
    recent_low = _safe_float(prior["Low"].min(), last_low)
    upper_wick = max(last_high - max(last_open, last_close), 0.0)
    lower_wick = max(min(last_open, last_close) - last_low, 0.0)
    wick_ratio = max(upper_wick, lower_wick) / candle_range if candle_range > 0 else 0.0

    bullish_sweep = last_low < recent_low and close_location >= 0.55
    bearish_sweep = last_high > recent_high and close_location <= 0.45
    liquidity_sweep = bool(bullish_sweep or bearish_sweep)
    sweep_direction = "BULLISH" if bullish_sweep else "BEARISH" if bearish_sweep else "NONE"

    bid_ask_pressure = _clamp(
        (directional_pressure * 70.0)
        + (1.0 if last_close >= prev_close else 0.0) * (15.0 if side == "LONG" else 0.0)
        + (1.0 if last_close <= prev_close else 0.0) * (15.0 if side == "SHORT" else 0.0)
        + min(volume_ratio, 2.0) * 7.5
    )

    spread_ratio = candle_range / atr if atr > 0 else 1.0
    if 0.45 <= spread_ratio <= 1.8:
        spread_behavior = 80.0
    elif spread_ratio < 0.25:
        spread_behavior = 45.0
    else:
        spread_behavior = _clamp(90.0 - ((spread_ratio - 1.8) * 22.0))

    returns = close.pct_change().tail(6).dropna()
    direction_unit = 1 if side == "LONG" else -1
    aligned_ticks = 0
    for value in returns:
        if value * direction_unit > 0:
            aligned_ticks += 1
    tick_consistency = aligned_ticks / max(len(returns), 1)
    acceleration = _safe_float(returns.tail(3).mean() - returns.head(3).mean())
    tick_behavior = _clamp((tick_consistency * 70.0) + (50.0 + (acceleration * direction_unit * 5000.0)) * 0.3)

    volume_quality = _clamp(min(volume_ratio, 1.8) / 1.8 * 100.0)
    spread_quality = spread_behavior
    wick_quality = _clamp(100.0 - (wick_ratio * 100.0))
    range_quality = 70.0
    if avg_range > 0:
        range_quality = _clamp(100.0 - abs((candle_range / avg_range) - 1.0) * 35.0)

    liquidity_quality = _clamp(
        (volume_quality * 0.30)
        + (spread_quality * 0.25)
        + (wick_quality * 0.20)
        + (range_quality * 0.15)
        + ((100.0 - 25.0) if liquidity_sweep else 100.0) * 0.10
    )

    warnings = []
    if liquidity_quality < 45:
        warnings.append("weak_liquidity_quality")
    if liquidity_sweep:
        warnings.append("liquidity_sweep_detected")
    if spread_behavior < 45:
        warnings.append("unstable_spread_behavior_proxy")

    return {
        "available": True,
        "order_imbalance_proxy": round(order_imbalance, 2),
        "liquidity_sweep": liquidity_sweep,
        "liquidity_sweep_direction": sweep_direction,
        "bid_ask_pressure_proxy": round(bid_ask_pressure, 2),
        "spread_behavior_proxy": round(spread_behavior, 2),
        "tick_behavior_proxy": round(tick_behavior, 2),
        "liquidity_quality_score": round(liquidity_quality, 2),
        "volume_ratio": round(volume_ratio, 3),
        "spread_ratio": round(spread_ratio, 3),
        "warnings": warnings,
    }
