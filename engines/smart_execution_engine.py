"""
TITAN Phase 25 - Smart Execution Engine
---------------------------------------

Analysis-only execution-quality intelligence. It never places real orders,
never enables live trading, and never bypasses broker execution safety.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List


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


def clamp(value: Any, min_value: float = 0.0, max_value: float = 100.0) -> float:
    low = safe_float(min_value, 0.0)
    high = safe_float(max_value, 100.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, safe_float(value, low)))


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _symbol(order: Dict[str, Any]) -> str:
    return safe_text(order.get("symbol") or order.get("stock") or order.get("ticker"), "UNKNOWN").replace(".NS", "").upper()


def _entry(order: Dict[str, Any]) -> float:
    return safe_float(order.get("entry") or order.get("entry_price") or order.get("price"), 0.0)


def _quantity(order: Dict[str, Any]) -> float:
    return safe_float(order.get("quantity") or order.get("qty") or order.get("position_size"), 0.0)


def _side(order: Dict[str, Any]) -> str:
    side = safe_text(order.get("side") or order.get("direction"), "LONG").upper()
    if side in {"BUY", "BULLISH"}:
        return "LONG"
    if side in {"SELL", "BEARISH"}:
        return "SHORT"
    return side if side in {"LONG", "SHORT"} else "LONG"


def _liquidity(context: Dict[str, Any]) -> float:
    return clamp(context.get("liquidity_score") or context.get("liquidity_quality_score"), 0.0, 100.0)


def _volatility(context: Dict[str, Any]) -> float:
    return clamp(context.get("volatility_score") or context.get("portfolio_heat_score") or context.get("vix_pressure_score"), 0.0, 100.0)


def predict_slippage(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    order = _dict(order)
    context = _dict(market_context)
    entry = _entry(order)
    liquidity = _liquidity(context) or 50.0
    volatility = _volatility(context) or 50.0
    spread_bps = safe_float(context.get("spread_bps"), 8.0)
    notional = entry * _quantity(order)
    size_pressure = clamp(notional / max(safe_float(context.get("avg_turnover"), 1000000.0), 1.0) * 100.0)
    slippage_bps = clamp(2.0 + spread_bps * 0.35 + volatility * 0.08 + size_pressure * 0.12 - liquidity * 0.04, 0.5, 100.0)
    return {
        "slippage_bps": round(slippage_bps, 2),
        "slippage_value": round(entry * slippage_bps / 10000.0, 4) if entry else 0.0,
        "risk_level": "HIGH" if slippage_bps >= 20 else "MEDIUM" if slippage_bps >= 8 else "LOW",
    }


def analyze_liquidity_sensitive_timing(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    context = _dict(market_context)
    liquidity = _liquidity(context) or 50.0
    minutes_from_open = safe_float(context.get("minutes_from_open"), 120.0)
    avoid_open = minutes_from_open < 10 and liquidity < 65
    avoid_close = minutes_from_open > 360 and liquidity < 55
    score = clamp(liquidity - (20 if avoid_open else 0) - (15 if avoid_close else 0))
    return {
        "liquidity_score": round(liquidity, 2),
        "timing_score": round(score, 2),
        "preferred_timing": "WAIT_AFTER_OPEN" if avoid_open else "AVOID_CLOSE" if avoid_close else "OK_TO_ANALYZE",
        "liquidity_state": "WEAK" if score < 40 else "NORMAL" if score < 70 else "STRONG",
    }


def detect_chase_entry_risk(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    order = _dict(order)
    context = _dict(market_context)
    entry = _entry(order)
    current = safe_float(context.get("current_price") or context.get("last_price"), entry)
    side = _side(order)
    move_pct = ((current - entry) / max(entry, 1.0) * 100.0) if side == "LONG" else ((entry - current) / max(entry, 1.0) * 100.0)
    momentum_extension = safe_float(context.get("momentum_extension_pct"), max(0.0, move_pct))
    risk = clamp(max(0.0, move_pct) * 25.0 + max(0.0, momentum_extension) * 18.0)
    return {
        "move_from_entry_pct": round(move_pct, 3),
        "momentum_extension_pct": round(momentum_extension, 3),
        "risk_score": round(risk, 2),
        "state": "HIGH" if risk >= 65 else "MEDIUM" if risk >= 35 else "LOW",
    }


def calculate_vwap_execution_plan(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    qty = max(0, safe_int(_dict(order).get("quantity") or _dict(order).get("qty"), 0))
    slices = max(1, min(5, math.ceil(qty / 100))) if qty else 1
    return {"method": "VWAP", "slices": slices, "participation_rate_pct": 10, "use_only_in_paper": True}


def calculate_twap_execution_plan(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    qty = max(0, safe_int(_dict(order).get("quantity") or _dict(order).get("qty"), 0))
    slices = max(1, min(6, math.ceil(qty / 75))) if qty else 1
    return {"method": "TWAP", "slices": slices, "interval_minutes": 3, "use_only_in_paper": True}


def calculate_spread_risk_score(order: Any = None, market_context: Any = None) -> float:
    context = _dict(market_context)
    spread_bps = safe_float(context.get("spread_bps"), 8.0)
    liquidity = _liquidity(context) or 50.0
    return round(clamp(spread_bps * 4.0 - liquidity * 0.25), 2)


def detect_bad_fill_risk(order: Any = None, fill: Any = None, market_context: Any = None) -> Dict[str, Any]:
    order = _dict(order)
    fill = _dict(fill)
    expected = _entry(order)
    actual = safe_float(fill.get("fill_price") or fill.get("price"), expected)
    side = _side(order)
    adverse_pct = ((actual - expected) / max(expected, 1.0) * 100.0) if side == "LONG" else ((expected - actual) / max(expected, 1.0) * 100.0)
    risk = clamp(max(0.0, adverse_pct) * 30.0 + calculate_spread_risk_score(order, market_context) * 0.3)
    return {"adverse_fill_pct": round(adverse_pct, 3), "risk_score": round(risk, 2), "state": "HIGH" if risk >= 65 else "MEDIUM" if risk >= 35 else "LOW"}


def build_retry_skip_logic(order: Any = None, execution_context: Any = None) -> Dict[str, Any]:
    context = _dict(execution_context)
    attempts = safe_int(context.get("attempts"), 0)
    last_error = safe_text(context.get("last_error"), "")
    skip = attempts >= 2 or any(term in last_error.lower() for term in ("rejected", "locked", "kill", "disconnect"))
    return {"max_attempts": 2, "current_attempts": attempts, "action": "SKIP" if skip else "RETRY_PAPER_ONLY", "reason": last_error if skip else "within_retry_limit"}


def plan_smart_scaling_entries(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    qty = max(0, safe_int(_dict(order).get("quantity") or _dict(order).get("qty"), 0))
    if qty <= 1:
        slices = [100]
    else:
        slices = [40, 30, 30]
    return {"scale_in_percentages": slices, "condition": "paper_only_limit_entries", "cancel_if_chase_risk_high": True}


def handle_partial_fill_analysis(order: Any = None, fills: Any = None) -> Dict[str, Any]:
    order = _dict(order)
    fill_rows = [item for item in _list(fills) if isinstance(item, dict)]
    ordered_qty = _quantity(order)
    filled_qty = sum(safe_float(item.get("quantity") or item.get("qty"), 0.0) for item in fill_rows)
    fill_pct = filled_qty / max(ordered_qty, 1.0) * 100.0 if ordered_qty else 0.0
    return {"ordered_qty": ordered_qty, "filled_qty": filled_qty, "fill_pct": round(fill_pct, 2), "state": "PARTIAL" if 0 < fill_pct < 100 else "NONE" if fill_pct == 0 else "FILLED"}


def calculate_adaptive_execution_timing(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    liquidity = analyze_liquidity_sensitive_timing(order, market_context)
    chase = detect_chase_entry_risk(order, market_context)
    spread = calculate_spread_risk_score(order, market_context)
    if chase["state"] == "HIGH" or spread >= 65:
        timing = "WAIT"
    elif liquidity["liquidity_state"] == "WEAK":
        timing = "DELAY_AND_RECHECK"
    else:
        timing = "PAPER_EXECUTION_WINDOW_OK"
    return {"timing_action": timing, "recheck_seconds": 60 if timing != "PAPER_EXECUTION_WINDOW_OK" else 0}


def build_order_slicing_plan(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    spread = calculate_spread_risk_score(order, market_context)
    liquidity = _liquidity(_dict(market_context)) or 50.0
    plan = calculate_vwap_execution_plan(order, market_context) if liquidity >= 60 and spread < 45 else calculate_twap_execution_plan(order, market_context)
    plan["reason"] = "liquidity_supports_vwap" if plan["method"] == "VWAP" else "reduce_spread_and_timing_risk"
    return plan


def calculate_execution_quality_score(order: Any = None, market_context: Any = None) -> float:
    slippage = predict_slippage(order, market_context)
    liquidity = analyze_liquidity_sensitive_timing(order, market_context)
    chase = detect_chase_entry_risk(order, market_context)
    spread = calculate_spread_risk_score(order, market_context)
    score = 100.0
    score -= safe_float(slippage.get("slippage_bps")) * 1.2
    score -= safe_float(chase.get("risk_score")) * 0.35
    score -= spread * 0.30
    score += (safe_float(liquidity.get("timing_score")) - 50.0) * 0.25
    return round(clamp(score), 2)


def build_smart_execution_report(order: Any = None, market_context: Any = None) -> Dict[str, Any]:
    order = _dict(order)
    context = _dict(market_context)
    slippage = predict_slippage(order, context)
    liquidity = analyze_liquidity_sensitive_timing(order, context)
    chase = detect_chase_entry_risk(order, context)
    spread = calculate_spread_risk_score(order, context)
    bad_fill = detect_bad_fill_risk(order, context.get("fill") if isinstance(context.get("fill"), dict) else {}, context)
    quality = calculate_execution_quality_score(order, context)
    timing = calculate_adaptive_execution_timing(order, context)

    if liquidity["liquidity_state"] == "WEAK" or chase["state"] == "HIGH":
        recommendation = "WAIT"
    elif spread >= 70 or bad_fill["state"] == "HIGH":
        recommendation = "SKIP"
    elif quality >= 70:
        recommendation = "EXECUTE_PAPER"
    else:
        recommendation = "REVIEW"

    explanations = ["Analysis-only smart execution; live orders are disabled."]
    if slippage["risk_level"] != "LOW":
        explanations.append("Slippage risk is above low.")
    if chase["state"] == "HIGH":
        explanations.append("Chase entry risk is high; wait is preferred.")
    if spread >= 55:
        explanations.append("Spread risk requires review.")
    if recommendation == "EXECUTE_PAPER":
        explanations.append("Quality is sufficient for paper execution only.")

    return {
        "advisory_only": True,
        "execution_analysis_only": True,
        "shadow_mode": True,
        "live_order_allowed": False,
        "broker_orders": False,
        "telegram_changes": False,
        "live_rank_mutation_allowed": False,
        "pyramid_placement": "master_controller_execution_quality_sidecar",
        "execution_mode": "ANALYSIS_ONLY",
        "symbol": _symbol(order),
        "slippage_prediction": slippage,
        "liquidity_timing": liquidity,
        "chase_entry_risk": chase,
        "vwap_plan": calculate_vwap_execution_plan(order, context),
        "twap_plan": calculate_twap_execution_plan(order, context),
        "spread_risk_score": spread,
        "bad_fill_risk": bad_fill,
        "retry_skip_logic": build_retry_skip_logic(order, context),
        "scaling_plan": plan_smart_scaling_entries(order, context),
        "partial_fill_analysis": handle_partial_fill_analysis(order, context.get("fills")),
        "adaptive_execution_timing": timing,
        "order_slicing_plan": build_order_slicing_plan(order, context),
        "execution_quality_score": quality,
        "execution_recommendation": recommendation,
        "live_order_allowed": False,
        "explanations": explanations[:8],
    }


if __name__ == "__main__":
    sample_order = {"symbol": "TCS", "side": "LONG", "entry": 3900, "quantity": 40}
    sample_context = {
        "current_price": 3908,
        "liquidity_score": 72,
        "volatility_score": 38,
        "spread_bps": 5,
        "avg_turnover": 2500000,
        "minutes_from_open": 45,
    }
    print(json.dumps(build_smart_execution_report(sample_order, sample_context), indent=2, sort_keys=True))
