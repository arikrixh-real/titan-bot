"""Candidate validation rules for HFT simulation inputs."""

from __future__ import annotations

from hft_mode.hft_data_contracts import HFTCandidate, HFTPriceTick

MIN_PRICE = 15.0
MAX_PRICE = 25.0
PREFERRED_MIN_PRICE = 20.0
PREFERRED_MAX_PRICE = 25.0
MAX_SPREAD_PCT = 0.75


def calculate_spread_pct(bid: float, ask: float) -> float:
    midpoint = (bid + ask) / 2
    if midpoint <= 0:
        raise ValueError("invalid_bid_ask")
    return round(((ask - bid) / midpoint) * 100, 6)


def reject_reason_for_tick(tick: HFTPriceTick, spread_pct: float | None = None) -> str | None:
    if tick.price is None or tick.price <= 0:
        return "missing_price"
    if tick.price < MIN_PRICE or tick.price > MAX_PRICE:
        return "price_outside_15_25"
    if tick.bid is None or tick.ask is None or tick.bid <= 0 or tick.ask <= 0 or tick.bid > tick.ask:
        return "invalid_bid_ask"
    if tick.volume is None or tick.volume <= 0:
        return "missing_volume"

    effective_spread = spread_pct if spread_pct is not None else tick.spread_pct
    if effective_spread is None:
        return "missing_spread"
    if effective_spread > MAX_SPREAD_PCT:
        return "bad_spread"
    return None


def build_candidate(tick: HFTPriceTick, spread_pct: float) -> HFTCandidate:
    reason = reject_reason_for_tick(tick, spread_pct=spread_pct)
    if reason:
        raise ValueError(reason)
    return HFTCandidate(
        symbol=tick.symbol,
        price=float(tick.price),
        timestamp=tick.timestamp,
        volume=int(tick.volume),
        bid=float(tick.bid),
        ask=float(tick.ask),
        spread_pct=spread_pct,
        source=tick.source,
        is_fresh=True,
        reason_if_rejected=None,
    )


def is_preferred_price(price: float) -> bool:
    return PREFERRED_MIN_PRICE <= price <= PREFERRED_MAX_PRICE
