"""Stats engine for HFT-only paper trades."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from hft_mode import hft_config
from hft_mode.hft_execution_engine import _safe_write
from hft_mode.hft_risk_engine import HFTRiskState


def _best_and_worst(items: dict[str, float]) -> tuple[str | None, str | None]:
    if not items:
        return None, None
    return max(items, key=items.get), min(items, key=items.get)


def calculate_hft_stats(
    outcomes: list[dict[str, Any]],
    state: HFTRiskState,
    *,
    safety_status: str = "SEALED",
) -> dict[str, Any]:
    total = len(outcomes)
    wins = sum(1 for outcome in outcomes if outcome.get("result") == "WIN")
    losses = sum(1 for outcome in outcomes if outcome.get("result") == "LOSS")
    timeouts = sum(1 for outcome in outcomes if outcome.get("result") == "TIMEOUT")
    strategy_pnl: dict[str, float] = defaultdict(float)
    symbol_pnl: dict[str, float] = defaultdict(float)
    for outcome in outcomes:
        strategy_pnl[str(outcome.get("strategy_source"))] += float(outcome.get("pnl", 0.0))
        symbol_pnl[str(outcome.get("symbol"))] += float(outcome.get("pnl", 0.0))
    best_strategy, worst_strategy = _best_and_worst(strategy_pnl)
    best_symbol, worst_symbol = _best_and_worst(symbol_pnl)
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "accuracy": round((wins / total) * 100, 2) if total else 0.0,
        "open_trades": len(state.active_trades),
        "daily_pnl": state.daily_pnl,
        "current_capital": state.available_capital,
        "best_strategy": best_strategy,
        "worst_strategy": worst_strategy,
        "best_symbol": best_symbol,
        "worst_symbol": worst_symbol,
        "consecutive_losses": state.consecutive_losses,
        "safety_status": safety_status,
        "mode": hft_config.MODE,
        "connected_to_titan_runtime": False,
    }


def write_hft_stats(outcomes: list[dict[str, Any]], state: HFTRiskState, *, safety_status: str = "SEALED") -> dict[str, Any]:
    stats = calculate_hft_stats(outcomes, state, safety_status=safety_status)
    _safe_write("hft_stats.json", stats)
    _safe_write("hft_daily_pnl.json", {"daily_pnl": state.daily_pnl})
    return stats
