# TITAN MASTER BRAIN - SETUP NORMALIZER
# STEP 3A
# Purpose:
# Converts setup output into safe dictionary format.
# This prevents errors like:
#     'tuple' object has no attribute 'get'

from typing import Any, Dict


def normalize_setup(setup: Any) -> Dict[str, Any]:
    """
    Convert any setup format into a safe dict.

    Supports:
    - dict
    - tuple/list
    - unknown objects

    Output always has common keys:
    symbol, side, entry, sl, target, rr, score, reason, raw
    """

    if isinstance(setup, dict):
        normalized = {
            "symbol": setup.get("symbol") or setup.get("stock") or setup.get("ticker") or "UNKNOWN",
            "side": setup.get("side") or setup.get("direction") or setup.get("trade_side") or "UNKNOWN",
            "entry": setup.get("entry") or setup.get("entry_price"),
            "sl": setup.get("sl") or setup.get("stop_loss") or setup.get("stoploss"),
            "target": setup.get("target") or setup.get("tp") or setup.get("t1") or setup.get("target1"),
            "rr": setup.get("rr") or setup.get("risk_reward") or setup.get("risk_reward_ratio"),
            "score": setup.get("score") or setup.get("final_score") or setup.get("rank_score"),
            "strategy": setup.get("strategy") or setup.get("setup_type") or "UNKNOWN",
            "reason": setup.get("reason") or setup.get("setup_reason") or setup.get("message") or "",
            "raw": setup,
        }

        for key in [
            "microstructure",
            "advanced_regime",
            "professional_risk",
            "liquidity_quality_score",
            "regime_confidence",
            "risk_quality_score",
            "institutional_score_adjustment",
            "phase1_blocked",
            "phase1_block_reason",
            "portfolio_construction",
            "execution_quality",
            "sector_exposure_score",
            "portfolio_concentration_risk",
            "correlation_proxy",
            "beta_like_market_sensitivity",
            "volatility_contribution_score",
            "execution_quality_score",
            "slippage_risk_estimate",
            "chase_entry_penalty",
            "phase2_score_adjustment",
            "phase2_risk_warnings",
            "phase3_base_score",
            "adaptive_confidence_score",
            "adaptive_feature_adjustment",
            "adaptive_regime_adjustment",
            "adaptive_sector_adjustment",
            "adaptive_symbol_adjustment",
            "adaptive_side_adjustment",
            "cluster_id",
            "cluster_quality_score",
            "cluster_adjustment",
            "news_sentiment_refined",
            "news_sentiment_score",
            "news_relevance_score",
            "news_reaction_adjustment",
            "phase3_adjustment",
            "phase3_adjustment_ratio",
            "phase3_memory_closed_trades",
            "phase3_applied",
            "phase3_active",
            "phase3_error",
            "phase4_data_advantage",
            "phase4_score_adjustment",
            "data_advantage_score",
            "market_risk_tone",
            "sector_strength_score",
            "unusual_activity_score",
        ]:
            if key in setup:
                normalized[key] = setup.get(key)

        return normalized

    if isinstance(setup, (tuple, list)):
        values = list(setup)

        return {
            "symbol": values[0] if len(values) > 0 else "UNKNOWN",
            "side": values[1] if len(values) > 1 else "UNKNOWN",
            "entry": values[2] if len(values) > 2 else None,
            "sl": values[3] if len(values) > 3 else None,
            "target": values[4] if len(values) > 4 else None,
            "rr": values[5] if len(values) > 5 else None,
            "score": values[6] if len(values) > 6 else None,
            "strategy": "UNKNOWN",
            "reason": "Converted from tuple/list setup output",
            "raw": values,
        }

    return {
        "symbol": "UNKNOWN",
        "side": "UNKNOWN",
        "entry": None,
        "sl": None,
        "target": None,
        "rr": None,
        "score": None,
        "strategy": "UNKNOWN",
        "reason": f"Unsupported setup type converted safely: {type(setup).__name__}",
        "raw": str(setup),
    }


def normalize_setups(setups: Any) -> list[Dict[str, Any]]:
    """
    Convert scan_for_setups() output into list of safe setup dicts.
    """

    if setups is None:
        return []

    if isinstance(setups, dict):
        for key in ["setups", "setup_candidates", "candidates", "data"]:
            if isinstance(setups.get(key), list):
                return [normalize_setup(item) for item in setups.get(key)]
        return [normalize_setup(setups)]

    if isinstance(setups, (list, tuple)):
        return [normalize_setup(item) for item in setups]

    return [normalize_setup(setups)]
