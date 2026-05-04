"""
TITAN Evolution Adapter
=======================

Purpose:
- Safely connects Evolution Engine output to setup scoring/ranking.
- Does NOT send Telegram alerts.
- Does NOT change 3 alerts/day cap.
- Does NOT modify journal/outcome/learning files.
- Safe to import inside setup_engine.py later.

Use:
    from engines.evolution_adapter import evolve_setup, rank_evolved_setups

    setup = evolve_setup(setup)
    setups = rank_evolved_setups(setups)

Expected setup keys can be flexible:
- symbol / stock / ticker
- score / final_score / signal_score / setup_score
- side / direction / trade_side
- reason / setup_reason

This adapter preserves original score and adds:
- base_score
- evolved_score
- evolution_applied
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if text == "":
            return default
        return float(text)
    except Exception:
        return default


def _get_symbol(setup: Dict[str, Any]) -> str:
    for key in ["symbol", "stock", "ticker", "Stock", "SYMBOL"]:
        if setup.get(key):
            return str(setup.get(key)).strip().upper()
    return "UNKNOWN"


def _get_score_key(setup: Dict[str, Any]) -> Optional[str]:
    for key in ["score", "final_score", "signal_score", "setup_score", "Score", "SCORE"]:
        if key in setup:
            return key
    return None


def _get_score(setup: Dict[str, Any]) -> float:
    key = _get_score_key(setup)
    if key is None:
        return 0.0
    return _safe_float(setup.get(key), 0.0)


def evolve_setup(setup: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evolves one setup score safely.

    If evolution_engine is missing or fails, original setup is returned.
    """

    if not isinstance(setup, dict):
        return setup

    result = dict(setup)

    base_score = _get_score(result)
    symbol = _get_symbol(result)

    result["base_score"] = round(base_score, 2)

    try:
        from engines.evolution_engine import apply_evolution_score

        evolved_score = apply_evolution_score(
            symbol=symbol,
            base_score=base_score,
            setup_data=result,
        )

        result["evolved_score"] = round(float(evolved_score), 2)
        result["evolution_applied"] = True

        score_key = _get_score_key(result)
        if score_key:
            result[score_key] = result["evolved_score"]
        else:
            result["score"] = result["evolved_score"]

    except Exception as e:
        result["evolved_score"] = round(base_score, 2)
        result["evolution_applied"] = False
        result["evolution_error"] = str(e)

    return result


def rank_evolved_setups(setups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Evolves and sorts setups from best to weakest.

    This is safe for eligible setup lists before Telegram selection.
    Telegram cap remains controlled elsewhere.
    """

    if not isinstance(setups, list):
        return []

    evolved: List[Dict[str, Any]] = []

    for setup in setups:
        if isinstance(setup, dict):
            evolved.append(evolve_setup(setup))

    evolved.sort(
        key=lambda x: _safe_float(
            x.get("evolved_score", x.get("score", x.get("final_score", 0))),
            0.0,
        ),
        reverse=True,
    )

    return evolved


def passes_evolution_filter(setup: Dict[str, Any], base_threshold: float = 70.0) -> bool:
    """
    Optional adaptive filter.

    Do NOT use this until we confirm your current setup_engine.py structure.
    For now, ranking is safe. Filtering will be connected after seeing your current file.
    """

    try:
        from engines.evolution_engine import get_evolution_filter_threshold

        threshold = get_evolution_filter_threshold(base_threshold)
    except Exception:
        threshold = base_threshold

    score = _safe_float(setup.get("evolved_score", setup.get("score", 0)), 0.0)
    return score >= threshold