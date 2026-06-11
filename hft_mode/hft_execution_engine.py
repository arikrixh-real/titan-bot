"""Paper-only HFT simulation execution engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from hft_mode import hft_config
from hft_mode.hft_data_contracts import HFTCandidate
from hft_mode.hft_risk_engine import HFTRiskState, evaluate_hft_risk
from hft_mode.hft_runtime_state import write_hft_json
from hft_mode.hft_safety_gate import assert_broker_allowed, assert_telegram_allowed


ALLOWED_HFT_WRITE_FILES = {
    "hft_runtime_state.json",
    "hft_active_trades.json",
    "hft_closed_summary.json",
    "hft_outcomes.json",
    "hft_daily_pnl.json",
    "hft_rejected_count.json",
    "hft_stats.json",
    "hft_health.json",
}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _safe_write(file_name: str, payload: dict[str, Any]) -> None:
    if file_name not in ALLOWED_HFT_WRITE_FILES:
        raise ValueError("HFT simulation writes must use approved hft_mode data files")
    write_hft_json(file_name, payload)


def _persist_state(state: HFTRiskState, rejection_reason: str | None = None) -> None:
    _safe_write("hft_active_trades.json", {"active_trades": state.active_trades})
    _safe_write(
        "hft_runtime_state.json",
        {
            "hft_enabled": hft_config.HFT_ENABLED,
            "mode": hft_config.MODE,
            "connected_to_runtime": False,
            "worker_started": False,
            "open_trades": len(state.active_trades),
        },
    )
    _safe_write(
        "hft_stats.json",
        {
            "simulated_orders": len(state.used_signal_ids),
            "live_orders": 0,
            "open_trades": len(state.active_trades),
            "rejections": 1 if rejection_reason else 0,
        },
    )
    _safe_write(
        "hft_health.json",
        {
            "status": "SIMULATION_ONLY",
            "mode": hft_config.MODE,
            "broker_allowed": hft_config.BROKER_ALLOWED,
            "telegram_allowed": hft_config.TELEGRAM_ALLOWED,
            "runtime_connection_allowed": hft_config.ACTIVE_RUNTIME_CONNECTION_ALLOWED,
        },
    )
    if rejection_reason:
        _safe_write("hft_rejected_count.json", {"rejected_count": 1, "reasons": {rejection_reason: 1}})


def assert_external_access_impossible() -> None:
    assert_broker_allowed()
    assert_telegram_allowed()


def open_simulated_hft_trade(
    candidate: HFTCandidate,
    state: HFTRiskState,
    *,
    internal_simulation_test_mode: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    opened_at = now or datetime.now(timezone.utc)
    decision = evaluate_hft_risk(
        candidate,
        state,
        internal_simulation_test_mode=internal_simulation_test_mode,
        now=opened_at,
    )
    if not decision.accepted:
        _persist_state(state, rejection_reason=decision.reason_if_rejected)
        return {"accepted": False, "reason_if_rejected": decision.reason_if_rejected}

    trade = {
        "trade_id": f"HFTSIM-{candidate.signal_id}",
        "signal_id": candidate.signal_id,
        "symbol": candidate.symbol,
        "strategy_name": candidate.strategy_name,
        "entry_price": decision.entry_price,
        "quantity": decision.quantity,
        "capital_used": decision.capital_used,
        "take_profit_price": decision.take_profit_price,
        "stop_loss_price": decision.stop_loss_price,
        "opened_at": _iso(opened_at),
        "status": "OPEN",
        "mode": hft_config.MODE,
        "paper_only": True,
    }
    state.active_trades.append(trade)
    state.used_signal_ids.add(candidate.signal_id)
    state.available_capital = round(state.available_capital - decision.capital_used, 2)
    _persist_state(state)
    return {"accepted": True, "trade": trade}
