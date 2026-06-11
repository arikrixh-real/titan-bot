"""Read-only HFT feed snapshot builder for real cached/depth ticks."""

from __future__ import annotations

from datetime import datetime, timezone

from hft_mode.hft_candidate import build_candidate, calculate_spread_pct, reject_reason_for_tick
from hft_mode.hft_data_contracts import HFTCandidate, HFTFeedSnapshot, HFTPriceTick
from hft_mode.hft_safety_gate import assert_hft_simulation_only

MAX_TICK_AGE_SECONDS = 5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def is_tick_fresh(timestamp: datetime, now: datetime | None = None, max_age_seconds: int = MAX_TICK_AGE_SECONDS) -> bool:
    now_utc = _normalize_timestamp(now or _utc_now())
    tick_utc = _normalize_timestamp(timestamp)
    age_seconds = (now_utc - tick_utc).total_seconds()
    return 0 <= age_seconds <= max_age_seconds


def process_real_hft_tick(
    tick: HFTPriceTick,
    now: datetime | None = None,
    max_age_seconds: int = MAX_TICK_AGE_SECONDS,
) -> HFTFeedSnapshot:
    assert_hft_simulation_only()

    is_fresh = is_tick_fresh(tick.timestamp, now=now, max_age_seconds=max_age_seconds)
    spread_pct = None
    reason = None

    if not is_fresh:
        reason = "stale_feed"
    elif tick.bid is not None and tick.ask is not None and tick.bid > 0 and tick.ask > 0 and tick.bid <= tick.ask:
        spread_pct = calculate_spread_pct(float(tick.bid), float(tick.ask))
        reason = reject_reason_for_tick(tick, spread_pct=spread_pct)
    else:
        reason = reject_reason_for_tick(tick, spread_pct=spread_pct)

    candidate: HFTCandidate | None = None
    if reason is None and spread_pct is not None:
        candidate = build_candidate(tick, spread_pct=spread_pct)

    return HFTFeedSnapshot(
        symbol=tick.symbol,
        price=tick.price,
        timestamp=tick.timestamp,
        volume=tick.volume,
        bid=tick.bid,
        ask=tick.ask,
        spread_pct=spread_pct,
        source=tick.source,
        is_fresh=is_fresh,
        reason_if_rejected=reason,
        accepted=reason is None,
        candidates=(candidate,) if candidate else (),
    )


def process_real_hft_ticks(
    ticks: list[HFTPriceTick],
    now: datetime | None = None,
    max_age_seconds: int = MAX_TICK_AGE_SECONDS,
) -> list[HFTFeedSnapshot]:
    return [process_real_hft_tick(tick, now=now, max_age_seconds=max_age_seconds) for tick in ticks]
