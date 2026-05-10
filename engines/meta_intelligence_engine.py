"""
TITAN Phase 5 - Meta Intelligence Runtime Layer
-----------------------------------------------

Fuses existing TITAN intelligence layers into one explainable ranking score.

Safety:
- Metadata/ranking only.
- Does not send Telegram alerts.
- Does not create trades or broker orders.
- Does not bypass market-hours, duplicate, or alert-cap guards.
- Does not hard-block setups.
- Fails open by returning the original setup unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FAMILY_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "strategy_family_memory.json"

MAX_META_RANK_ADJUSTMENT = 0.30
MAX_POSITIVE_ADJUSTMENT = 0.20
MIN_GLOBAL_TRADES_FOR_MEMORY = 10
MIN_FAMILY_TRADES_FOR_MEMORY = 5


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _scale_setup_score(score: float) -> float:
    if score <= 5.0:
        return _clamp(score / 5.0 * 100.0)
    return _clamp(score)


def _raw_setup(setup: Dict[str, Any]) -> Dict[str, Any]:
    raw = setup.get("raw")
    return raw if isinstance(raw, dict) else setup


def classify_strategy_family(setup: Dict[str, Any]) -> str:
    """
    Stable, broad setup-family classifier.
    Avoids overfitting to exact reason text.
    """

    raw = _raw_setup(setup)
    reason = str(raw.get("reason") or setup.get("reason") or "").lower()
    cluster = str(raw.get("cluster_id") or setup.get("cluster_id") or "").lower()
    text = f"{reason} {cluster}"

    phase4 = raw.get("phase4_data_advantage") or setup.get("phase4_data_advantage") or {}
    regime = raw.get("advanced_regime") or setup.get("advanced_regime") or {}
    micro = raw.get("microstructure") or setup.get("microstructure") or {}

    if "news" in text or _safe_float(regime.get("news_driven_score"), 0.0) >= 60.0:
        return "NEWS_DRIVEN"
    if micro.get("liquidity_sweep") or "liquidity_sweep" in text:
        return "LIQUIDITY_SWEEP"
    if "compression" in text or "squeeze" in text:
        return "COMPRESSION_BREAKOUT"
    if "breakout" in text:
        return "BREAKOUT"
    if "trend" in text or str(regime.get("regime_type", "")).upper() == "TRENDING":
        return "TREND_CONTINUATION"
    if "mean" in text or str(regime.get("regime_type", "")).upper() == "MEAN_REVERTING":
        return "MEAN_REVERSION"
    if "volume" in text or _safe_float((phase4.get("institutional_flow_proxy") or {}).get("volume_surge_ratio"), 1.0) >= 1.8:
        return "VOLUME_EXPANSION"
    return "GENERAL"


def _load_family_memory() -> Dict[str, Any]:
    try:
        if not FAMILY_MEMORY_PATH.exists():
            return {}
        with FAMILY_MEMORY_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _layer_scores(setup: Dict[str, Any], family: str, memory: Dict[str, Any]) -> Dict[str, float]:
    raw = _raw_setup(setup)

    setup_score = _scale_setup_score(_safe_float(raw.get("score", setup.get("score")), 0.0))

    micro = raw.get("microstructure") or setup.get("microstructure") or {}
    regime = raw.get("advanced_regime") or setup.get("advanced_regime") or {}
    risk = raw.get("professional_risk") or setup.get("professional_risk") or {}
    phase1 = _clamp(
        (_safe_float(micro.get("liquidity_quality_score"), 50.0) * 0.35)
        + (_safe_float(risk.get("risk_quality_score"), 50.0) * 0.45)
        + (_safe_float(regime.get("regime_confidence"), 50.0) * 0.20)
        - (_safe_float(regime.get("panic_score"), 0.0) * 0.08)
        - (_safe_float(regime.get("liquidity_crisis_score"), 0.0) * 0.08)
    )

    portfolio = raw.get("portfolio_construction") or setup.get("portfolio_construction") or {}
    execution = raw.get("execution_quality") or setup.get("execution_quality") or {}
    phase2 = _clamp(
        (_safe_float(portfolio.get("portfolio_quality_score"), 50.0) * 0.45)
        + (_safe_float(execution.get("execution_quality_score"), 50.0) * 0.45)
        + ((100.0 - _safe_float(execution.get("slippage_risk_estimate"), 50.0)) * 0.10)
    )

    phase3 = _clamp(
        (_safe_float(raw.get("adaptive_confidence_score", setup.get("adaptive_confidence_score")), 50.0) * 0.60)
        + (_safe_float(raw.get("cluster_quality_score", setup.get("cluster_quality_score")), 50.0) * 0.40)
    )

    phase4 = _clamp(_safe_float(raw.get("data_advantage_score", setup.get("data_advantage_score")), 50.0))

    family_score = 50.0
    total_trades = _safe_int(memory.get("total_closed_trades"), 0)
    bucket = (memory.get("families") or {}).get(family, {}) if isinstance(memory.get("families"), dict) else {}
    family_trades = _safe_int(bucket.get("trades"), 0)
    if total_trades >= MIN_GLOBAL_TRADES_FOR_MEMORY and family_trades >= MIN_FAMILY_TRADES_FOR_MEMORY:
        family_score = _safe_float(bucket.get("family_quality_score"), 50.0)

    return {
        "setup_score": round(setup_score, 2),
        "phase1_score": round(phase1, 2),
        "phase2_score": round(phase2, 2),
        "phase3_score": round(phase3, 2),
        "phase4_score": round(phase4, 2),
        "family_score": round(_clamp(family_score), 2),
    }


def _meta_score(scores: Dict[str, float]) -> float:
    return _clamp(
        (scores["setup_score"] * 0.25)
        + (scores["phase1_score"] * 0.20)
        + (scores["phase2_score"] * 0.15)
        + (scores["phase3_score"] * 0.15)
        + (scores["phase4_score"] * 0.15)
        + (scores["family_score"] * 0.10)
    )


def _family_strength(family: str, memory: Dict[str, Any]) -> Dict[str, Any]:
    bucket = {}
    if isinstance(memory.get("families"), dict):
        bucket = memory["families"].get(family, {}) or {}

    trades = _safe_int(bucket.get("trades"), 0)
    total = _safe_int(memory.get("total_closed_trades"), 0)
    active = total >= MIN_GLOBAL_TRADES_FOR_MEMORY and trades >= MIN_FAMILY_TRADES_FOR_MEMORY

    return {
        "family": family,
        "memory_active": active,
        "trades": trades,
        "wins": _safe_int(bucket.get("wins"), 0),
        "losses": _safe_int(bucket.get("losses"), 0),
        "posterior_win_rate": _safe_float(bucket.get("posterior_win_rate"), 0.5),
        "sample_confidence": _safe_float(bucket.get("sample_confidence"), 0.0),
        "family_quality_score": _safe_float(bucket.get("family_quality_score"), 50.0),
        "note": "family_memory_active" if active else "family_memory_neutral_until_sample_size",
    }


def _explanations(scores: Dict[str, float], family_strength: Dict[str, Any]) -> tuple[List[str], List[str], str]:
    positives: List[str] = []
    negatives: List[str] = []

    labels = {
        "setup_score": "base setup quality",
        "phase1_score": "risk/regime/microstructure",
        "phase2_score": "portfolio/execution quality",
        "phase3_score": "adaptive confidence",
        "phase4_score": "data advantage context",
        "family_score": "strategy family memory",
    }

    for key, label in labels.items():
        value = _safe_float(scores.get(key), 50.0)
        if value >= 60.0:
            positives.append(f"{label} supportive")
        elif value <= 42.0:
            negatives.append(f"{label} weak")

    if not family_strength.get("memory_active"):
        positives.append("strategy family memory kept neutral due to sample rules")

    explanation = "; ".join((positives[:3] + negatives[:3])[:5])
    if not explanation:
        explanation = "meta score near neutral; no single layer dominates ranking"

    return positives, negatives, explanation


def apply_meta_intelligence(setup: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attach Phase 5 metadata and bounded ranking adjustment.
    Never rejects or blocks a setup.
    """

    if not isinstance(setup, dict):
        return setup

    original = setup

    try:
        result = dict(setup)
        family = classify_strategy_family(result)
        memory = _load_family_memory()
        scores = _layer_scores(result, family, memory)
        meta_quality_score = round(_meta_score(scores), 2)
        family_strength = _family_strength(family, memory)

        base_rank = _safe_float(
            result.get("rank_score", result.get("score", result.get("final_score"))),
            0.0,
        )
        raw_adjustment = ((meta_quality_score - 50.0) / 50.0) * MAX_POSITIVE_ADJUSTMENT
        adjustment = max(-MAX_META_RANK_ADJUSTMENT, min(MAX_POSITIVE_ADJUSTMENT, raw_adjustment))

        positives, negatives, explanation = _explanations(scores, family_strength)

        result["strategy_family"] = family
        result["strategy_family_strength"] = family_strength
        result["meta_layer_scores"] = scores
        result["meta_quality_score"] = meta_quality_score
        result["meta_rank_adjustment"] = round(adjustment, 4)
        result["meta_adjustment_bounded"] = True
        result["meta_positive_factors"] = positives
        result["meta_negative_factors"] = negatives
        result["meta_explanation"] = explanation
        result["phase5_applied"] = True
        result["phase5_blocked"] = False
        result["rank_score"] = round(max(0.0, base_rank + adjustment), 4)

        if isinstance(result.get("scores"), dict):
            result["scores"] = dict(result["scores"])
            result["scores"]["meta_quality_score"] = meta_quality_score
            result["scores"]["meta_rank_adjustment"] = result["meta_rank_adjustment"]

        if isinstance(result.get("setup_context"), dict):
            result["setup_context"] = dict(result["setup_context"])
            result["setup_context"]["strategy_family"] = family
            result["setup_context"]["meta_quality_score"] = meta_quality_score

        return result

    except Exception as exc:
        try:
            failed = dict(original)
            failed["phase5_applied"] = False
            failed["phase5_blocked"] = False
            failed["phase5_error"] = str(exc)
            return failed
        except Exception:
            return original
