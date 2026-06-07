"""
TITAN Phase 1 - Professional Risk Engine
----------------------------------------

Research-only risk guards for setup quality. This module does not place,
modify, or close broker orders.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable

from data.active_trade_store import load_canonical_open_trades


ACTIVE_TRADE_FILES = [
    Path("data/journals/active_trades.csv"),
]

OUTCOME_FILES = [
    Path("data/journals/trade_results.csv"),
    Path("data/journals/trade_outcomes.csv"),
    Path("data/journals/trade_outcomes.jsonl"),
]

MAX_OPEN_TRADES = 8
MAX_SECTOR_OPEN_TRADES = 3
RECENT_OUTCOME_LIMIT = 12
MAX_RECENT_LOSSES = 5

SECTOR_MAP = {
    "RELIANCE": "Energy / Telecom / Retail",
    "ONGC": "Oil & Gas",
    "COALINDIA": "Energy / Coal",
    "NTPC": "Power",
    "POWERGRID": "Power",
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "LTIM": "IT",
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "AXISBANK": "Banking",
    "KOTAKBANK": "Banking",
    "BANKBARODA": "Banking",
    "CANBK": "Banking",
    "PNB": "Banking",
    "BAJFINANCE": "NBFC",
    "BAJAJFINSV": "Financial Services",
    "HDFCLIFE": "Insurance",
    "SBILIFE": "Insurance",
    "SBICARD": "Financial Services",
    "BHARTIARTL": "Telecom",
    "ADANIENT": "Conglomerate / Infrastructure",
    "ADANIPORTS": "Ports / Logistics",
    "LT": "Capital Goods / Infrastructure",
    "TATAMOTORS": "Auto",
    "MARUTI": "Auto",
    "M&M": "Auto",
    "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto",
    "HEROMOTOCO": "Auto",
    "TVSMOTOR": "Auto",
    "INDIGO": "Aviation",
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "TATACONSUM": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "MARICO": "FMCG",
    "DABUR": "FMCG",
    "COLPAL": "FMCG",
    "GODREJCP": "FMCG",
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "LUPIN": "Pharma",
    "AUROPHARMA": "Pharma",
    "TORNTPHARM": "Pharma",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "JINDALSTEL": "Metals",
    "SAIL": "Metals",
    "NMDC": "Metals",
    "VEDL": "Metals",
    "ULTRACEMCO": "Cement",
    "AMBUJACEM": "Cement",
    "ACC": "Cement",
    "GRASIM": "Cement / Chemicals",
    "ASIANPAINT": "Paints / Consumer",
    "TITAN": "Consumer / Jewellery",
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


def normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").replace(".NS", "").strip().upper()


def sector_for_symbol(symbol: Any) -> str:
    return SECTOR_MAP.get(normalize_symbol(symbol), "UNKNOWN")


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []

    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _open_trade_rows() -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for row in load_canonical_open_trades():
        symbol = normalize_symbol(row.get("symbol"))
        side = str(row.get("side", "")).upper()
        key = f"{symbol}|{side}"

        if not symbol or key in seen:
            continue

        seen.add(key)
        rows.append(row)

    return rows


def _recent_outcomes() -> list[str]:
    outcomes = []

    for path in OUTCOME_FILES:
        if not path.exists() or path.stat().st_size == 0:
            continue

        if path.suffix == ".jsonl":
            try:
                lines = path.read_text(encoding="utf-8").splitlines()[-RECENT_OUTCOME_LIMIT:]
            except Exception:
                lines = []
            for line in lines:
                upper = line.upper()
                if "LOSS" in upper or '"SL"' in upper:
                    outcomes.append("LOSS")
                elif "WIN" in upper or "TARGET" in upper or '"TP"' in upper:
                    outcomes.append("WIN")
            continue

        for row in _read_csv_rows(path)[-RECENT_OUTCOME_LIMIT:]:
            result = str(row.get("result") or row.get("outcome") or "").upper()
            if result in {"LOSS", "SL", "STOP_LOSS"}:
                outcomes.append("LOSS")
            elif result in {"WIN", "TARGET", "TP"}:
                outcomes.append("WIN")

    return outcomes[-RECENT_OUTCOME_LIMIT:]


def _count_sector_open(rows: Iterable[dict[str, Any]], sector: str) -> int:
    count = 0
    for row in rows:
        if sector_for_symbol(row.get("symbol")) == sector:
            count += 1
    return count


def evaluate_professional_risk(
    setup: Dict[str, Any],
    microstructure: Dict[str, Any] | None = None,
    regime: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Evaluates non-broker risk quality and explicit hard-risk blocks.
    """

    microstructure = microstructure or {}
    regime = regime or {}

    symbol = normalize_symbol(setup.get("symbol"))
    sector = sector_for_symbol(symbol)
    score = _safe_float(setup.get("score"))
    rr = _safe_float(setup.get("rr"))

    open_rows = _open_trade_rows()
    open_count = len(open_rows)
    sector_open_count = _count_sector_open(open_rows, sector) if sector != "UNKNOWN" else 0

    recent_outcomes = _recent_outcomes()
    recent_losses = recent_outcomes.count("LOSS")
    loss_rate = recent_losses / max(len(recent_outcomes), 1)

    liquidity_quality = _safe_float(microstructure.get("liquidity_quality_score"), 50.0)
    spread_quality = _safe_float(microstructure.get("spread_behavior_proxy"), 50.0)
    panic_score = _safe_float(regime.get("panic_score"), 0.0)
    liquidity_crisis_score = _safe_float(regime.get("liquidity_crisis_score"), 0.0)
    regime_type = str(regime.get("regime_type") or "UNKNOWN").upper()

    volatility_adjusted_risk_quality = _clamp(
        100.0
        - (panic_score * 0.35)
        - (liquidity_crisis_score * 0.35)
        + ((liquidity_quality - 50.0) * 0.25)
        + ((spread_quality - 50.0) * 0.15)
    )

    drawdown_guard = {
        "active": bool(len(recent_outcomes) >= 6 and recent_losses >= MAX_RECENT_LOSSES),
        "recent_outcomes": len(recent_outcomes),
        "recent_losses": recent_losses,
        "loss_rate": round(loss_rate, 3),
    }

    sector_exposure_guard = {
        "active": bool(sector != "UNKNOWN" and sector_open_count >= MAX_SECTOR_OPEN_TRADES),
        "sector": sector,
        "open_in_sector": sector_open_count,
        "max_sector_open_trades": MAX_SECTOR_OPEN_TRADES,
    }

    max_open_trades_guard = {
        "active": bool(open_count >= MAX_OPEN_TRADES),
        "open_trades": open_count,
        "max_open_trades": MAX_OPEN_TRADES,
    }

    bad_regime_guard_active = bool(
        regime_type in {"PANIC_VOLATILITY_SPIKE", "LIQUIDITY_CRISIS"}
        and (score < 3.0 or rr < 2.0 or liquidity_quality < 55.0)
    )

    risk_blocks = []
    risk_warnings = []

    if max_open_trades_guard["active"]:
        risk_blocks.append("max_open_trades_guard")

    if sector_exposure_guard["active"]:
        risk_blocks.append("sector_exposure_guard")

    if liquidity_crisis_score >= 75.0 and liquidity_quality < 45.0:
        risk_blocks.append("liquidity_crisis_low_quality")

    if bad_regime_guard_active:
        risk_blocks.append("bad_regime_weak_trade")

    if drawdown_guard["active"]:
        risk_warnings.append("recent_drawdown_guard_active")

    if volatility_adjusted_risk_quality < 45.0:
        risk_warnings.append("poor_volatility_adjusted_risk_quality")

    if rr < 2.0:
        risk_warnings.append("rr_below_phase1_preferred_2r")

    risk_quality_score = _clamp(
        (score * 12.0)
        + (min(rr, 3.0) * 10.0)
        + (liquidity_quality * 0.25)
        + (volatility_adjusted_risk_quality * 0.25)
        - (len(risk_blocks) * 22.0)
        - (len(risk_warnings) * 5.0)
    )

    return {
        "risk_allowed": len(risk_blocks) == 0,
        "risk_quality_score": round(risk_quality_score, 2),
        "risk_blocks": risk_blocks,
        "risk_warnings": risk_warnings,
        "drawdown_guard": drawdown_guard,
        "sector_exposure_guard": sector_exposure_guard,
        "max_open_trades_guard": max_open_trades_guard,
        "bad_regime_guard": {"active": bad_regime_guard_active},
        "volatility_adjusted_risk_quality": round(volatility_adjusted_risk_quality, 2),
        "sector": sector,
    }
