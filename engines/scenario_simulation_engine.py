"""
TITAN Phase 31 - Scenario Simulation Engine
-------------------------------------------

Deterministic scenario simulation sidecar. Builds bullish, bearish, sideways,
volatility-shock, sector-rotation, and regime-flip branches from available
market/setup/context data. It never places orders or enables live execution.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List


REPORT_PATH = Path("data/scenario_simulation/latest_scenario_simulation_report.json")


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


def _first(data: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return default


def normalize_scenario_inputs(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    ctx = _dict(context)
    market = _dict(market_data)
    rows = []
    source_rows = market.get("ohlcv") or market.get("candles") or market.get("data") or ctx.get("ohlcv") or ctx.get("candles")
    for row in safe_list(source_rows):
        if isinstance(row, dict):
            close = safe_float(row.get("close") or row.get("Close") or row.get("c") or row.get("ltp"))
            volume = safe_float(row.get("volume") or row.get("Volume") or row.get("v"))
            high = safe_float(row.get("high") or row.get("High") or row.get("h"), close)
            low = safe_float(row.get("low") or row.get("Low") or row.get("l"), close)
            if close > 0:
                rows.append({"close": close, "high": high, "low": low, "volume": volume})
    symbol = safe_text(setup_data.get("symbol") or raw.get("symbol") or setup_data.get("stock") or raw.get("stock"), "UNKNOWN").upper()
    side = safe_text(setup_data.get("side") or raw.get("side") or setup_data.get("direction") or raw.get("direction"), "").upper()
    entry = safe_float(setup_data.get("entry") or raw.get("entry") or setup_data.get("price") or raw.get("price") or ctx.get("price") or ctx.get("last_price") or market.get("price") or (rows[-1]["close"] if rows else 0.0))
    target = safe_float(setup_data.get("target") or setup_data.get("tp") or raw.get("target") or raw.get("tp"))
    stop = safe_float(setup_data.get("sl") or setup_data.get("stop_loss") or raw.get("sl") or raw.get("stop_loss"))
    rr = safe_float(setup_data.get("rr") or raw.get("rr") or setup_data.get("risk_reward") or raw.get("risk_reward"), 1.5)
    trend_score = safe_float(ctx.get("trend_score") or setup_data.get("trend_score") or raw.get("trend_score"), 50.0)
    momentum_score = safe_float(ctx.get("momentum_score") or setup_data.get("momentum_score") or raw.get("momentum_score"), 50.0)
    volatility_score = safe_float(ctx.get("volatility_score") or ctx.get("vix") or ctx.get("india_vix"), 50.0)
    sector_strength = safe_float(ctx.get("sector_strength") or setup_data.get("sector_strength") or raw.get("sector_strength"), 50.0)
    regime = safe_text(ctx.get("market_regime") or ctx.get("market_type") or ctx.get("regime"), "UNKNOWN").upper()
    if not target and entry > 0:
        target = entry * (1.01 if side != "SHORT" else 0.99)
    if not stop and entry > 0:
        stop = entry * (0.995 if side != "SHORT" else 1.005)
    useful_market = bool(rows or market)
    useful_proxy = bool(setup_data or ctx)
    return {
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "target": target,
        "stop": stop,
        "rr": rr,
        "trend_score": trend_score,
        "momentum_score": momentum_score,
        "volatility_score": volatility_score,
        "sector_strength": sector_strength,
        "regime": regime,
        "rows": rows,
        "market_data_available": useful_market,
        "proxy_available": useful_proxy,
    }


def _directional_alignment(inputs: Dict[str, Any], bullish: bool = True) -> float:
    side = inputs.get("side")
    if side == "SHORT":
        bullish = not bullish
    trend = safe_float(inputs.get("trend_score"), 50.0)
    momentum = safe_float(inputs.get("momentum_score"), 50.0)
    base = (trend * 0.55) + (momentum * 0.45)
    return base if bullish else 100.0 - base


def simulate_bullish_scenario(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    inputs = normalize_scenario_inputs(setup, context, market_data)
    probability = clamp(_directional_alignment(inputs, bullish=True) * 0.62 + safe_float(inputs.get("sector_strength"), 50.0) * 0.25 + max(0.0, safe_float(inputs.get("rr"), 1.5) - 1.0) * 8.0)
    reward_pct = abs(inputs["target"] - inputs["entry"]) / max(inputs["entry"], 1.0) * 100.0 if inputs["entry"] and inputs["target"] else 1.0
    return {"probability": round(probability, 2), "projected_move_pct": round(reward_pct, 2), "outcome": "TARGET_EXTENSION" if probability >= 65 else "CONTROLLED_UPSIDE"}


def simulate_bearish_scenario(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    inputs = normalize_scenario_inputs(setup, context, market_data)
    probability = clamp(_directional_alignment(inputs, bullish=False) * 0.68 + (100.0 - safe_float(inputs.get("sector_strength"), 50.0)) * 0.22 + max(0.0, safe_float(inputs.get("volatility_score"), 50.0) - 55.0) * 0.6)
    loss_pct = abs(inputs["entry"] - inputs["stop"]) / max(inputs["entry"], 1.0) * 100.0 if inputs["entry"] and inputs["stop"] else 0.7
    return {"probability": round(probability, 2), "projected_move_pct": round(loss_pct, 2), "outcome": "STOP_RISK" if probability >= 60 else "PULLBACK_RISK"}


def simulate_sideways_scenario(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    inputs = normalize_scenario_inputs(setup, context, market_data)
    trend_neutrality = 100.0 - abs(safe_float(inputs.get("trend_score"), 50.0) - 50.0) * 2.0
    momentum_neutrality = 100.0 - abs(safe_float(inputs.get("momentum_score"), 50.0) - 50.0) * 2.0
    probability = clamp(trend_neutrality * 0.45 + momentum_neutrality * 0.35 + (100.0 - abs(safe_float(inputs.get("volatility_score"), 50.0) - 50.0)) * 0.20)
    return {"probability": round(probability, 2), "projected_move_pct": 0.25, "outcome": "TIME_DECAY_OR_CHOP"}


def simulate_volatility_shock_scenario(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    inputs = normalize_scenario_inputs(setup, context, market_data)
    vol = safe_float(inputs.get("volatility_score"), 50.0)
    rows = inputs.get("rows") or []
    range_score = 0.0
    if rows:
        ranges = [(r["high"] - r["low"]) / max(r["close"], 1.0) * 100.0 for r in rows[-10:]]
        range_score = clamp(sum(ranges) / max(len(ranges), 1) * 25.0)
    probability = clamp(max(vol, range_score) * 0.85 + max(0.0, vol - 65.0) * 0.45)
    return {"probability": round(probability, 2), "shock_risk_score": round(probability, 2), "outcome": "VOLATILITY_EXPANSION" if probability >= 60 else "NORMAL_VOLATILITY"}


def simulate_sector_rotation_scenario(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    inputs = normalize_scenario_inputs(setup, context, market_data)
    sector = safe_float(inputs.get("sector_strength"), 50.0)
    probability = clamp(abs(sector - 50.0) * 1.3 + safe_float(_dict(context).get("sector_rotation_score"), 0.0))
    direction = "INTO_SECTOR" if sector >= 58 else "OUT_OF_SECTOR" if sector <= 42 else "MIXED"
    return {"probability": round(probability, 2), "rotation_direction": direction, "sector_strength": round(sector, 2)}


def simulate_regime_flip_scenario(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    inputs = normalize_scenario_inputs(setup, context, market_data)
    regime = safe_text(inputs.get("regime"), "UNKNOWN")
    vol = safe_float(inputs.get("volatility_score"), 50.0)
    trend = safe_float(inputs.get("trend_score"), 50.0)
    probability = clamp(max(0.0, vol - 55.0) * 1.4 + (35.0 if regime in {"CHOPPY", "VOLATILE", "RISK_OFF"} else 10.0) + abs(trend - 50.0) * 0.25)
    return {"probability": round(probability, 2), "current_regime": regime, "flip_risk_score": round(probability, 2)}


def build_probability_tree(scenarios: Any = None) -> Dict[str, Any]:
    items = _dict(scenarios)
    branches = {}
    total = 0.0
    for key, value in items.items():
        probability = safe_float(_dict(value).get("probability"), 0.0)
        branches[key] = probability
        total += probability
    if total > 0:
        branches = {key: round(value / total * 100.0, 2) for key, value in branches.items()}
    dominant = max(branches, key=branches.get) if branches else "NONE"
    return {"branches": branches, "dominant_branch": dominant, "branch_count": len(branches)}


def calculate_expected_value_projection(setup: Any = None, scenarios: Any = None) -> Dict[str, Any]:
    setup_data = _dict(setup)
    raw = _dict(setup_data.get("raw"))
    rr = safe_float(setup_data.get("rr") or raw.get("rr") or setup_data.get("risk_reward") or raw.get("risk_reward"), 1.5)
    items = _dict(scenarios)
    bull = safe_float(_dict(items.get("bullish_scenario")).get("probability"), 50.0) / 100.0
    bear = safe_float(_dict(items.get("bearish_scenario")).get("probability"), 35.0) / 100.0
    shock = safe_float(_dict(items.get("volatility_shock_scenario")).get("probability"), 20.0) / 100.0
    ev = (bull * rr) - (bear * 1.0) - (shock * 0.35)
    score = clamp(50.0 + ev * 22.0)
    return {"expected_value": round(ev, 4), "ev_score": round(score, 2), "reward_risk_used": round(rr, 2)}


def build_multi_branch_forecast(setup: Any = None, scenarios: Any = None) -> Dict[str, Any]:
    tree = build_probability_tree(scenarios)
    branches = tree.get("branches", {})
    return {
        "primary_path": tree.get("dominant_branch"),
        "bullish_path_probability": branches.get("bullish_scenario", 0.0),
        "bearish_path_probability": branches.get("bearish_scenario", 0.0),
        "shock_path_probability": branches.get("volatility_shock_scenario", 0.0),
        "forecast_confidence": round(clamp(max(branches.values()) if branches else 0.0), 2),
    }


def run_stress_case_simulation(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    vol = simulate_volatility_shock_scenario(setup, context, market_data)
    flip = simulate_regime_flip_scenario(setup, context, market_data)
    bearish = simulate_bearish_scenario(setup, context, market_data)
    stress = clamp(safe_float(vol.get("shock_risk_score")) * 0.38 + safe_float(flip.get("flip_risk_score")) * 0.32 + safe_float(bearish.get("probability")) * 0.30)
    return {"stress_risk_score": round(stress, 2), "stress_state": "HIGH" if stress >= 70 else "ELEVATED" if stress >= 45 else "NORMAL"}


def _has_real_data(context: Dict[str, Any], market_data: Dict[str, Any], inputs: Dict[str, Any]) -> bool:
    return bool(inputs.get("rows") or market_data.get("ohlcv") or market_data.get("candles") or context.get("market_data"))


def build_scenario_simulation_report(setup: Any = None, context: Any = None, market_data: Any = None) -> Dict[str, Any]:
    inputs = normalize_scenario_inputs(setup, context, market_data)
    ctx = _dict(context)
    market = _dict(market_data)
    if _has_real_data(ctx, market, inputs):
        mode = "REAL_SCENARIO"
    elif inputs.get("proxy_available") and (inputs.get("entry") > 0 or ctx):
        mode = "PROXY"
    else:
        mode = "INSUFFICIENT"

    bullish = simulate_bullish_scenario(setup, context, market_data)
    bearish = simulate_bearish_scenario(setup, context, market_data)
    sideways = simulate_sideways_scenario(setup, context, market_data)
    shock = simulate_volatility_shock_scenario(setup, context, market_data)
    rotation = simulate_sector_rotation_scenario(setup, context, market_data)
    flip = simulate_regime_flip_scenario(setup, context, market_data)
    scenarios = {
        "bullish_scenario": bullish,
        "bearish_scenario": bearish,
        "sideways_scenario": sideways,
        "volatility_shock_scenario": shock,
        "sector_rotation_scenario": rotation,
        "regime_flip_scenario": flip,
    }
    tree = build_probability_tree(scenarios)
    ev = calculate_expected_value_projection(setup, scenarios)
    forecast = build_multi_branch_forecast(setup, scenarios)
    stress = run_stress_case_simulation(setup, context, market_data)

    if mode == "INSUFFICIENT":
        score = 50.0
        warning = "REVIEW"
    else:
        score = clamp(
            safe_float(ev.get("ev_score"), 50.0) * 0.42
            + safe_float(bullish.get("probability")) * 0.24
            + (100.0 - safe_float(bearish.get("probability"))) * 0.14
            + (100.0 - safe_float(stress.get("stress_risk_score"))) * 0.12
            + (100.0 - safe_float(flip.get("flip_risk_score"))) * 0.08
        )
        warning = "NONE"
        if safe_float(stress.get("stress_risk_score")) >= 78 or safe_float(bearish.get("probability")) >= 82:
            warning = "SKIP"
        elif safe_float(shock.get("shock_risk_score")) >= 65 or safe_float(flip.get("flip_risk_score")) >= 60:
            warning = "WAIT"
        elif safe_float(stress.get("stress_risk_score")) >= 45:
            warning = "REVIEW"

    bias = "BULLISH" if score >= 58 else "BEARISH" if score <= 42 else "NEUTRAL"
    explanations = [f"Scenario data mode: {mode}."]
    if safe_float(ev.get("expected_value")) > 0:
        explanations.append("Expected-value projection is positive.")
    if stress.get("stress_state") != "NORMAL":
        explanations.append(f"Stress case is {stress.get('stress_state')}.")
    if warning in {"WAIT", "REVIEW", "SKIP"}:
        explanations.append(f"Scenario warning is {warning}.")
    if mode == "INSUFFICIENT":
        explanations.append("No useful scenario inputs; score kept neutral.")

    report = {
        "symbol": inputs.get("symbol", "UNKNOWN"),
        "scenario_data_mode": mode,
        "bullish_scenario": bullish,
        "bearish_scenario": bearish,
        "sideways_scenario": sideways,
        "volatility_shock_scenario": shock,
        "sector_rotation_scenario": rotation,
        "regime_flip_scenario": flip,
        "probability_tree": tree,
        "expected_value_projection": ev,
        "multi_branch_forecast": forecast,
        "stress_case_simulation": stress,
        "scenario_score": round(clamp(score), 2),
        "scenario_bias": bias,
        "scenario_warning": warning,
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
    sample_setup = {"symbol": "RELIANCE", "side": "LONG", "entry": 100.0, "target": 103.0, "sl": 98.8, "rr": 2.5}
    sample_context = {"trend_score": 68, "momentum_score": 64, "sector_strength": 61, "volatility_score": 44, "market_regime": "TRENDING"}
    sample_market_data = {
        "ohlcv": [
            {"close": 98.5, "high": 99.0, "low": 97.9, "volume": 1000},
            {"close": 99.2, "high": 99.8, "low": 98.7, "volume": 1200},
            {"close": 100.0, "high": 100.6, "low": 99.4, "volume": 1500},
        ]
    }
    print(json.dumps(build_scenario_simulation_report(sample_setup, sample_context, sample_market_data), indent=2, sort_keys=True))
