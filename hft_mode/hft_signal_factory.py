"""Signal factory for sealed HFT simulation strategy decisions."""

from __future__ import annotations

from dataclasses import dataclass

from hft_mode.hft_data_contracts import HFTCandidate, HFTFeedSnapshot
from hft_mode.hft_filters import apply_filter_chain
from hft_mode.hft_score_engine import DEFAULT_EXECUTION_THRESHOLD, mark_score
from hft_mode.hft_safety_gate import assert_hft_simulation_only
from hft_mode.hft_strategy_funnels import run_all_funnels


@dataclass(frozen=True)
class HFTSignalDecision:
    candidate: HFTCandidate
    accepted: bool
    eligible: bool
    reason_if_rejected: str | None


def create_hft_signals(
    snapshots: list[HFTFeedSnapshot],
    strategy_context: dict[str, dict[str, float]],
    threshold: float = DEFAULT_EXECUTION_THRESHOLD,
) -> list[HFTSignalDecision]:
    assert_hft_simulation_only()

    decisions: list[HFTSignalDecision] = []
    for snapshot in snapshots:
        context = strategy_context.get(snapshot.symbol, {})
        raw_candidates = run_all_funnels(snapshot, context)
        for candidate in raw_candidates:
            filter_result = apply_filter_chain(candidate)
            scored = mark_score(candidate, threshold=threshold)
            decisions.append(
                HFTSignalDecision(
                    candidate=scored,
                    accepted=filter_result.accepted,
                    eligible=scored.eligible,
                    reason_if_rejected=scored.reason_if_rejected,
                )
            )
    return decisions
