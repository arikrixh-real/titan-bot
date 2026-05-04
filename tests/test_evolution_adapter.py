"""
Test Evolution Adapter.

Run from project root:
python tests/test_evolution_adapter.py
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engines.evolution_adapter import evolve_setup, rank_evolved_setups


def main():
    sample_setups = [
        {
            "symbol": "RELIANCE",
            "side": "LONG",
            "score": 72,
            "reason": "breakout with volume and momentum",
        },
        {
            "symbol": "TCS",
            "side": "LONG",
            "score": 80,
            "reason": "trend and relative strength",
        },
        {
            "symbol": "HDFCBANK",
            "side": "SHORT",
            "score": 68,
            "reason": "fake breakout trap avoidance",
        },
    ]

    ranked = rank_evolved_setups(sample_setups)

    print("✅ Evolution Adapter Test Complete")
    print("-" * 50)

    for s in ranked:
        print(
            s.get("symbol"),
            "| base:",
            s.get("base_score"),
            "| evolved:",
            s.get("evolved_score"),
            "| applied:",
            s.get("evolution_applied"),
        )

    print("-" * 50)
    single = evolve_setup(sample_setups[0])
    print("Single setup evolved:", single)


if __name__ == "__main__":
    main()