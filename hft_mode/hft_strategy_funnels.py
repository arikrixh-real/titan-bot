"""Always-active strategy funnels for HFT simulation candidates."""

from __future__ import annotations

from dataclasses import replace

from hft_mode.hft_data_contracts import HFTCandidate, HFTFeedSnapshot

STRATEGY_MOMENTUM_CONTINUATION = "momentum_continuation"
STRATEGY_PULLBACK_CONTINUATION = "pullback_continuation"
STRATEGY_VOLATILITY_EXPANSION = "volatility_expansion"
STRATEGY_RELATIVE_STRENGTH_BURST = "relative_strength_burst"
STRATEGY_INTRADAY_RANGE_ESCAPE = "intraday_range_escape"

ALL_STRATEGIES = (
    STRATEGY_MOMENTUM_CONTINUATION,
    STRATEGY_PULLBACK_CONTINUATION,
    STRATEGY_VOLATILITY_EXPANSION,
    STRATEGY_RELATIVE_STRENGTH_BURST,
    STRATEGY_INTRADAY_RANGE_ESCAPE,
)


def _base_candidate(snapshot: HFTFeedSnapshot) -> HFTCandidate | None:
    if not snapshot.accepted or not snapshot.candidates:
        return None
    return snapshot.candidates[0]


def _metric(context: dict[str, float], key: str, default: float = 0.0) -> float:
    return float(context.get(key, default))


def momentum_continuation(snapshot: HFTFeedSnapshot, context: dict[str, float]) -> HFTCandidate | None:
    base = _base_candidate(snapshot)
    if base is None:
        return None
    short_rise = _metric(context, "short_term_price_rise")
    acceleration = _metric(context, "acceleration")
    continuation = _metric(context, "continuation_pressure")
    volume = _metric(context, "volume_strength")
    if min(short_rise, acceleration, continuation, volume) < 0.6:
        return None
    return replace(
        base,
        strategy_name=STRATEGY_MOMENTUM_CONTINUATION,
        momentum_strength=(short_rise + acceleration + continuation) / 3,
        volume_strength=volume,
        volatility_quality=_metric(context, "volatility_quality", 0.65),
        spread_quality=_metric(context, "spread_quality", 0.8),
        speed_of_move=_metric(context, "speed_of_move", 0.65),
        strategy_confidence=0.84,
        setup_cleanliness=_metric(context, "setup_cleanliness", 0.78),
        executable=False,
    )


def pullback_continuation(snapshot: HFTFeedSnapshot, context: dict[str, float]) -> HFTCandidate | None:
    base = _base_candidate(snapshot)
    if base is None:
        return None
    prior_move = _metric(context, "prior_strong_move")
    pullback_control = _metric(context, "controlled_pullback")
    resumption = _metric(context, "resumption_confirmation")
    volume = _metric(context, "volume_strength")
    if min(prior_move, pullback_control, resumption, volume) < 0.6:
        return None
    return replace(
        base,
        strategy_name=STRATEGY_PULLBACK_CONTINUATION,
        momentum_strength=(prior_move + resumption) / 2,
        volume_strength=volume,
        volatility_quality=_metric(context, "volatility_quality", 0.62),
        spread_quality=_metric(context, "spread_quality", 0.82),
        speed_of_move=_metric(context, "speed_of_move", 0.58),
        strategy_confidence=(pullback_control + resumption) / 2,
        setup_cleanliness=_metric(context, "setup_cleanliness", 0.82),
        executable=False,
    )


def volatility_expansion(snapshot: HFTFeedSnapshot, context: dict[str, float]) -> HFTCandidate | None:
    base = _base_candidate(snapshot)
    if base is None:
        return None
    compression = _metric(context, "compression")
    range_expansion = _metric(context, "range_expansion")
    momentum = _metric(context, "momentum_confirmation")
    volume = _metric(context, "volume_strength")
    if min(compression, range_expansion, momentum, volume) < 0.6:
        return None
    return replace(
        base,
        strategy_name=STRATEGY_VOLATILITY_EXPANSION,
        momentum_strength=momentum,
        volume_strength=volume,
        volatility_quality=(compression + range_expansion) / 2,
        spread_quality=_metric(context, "spread_quality", 0.78),
        speed_of_move=_metric(context, "speed_of_move", 0.72),
        strategy_confidence=0.82,
        setup_cleanliness=_metric(context, "setup_cleanliness", 0.74),
        executable=False,
    )


def relative_strength_burst(snapshot: HFTFeedSnapshot, context: dict[str, float]) -> HFTCandidate | None:
    base = _base_candidate(snapshot)
    if base is None:
        return None
    outperformance = _metric(context, "peer_outperformance")
    strength_burst = _metric(context, "strength_burst")
    volume = _metric(context, "volume_strength")
    if min(outperformance, strength_burst, volume) < 0.6:
        return None
    return replace(
        base,
        strategy_name=STRATEGY_RELATIVE_STRENGTH_BURST,
        momentum_strength=strength_burst,
        volume_strength=volume,
        volatility_quality=_metric(context, "volatility_quality", 0.68),
        spread_quality=_metric(context, "spread_quality", 0.82),
        speed_of_move=_metric(context, "speed_of_move", 0.7),
        strategy_confidence=(outperformance + strength_burst) / 2,
        setup_cleanliness=_metric(context, "setup_cleanliness", 0.76),
        executable=False,
    )


def intraday_range_escape(snapshot: HFTFeedSnapshot, context: dict[str, float]) -> HFTCandidate | None:
    base = _base_candidate(snapshot)
    if base is None:
        return None
    tight_range = _metric(context, "tight_intraday_range")
    range_break = _metric(context, "range_break")
    momentum = _metric(context, "momentum_confirmation")
    volume = _metric(context, "volume_strength")
    if min(tight_range, range_break, momentum, volume) < 0.6:
        return None
    return replace(
        base,
        strategy_name=STRATEGY_INTRADAY_RANGE_ESCAPE,
        momentum_strength=momentum,
        volume_strength=volume,
        volatility_quality=(tight_range + range_break) / 2,
        spread_quality=_metric(context, "spread_quality", 0.8),
        speed_of_move=_metric(context, "speed_of_move", 0.69),
        strategy_confidence=(range_break + momentum) / 2,
        setup_cleanliness=_metric(context, "setup_cleanliness", 0.78),
        executable=False,
    )


FUNNELS = (
    momentum_continuation,
    pullback_continuation,
    volatility_expansion,
    relative_strength_burst,
    intraday_range_escape,
)


def run_all_funnels(snapshot: HFTFeedSnapshot, context: dict[str, float]) -> list[HFTCandidate]:
    return [candidate for funnel in FUNNELS if (candidate := funnel(snapshot, context)) is not None]
