from pathlib import Path


FORMULA_VERSION = "TOIF-v4"
SHADOW_ONLY = True

LANES = ("ELITE", "STRONG", "MICRO", "NO_TRADE")

ALPHA_RUNTIME_DIR = Path("data") / "runtime" / "alpha_math"

REPO_ROOT = Path(__file__).resolve().parents[1]

LANE_WEIGHTS = {
    "ELITE": {"A": 1.30, "E": 1.20, "F": 1.10, "R": 1.10, "B": 1.00, "Q": 0.85, "M": 0.75},
    "STRONG": {"A": 1.15, "E": 1.10, "F": 1.00, "R": 1.00, "B": 0.85, "Q": 0.75, "M": 0.65},
    "MICRO": {"A": 0.95, "E": 1.10, "F": 1.25, "R": 0.70, "B": 0.60, "Q": 0.65, "M": 0.35},
}

LANE_THRESHOLDS = {
    "ELITE": {
        "probability": 0.74,
        "trade_power": 0.70,
        "agreement": 0.75,
        "trap_risk_max": 0.25,
        "liquidity": 0.70,
        "regime": 0.65,
    },
    "STRONG": {
        "probability": 0.66,
        "trade_power": 0.58,
        "agreement": 0.65,
        "trap_risk_max": 0.35,
        "liquidity": 0.60,
        "regime": 0.55,
    },
    "MICRO": {
        "probability": 0.56,
        "trade_power": 0.48,
        "agreement": 0.60,
        "trap_risk_max": 0.30,
        "liquidity": 0.80,
    },
}

OUTPUT_FILES = {
    "latest_scores": "latest_scores.json",
    "lane_candidates": "lane_candidates.json",
    "alpha_health": "alpha_health.json",
    "shadow_comparison": "shadow_comparison.json",
    "shadow_journal": "alpha_shadow_journal.csv",
}

ALLOWED_OUTPUT_FILES = frozenset(OUTPUT_FILES.values())
