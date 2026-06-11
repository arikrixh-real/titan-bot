"""Risk gates for paper-only HFT simulation execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from hft_mode import hft_config
from hft_mode.hft_candidate import MAX_SPREAD_PCT
from hft_mode.hft_data_contracts import HFTCandidate
from hft_mode.hft_score_engine import DEFAULT_EXECUTION_THRESHOLD

MAX_OPEN_TRADES = 1
TAKE_PROFIT_CAPITAL_PCT = 0.005
STOP_LOSS_CAPITAL_PCT = 0.0025
MAX_DAILY_LOSS_PCT = 0.03
MAX_DRAWDOWN_PCT = 0.10
MAX_CONSECUTIVE_LOSSES = 5
DEFAULT_AVAILABLE_CAPITAL = 10000.0
DEFAULT_COOLDOWN_SECONDS = 60


@dataclass
class HFTRiskState:
    available_capital: float = DEFAULT_AVAILABLE_CAPITAL
    starting_capital: float = DEFAULT_AVAILABLE_CAPITAL
    equity: float = DEFAULT_AVAILABLE_CAPITAL
    peak_equity: float = DEFAULT_AVAILABLE_CAPITAL
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    active_trades: list[dict[str, Any]] = field(default_factory=list)
    used_signal_ids: set[str] = field(default_factory=set)
    cooldown_until: dict[str, datetime] = field(default_factory=dict)


@dataclass(frozen=True)
class HFTRiskDecision:
    accepted: bool
    reason_if_rejected: str | None = None
    quantity: int = 0
    entry_price: float = 0.0
    take_profit_price: float = 0.0
    stop_loss_price: float = 0.0
    capital_used: float = 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_key(candidate: HFTCandidate) -> str:
    return f"{candidate.symbol}:{candidate.strategy_name}"


def _daily_loss_limit_hit(state: HFTRiskState) -> bool:
    return state.daily_pnl <= -(state.starting_capital * MAX_DAILY_LOSS_PCT)


def _drawdown_limit_hit(state: HFTRiskState) -> bool:
    if state.peak_equity <= 0:
        return True
    return (state.peak_equity - state.equity) / state.peak_equity >= MAX_DRAWDOWN_PCT


def evaluate_hft_risk(
    candidate: HFTCandidate,
    state: HFTRiskState,
    *,
    internal_simulation_test_mode: bool = False,
    now: datetime | None = None,
) -> HFTRiskDecision:
    if hft_config.MODE != "SIMULATION_ONLY":
        return HFTRiskDecision(False, "mode_not_simulation_only")
    if hft_config.HFT_ENABLED is False and not internal_simulation_test_mode:
        return HFTRiskDecision(False, "hft_disabled")
    if not candidate.signal_id:
        return HFTRiskDecision(False, "missing_signal_id")
    if candidate.signal_id in state.used_signal_ids:
        return HFTRiskDecision(False, "duplicate_signal_id")
    if candidate.score < DEFAULT_EXECUTION_THRESHOLD:
        return HFTRiskDecision(False, "score_below_threshold")
    if not candidate.eligible or candidate.executable:
        return HFTRiskDecision(False, "candidate_not_eligible")
    if not candidate.is_fresh:
        return HFTRiskDecision(False, "stale_feed")
    if candidate.spread_pct > MAX_SPREAD_PCT:
        return HFTRiskDecision(False, "spread_unsafe")
    if len(state.active_trades) >= MAX_OPEN_TRADES:
        return HFTRiskDecision(False, "open_trade_exists")
    if any(trade.get("symbol") == candidate.symbol and trade.get("strategy_name") == candidate.strategy_name for trade in state.active_trades):
        return HFTRiskDecision(False, "duplicate_active_symbol_strategy")
    cooldown_key = _active_key(candidate)
    if state.cooldown_until.get(cooldown_key) and (now or _now()) < state.cooldown_until[cooldown_key]:
        return HFTRiskDecision(False, "cooldown_active")
    if _daily_loss_limit_hit(state):
        return HFTRiskDecision(False, "daily_loss_limit_hit")
    if _drawdown_limit_hit(state):
        return HFTRiskDecision(False, "drawdown_limit_hit")
    if state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return HFTRiskDecision(False, "consecutive_loss_limit_hit")

    quantity = int(state.available_capital // candidate.price)
    if quantity <= 0:
        return HFTRiskDecision(False, "insufficient_capital")

    capital_used = round(quantity * candidate.price, 2)
    take_profit_price = round(candidate.price + ((state.available_capital * TAKE_PROFIT_CAPITAL_PCT) / quantity), 4)
    stop_loss_price = round(candidate.price - ((state.available_capital * STOP_LOSS_CAPITAL_PCT) / quantity), 4)
    return HFTRiskDecision(
        accepted=True,
        quantity=quantity,
        entry_price=candidate.price,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
        capital_used=capital_used,
    )


def mark_cooldown(state: HFTRiskState, symbol: str, strategy_name: str | None, now: datetime | None = None) -> None:
    state.cooldown_until[f"{symbol}:{strategy_name}"] = (now or _now()) + timedelta(seconds=DEFAULT_COOLDOWN_SECONDS)
