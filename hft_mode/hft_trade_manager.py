"""Trade manager for paper-only HFT simulated trades."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from hft_mode.hft_execution_engine import _safe_write
from hft_mode.hft_risk_engine import HFTRiskState, mark_cooldown

DEFAULT_TIMEOUT_SECONDS = 240


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _close_trade(
    state: HFTRiskState,
    trade: dict[str, Any],
    *,
    exit_price: float,
    outcome: str,
    closed_at: datetime,
) -> dict[str, Any]:
    pnl = round((exit_price - trade["entry_price"]) * trade["quantity"], 2)
    state.active_trades = [active for active in state.active_trades if active["trade_id"] != trade["trade_id"]]
    state.available_capital = round(state.available_capital + trade["capital_used"] + pnl, 2)
    state.daily_pnl = round(state.daily_pnl + pnl, 2)
    state.equity = round(state.equity + pnl, 2)
    state.peak_equity = max(state.peak_equity, state.equity)
    state.consecutive_losses = state.consecutive_losses + 1 if pnl < 0 else 0
    mark_cooldown(state, trade["symbol"], trade.get("strategy_name"), now=closed_at)

    closed = {
        **trade,
        "mode": "HFT",
        "status": "CLOSED",
        "outcome": outcome,
        "exit_price": exit_price,
        "pnl": pnl,
        "closed_at": closed_at.astimezone(timezone.utc).isoformat(),
        "capital_after_trade": state.available_capital,
    }
    _safe_write("hft_active_trades.json", {"active_trades": state.active_trades})
    _safe_write("hft_outcomes.json", {"outcomes": [closed]})
    _safe_write(
        "hft_closed_summary.json",
        {
            "closed_trades": 1,
            "wins": 1 if outcome == "WIN" else 0,
            "losses": 1 if outcome == "LOSS" else 0,
            "net_pnl": pnl,
        },
    )
    _safe_write("hft_daily_pnl.json", {"daily_pnl": [{"date": closed_at.date().isoformat(), "pnl": state.daily_pnl}]})
    return closed


def manage_simulated_trade(
    state: HFTRiskState,
    trade_id: str,
    *,
    current_price: float,
    now: datetime | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    trade = next((active for active in state.active_trades if active["trade_id"] == trade_id), None)
    if trade is None:
        return {"closed": False, "reason": "trade_not_found"}

    if current_price >= trade["take_profit_price"]:
        return {"closed": True, "trade": _close_trade(state, trade, exit_price=current_price, outcome="WIN", closed_at=current_time)}
    if current_price <= trade["stop_loss_price"]:
        return {"closed": True, "trade": _close_trade(state, trade, exit_price=current_price, outcome="LOSS", closed_at=current_time)}

    opened_at = _parse_time(trade["opened_at"])
    if current_time - opened_at >= timedelta(seconds=timeout_seconds):
        return {"closed": True, "trade": _close_trade(state, trade, exit_price=current_price, outcome="TIMEOUT", closed_at=current_time)}
    return {"closed": False, "reason": "still_open"}


def overnight_holding_allowed() -> bool:
    return False
