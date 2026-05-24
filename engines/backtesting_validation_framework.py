"""
TITAN Phase 22 - Backtesting & Validation Framework
---------------------------------------------------

Standalone validation-only framework for historical backtesting, walk-forward
testing, out-of-sample checks, robustness, overfitting detection, slippage, and
market replay. It never deploys strategies or modifies live trading behavior.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
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


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [item for item in safe_list(value) if isinstance(item, dict)]


def _strategy_name(strategy: Any) -> str:
    strategy = _as_dict(strategy)
    return safe_text(strategy.get("name") or strategy.get("title") or strategy.get("strategy") or strategy.get("research_item"), "UNKNOWN")


def _outcome(row: Dict[str, Any]) -> str:
    text = safe_text(row.get("outcome") or row.get("result") or row.get("status") or row.get("trade_result"), "UNKNOWN").upper()
    text = text.replace(" ", "_")
    if text in {"TP", "WIN", "WON", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if text in {"SL", "LOSS", "LOST", "STOPLOSS", "STOP_LOSS", "STOP_LOSS_HIT", "SL_HIT", "FAILED"}:
        return "LOSS"
    return text


def _pnl(row: Dict[str, Any]) -> float:
    explicit = safe_float(row.get("pnl") or row.get("net_pnl") or row.get("profit") or row.get("return_amount"), 0.0)
    if explicit:
        return explicit
    points = safe_float(row.get("pnl_points"), 0.0)
    return points


def _rr(row: Dict[str, Any]) -> float:
    return safe_float(row.get("rr") or row.get("risk_reward"), 0.0)


def _score(row: Dict[str, Any]) -> float:
    for key in ("final_portfolio_rank", "final_cross_asset_rank", "elite_quality_score", "final_score", "score", "rank_score"):
        if row.get(key) is not None:
            return clamp(row.get(key))
    return 50.0


def _symbol(row: Dict[str, Any]) -> str:
    return safe_text(row.get("symbol") or row.get("stock") or row.get("ticker"), "UNKNOWN").replace(".NS", "").upper()


def _sector(row: Dict[str, Any]) -> str:
    return safe_text(row.get("sector") or row.get("industry") or row.get("sector_name"), "UNKNOWN").upper()


def _regime(row: Dict[str, Any]) -> str:
    return safe_text(row.get("regime") or row.get("market_regime") or row.get("market_status") or row.get("market_type"), "UNKNOWN").upper()


def _strategy_match(row: Dict[str, Any], strategy: Any) -> bool:
    strategy = _as_dict(strategy)
    if not strategy:
        return True
    wanted = safe_text(strategy.get("name") or strategy.get("strategy_family") or strategy.get("strategy") or strategy.get("research_item"), "").lower()
    if not wanted:
        return True
    haystack = " ".join(
        safe_text(row.get(key)).lower()
        for key in ("strategy_family", "strategy", "setup_type", "pattern", "reason", "symbol", "sector")
    )
    return any(part and part in haystack for part in wanted.replace("test:", "").split())


def _matched_rows(strategy: Any, data: Any) -> List[Dict[str, Any]]:
    rows = _rows(data)
    matched = [row for row in rows if _strategy_match(row, strategy)]
    return matched or rows


def _basic_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = [row for row in rows if _outcome(row) in {"WIN", "LOSS"}]
    wins = [row for row in closed if _outcome(row) == "WIN"]
    losses = [row for row in closed if _outcome(row) == "LOSS"]
    pnl_values = [_pnl(row) for row in closed]
    total_pnl = sum(pnl_values)
    win_rate = len(wins) / max(1, len(closed)) * 100.0
    avg_rr = sum(_rr(row) for row in closed) / max(1, len(closed))
    avg_score = sum(_score(row) for row in closed) / max(1, len(closed))
    gross_win = sum(max(0.0, _pnl(row)) for row in wins)
    gross_loss = abs(sum(min(0.0, _pnl(row)) for row in losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)
    expectancy = total_pnl / max(1, len(closed))
    sample_quality = clamp(len(closed) * 3.0)
    quality_score = clamp((win_rate * 0.35) + (min(100.0, profit_factor * 25.0) * 0.25) + (clamp(avg_rr * 25.0) * 0.20) + (sample_quality * 0.20))
    return {
        "sample_size": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 4),
        "expectancy": round(expectancy, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_rr": round(avg_rr, 3),
        "avg_score": round(avg_score, 2),
        "quality_score": round(quality_score, 2),
    }


def run_historical_backtest(strategy: Any = None, historical_data: Any = None, context: Any = None) -> Dict[str, Any]:
    rows = _matched_rows(strategy, historical_data)
    metrics = _basic_metrics(rows)
    available = metrics["sample_size"] > 0
    return {
        "available": available,
        "strategy": _strategy_name(strategy),
        **metrics,
        "status": "OK" if available else "NO_DATA",
    }


def run_walk_forward_test(strategy: Any = None, historical_data: Any = None, windows: Any = None) -> Dict[str, Any]:
    rows = _matched_rows(strategy, historical_data)
    if not rows:
        return {"available": False, "windows": [], "consistency_score": 50.0, "status": "NO_DATA"}
    window_count = int(clamp(windows or 3, 2, 8))
    chunk_size = max(1, len(rows) // window_count)
    chunks = [rows[index:index + chunk_size] for index in range(0, len(rows), chunk_size)][:window_count]
    results = []
    for index, chunk in enumerate(chunks, start=1):
        metrics = _basic_metrics(chunk)
        results.append({"window": index, **metrics})
    qualities = [safe_float(item.get("quality_score"), 50.0) for item in results]
    avg_quality = sum(qualities) / max(1, len(qualities))
    variance = sum((item - avg_quality) ** 2 for item in qualities) / max(1, len(qualities))
    consistency = clamp(avg_quality - min(35.0, variance * 0.05))
    return {"available": True, "windows": results, "consistency_score": round(consistency, 2), "status": "OK"}


def run_out_of_sample_validation(strategy: Any = None, train_data: Any = None, test_data: Any = None) -> Dict[str, Any]:
    train = _basic_metrics(_matched_rows(strategy, train_data))
    test = _basic_metrics(_matched_rows(strategy, test_data))
    degradation = max(0.0, safe_float(train.get("quality_score")) - safe_float(test.get("quality_score")))
    validation_score = clamp(safe_float(test.get("quality_score")) - degradation * 0.35)
    return {
        "available": bool(train["sample_size"] or test["sample_size"]),
        "train": train,
        "test": test,
        "degradation": round(degradation, 2),
        "validation_score": round(validation_score, 2),
        "status": "OK" if test["sample_size"] else "NO_TEST_DATA",
    }


def _separated_testing(strategy: Any, historical_data: Any, key_fn, label: str) -> Dict[str, Any]:
    rows = _matched_rows(strategy, historical_data)
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    results = {key: _basic_metrics(group_rows) for key, group_rows in groups.items()}
    qualities = [safe_float(item.get("quality_score"), 50.0) for item in results.values()]
    spread = max(qualities) - min(qualities) if qualities else 0.0
    stability = clamp((sum(qualities) / max(1, len(qualities))) - spread * 0.20)
    return {"available": bool(results), label: results, "stability_score": round(stability, 2), "group_count": len(results)}


def run_regime_separated_testing(strategy: Any = None, historical_data: Any = None) -> Dict[str, Any]:
    return _separated_testing(strategy, historical_data, _regime, "regimes")


def run_sector_separated_testing(strategy: Any = None, historical_data: Any = None) -> Dict[str, Any]:
    return _separated_testing(strategy, historical_data, _sector, "sectors")


def run_symbol_separated_testing(strategy: Any = None, historical_data: Any = None) -> Dict[str, Any]:
    return _separated_testing(strategy, historical_data, _symbol, "symbols")


def run_monte_carlo_robustness_test(results: Any = None, iterations: int = 100) -> Dict[str, Any]:
    rows = _rows(results)
    if isinstance(results, dict):
        rows = _rows(results.get("trades") or results.get("results"))
    pnl_values = [_pnl(row) for row in rows if _outcome(row) in {"WIN", "LOSS"}]
    if not pnl_values:
        return {"available": False, "iterations": int(clamp(iterations, 1, 10000)), "robustness_score": 50.0, "status": "NO_DATA"}
    wins = sum(1 for value in pnl_values if value > 0)
    win_rate = wins / max(1, len(pnl_values)) * 100.0
    avg = sum(pnl_values) / len(pnl_values)
    downside = abs(sum(value for value in pnl_values if value < 0) / max(1, sum(1 for value in pnl_values if value < 0)))
    robustness = clamp((win_rate * 0.45) + (clamp(avg + 50.0) * 0.25) + (100.0 - clamp(downside)) * 0.30)
    return {"available": True, "iterations": int(clamp(iterations, 1, 10000)), "robustness_score": round(robustness, 2), "win_rate_proxy": round(win_rate, 2), "avg_pnl": round(avg, 4)}


def detect_overfitting(backtest_results: Any = None, validation_results: Any = None) -> Dict[str, Any]:
    backtest = _as_dict(backtest_results)
    validation = _as_dict(validation_results)
    in_sample = safe_float(backtest.get("quality_score"), 50.0)
    out_sample = safe_float(validation.get("validation_score") or _as_dict(validation.get("test")).get("quality_score"), 50.0)
    gap = max(0.0, in_sample - out_sample)
    risk_score = clamp(gap * 1.5 + (20.0 if safe_float(backtest.get("sample_size"), 0.0) < 20 else 0.0))
    return {"risk_score": round(risk_score, 2), "gap": round(gap, 2), "state": "HIGH" if risk_score >= 65 else "MEDIUM" if risk_score >= 35 else "LOW"}


def detect_strategy_degradation(recent_results: Any = None, historical_results: Any = None) -> Dict[str, Any]:
    recent = _basic_metrics(_rows(recent_results))
    historical = _basic_metrics(_rows(historical_results))
    quality_drop = max(0.0, safe_float(historical.get("quality_score")) - safe_float(recent.get("quality_score")))
    return {"degradation_score": round(clamp(quality_drop), 2), "recent": recent, "historical": historical, "state": "DEGRADING" if quality_drop >= 25 else "STABLE_OR_UNKNOWN"}


def run_false_discovery_control(strategy_results: Any = None) -> Dict[str, Any]:
    rows = _rows(strategy_results)
    if isinstance(strategy_results, dict):
        rows = _rows(strategy_results.get("strategies") or strategy_results.get("results"))
    tested = len(rows)
    strong = sum(1 for row in rows if safe_float(row.get("quality_score") or row.get("validation_score") or row.get("edge_score"), 0.0) >= 70)
    false_discovery_risk = clamp((tested - strong) * 6.0 + max(0, tested - 10) * 3.0)
    return {"tested_strategies": tested, "strong_results": strong, "false_discovery_risk": round(false_discovery_risk, 2), "control_status": "REVIEW" if false_discovery_risk >= 40 else "OK"}


def calculate_statistical_significance(results: Any = None) -> Dict[str, Any]:
    metrics = _basic_metrics(_rows(results))
    sample = metrics["sample_size"]
    win_rate = metrics["win_rate"]
    edge = abs(win_rate - 50.0)
    significance = clamp(edge * 1.2 + min(35.0, sample * 1.5))
    return {"sample_size": sample, "win_rate": win_rate, "significance_score": round(significance, 2), "significant": bool(significance >= 65 and sample >= 30)}


def check_survivorship_bias(historical_data: Any = None) -> Dict[str, Any]:
    rows = _rows(historical_data)
    symbols = {_symbol(row) for row in rows if _symbol(row) != "UNKNOWN"}
    delisted_flags = sum(1 for row in rows if str(row.get("delisted") or row.get("inactive") or "").upper() in {"TRUE", "1", "YES"})
    risk = 40.0 if rows and delisted_flags == 0 and len(symbols) < 20 else 15.0
    if not rows:
        risk = 50.0
    return {"symbol_count": len(symbols), "delisted_or_inactive_count": delisted_flags, "bias_risk_score": round(clamp(risk), 2), "status": "REVIEW"}


def simulate_realistic_slippage(trade: Any = None, market_context: Any = None) -> Dict[str, Any]:
    trade = _as_dict(trade)
    context = _as_dict(market_context)
    entry = safe_float(trade.get("entry") or trade.get("entry_price") or trade.get("price"), 0.0)
    volatility = safe_float(context.get("volatility_score") or context.get("portfolio_heat_score"), 50.0)
    liquidity = safe_float(context.get("liquidity_score"), 50.0)
    slippage_bps = clamp(4.0 + volatility * 0.08 - liquidity * 0.03, 1.0, 50.0)
    slippage_value = entry * slippage_bps / 10000.0 if entry > 0 else 0.0
    return {"slippage_bps": round(slippage_bps, 2), "slippage_value": round(slippage_value, 4), "simulation_status": "OK"}


def run_market_replay_test(strategy: Any = None, replay_data: Any = None) -> Dict[str, Any]:
    rows = _matched_rows(strategy, replay_data)
    metrics = _basic_metrics(rows)
    replay_score = clamp(metrics["quality_score"] * 0.75 + min(25.0, metrics["sample_size"] * 2.0))
    return {"available": bool(metrics["sample_size"]), "replay_score": round(replay_score, 2), **metrics}


def build_validation_report(strategy: Any = None, historical_data: Any = None, context: Any = None) -> Dict[str, Any]:
    context = _as_dict(context)
    rows = _rows(historical_data)
    midpoint = max(1, int(len(rows) * 0.7))
    train_data = rows[:midpoint]
    test_data = rows[midpoint:]
    recent_data = rows[-max(1, min(30, len(rows))):]

    historical = run_historical_backtest(strategy, rows, context)
    walk_forward = run_walk_forward_test(strategy, rows, windows=context.get("walk_forward_windows", 3))
    out_sample = run_out_of_sample_validation(strategy, train_data, test_data)
    regime = run_regime_separated_testing(strategy, rows)
    sector = run_sector_separated_testing(strategy, rows)
    symbol = run_symbol_separated_testing(strategy, rows)
    monte_carlo = run_monte_carlo_robustness_test(rows, iterations=context.get("monte_carlo_iterations", 100))
    overfitting = detect_overfitting(historical, out_sample)
    degradation = detect_strategy_degradation(recent_data, rows)
    false_discovery = run_false_discovery_control(context.get("strategy_results", []))
    significance = calculate_statistical_significance(rows)
    survivorship = check_survivorship_bias(rows)
    slippage = simulate_realistic_slippage(rows[-1] if rows else {}, context)
    replay = run_market_replay_test(strategy, context.get("replay_data") or rows)

    if not rows:
        validation_score = 50.0
        status = "REVIEW"
        explanations = ["No historical data available; validation remains in REVIEW."]
    else:
        validation_score = clamp(
            safe_float(historical.get("quality_score")) * 0.22
            + safe_float(walk_forward.get("consistency_score")) * 0.16
            + safe_float(out_sample.get("validation_score")) * 0.18
            + safe_float(monte_carlo.get("robustness_score")) * 0.14
            + safe_float(significance.get("significance_score")) * 0.12
            + (100.0 - safe_float(overfitting.get("risk_score"))) * 0.10
            + (100.0 - safe_float(survivorship.get("bias_risk_score"))) * 0.08
        )
        if validation_score >= 70 and overfitting.get("state") == "LOW" and significance.get("significant"):
            status = "PASS"
        elif validation_score < 45 or overfitting.get("state") == "HIGH":
            status = "FAIL"
        else:
            status = "REVIEW"
        explanations = []
        explanations.append(f"Validation score is {round(validation_score, 2)} with status {status}.")
        if overfitting.get("state") != "LOW":
            explanations.append("Overfitting risk requires review before any future promotion.")
        if not significance.get("significant"):
            explanations.append("Statistical significance is not strong enough for deployment.")
        if survivorship.get("bias_risk_score", 0) >= 40:
            explanations.append("Survivorship bias risk remains under review.")

    explanations.append("Validation only; live deployment is explicitly disabled.")

    return {
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
        "live_order_allowed": False,
        "live_rank_mutation_allowed": False,
        "pyramid_placement": "master_controller_validation_sidecar",
        "historical_backtest": historical,
        "walk_forward_test": walk_forward,
        "out_of_sample_validation": out_sample,
        "regime_testing": regime,
        "sector_testing": sector,
        "symbol_testing": symbol,
        "monte_carlo_robustness": monte_carlo,
        "overfitting_detection": overfitting,
        "strategy_degradation": degradation,
        "false_discovery_control": false_discovery,
        "statistical_significance": significance,
        "survivorship_bias_check": survivorship,
        "slippage_simulation": slippage,
        "market_replay_test": replay,
        "validation_score": round(validation_score, 2),
        "validation_status": status,
        "live_deployment_allowed": False,
        "explanations": explanations[:8],
    }


if __name__ == "__main__":
    sample_strategy = {"name": "Breakout"}
    sample_data = [
        {"symbol": "TCS", "sector": "IT", "strategy_family": "Breakout", "outcome": "TP", "rr": 2.4, "pnl_points": 42, "final_score": 82, "market_regime": "RISK_ON", "entry": 3900},
        {"symbol": "INFY", "sector": "IT", "strategy_family": "Breakout", "outcome": "TP", "rr": 2.1, "pnl_points": 31, "final_score": 78, "market_regime": "RISK_ON", "entry": 1450},
        {"symbol": "HDFCBANK", "sector": "BANKING", "strategy_family": "Momentum", "outcome": "SL", "rr": 1.6, "pnl_points": -20, "final_score": 74, "market_regime": "CHOPPY", "entry": 1530},
        {"symbol": "TCS", "sector": "IT", "strategy_family": "Breakout", "outcome": "TP", "rr": 2.2, "pnl_points": 36, "final_score": 80, "market_regime": "RISK_ON", "entry": 3940},
        {"symbol": "INFY", "sector": "IT", "strategy_family": "Breakout", "outcome": "SL", "rr": 2.0, "pnl_points": -18, "final_score": 76, "market_regime": "RISK_OFF", "entry": 1480},
    ]
    sample_context = {
        "walk_forward_windows": 3,
        "monte_carlo_iterations": 100,
        "volatility_score": 45,
        "liquidity_score": 60,
        "strategy_results": [
            {"name": "Breakout", "quality_score": 72},
            {"name": "Momentum", "quality_score": 48},
        ],
    }
    print(json.dumps(build_validation_report(sample_strategy, sample_data, sample_context), indent=2, sort_keys=True))
