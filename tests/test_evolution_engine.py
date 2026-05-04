"""
Simple TITAN Evolution Engine test runner.

Run from project root:
python tests/test_evolution_engine.py

This only tests the evolution engine.
It does NOT send Telegram alerts.
It does NOT change the 3 alerts/day cap.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines.evolution_engine import (
    run_evolution_engine,
    get_evolution_state,
    apply_evolution_score,
    get_evolution_filter_threshold,
)


def main():
    state = run_evolution_engine()

    print("✅ Evolution Engine Test Complete")
    print("-" * 50)
    print("Closed Trades:", state.get("total_closed_trades"))
    print("Wins:", state.get("total_wins"))
    print("Losses:", state.get("total_losses"))
    print("Win Rate:", round(float(state.get("win_rate", 0)) * 100, 2), "%")
    print("Score Boost:", state.get("score_boost"))
    print("Filter Strictness:", state.get("filter_strictness"))
    print("Ranking Confidence:", state.get("ranking_confidence"))
    print("-" * 50)

    sample_score = apply_evolution_score(
        symbol="RELIANCE",
        base_score=75,
        setup_data={
            "side": "LONG",
            "reason": "breakout with volume and momentum",
        },
    )

    adaptive_threshold = get_evolution_filter_threshold(70)

    print("Sample evolved score:", sample_score)
    print("Adaptive filter threshold:", adaptive_threshold)

    saved_state = get_evolution_state()
    print("State last updated:", saved_state.get("last_updated"))


if __name__ == "__main__":
    main()