"""Outcome tracker for HFT-only paper trades."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from hft_mode.hft_execution_engine import _safe_write


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compact_hft_outcome(closed_trade: dict[str, Any]) -> dict[str, Any]:
    entry_time = closed_trade["opened_at"]
    exit_time = closed_trade["closed_at"]
    duration = int((_parse_time(exit_time) - _parse_time(entry_time)).total_seconds())
    return {
        "symbol": closed_trade["symbol"],
        "strategy_source": closed_trade.get("strategy_name"),
        "entry_price": closed_trade["entry_price"],
        "exit_price": closed_trade["exit_price"],
        "entry_time": entry_time,
        "exit_time": exit_time,
        "result": closed_trade["outcome"],
        "pnl": closed_trade["pnl"],
        "duration_seconds": duration,
        "capital_after_trade": closed_trade["capital_after_trade"],
    }


def write_hft_outcomes(closed_trades: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = [compact_hft_outcome(trade) for trade in closed_trades]
    payload = {"outcomes": outcomes}
    _safe_write("hft_outcomes.json", payload)
    return payload
