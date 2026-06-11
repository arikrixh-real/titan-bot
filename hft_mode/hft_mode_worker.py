"""Standalone HFT worker shell for isolated simulation cycles."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from hft_mode import hft_config
from hft_mode.hft_execution_engine import _safe_write
from hft_mode.hft_risk_engine import HFTRiskState
from hft_mode.hft_stats_engine import write_hft_stats

AUTO_STARTED = False


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def write_hft_health_heartbeat(
    state: HFTRiskState,
    *,
    cycle_start: datetime,
    cycle_duration_ms: float,
    feed_status: str = "SIMULATION_ONLY",
    safety_status: str = "SEALED",
    running: bool = False,
) -> dict[str, Any]:
    payload = {
        "running": running,
        "last_cycle_time": _iso(cycle_start),
        "cycle_duration_ms": round(cycle_duration_ms, 3),
        "active_trade": bool(state.active_trades),
        "trades_today": 0,
        "daily_pnl": state.daily_pnl,
        "safety_status": safety_status,
        "feed_status": feed_status,
        "mode": hft_config.MODE,
        "connected_to_titan_runtime": False,
        "broker_allowed": hft_config.BROKER_ALLOWED,
        "telegram_allowed": hft_config.TELEGRAM_ALLOWED,
    }
    _safe_write("hft_health.json", payload)
    return payload


def run_isolated_simulation_cycle(
    state: HFTRiskState | None = None,
    outcomes: list[dict[str, Any]] | None = None,
    *,
    internal_simulation_mode: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not internal_simulation_mode:
        return {
            "ran": False,
            "reason_if_rejected": "internal_simulation_mode_required",
            "connected_to_titan_runtime": False,
            "mode": hft_config.MODE,
        }
    if hft_config.MODE != "SIMULATION_ONLY":
        return {
            "ran": False,
            "reason_if_rejected": "mode_not_simulation_only",
            "connected_to_titan_runtime": False,
            "mode": hft_config.MODE,
        }

    risk_state = state or HFTRiskState()
    cycle_start = now or datetime.now(timezone.utc)
    start = perf_counter()
    stats = write_hft_stats(outcomes or [], risk_state, safety_status="SEALED")
    duration_ms = (perf_counter() - start) * 1000
    health = write_hft_health_heartbeat(
        risk_state,
        cycle_start=cycle_start,
        cycle_duration_ms=duration_ms,
        running=False,
    )
    return {
        "ran": True,
        "stats": stats,
        "health": health,
        "connected_to_titan_runtime": False,
        "mode": hft_config.MODE,
    }
