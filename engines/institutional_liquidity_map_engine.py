"""
TITAN Phase 30 - Institutional Liquidity Map
--------------------------------------------

Liquidity-map sidecar for OHLCV, VWAP, volume-profile, and proxy liquidity
signals. It is fail-open for TITAN and fail-closed for live execution.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List


REPORT_PATH = Path("data/liquidity_map/latest_institutional_liquidity_report.json")


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


def _row_from_dict(row: Dict[str, Any]) -> Dict[str, float]:
    return {
        "open": safe_float(row.get("open") or row.get("Open") or row.get("o")),
        "high": safe_float(row.get("high") or row.get("High") or row.get("h")),
        "low": safe_float(row.get("low") or row.get("Low") or row.get("l")),
        "close": safe_float(row.get("close") or row.get("Close") or row.get("c") or row.get("ltp")),
        "volume": safe_float(row.get("volume") or row.get("Volume") or row.get("v") or row.get("qty")),
        "vwap": safe_float(row.get("vwap") or row.get("VWAP")),
    }


def _row_from_seq(row: Any) -> Dict[str, float]:
    values = list(row) if isinstance(row, (list, tuple)) else []
    return {
        "open": safe_float(values[0] if len(values) > 0 else 0.0),
        "high": safe_float(values[1] if len(values) > 1 else 0.0),
        "low": safe_float(values[2] if len(values) > 2 else 0.0),
        "close": safe_float(values[3] if len(values) > 3 else 0.0),
        "volume": safe_float(values[4] if len(values) > 4 else 0.0),
        "vwap": safe_float(values[5] if len(values) > 5 else 0.0),
    }


def _extract_rows(liquidity_data: Any) -> List[Any]:
    if isinstance(liquidity_data, list):
        return liquidity_data
    data = _dict(liquidity_data)
    for key in ("ohlcv", "candles", "bars", "data", "rows", "history"):
        if isinstance(data.get(key), list):
            return data.get(key)
    return []


def normalize_liquidity_data(liquidity_data: Any = None) -> Dict[str, Any]:
    raw = _dict(liquidity_data)
    rows = []
    for row in _extract_rows(liquidity_data):
        normalized = _row_from_dict(row) if isinstance(row, dict) else _row_from_seq(row)
        if normalized["high"] > 0 and normalized["low"] > 0 and normalized["close"] > 0:
            rows.append(normalized)
    volume_profile = safe_list(raw.get("volume_profile") or raw.get("profile"))
    zones = safe_list(raw.get("liquidity_zones") or raw.get("zones"))
    latest_price = safe_float(raw.get("price") or raw.get("last_price") or raw.get("ltp"))
    if latest_price <= 0 and rows:
        latest_price = rows[-1]["close"]
    return {
        "rows": rows,
        "volume_profile": volume_profile,
        "zones": zones,
        "latest_price": latest_price,
        "vwap": safe_float(raw.get("vwap") or (rows[-1]["vwap"] if rows else 0.0)),
        "previous_day_high": safe_float(raw.get("previous_day_high") or raw.get("pdh")),
        "previous_day_low": safe_float(raw.get("previous_day_low") or raw.get("pdl")),
        "previous_day_close": safe_float(raw.get("previous_day_close") or raw.get("pdc")),
        "available": bool(rows or volume_profile or zones),
    }


def _setup_entry(setup: Any, context: Any = None, data: Dict[str, Any] | None = None) -> float:
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    ctx = _dict(context)
    return safe_float(
        setup_data.get("entry") or setup_data.get("price") or raw.get("entry") or raw.get("price")
        or ctx.get("price") or ctx.get("last_price") or (data or {}).get("latest_price")
    )


def _near_score(price: float, level: float, tolerance_pct: float = 0.35) -> float:
    if price <= 0 or level <= 0:
        return 0.0
    distance_pct = abs(price - level) / price * 100.0
    return clamp(100.0 - (distance_pct / max(tolerance_pct, 0.01) * 100.0))


def detect_high_volume_zones(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    data = normalize_liquidity_data(liquidity_data)
    rows = data["rows"]
    if not rows and data["volume_profile"]:
        zones = [
            {"price": safe_float(z.get("price") if isinstance(z, dict) else 0.0), "volume": safe_float(z.get("volume") if isinstance(z, dict) else 0.0)}
            for z in data["volume_profile"]
        ]
    else:
        avg_vol = sum(r["volume"] for r in rows) / max(len(rows), 1)
        zones = [{"price": (r["high"] + r["low"] + r["close"]) / 3.0, "volume": r["volume"]} for r in rows if r["volume"] >= avg_vol * 1.4 and r["volume"] > 0]
    entry = _setup_entry(setup, context, data)
    nearest = max([_near_score(entry, z["price"], 0.5) for z in zones], default=0.0)
    return {"active": bool(zones), "zone_count": len(zones), "nearest_zone_score": round(nearest, 2), "zones": zones[-8:]}


def detect_previous_day_liquidity(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    data = normalize_liquidity_data(liquidity_data)
    ctx = _dict(context)
    pdh = data["previous_day_high"] or safe_float(ctx.get("previous_day_high") or ctx.get("pdh"))
    pdl = data["previous_day_low"] or safe_float(ctx.get("previous_day_low") or ctx.get("pdl"))
    pdc = data["previous_day_close"] or safe_float(ctx.get("previous_day_close") or ctx.get("pdc"))
    entry = _setup_entry(setup, context, data)
    levels = [x for x in (pdh, pdl, pdc) if x > 0]
    magnet = max([_near_score(entry, level, 0.45) for level in levels], default=0.0)
    return {"active": bool(levels), "pdh": pdh, "pdl": pdl, "pdc": pdc, "near_previous_day_liquidity_score": round(magnet, 2)}


def detect_vwap_zones(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    data = normalize_liquidity_data(liquidity_data)
    rows = data["rows"]
    if data["vwap"] > 0:
        vwap = data["vwap"]
    elif rows and sum(r["volume"] for r in rows) > 0:
        vwap = sum(((r["high"] + r["low"] + r["close"]) / 3.0) * r["volume"] for r in rows) / sum(r["volume"] for r in rows)
    else:
        vwap = safe_float(_dict(context).get("vwap"))
    entry = _setup_entry(setup, context, data)
    score = _near_score(entry, vwap, 0.4)
    side = safe_text(_dict(setup).get("side") or _dict(setup).get("direction")).upper()
    supportive = (side == "LONG" and entry >= vwap > 0) or (side == "SHORT" and 0 < entry <= vwap)
    return {"active": vwap > 0, "vwap": round(vwap, 4), "near_vwap_score": round(score, 2), "supportive": supportive}


def estimate_stop_loss_clusters(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    data = normalize_liquidity_data(liquidity_data)
    rows = data["rows"]
    entry = _setup_entry(setup, context, data)
    levels = []
    pd = detect_previous_day_liquidity(liquidity_data, setup, context)
    for level in (pd.get("pdh"), pd.get("pdl")):
        if safe_float(level) > 0:
            levels.append(safe_float(level))
    for row in rows[-20:]:
        levels.extend([row["high"], row["low"]])
    near = max([_near_score(entry, level, 0.30) for level in levels], default=safe_float(_dict(context).get("stop_cluster_score"), 0.0))
    return {"active": near >= 45.0, "cluster_risk_score": round(clamp(near), 2), "near_entry": near >= 55.0, "levels_sample": [round(x, 4) for x in levels[-8:]]}


def detect_gap_zones(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    data = normalize_liquidity_data(liquidity_data)
    rows = data["rows"]
    gaps = []
    for prev, cur in zip(rows, rows[1:]):
        prev_close = prev["close"]
        if prev_close <= 0:
            continue
        gap_pct = (cur["open"] - prev_close) / prev_close * 100.0
        if abs(gap_pct) >= 0.8:
            gaps.append({"from": prev_close, "to": cur["open"], "gap_pct": round(gap_pct, 2)})
    entry = _setup_entry(setup, context, data)
    near = max([_near_score(entry, (g["from"] + g["to"]) / 2.0, 0.55) for g in gaps], default=safe_float(_dict(context).get("gap_zone_score"), 0.0))
    return {"active": bool(gaps), "gap_count": len(gaps), "near_gap_score": round(clamp(near), 2), "zones": gaps[-6:]}


def detect_breakout_trap_zones(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    data = normalize_liquidity_data(liquidity_data)
    rows = data["rows"]
    traps = []
    for i in range(2, len(rows)):
        prev_high = max(r["high"] for r in rows[max(0, i - 5):i])
        prev_low = min(r["low"] for r in rows[max(0, i - 5):i])
        cur = rows[i]
        if cur["high"] > prev_high and cur["close"] < prev_high:
            traps.append({"type": "BULL_TRAP", "level": prev_high, "close": cur["close"]})
        if cur["low"] < prev_low and cur["close"] > prev_low:
            traps.append({"type": "BEAR_TRAP", "level": prev_low, "close": cur["close"]})
    entry = _setup_entry(setup, context, data)
    near = max([_near_score(entry, t["level"], 0.45) for t in traps], default=safe_float(_dict(context).get("trap_zone_score"), 0.0))
    return {"active": bool(traps) or near > 0, "trap_risk_score": round(clamp(near), 2), "near_entry": near >= 50.0, "zones": traps[-8:]}


def calculate_liquidity_magnet_score(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> float:
    hvn = detect_high_volume_zones(liquidity_data, setup, context)
    pd = detect_previous_day_liquidity(liquidity_data, setup, context)
    vwap = detect_vwap_zones(liquidity_data, setup, context)
    gap = detect_gap_zones(liquidity_data, setup, context)
    score = (
        safe_float(hvn.get("nearest_zone_score")) * 0.30
        + safe_float(pd.get("near_previous_day_liquidity_score")) * 0.25
        + safe_float(vwap.get("near_vwap_score")) * 0.25
        + safe_float(gap.get("near_gap_score")) * 0.20
    )
    return round(clamp(score), 2)


def detect_institutional_accumulation_zones(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    data = normalize_liquidity_data(liquidity_data)
    rows = data["rows"]
    score = safe_float(_dict(context).get("accumulation_score"), 0.0)
    zones = []
    if len(rows) >= 5:
        avg_vol = sum(r["volume"] for r in rows) / max(len(rows), 1)
        for row in rows[-20:]:
            spread = max(row["high"] - row["low"], 0.0)
            body = abs(row["close"] - row["open"])
            if row["volume"] >= avg_vol * 1.35 and spread > 0 and body / spread <= 0.45 and row["close"] >= row["open"]:
                zones.append({"price": row["close"], "volume": row["volume"]})
        score = max(score, min(100.0, len(zones) * 18.0))
    return {"active": score >= 45.0, "score": round(clamp(score), 2), "zones": zones[-8:]}


def detect_distribution_zones(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    data = normalize_liquidity_data(liquidity_data)
    rows = data["rows"]
    score = safe_float(_dict(context).get("distribution_score"), 0.0)
    zones = []
    if len(rows) >= 5:
        avg_vol = sum(r["volume"] for r in rows) / max(len(rows), 1)
        for row in rows[-20:]:
            spread = max(row["high"] - row["low"], 0.0)
            body = abs(row["close"] - row["open"])
            if row["volume"] >= avg_vol * 1.35 and spread > 0 and body / spread <= 0.55 and row["close"] < row["open"]:
                zones.append({"price": row["close"], "volume": row["volume"]})
        score = max(score, min(100.0, len(zones) * 18.0))
    return {"active": score >= 45.0, "score": round(clamp(score), 2), "zones": zones[-8:]}


def detect_smart_money_footprints(liquidity_data: Any = None, setup: Any = None, context: Any = None) -> Dict[str, Any]:
    accumulation = detect_institutional_accumulation_zones(liquidity_data, setup, context)
    distribution = detect_distribution_zones(liquidity_data, setup, context)
    magnet = calculate_liquidity_magnet_score(liquidity_data, setup, context)
    score = clamp(safe_float(accumulation.get("score")) * 0.45 + (100.0 - safe_float(distribution.get("score"))) * 0.25 + magnet * 0.30)
    bias = "BULLISH" if accumulation.get("score", 0) > distribution.get("score", 0) + 15 else "BEARISH" if distribution.get("score", 0) > accumulation.get("score", 0) + 15 else "NEUTRAL"
    return {"active": score >= 55.0, "score": round(score, 2), "bias": bias, "accumulation_score": accumulation.get("score"), "distribution_score": distribution.get("score")}


def _proxy_available(context: Dict[str, Any]) -> bool:
    keys = ("price", "last_price", "volume_ratio", "relative_volume", "vwap", "previous_day_high", "previous_day_low", "pdh", "pdl", "gap_zone_score", "trap_zone_score", "accumulation_score", "distribution_score")
    return any(context.get(key) is not None for key in keys)


def build_institutional_liquidity_report(setup: Any = None, liquidity_data: Any = None, context: Any = None) -> Dict[str, Any]:
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    ctx = _dict(context)
    if liquidity_data is None:
        liquidity_data = (
            setup_data.get("liquidity_data")
            or raw.get("liquidity_data")
            or setup_data.get("ohlcv")
            or raw.get("ohlcv")
            or ctx.get("liquidity_data")
            or ctx.get("ohlcv")
            or ctx.get("candles")
        )
    data = normalize_liquidity_data(liquidity_data)
    mode = "REAL_LIQUIDITY" if data["available"] else "PROXY" if _proxy_available(ctx) else "INSUFFICIENT"

    high_volume = detect_high_volume_zones(liquidity_data, setup_data, ctx)
    previous_day = detect_previous_day_liquidity(liquidity_data, setup_data, ctx)
    vwap = detect_vwap_zones(liquidity_data, setup_data, ctx)
    stops = estimate_stop_loss_clusters(liquidity_data, setup_data, ctx)
    gaps = detect_gap_zones(liquidity_data, setup_data, ctx)
    traps = detect_breakout_trap_zones(liquidity_data, setup_data, ctx)
    magnet = calculate_liquidity_magnet_score(liquidity_data, setup_data, ctx)
    accumulation = detect_institutional_accumulation_zones(liquidity_data, setup_data, ctx)
    distribution = detect_distribution_zones(liquidity_data, setup_data, ctx)
    smart = detect_smart_money_footprints(liquidity_data, setup_data, ctx)

    if mode == "INSUFFICIENT":
        score = 50.0
    else:
        score = clamp(
            50.0
            + (safe_float(accumulation.get("score")) - safe_float(distribution.get("score"))) * 0.25
            + (magnet - 50.0) * 0.20
            + (12.0 if vwap.get("supportive") else -5.0 if vwap.get("active") else 0.0)
            - safe_float(stops.get("cluster_risk_score")) * 0.12
            - safe_float(traps.get("trap_risk_score")) * 0.16
        )
    warning = "NONE"
    if mode == "INSUFFICIENT":
        warning = "REVIEW"
    elif traps.get("trap_risk_score", 0) >= 75 and stops.get("cluster_risk_score", 0) >= 65:
        warning = "SKIP"
    elif traps.get("near_entry") or stops.get("near_entry"):
        warning = "WAIT"
    elif distribution.get("score", 0) >= 65:
        warning = "REVIEW"

    bias = smart.get("bias", "NEUTRAL")
    if bias == "NEUTRAL":
        bias = "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL"
    symbol = safe_text(setup_data.get("symbol") or raw.get("symbol") or setup_data.get("stock") or raw.get("stock"), "UNKNOWN").upper()
    explanations = [f"Liquidity data mode: {mode}."]
    if accumulation.get("active"):
        explanations.append("Institutional accumulation footprint detected.")
    if distribution.get("active"):
        explanations.append("Distribution footprint detected.")
    if stops.get("near_entry") or traps.get("near_entry"):
        explanations.append("Stop-loss cluster or breakout trap is near entry.")
    if mode == "INSUFFICIENT":
        explanations.append("No useful liquidity/OHLCV/proxy data; score kept neutral.")

    report = {
        "symbol": symbol,
        "liquidity_data_mode": mode,
        "high_volume_zones": high_volume,
        "previous_day_liquidity": previous_day,
        "vwap_zones": vwap,
        "stop_loss_clusters": stops,
        "gap_zones": gaps,
        "breakout_trap_zones": traps,
        "liquidity_magnet_score": round(clamp(magnet), 2),
        "accumulation_zones": accumulation,
        "distribution_zones": distribution,
        "smart_money_footprints": smart,
        "liquidity_map_score": round(clamp(score), 2),
        "liquidity_bias": bias,
        "liquidity_warning": warning,
        "live_order_allowed": False,
        "explanations": explanations[:8],
    }
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return report


if __name__ == "__main__":
    sample_liquidity = {
        "previous_day_high": 101.8,
        "previous_day_low": 98.2,
        "vwap": 100.7,
        "ohlcv": [
            {"open": 99.5, "high": 100.2, "low": 99.1, "close": 100.0, "volume": 1000},
            {"open": 100.0, "high": 101.0, "low": 99.8, "close": 100.8, "volume": 2100},
            {"open": 100.9, "high": 102.0, "low": 100.6, "close": 101.2, "volume": 2600},
            {"open": 101.4, "high": 102.3, "low": 100.9, "close": 101.0, "volume": 3200},
            {"open": 101.1, "high": 101.9, "low": 100.3, "close": 101.6, "volume": 2800},
        ],
    }
    sample_setup = {"symbol": "RELIANCE", "side": "LONG", "entry": 101.5}
    sample_context = {"volume_ratio": 1.8, "price": 101.5}
    print(json.dumps(build_institutional_liquidity_report(sample_setup, sample_liquidity, sample_context), indent=2, sort_keys=True))
