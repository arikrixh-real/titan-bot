"""
TITAN Phase 2 - Execution Quality Intelligence
----------------------------------------------

Decision-quality entry proxies from OHLCV and live/entry price data.
This module never places, modifies, or routes broker orders.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _neutral(reason: str = "execution_data_unavailable") -> Dict[str, Any]:
    return {
        "available": False,
        "vwap_like_entry_quality_proxy": 50.0,
        "twap_like_stability_proxy": 50.0,
        "slippage_risk_estimate": 50.0,
        "liquidity_sensitive_entry_quality": 50.0,
        "chase_entry_penalty": 0.0,
        "extended_candle_risk": False,
        "execution_quality_score": 50.0,
        "warnings": [reason],
    }


def _clean_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None

    clean = df.copy()
    clean.columns = [str(col).strip() for col in clean.columns]

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

    return max(0.0, min(1.0, (close - low) / span))


def _side_direction(side: Any) -> int:
    side = str(side or "").upper()
    if side in {"LONG", "BUY"}:
        return 1
    if side in {"SHORT", "SELL"}:
        return -1
    return 0


def analyze_execution_quality(
    df: pd.DataFrame | None,
    setup: Dict[str, Any],
    microstructure: Dict[str, Any] | None = None,
    live_price: float | None = None,
) -> Dict[str, Any]:
    """
    Returns entry/execution quality proxy metadata.

    Scores are 0-100 where higher is better, except slippage risk and penalty.
    """

    clean = _clean_df(df)
    if clean is None or len(clean) < 20 or not isinstance(setup, dict):
        return _neutral()

    side = str(setup.get("side") or setup.get("direction") or "").upper()
    direction = _side_direction(side)
    if direction == 0:
        return _neutral("execution_side_unavailable")

    entry = _safe_float(setup.get("entry") or setup.get("entry_price") or live_price, None)
    if entry is None or entry <= 0:
        return _neutral("execution_entry_unavailable")

    microstructure = microstructure or {}

    recent = clean.tail(20)
    last = clean.iloc[-1]

    typical_price = (recent["High"] + recent["Low"] + recent["Close"]) / 3.0
    volume = recent["Volume"].fillna(0.0)
    volume_sum = _safe_float(volume.sum())

    if volume_sum > 0:
        vwap_like = _safe_float((typical_price * volume).sum() / volume_sum)
    else:
        vwap_like = _safe_float(typical_price.mean())

    twap_like = _safe_float(typical_price.mean())
    atr = _atr_proxy(clean)
    price_unit = atr if atr > 0 else max(entry * 0.005, 0.01)

    vwap_distance = ((entry - vwap_like) * direction) / price_unit
    twap_distance = abs(entry - twap_like) / price_unit

    vwap_quality = _clamp(82.0 - max(0.0, vwap_distance) * 28.0 - max(0.0, -vwap_distance) * 6.0)
    twap_stability = _clamp(86.0 - twap_distance * 18.0)

    ranges = clean["High"] - clean["Low"]
    last_range = _safe_float(ranges.iloc[-1])
    avg_range = _safe_float(ranges.tail(20).mean())
    range_ratio = last_range / avg_range if avg_range > 0 else 1.0

    avg_volume = _safe_float(clean["Volume"].tail(20).mean())
    last_volume = _safe_float(clean["Volume"].iloc[-1])
    volume_ratio = last_volume / avg_volume if avg_volume > 0 else 1.0

    liquidity_quality = _safe_float(microstructure.get("liquidity_quality_score"), 50.0)
    spread_behavior = _safe_float(microstructure.get("spread_behavior_proxy"), 50.0)

    slippage_risk = _clamp(
        35.0
        + max(0.0, range_ratio - 1.0) * 24.0
        + max(0.0, 1.0 - min(volume_ratio, 1.0)) * 25.0
        + max(0.0, 50.0 - liquidity_quality) * 0.35
        + max(0.0, 50.0 - spread_behavior) * 0.25
    )

    volume_quality = _clamp(min(volume_ratio, 1.8) / 1.8 * 100.0)
    range_quality = _clamp(100.0 - abs(range_ratio - 1.0) * 35.0)
    liquidity_sensitive_quality = _clamp(
        (liquidity_quality * 0.35)
        + (spread_behavior * 0.20)
        + (volume_quality * 0.25)
        + (range_quality * 0.20)
    )

    last_open = _safe_float(last.get("Open"))
    last_close = _safe_float(last.get("Close"))
    body = abs(last_close - last_open)
    body_ratio = body / last_range if last_range > 0 else 0.0
    close_location = _close_location(last)

    directional_close_extreme = close_location if direction == 1 else 1.0 - close_location
    entry_to_extreme = ((entry - twap_like) * direction) / price_unit
    extended_candle_risk = bool(range_ratio >= 1.8 and body_ratio >= 0.58 and directional_close_extreme >= 0.72)

    chase_entry_penalty = 0.0
    if extended_candle_risk:
        chase_entry_penalty += 12.0
    if entry_to_extreme > 0.9:
        chase_entry_penalty += min(18.0, entry_to_extreme * 7.0)
    chase_entry_penalty = _clamp(chase_entry_penalty, 0.0, 30.0)

    execution_quality_score = _clamp(
        (vwap_quality * 0.28)
        + (twap_stability * 0.22)
        + ((100.0 - slippage_risk) * 0.20)
        + (liquidity_sensitive_quality * 0.22)
        + ((100.0 - chase_entry_penalty) * 0.08)
    )

    warnings = []
    if slippage_risk >= 65:
        warnings.append("high_slippage_risk")
    if liquidity_sensitive_quality < 45:
        warnings.append("weak_liquidity_sensitive_entry_quality")
    if extended_candle_risk:
        warnings.append("extended_candle_chase_risk")
    if chase_entry_penalty >= 15:
        warnings.append("chase_entry_penalty_active")

    return {
        "available": True,
        "vwap_like_entry_quality_proxy": round(vwap_quality, 2),
        "twap_like_stability_proxy": round(twap_stability, 2),
        "slippage_risk_estimate": round(slippage_risk, 2),
        "liquidity_sensitive_entry_quality": round(liquidity_sensitive_quality, 2),
        "chase_entry_penalty": round(chase_entry_penalty, 2),
        "extended_candle_risk": extended_candle_risk,
        "execution_quality_score": round(execution_quality_score, 2),
        "vwap_like_price": round(vwap_like, 4),
        "twap_like_price": round(twap_like, 4),
        "range_ratio": round(range_ratio, 4),
        "volume_ratio": round(volume_ratio, 4),
        "warnings": warnings,
    }
