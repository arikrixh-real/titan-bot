"""Filter chain for HFT simulation candidates."""

from __future__ import annotations

from dataclasses import dataclass

from hft_mode.hft_candidate import MAX_PRICE, MAX_SPREAD_PCT, MIN_PRICE
from hft_mode.hft_data_contracts import HFTCandidate

MIN_VOLUME = 250000
MIN_MOMENTUM_STRENGTH = 0.45
MIN_VOLATILITY_QUALITY = 0.35
MAX_SPEED_OF_MOVE = 0.95
MIN_SETUP_CLEANLINESS = 0.35


@dataclass(frozen=True)
class HFTFilterResult:
    accepted: bool
    reason_if_rejected: str | None = None


def reject_reason_for_candidate(candidate: HFTCandidate | None) -> str | None:
    if candidate is None:
        return "malformed_candidate"
    if not isinstance(candidate.symbol, str) or not candidate.symbol.strip():
        return "malformed_candidate"
    if candidate.price is None or candidate.price < MIN_PRICE or candidate.price > MAX_PRICE:
        return "bad_price_range"
    if not candidate.is_fresh:
        return "stale_feed"
    if candidate.volume is None or candidate.volume < MIN_VOLUME:
        return "weak_volume"
    if candidate.spread_pct is None or candidate.spread_pct > MAX_SPREAD_PCT:
        return "wide_spread"
    if candidate.momentum_strength < MIN_MOMENTUM_STRENGTH:
        return "weak_momentum"
    if candidate.volatility_quality < MIN_VOLATILITY_QUALITY:
        return "poor_volatility"
    if candidate.speed_of_move > MAX_SPEED_OF_MOVE:
        return "late_entry"
    if candidate.setup_cleanliness < MIN_SETUP_CLEANLINESS:
        return "choppy_movement"
    return None


def apply_filter_chain(candidate: HFTCandidate | None) -> HFTFilterResult:
    reason = reject_reason_for_candidate(candidate)
    return HFTFilterResult(accepted=reason is None, reason_if_rejected=reason)
