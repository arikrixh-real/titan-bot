"""
TITAN Phase 26 - Order Book / Microstructure Intelligence
---------------------------------------------------------

Depth-aware and proxy microstructure analyzer. Uses real market depth when
available and safe proxy logic when not. It never places orders or enables live
execution.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List


REPORT_PATH = Path("data/microstructure/latest_microstructure_report.json")


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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
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


def _price_level(row: Any) -> Dict[str, float]:
    if isinstance(row, dict):
        return {
            "price": safe_float(row.get("price") or row.get("rate") or row.get("p"), 0.0),
            "quantity": safe_float(row.get("quantity") or row.get("qty") or row.get("size") or row.get("volume") or row.get("q"), 0.0),
            "orders": safe_int(row.get("orders") or row.get("order_count"), 0),
        }
    if isinstance(row, (list, tuple)):
        return {
            "price": safe_float(row[0] if len(row) > 0 else 0.0),
            "quantity": safe_float(row[1] if len(row) > 1 else 0.0),
            "orders": safe_int(row[2] if len(row) > 2 else 0),
        }
    return {"price": 0.0, "quantity": 0.0, "orders": 0}


def normalize_depth_data(depth_data: Any = None) -> Dict[str, Any]:
    data = _dict(depth_data)
    raw_bids = data.get("bids") or data.get("buy") or data.get("bid") or []
    raw_asks = data.get("asks") or data.get("sell") or data.get("ask") or []
    bids = [_price_level(row) for row in safe_list(raw_bids)]
    asks = [_price_level(row) for row in safe_list(raw_asks)]
    bids = [row for row in bids if row["price"] > 0 and row["quantity"] > 0]
    asks = [row for row in asks if row["price"] > 0 and row["quantity"] > 0]
    bids.sort(key=lambda row: row["price"], reverse=True)
    asks.sort(key=lambda row: row["price"])
    return {"bids": bids[:20], "asks": asks[:20], "available": bool(bids and asks)}


def extract_best_bid_ask(depth_data: Any = None) -> Dict[str, Any]:
    depth = normalize_depth_data(depth_data)
    bid = depth["bids"][0] if depth["bids"] else {}
    ask = depth["asks"][0] if depth["asks"] else {}
    best_bid = safe_float(bid.get("price"), 0.0)
    best_ask = safe_float(ask.get("price"), 0.0)
    spread = max(0.0, best_ask - best_bid) if best_bid and best_ask else 0.0
    return {"best_bid": best_bid, "best_ask": best_ask, "spread": round(spread, 4), "available": bool(best_bid and best_ask)}


def _proxy_direction_score(market_context: Dict[str, Any]) -> float:
    change = safe_float(market_context.get("change_pct") or market_context.get("price_change_pct"), 0.0)
    volume = safe_float(market_context.get("volume_ratio") or market_context.get("relative_volume"), 1.0)
    return clamp(50.0 + change * 12.0 + (volume - 1.0) * 10.0)


def calculate_bid_ask_pressure(depth_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    depth = normalize_depth_data(depth_data)
    context = _dict(market_context)
    if depth["available"]:
        bid_qty = sum(row["quantity"] for row in depth["bids"][:5])
        ask_qty = sum(row["quantity"] for row in depth["asks"][:5])
        total = bid_qty + ask_qty
        pressure = (bid_qty / total * 100.0) if total else 50.0
        return {"score": round(clamp(pressure), 2), "bid_qty": round(bid_qty, 2), "ask_qty": round(ask_qty, 2), "mode": "REAL_DEPTH"}
    proxy = _proxy_direction_score(context)
    return {"score": round(proxy, 2), "bid_qty": 0.0, "ask_qty": 0.0, "mode": "PROXY"}


def calculate_order_book_imbalance(depth_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    pressure = calculate_bid_ask_pressure(depth_data, market_context)
    imbalance = safe_float(pressure.get("score"), 50.0) - 50.0
    return {"imbalance_score": round(clamp(abs(imbalance) * 2.0), 2), "direction": "BULLISH" if imbalance > 8 else "BEARISH" if imbalance < -8 else "NEUTRAL", "raw_delta": round(imbalance, 2)}


def detect_liquidity_sweeps(depth_data: Any = None, tick_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    ticks = [item for item in safe_list(tick_data) if isinstance(item, dict)]
    context = _dict(market_context)
    sweep_score = 0.0
    if len(ticks) >= 3:
        volumes = [safe_float(t.get("volume") or t.get("qty"), 0.0) for t in ticks[-5:]]
        prices = [safe_float(t.get("price") or t.get("ltp"), 0.0) for t in ticks[-5:]]
        if volumes and max(volumes) > max(1.0, sum(volumes) / len(volumes) * 2.5):
            sweep_score += 35.0
        if prices and max(prices) - min(prices) > safe_float(context.get("atr") or context.get("avg_tick_range"), 1.0):
            sweep_score += 25.0
    depth = normalize_depth_data(depth_data)
    if depth["available"] and (sum(r["quantity"] for r in depth["bids"][:2]) < sum(r["quantity"] for r in depth["bids"][2:6]) * 0.25 or sum(r["quantity"] for r in depth["asks"][:2]) < sum(r["quantity"] for r in depth["asks"][2:6]) * 0.25):
        sweep_score += 20.0
    return {"active": sweep_score >= 45.0, "risk_score": round(clamp(sweep_score), 2)}


def detect_spoof_like_behavior(depth_data: Any = None, tick_data: Any = None) -> Dict[str, Any]:
    depth = normalize_depth_data(depth_data)
    if not depth["available"]:
        return {"active": False, "risk_score": 0.0, "reason": "no_real_depth"}
    bid_top = sum(r["quantity"] for r in depth["bids"][:2])
    ask_top = sum(r["quantity"] for r in depth["asks"][:2])
    bid_deep = sum(r["quantity"] for r in depth["bids"][2:8])
    ask_deep = sum(r["quantity"] for r in depth["asks"][2:8])
    wall_ratio = max(bid_top / max(1.0, bid_deep), ask_top / max(1.0, ask_deep))
    risk = clamp((wall_ratio - 2.0) * 25.0)
    return {"active": risk >= 45.0, "risk_score": round(risk, 2), "wall_ratio": round(wall_ratio, 3)}


def calculate_queue_imbalance(depth_data: Any = None) -> Dict[str, Any]:
    best = extract_best_bid_ask(depth_data)
    depth = normalize_depth_data(depth_data)
    if not depth["available"]:
        return {"queue_score": 50.0, "direction": "NEUTRAL"}
    bid_qty = depth["bids"][0]["quantity"]
    ask_qty = depth["asks"][0]["quantity"]
    score = bid_qty / max(1.0, bid_qty + ask_qty) * 100.0
    return {"queue_score": round(clamp(score), 2), "direction": "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL", "best_bid": best["best_bid"], "best_ask": best["best_ask"]}


def detect_spread_widening(depth_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    best = extract_best_bid_ask(depth_data)
    context = _dict(market_context)
    spread = safe_float(best.get("spread"), safe_float(context.get("spread"), 0.0))
    price = safe_float(best.get("best_ask") or context.get("price") or context.get("last_price"), 0.0)
    spread_bps = spread / max(price, 1.0) * 10000.0 if spread else safe_float(context.get("spread_bps"), 0.0)
    normal = safe_float(context.get("normal_spread_bps"), 8.0)
    risk = clamp((spread_bps - normal) * 5.0)
    return {"active": risk >= 35.0, "spread_bps": round(spread_bps, 2), "risk_score": round(risk, 2)}


def detect_tick_acceleration(tick_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    ticks = [item for item in safe_list(tick_data) if isinstance(item, dict)]
    if len(ticks) < 3:
        volume_ratio = safe_float(_dict(market_context).get("volume_ratio"), 1.0)
        score = clamp((volume_ratio - 1.0) * 35.0)
        return {"active": score >= 35.0, "score": round(score, 2), "mode": "PROXY"}
    prices = [safe_float(t.get("price") or t.get("ltp"), 0.0) for t in ticks[-6:]]
    deltas = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices)) if prices[i] and prices[i - 1]]
    score = clamp((sum(deltas[-3:]) - sum(deltas[:3])) * 20.0) if len(deltas) >= 4 else clamp(sum(deltas) * 10.0)
    return {"active": score >= 35.0, "score": round(score, 2), "mode": "TICK"}


def detect_absorption(depth_data: Any = None, tick_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    depth = normalize_depth_data(depth_data)
    ticks = [item for item in safe_list(tick_data) if isinstance(item, dict)]
    score = 0.0
    side = "NEUTRAL"
    if depth["available"]:
        bid_qty = depth["bids"][0]["quantity"]
        ask_qty = depth["asks"][0]["quantity"]
        if bid_qty > ask_qty * 1.8:
            score = 55.0
            side = "BULLISH"
        elif ask_qty > bid_qty * 1.8:
            score = 55.0
            side = "BEARISH"
    if ticks:
        prices = [safe_float(t.get("price") or t.get("ltp"), 0.0) for t in ticks[-5:]]
        volumes = [safe_float(t.get("volume") or t.get("qty"), 0.0) for t in ticks[-5:]]
        if prices and max(prices) - min(prices) < safe_float(_dict(market_context).get("avg_tick_range"), 1.0) and sum(volumes) > 0:
            score += 15.0
    return {"active": score >= 50.0, "score": round(clamp(score), 2), "side": side}


def estimate_hidden_liquidity_proxy(depth_data: Any = None, tick_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    absorption = detect_absorption(depth_data, tick_data, market_context)
    sweep = detect_liquidity_sweeps(depth_data, tick_data, market_context)
    score = clamp(safe_float(absorption.get("score")) * 0.7 + (20.0 if sweep.get("active") else 0.0))
    return {"proxy_score": round(score, 2), "likely_hidden_liquidity": bool(score >= 55.0)}


def detect_high_frequency_volatility_burst(tick_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    accel = detect_tick_acceleration(tick_data, market_context)
    vol = safe_float(_dict(market_context).get("volatility_score"), 50.0)
    score = clamp(safe_float(accel.get("score")) * 0.65 + max(0.0, vol - 50.0) * 0.7)
    return {"active": score >= 55.0, "risk_score": round(score, 2)}


def classify_aggressive_passive_flow(depth_data: Any = None, tick_data: Any = None) -> Dict[str, Any]:
    pressure = calculate_bid_ask_pressure(depth_data)
    score = safe_float(pressure.get("score"), 50.0)
    if score >= 62:
        flow = "AGGRESSIVE_BUYING"
    elif score <= 38:
        flow = "AGGRESSIVE_SELLING"
    else:
        flow = "PASSIVE_OR_MIXED"
    return {"flow": flow, "pressure_score": round(score, 2)}


def estimate_smart_money_pressure(depth_data: Any = None, tick_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    pressure = calculate_bid_ask_pressure(depth_data, market_context)
    imbalance = calculate_order_book_imbalance(depth_data, market_context)
    absorption = detect_absorption(depth_data, tick_data, market_context)
    hidden = estimate_hidden_liquidity_proxy(depth_data, tick_data, market_context)
    score = clamp((safe_float(pressure.get("score")) - 50.0) + safe_float(absorption.get("score")) * (1 if absorption.get("side") == "BULLISH" else -1 if absorption.get("side") == "BEARISH" else 0) * 0.35 + (safe_float(hidden.get("proxy_score")) - 50.0) * 0.20 + 50.0)
    return {"score": round(score, 2), "bias": "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL", "imbalance_direction": imbalance.get("direction")}


def _data_mode(depth_data: Any, tick_data: Any, market_context: Any) -> str:
    if normalize_depth_data(depth_data)["available"]:
        return "REAL_DEPTH"
    if safe_list(tick_data) or _dict(market_context):
        return "PROXY"
    return "INSUFFICIENT"


def build_microstructure_report(setup: Any = None, depth_data: Any = None, tick_data: Any = None, market_context: Any = None) -> Dict[str, Any]:
    setup = _dict(setup)
    context = _dict(market_context)
    mode = _data_mode(depth_data, tick_data, context)
    best = extract_best_bid_ask(depth_data)
    pressure = calculate_bid_ask_pressure(depth_data, context)
    imbalance = calculate_order_book_imbalance(depth_data, context)
    sweeps = detect_liquidity_sweeps(depth_data, tick_data, context)
    spoof = detect_spoof_like_behavior(depth_data, tick_data)
    queue = calculate_queue_imbalance(depth_data)
    spread = detect_spread_widening(depth_data, context)
    accel = detect_tick_acceleration(tick_data, context)
    absorption = detect_absorption(depth_data, tick_data, context)
    hidden = estimate_hidden_liquidity_proxy(depth_data, tick_data, context)
    hf = detect_high_frequency_volatility_burst(tick_data, context)
    flow = classify_aggressive_passive_flow(depth_data, tick_data)
    smart = estimate_smart_money_pressure(depth_data, tick_data, context)

    if mode == "INSUFFICIENT":
        score = 50.0
    else:
        score = clamp(
            safe_float(pressure.get("score")) * 0.25
            + (50.0 + safe_float(imbalance.get("raw_delta")) * 1.4) * 0.20
            + safe_float(smart.get("score")) * 0.25
            + (100.0 - safe_float(spread.get("risk_score"))) * 0.15
            + (100.0 - safe_float(spoof.get("risk_score"))) * 0.15
        )

    if smart.get("bias") == "BULLISH" and score >= 57:
        bias = "BULLISH"
    elif smart.get("bias") == "BEARISH" and score <= 43:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    warning = "NONE"
    if spoof.get("risk_score", 0) >= 70 or spread.get("risk_score", 0) >= 75:
        warning = "SKIP"
    elif spoof.get("risk_score", 0) >= 45 or spread.get("risk_score", 0) >= 45 or hf.get("risk_score", 0) >= 65:
        warning = "REVIEW"
    elif sweeps.get("active"):
        warning = "WAIT"

    explanations = []
    explanations.append(f"Microstructure data mode: {mode}.")
    if warning != "NONE":
        explanations.append(f"Execution warning is {warning} due to spread/spoof/volatility risk.")
    if bias != "NEUTRAL":
        explanations.append(f"Order-flow pressure is {bias}.")
    if mode == "INSUFFICIENT":
        explanations.append("Insufficient depth or proxy data; score kept neutral.")

    report = {
        "symbol": safe_text(setup.get("symbol") or setup.get("stock"), "UNKNOWN").upper(),
        "data_mode": mode,
        "best_bid": best.get("best_bid"),
        "best_ask": best.get("best_ask"),
        "spread": best.get("spread"),
        "bid_ask_pressure": pressure,
        "order_book_imbalance": imbalance,
        "liquidity_sweeps": sweeps,
        "spoof_like_detection": spoof,
        "queue_imbalance": queue,
        "spread_widening": spread,
        "tick_acceleration": accel,
        "absorption_detection": absorption,
        "hidden_liquidity_proxy": hidden,
        "hf_volatility_burst": hf,
        "aggressive_passive_flow": flow,
        "smart_money_pressure": smart,
        "microstructure_score": round(score, 2),
        "microstructure_bias": bias,
        "execution_warning": warning,
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
    sample_depth = {
        "bids": [[100.0, 1200, 8], [99.9, 900, 5], [99.8, 700, 4]],
        "asks": [[100.1, 650, 4], [100.2, 700, 5], [100.3, 900, 6]],
    }
    sample_ticks = [
        {"price": 99.9, "volume": 100},
        {"price": 100.0, "volume": 140},
        {"price": 100.05, "volume": 420},
        {"price": 100.08, "volume": 180},
    ]
    real_report = build_microstructure_report({"symbol": "TCS"}, sample_depth, sample_ticks, {"normal_spread_bps": 8, "atr": 0.25})
    proxy_report = build_microstructure_report({"symbol": "INFY"}, None, sample_ticks, {"change_pct": 0.4, "volume_ratio": 1.8, "spread_bps": 9, "volatility_score": 45})
    print(json.dumps({"real_depth": real_report, "proxy": proxy_report}, indent=2, sort_keys=True))
