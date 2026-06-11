"""Score HFT simulation candidates without creating an execution path."""

from __future__ import annotations

from dataclasses import replace

from hft_mode.hft_data_contracts import HFTCandidate
from hft_mode.hft_filters import apply_filter_chain

DEFAULT_EXECUTION_THRESHOLD = 75.0

_WEIGHTS = {
    "momentum_strength": 0.18,
    "volume_strength": 0.15,
    "volatility_quality": 0.14,
    "spread_quality": 0.12,
    "speed_of_move": 0.12,
    "strategy_confidence": 0.17,
    "setup_cleanliness": 0.12,
}


def _bounded(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def score_candidate(candidate: HFTCandidate) -> float:
    score = 0.0
    for field_name, weight in _WEIGHTS.items():
        score += _bounded(getattr(candidate, field_name)) * weight
    return round(score * 100, 2)


def mark_score(candidate: HFTCandidate, threshold: float = DEFAULT_EXECUTION_THRESHOLD) -> HFTCandidate:
    filter_result = apply_filter_chain(candidate)
    score = score_candidate(candidate) if filter_result.accepted else 0.0
    eligible = filter_result.accepted and score >= threshold
    return replace(
        candidate,
        score=score,
        eligible=eligible,
        executable=False,
        reason_if_rejected=None if eligible else filter_result.reason_if_rejected or "score_below_threshold",
    )
