"""
TITAN Phase 18 Step 1 - True Portfolio Brain Engine
---------------------------------------------------

Standalone, rule-based portfolio intelligence layer. It evaluates portfolio
exposure, crowding, concentration, risk heat, capital efficiency, and hedge
balance without touching Telegram, dashboard, broker/execution, or alert caps.
All functions fail open and return bounded neutral outputs for missing data.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List

try:
    from engines.pro_risk_engine import sector_for_symbol
except Exception:
    def sector_for_symbol(symbol: Any) -> str:
        return "UNKNOWN"


CORRELATION_GROUPS = {
    "FINANCIALS": {"BANKING", "NBFC", "FINANCIAL SERVICES", "INSURANCE"},
    "ENERGY": {"OIL & GAS", "ENERGY", "POWER", "ENERGY / COAL", "ENERGY / TELECOM / RETAIL"},
    "CONSUMPTION": {"FMCG", "CONSUMER", "PAINTS / CONSUMER", "CONSUMER / JEWELLERY"},
    "EXPORTERS": {"IT", "PHARMA", "TEXTILE", "CHEMICALS"},
    "CYCLICALS": {"AUTO", "METALS", "CEMENT", "CAPITAL GOODS / INFRASTRUCTURE", "CONGLOMERATE / INFRASTRUCTURE"},
}


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


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _symbol(row: Dict[str, Any]) -> str:
    raw = row.get("symbol") or row.get("stock") or row.get("ticker")
    return safe_text(raw, "UNKNOWN").replace(".NS", "").upper()


def _side(row: Dict[str, Any]) -> str:
    side = safe_text(row.get("side") or row.get("direction") or row.get("bias"), "UNKNOWN").upper()
    if side in {"BUY", "BULLISH"}:
        return "LONG"
    if side in {"SELL", "BEARISH"}:
        return "SHORT"
    return side


def _sector(row: Dict[str, Any]) -> str:
    sector = row.get("sector") or row.get("industry") or row.get("sector_name")
    if sector:
        return safe_text(sector, "UNKNOWN").upper()
    return safe_text(sector_for_symbol(_symbol(row)), "UNKNOWN").upper()


def _strategy_family(row: Dict[str, Any]) -> str:
    return safe_text(
        row.get("strategy_family")
        or row.get("setup_type")
        or row.get("strategy")
        or row.get("pattern"),
        "UNKNOWN",
    ).upper()


def _entry(row: Dict[str, Any]) -> float:
    return safe_float(row.get("entry") or row.get("entry_price") or row.get("price") or row.get("ltp"), 0.0)


def _quantity(row: Dict[str, Any]) -> float:
    return safe_float(row.get("quantity") or row.get("qty") or row.get("position_size") or row.get("shares"), 0.0)


def _exposure(row: Dict[str, Any]) -> float:
    explicit = safe_float(
        row.get("exposure")
        or row.get("notional")
        or row.get("position_value")
        or row.get("capital_used")
        or row.get("allocated_capital"),
        0.0,
    )
    if explicit > 0:
        return explicit
    return max(0.0, _entry(row) * _quantity(row))


def _risk_amount(row: Dict[str, Any]) -> float:
    explicit = safe_float(row.get("risk_amount") or row.get("risk") or row.get("max_loss"), 0.0)
    if explicit > 0:
        return explicit
    entry = _entry(row)
    stop = safe_float(row.get("sl") or row.get("stop_loss") or row.get("stoploss"), 0.0)
    qty = _quantity(row)
    if entry > 0 and stop > 0 and qty > 0:
        return abs(entry - stop) * qty
    exposure = _exposure(row)
    return exposure * 0.01 if exposure > 0 else 0.0


def _clean_trades(open_trades: Any) -> List[Dict[str, Any]]:
    rows = []
    for item in _as_list(open_trades):
        if not isinstance(item, dict):
            continue
        status = safe_text(item.get("status"), "OPEN").upper()
        if status and status not in {"OPEN", "ACTIVE", "LIVE", "PENDING", "TRIGGERED"}:
            continue
        rows.append(item)
    return rows


def _account_equity(open_trades: List[Dict[str, Any]], account_info: Any = None) -> float:
    account = _as_dict(account_info)
    equity = safe_float(account.get("equity") or account.get("capital") or account.get("account_size"), 0.0)
    if equity > 0:
        return equity
    exposure = sum(_exposure(row) for row in open_trades)
    return max(100000.0, exposure * 2.0)


def calculate_total_portfolio_exposure(open_trades: Any) -> float:
    rows = _clean_trades(open_trades)
    return round(sum(_exposure(row) for row in rows), 2)


def calculate_sector_exposure(open_trades: Any) -> Dict[str, Any]:
    rows = _clean_trades(open_trades)
    total = sum(_exposure(row) for row in rows)
    sectors: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        sector = _sector(row)
        exposure = _exposure(row)
        bucket = sectors.setdefault(sector, {"count": 0, "exposure": 0.0, "symbols": []})
        bucket["count"] += 1
        bucket["exposure"] += exposure
        bucket["symbols"].append(_symbol(row))

    for sector, bucket in sectors.items():
        bucket["exposure"] = round(bucket["exposure"], 2)
        bucket["exposure_pct"] = round((bucket["exposure"] / total * 100.0) if total > 0 else 0.0, 2)
        bucket["symbols"] = sorted(set(bucket["symbols"]))

    return sectors


def detect_same_direction_crowding(open_trades: Any) -> Dict[str, Any]:
    rows = _clean_trades(open_trades)
    long_count = sum(1 for row in rows if _side(row) == "LONG")
    short_count = sum(1 for row in rows if _side(row) == "SHORT")
    total = len(rows)
    dominant = "LONG" if long_count > short_count else "SHORT" if short_count > long_count else "BALANCED"
    dominant_count = max(long_count, short_count)
    crowding_pct = (dominant_count / total * 100.0) if total else 0.0
    risk_score = clamp((crowding_pct - 50.0) * 2.0 if total >= 2 else 0.0)

    return {
        "long_count": long_count,
        "short_count": short_count,
        "dominant_side": dominant,
        "crowding_pct": round(crowding_pct, 2),
        "risk_score": round(risk_score, 2),
        "active": bool(total >= 3 and crowding_pct >= 75.0),
    }


def detect_correlation_clusters(open_trades: Any) -> List[Dict[str, Any]]:
    rows = _clean_trades(open_trades)
    clusters = []
    for group, sectors in CORRELATION_GROUPS.items():
        members = []
        exposure = 0.0
        for row in rows:
            sector = _sector(row)
            if any(label in sector for label in sectors):
                members.append(_symbol(row))
                exposure += _exposure(row)
        if len(set(members)) >= 2:
            clusters.append({
                "cluster": group,
                "symbols": sorted(set(members)),
                "count": len(set(members)),
                "exposure": round(exposure, 2),
                "risk_score": round(clamp((len(set(members)) - 1) * 22.0), 2),
            })
    clusters.sort(key=lambda item: item["risk_score"], reverse=True)
    return clusters


def calculate_portfolio_heat_score(open_trades: Any) -> float:
    rows = _clean_trades(open_trades)
    total_exposure = calculate_total_portfolio_exposure(rows)
    equity = _account_equity(rows)
    exposure_pct = (total_exposure / equity * 100.0) if equity > 0 else 0.0
    total_risk_pct = (sum(_risk_amount(row) for row in rows) / equity * 100.0) if equity > 0 else 0.0
    crowding = detect_same_direction_crowding(rows).get("risk_score", 0.0)
    clusters = detect_correlation_clusters(rows)
    cluster_risk = max([safe_float(item.get("risk_score")) for item in clusters] or [0.0])
    heat = (exposure_pct * 0.45) + (total_risk_pct * 10.0) + (crowding * 0.20) + (cluster_risk * 0.20)
    return round(clamp(heat), 2)


def calculate_max_daily_risk(open_trades: Any, account_info: Any = None) -> float:
    rows = _clean_trades(open_trades)
    equity = _account_equity(rows, account_info)
    risk_pct = (sum(_risk_amount(row) for row in rows) / equity * 100.0) if equity > 0 else 0.0
    return round(clamp(risk_pct, 0.0, 100.0), 2)


def calculate_max_sector_risk(open_trades: Any) -> float:
    rows = _clean_trades(open_trades)
    equity = _account_equity(rows)
    sector_risk: Dict[str, float] = {}
    for row in rows:
        sector = _sector(row)
        sector_risk[sector] = sector_risk.get(sector, 0.0) + _risk_amount(row)
    max_risk = max(sector_risk.values()) if sector_risk else 0.0
    return round(clamp((max_risk / equity * 100.0) if equity > 0 else 0.0), 2)


def calculate_strategy_family_exposure(open_trades: Any) -> Dict[str, Any]:
    rows = _clean_trades(open_trades)
    total = sum(_exposure(row) for row in rows)
    families: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        family = _strategy_family(row)
        bucket = families.setdefault(family, {"count": 0, "exposure": 0.0})
        bucket["count"] += 1
        bucket["exposure"] += _exposure(row)
    for bucket in families.values():
        bucket["exposure"] = round(bucket["exposure"], 2)
        bucket["exposure_pct"] = round((bucket["exposure"] / total * 100.0) if total > 0 else 0.0, 2)
    return families


def calculate_capital_allocation_score(setup: Any, open_trades: Any) -> float:
    setup = _as_dict(setup)
    rows = _clean_trades(open_trades)
    candidate_exposure = _exposure(setup)
    if candidate_exposure <= 0:
        score = 60.0
    else:
        equity = _account_equity(rows + [setup])
        allocation_pct = candidate_exposure / equity * 100.0
        score = 100.0 - max(0.0, allocation_pct - 8.0) * 5.0

    sector = _sector(setup)
    same_sector_count = sum(1 for row in rows if _sector(row) == sector and sector != "UNKNOWN")
    same_symbol_count = sum(1 for row in rows if _symbol(row) == _symbol(setup) and _symbol(setup) != "UNKNOWN")
    score -= same_sector_count * 10.0
    score -= same_symbol_count * 25.0
    return round(clamp(score), 2)


def detect_drawdown_risk(open_trades: Any, performance_data: Any = None) -> Dict[str, Any]:
    rows = _clean_trades(open_trades)
    perf = _as_dict(performance_data)
    recent_losses = safe_int(perf.get("recent_losses") or perf.get("loss_streak"), 0)
    recent_trades = max(1, safe_int(perf.get("recent_trades"), len(rows) or 1))
    drawdown_pct = safe_float(perf.get("drawdown_pct") or perf.get("current_drawdown_pct"), 0.0)
    unrealized_pnl = sum(safe_float(row.get("pnl") or row.get("unrealized_pnl"), 0.0) for row in rows)
    equity = _account_equity(rows, perf)
    unrealized_dd_pct = abs(min(0.0, unrealized_pnl)) / equity * 100.0 if equity > 0 else 0.0
    effective_dd = max(drawdown_pct, unrealized_dd_pct)
    loss_rate = recent_losses / recent_trades
    risk_score = clamp((effective_dd * 8.0) + (loss_rate * 45.0))

    return {
        "drawdown_pct": round(effective_dd, 2),
        "recent_losses": recent_losses,
        "recent_trades": recent_trades,
        "loss_rate": round(loss_rate, 3),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "risk_score": round(risk_score, 2),
        "state": "HIGH" if risk_score >= 65 else "MEDIUM" if risk_score >= 35 else "LOW",
    }


def calculate_portfolio_var(open_trades: Any) -> float:
    rows = _clean_trades(open_trades)
    total_risk = sum(_risk_amount(row) for row in rows)
    cluster_risk = sum(safe_float(item.get("risk_score")) for item in detect_correlation_clusters(rows)) / 100.0
    crowding_multiplier = 1.0 + safe_float(detect_same_direction_crowding(rows).get("risk_score")) / 150.0
    var_value = total_risk * (1.0 + min(0.6, cluster_risk)) * crowding_multiplier
    return round(max(0.0, var_value), 2)


def run_portfolio_stress_test(open_trades: Any) -> Dict[str, Any]:
    rows = _clean_trades(open_trades)
    exposure = calculate_total_portfolio_exposure(rows)
    downside_2pct = exposure * 0.02
    downside_5pct = exposure * 0.05
    gap_risk = sum(_risk_amount(row) for row in rows) * 1.5
    correlated_shock = calculate_portfolio_var(rows) * 1.25
    worst_case = max(downside_5pct, gap_risk, correlated_shock)
    equity = _account_equity(rows)
    worst_case_pct = worst_case / equity * 100.0 if equity > 0 else 0.0

    return {
        "market_down_2pct_loss": round(downside_2pct, 2),
        "market_down_5pct_loss": round(downside_5pct, 2),
        "gap_risk_loss": round(gap_risk, 2),
        "correlated_shock_loss": round(correlated_shock, 2),
        "worst_case_loss": round(worst_case, 2),
        "worst_case_equity_pct": round(worst_case_pct, 2),
        "stress_state": "DANGER" if worst_case_pct >= 8 else "CAUTION" if worst_case_pct >= 4 else "SAFE",
    }


def detect_concentration_risk(open_trades: Any) -> Dict[str, Any]:
    rows = _clean_trades(open_trades)
    total = sum(_exposure(row) for row in rows)
    sector_data = calculate_sector_exposure(rows)
    max_sector_pct = max([safe_float(item.get("exposure_pct")) for item in sector_data.values()] or [0.0])
    symbol_exposure: Dict[str, float] = {}
    for row in rows:
        symbol_exposure[_symbol(row)] = symbol_exposure.get(_symbol(row), 0.0) + _exposure(row)
    max_symbol_pct = max([(value / total * 100.0) for value in symbol_exposure.values()] or [0.0]) if total > 0 else 0.0
    risk_score = clamp((max_sector_pct - 30.0) * 1.2 + (max_symbol_pct - 18.0) * 1.4)

    return {
        "max_sector_exposure_pct": round(max_sector_pct, 2),
        "max_symbol_exposure_pct": round(max_symbol_pct, 2),
        "risk_score": round(risk_score, 2),
        "state": "HIGH" if risk_score >= 65 else "MEDIUM" if risk_score >= 35 else "LOW",
    }


def calculate_cross_strategy_balance(open_trades: Any) -> float:
    rows = _clean_trades(open_trades)
    families = calculate_strategy_family_exposure(rows)
    if not rows:
        return 100.0
    family_count = len(families)
    max_family_pct = max([safe_float(item.get("exposure_pct")) for item in families.values()] or [0.0])
    score = 45.0 + min(35.0, family_count * 12.0) - max(0.0, max_family_pct - 45.0) * 0.8
    return round(clamp(score), 2)


def detect_hedge_intelligence(open_trades: Any, context: Any) -> Dict[str, Any]:
    rows = _clean_trades(open_trades)
    context = _as_dict(context)
    long_exposure = sum(_exposure(row) for row in rows if _side(row) == "LONG")
    short_exposure = sum(_exposure(row) for row in rows if _side(row) == "SHORT")
    gross = long_exposure + short_exposure
    hedge_ratio = min(long_exposure, short_exposure) / gross if gross > 0 else 0.0
    market_mode = safe_text(context.get("global_risk_mode") or context.get("market_type") or context.get("risk_mode"), "NEUTRAL").upper()
    desired = 0.10 if market_mode in {"RISK_ON", "BULLISH"} else 0.25 if market_mode in {"RISK_OFF", "BEARISH", "HIGH_RISK"} else 0.18
    quality = clamp(100.0 - abs(hedge_ratio - desired) * 220.0)

    return {
        "long_exposure": round(long_exposure, 2),
        "short_exposure": round(short_exposure, 2),
        "hedge_ratio": round(hedge_ratio, 3),
        "desired_hedge_ratio": round(desired, 3),
        "hedge_quality_score": round(quality, 2),
        "state": "BALANCED" if quality >= 65 else "UNDER_HEDGED" if hedge_ratio < desired else "OVER_HEDGED",
    }


def calculate_capital_efficiency_score(setup: Any, open_trades: Any) -> float:
    setup = _as_dict(setup)
    rows = _clean_trades(open_trades)
    rr = safe_float(setup.get("rr") or setup.get("risk_reward"), 1.0)
    score = safe_float(setup.get("score") or setup.get("final_score") or setup.get("rank_score"), 50.0)
    exposure = _exposure(setup)
    risk = _risk_amount(setup)
    reward_per_risk = clamp(rr * 25.0)
    quality = clamp(score)
    risk_efficiency = 70.0 if risk <= 0 else clamp((exposure / max(risk, 1.0)) * 2.0)
    heat_penalty = calculate_portfolio_heat_score(rows) * 0.25
    efficiency = (reward_per_risk * 0.35) + (quality * 0.35) + (risk_efficiency * 0.30) - heat_penalty
    return round(clamp(efficiency), 2)


def build_portfolio_brain_report(setup: Any, open_trades: Any, context: Any = None) -> Dict[str, Any]:
    setup = _as_dict(setup)
    rows = _clean_trades(open_trades)
    context = _as_dict(context)

    total_exposure = calculate_total_portfolio_exposure(rows)
    sector_exposure = calculate_sector_exposure(rows)
    crowding = detect_same_direction_crowding(rows)
    clusters = detect_correlation_clusters(rows)
    heat = calculate_portfolio_heat_score(rows)
    max_daily_risk = calculate_max_daily_risk(rows, context.get("account_info") if isinstance(context, dict) else None)
    max_sector_risk = calculate_max_sector_risk(rows)
    strategy_exposure = calculate_strategy_family_exposure(rows)
    allocation = calculate_capital_allocation_score(setup, rows)
    drawdown = detect_drawdown_risk(rows, context.get("performance_data") if isinstance(context, dict) else None)
    var_value = calculate_portfolio_var(rows)
    stress = run_portfolio_stress_test(rows)
    concentration = detect_concentration_risk(rows)
    strategy_balance = calculate_cross_strategy_balance(rows)
    hedge = detect_hedge_intelligence(rows, context)
    efficiency = calculate_capital_efficiency_score(setup, rows)

    safety = (
        (100.0 - heat) * 0.18
        + (100.0 - safe_float(crowding.get("risk_score"))) * 0.12
        + (100.0 - safe_float(concentration.get("risk_score"))) * 0.16
        + (100.0 - safe_float(drawdown.get("risk_score"))) * 0.14
        + allocation * 0.12
        + strategy_balance * 0.10
        + safe_float(hedge.get("hedge_quality_score")) * 0.08
        + efficiency * 0.10
    )
    safety = round(clamp(safety), 2)
    bias = "SAFE" if safety >= 70 else "DANGER" if safety < 40 else "CAUTION"

    explanations = []
    if not rows:
        explanations.append("No open trades found; portfolio risk is currently low.")
    if heat >= 65:
        explanations.append("Portfolio heat is elevated from exposure, risk, or crowding.")
    elif heat <= 30:
        explanations.append("Portfolio heat is controlled.")
    if crowding.get("active"):
        explanations.append(f"Same-direction crowding is active on {crowding.get('dominant_side')} trades.")
    if clusters:
        explanations.append(f"Correlation cluster risk detected in {clusters[0].get('cluster')}.")
    if concentration.get("state") != "LOW":
        explanations.append("Concentration risk is above normal limits.")
    if drawdown.get("state") != "LOW":
        explanations.append("Drawdown conditions require caution.")
    if allocation < 55:
        explanations.append("Candidate capital allocation is fragile versus current portfolio.")
    if strategy_balance >= 70:
        explanations.append("Strategy-family exposure is reasonably balanced.")
    if not explanations:
        explanations.append("Portfolio conditions are balanced with no major risk flags.")

    return {
        "symbol": _symbol(setup),
        "total_portfolio_exposure": total_exposure,
        "sector_exposure": sector_exposure,
        "same_direction_crowding": crowding,
        "correlation_clusters": clusters,
        "portfolio_heat_score": heat,
        "max_daily_risk": max_daily_risk,
        "max_sector_risk": max_sector_risk,
        "strategy_family_exposure": strategy_exposure,
        "capital_allocation_score": allocation,
        "drawdown_risk": drawdown,
        "portfolio_var": var_value,
        "stress_test_results": stress,
        "concentration_risk": concentration,
        "cross_strategy_balance": strategy_balance,
        "hedge_intelligence": hedge,
        "capital_efficiency_score": efficiency,
        "portfolio_safety_score": safety,
        "portfolio_bias": bias,
        "explanations": explanations[:8],
    }


if __name__ == "__main__":
    sample_open_trades = [
        {
            "symbol": "HDFCBANK",
            "sector": "Banking",
            "side": "LONG",
            "entry": 1530,
            "qty": 20,
            "stop_loss": 1500,
            "strategy_family": "Breakout",
            "status": "OPEN",
        },
        {
            "symbol": "ICICIBANK",
            "sector": "Banking",
            "side": "LONG",
            "entry": 1090,
            "qty": 18,
            "stop_loss": 1065,
            "strategy_family": "Momentum",
            "status": "LIVE",
        },
        {
            "symbol": "INFY",
            "sector": "IT",
            "side": "SHORT",
            "entry": 1420,
            "qty": 12,
            "stop_loss": 1450,
            "strategy_family": "Mean Reversion",
            "status": "OPEN",
        },
    ]
    sample_setup = {
        "symbol": "TCS",
        "sector": "IT",
        "side": "LONG",
        "entry": 3900,
        "qty": 5,
        "stop_loss": 3820,
        "rr": 2.4,
        "score": 74,
        "strategy_family": "Breakout",
    }
    sample_context = {
        "market_type": "RISK_ON",
        "account_info": {"equity": 250000},
        "performance_data": {"recent_losses": 2, "recent_trades": 10, "drawdown_pct": 1.8},
    }
    print(json.dumps(build_portfolio_brain_report(sample_setup, sample_open_trades, sample_context), indent=2, sort_keys=True))
