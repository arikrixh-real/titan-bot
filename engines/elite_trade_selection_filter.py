"""
TITAN Phase 19 Step 1 - Elite Trade Selection Filter
----------------------------------------------------

Standalone, fail-open filter for selecting only elite high-probability setups.
This module does not integrate with Telegram, dashboard, broker/execution, or
the daily alert cap. It returns explainable selection metadata only.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except Exception:
        return default


def safe_text(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def clamp(value: Any, min_value: float = 0.0, max_value: float = 100.0) -> float:
    low = safe_float(min_value, 0.0)
    high = safe_float(max_value, 100.0)
    if low > high:
        low, high = high, low
    return max(low, min(high, safe_float(value, low)))


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _raw(setup: Dict[str, Any]) -> Dict[str, Any]:
    raw = setup.get("raw")
    return raw if isinstance(raw, dict) else {}


def _symbol(setup: Dict[str, Any]) -> str:
    raw = _raw(setup)
    return safe_text(setup.get("symbol") or raw.get("symbol") or setup.get("stock") or raw.get("stock"), "UNKNOWN").replace(".NS", "").upper()


def _side(setup: Dict[str, Any]) -> str:
    raw = _raw(setup)
    side = safe_text(setup.get("side") or raw.get("side") or setup.get("direction") or raw.get("direction"), "UNKNOWN").upper()
    if side in {"BUY", "BULLISH"}:
        return "LONG"
    if side in {"SELL", "BEARISH"}:
        return "SHORT"
    return side


def _sector(setup: Dict[str, Any]) -> str:
    raw = _raw(setup)
    return safe_text(
        setup.get("sector") or raw.get("sector") or setup.get("industry") or raw.get("industry"),
        "UNKNOWN",
    ).upper()


def _strategy(setup: Dict[str, Any]) -> str:
    raw = _raw(setup)
    return safe_text(
        setup.get("strategy_family")
        or raw.get("strategy_family")
        or setup.get("setup_type")
        or raw.get("setup_type")
        or setup.get("strategy")
        or raw.get("strategy"),
        "UNKNOWN",
    ).upper()


def _rank_score(setup: Dict[str, Any]) -> float:
    raw = _raw(setup)
    for key in (
        "final_portfolio_rank",
        "final_cross_asset_rank",
        "new_blended_rank_score",
        "blended_rank_score",
        "final_score",
        "score",
        "rank_score",
    ):
        if key in setup and setup.get(key) is not None:
            return clamp(setup.get(key))
        if key in raw and raw.get(key) is not None:
            return clamp(raw.get(key))
    return 0.0


def _confirmations(setup: Dict[str, Any]) -> int:
    raw = _raw(setup)
    setup_context = setup.get("setup_context") if isinstance(setup.get("setup_context"), dict) else raw.get("setup_context")
    setup_context = setup_context if isinstance(setup_context, dict) else {}
    return int(clamp(setup_context.get("confirmations") or setup.get("confirmations") or raw.get("confirmations"), 0, 20))


def _decision_points(setup: Dict[str, Any]) -> float:
    decision = safe_text(setup.get("decision"), "").upper()
    if decision == "TRUST":
        return 100.0
    if decision == "DOWNGRADE":
        return 68.0
    if decision == "REJECT":
        return 10.0
    return 50.0


def _confidence_points(setup: Dict[str, Any]) -> float:
    confidence = safe_text(setup.get("confidence"), "").upper()
    if confidence == "HIGH":
        return 100.0
    if confidence == "MEDIUM":
        return 65.0
    if confidence == "LOW":
        return 25.0
    return 50.0


def calculate_confidence_gap(setups: Any) -> float:
    rows = [_as_dict(item) for item in _as_list(setups) if isinstance(item, dict)]
    scores = sorted([_rank_score(row) for row in rows], reverse=True)
    if len(scores) < 2:
        return round(scores[0], 2) if scores else 0.0
    return round(clamp(scores[0] - scores[1]), 2)


def calculate_setup_uniqueness_score(setup: Any, other_setups: Any) -> float:
    setup = _as_dict(setup)
    others = [_as_dict(item) for item in _as_list(other_setups) if isinstance(item, dict)]
    if not setup:
        return 0.0

    symbol = _symbol(setup)
    sector = _sector(setup)
    side = _side(setup)
    strategy = _strategy(setup)
    penalty = 0.0

    for other in others:
        if other is setup:
            continue
        if _symbol(other) == symbol and symbol != "UNKNOWN":
            penalty += 45.0
        if _sector(other) == sector and sector != "UNKNOWN":
            penalty += 12.0
        if _side(other) == side and _side(other) != "UNKNOWN" and _sector(other) == sector:
            penalty += 10.0
        if _strategy(other) == strategy and strategy != "UNKNOWN":
            penalty += 8.0

    return round(clamp(100.0 - penalty), 2)


def detect_duplicate_trade_idea(setup: Any, selected_setups: Any) -> Dict[str, Any]:
    setup = _as_dict(setup)
    selected = [_as_dict(item) for item in _as_list(selected_setups) if isinstance(item, dict)]
    symbol = _symbol(setup)
    sector = _sector(setup)
    side = _side(setup)
    strategy = _strategy(setup)

    for item in selected:
        same_symbol = symbol != "UNKNOWN" and _symbol(item) == symbol
        same_sector_side = sector != "UNKNOWN" and _sector(item) == sector and _side(item) == side
        same_strategy_side = strategy != "UNKNOWN" and _strategy(item) == strategy and _side(item) == side
        if same_symbol or (same_sector_side and same_strategy_side):
            return {
                "duplicate": True,
                "reason": "same_symbol" if same_symbol else "same_sector_strategy_side",
                "matched_symbol": _symbol(item),
            }

    return {"duplicate": False, "reason": "", "matched_symbol": ""}


def select_best_symbol_per_sector(setups: Any) -> List[Dict[str, Any]]:
    rows = [_as_dict(item) for item in _as_list(setups) if isinstance(item, dict)]
    sector_best: Dict[str, Dict[str, Any]] = {}
    overflow = []

    for setup in sorted(rows, key=lambda item: calculate_elite_quality_score(item, rows), reverse=True):
        sector = _sector(setup)
        if sector == "UNKNOWN":
            overflow.append(setup)
            continue

        current = sector_best.get(sector)
        if current is None:
            sector_best[sector] = setup
            continue

        current_score = calculate_elite_quality_score(current, rows)
        setup_score = calculate_elite_quality_score(setup, rows)
        if setup_score >= current_score + 12.0:
            overflow.append(current)
            sector_best[sector] = setup
        elif setup_score >= 88.0 and setup_score >= current_score - 4.0:
            overflow.append(setup)

    selected = list(sector_best.values()) + overflow
    selected.sort(key=lambda item: calculate_elite_quality_score(item, rows), reverse=True)
    return selected


def detect_low_quality_day(setups: Any, context: Any = None) -> bool:
    rows = [_as_dict(item) for item in _as_list(setups) if isinstance(item, dict)]
    context = _as_dict(context)
    if not rows:
        return True

    scores = [calculate_elite_quality_score(row, rows, context) for row in rows]
    best = max(scores) if scores else 0.0
    average_top = sum(sorted(scores, reverse=True)[:3]) / max(1, min(3, len(scores)))
    market_risk = safe_text(context.get("risk_level") or context.get("market_type") or context.get("risk_mode"), "").upper()

    if market_risk in {"HIGH", "RISK_OFF", "PANIC", "DANGER"} and best < 82.0:
        return True
    return bool(best < 68.0 or average_top < 58.0)


def calculate_trade_scarcity_score(setups: Any, context: Any = None) -> float:
    rows = [_as_dict(item) for item in _as_list(setups) if isinstance(item, dict)]
    context = _as_dict(context)
    if not rows:
        return 100.0

    quality_scores = [
        (_rank_score(row) * 0.65) + (calculate_high_confluence_score(row) * 0.35)
        for row in rows
    ]
    elite_count = sum(1 for score in quality_scores if score >= 78.0)
    strong_count = sum(1 for score in quality_scores if score >= 68.0)
    scarcity = 100.0 - min(75.0, elite_count * 28.0 + max(0, strong_count - elite_count) * 10.0)
    if len(rows) <= 2:
        scarcity += 10.0
    return round(clamp(scarcity), 2)


def calculate_high_confluence_score(setup: Any) -> float:
    setup = _as_dict(setup)
    raw = _raw(setup)
    rr = safe_float(setup.get("rr") or raw.get("rr") or setup.get("risk_reward") or raw.get("risk_reward"), 0.0)
    confirmations = _confirmations(setup)
    probability = safe_float(setup.get("probability_score") or raw.get("probability_score"), 50.0)
    causal = safe_float(setup.get("causal_confidence_score") or raw.get("causal_confidence_score"), 50.0)
    portfolio = safe_float(setup.get("portfolio_safety_score") or raw.get("portfolio_safety_score"), 50.0)
    cross_asset = safe_float(setup.get("cross_asset_alignment_score") or raw.get("cross_asset_alignment_score"), 50.0)
    meta = safe_float(setup.get("meta_quality_score") or raw.get("meta_quality_score"), 50.0)

    score = (
        clamp(rr / 3.0 * 100.0) * 0.18
        + clamp(confirmations * 16.0) * 0.16
        + clamp(probability) * 0.16
        + clamp(causal) * 0.14
        + clamp(portfolio) * 0.12
        + clamp(cross_asset) * 0.12
        + clamp(meta) * 0.12
    )
    return round(clamp(score), 2)


def calculate_elite_quality_score(setup: Any, all_setups: Any = None, context: Any = None) -> float:
    setup = _as_dict(setup)
    rows = [_as_dict(item) for item in _as_list(all_setups) if isinstance(item, dict)]
    context = _as_dict(context)
    if not setup:
        return 0.0

    rank = _rank_score(setup)
    confluence = calculate_high_confluence_score(setup)
    uniqueness = calculate_setup_uniqueness_score(setup, rows)
    decision = _decision_points(setup)
    confidence = _confidence_points(setup)
    scarcity = calculate_trade_scarcity_score(rows, context) if rows else 50.0

    quality = (
        rank * 0.36
        + confluence * 0.24
        + uniqueness * 0.12
        + decision * 0.10
        + confidence * 0.10
        + scarcity * 0.08
    )

    if safe_text(setup.get("portfolio_bias"), "").upper() == "DANGER":
        quality -= 12.0
    if safe_text(setup.get("cross_asset_bias"), "").upper() == "BEARISH" and _side(setup) == "LONG":
        quality -= 8.0
    if safe_text(setup.get("decision"), "").upper() == "REJECT":
        quality -= 25.0

    return round(clamp(quality), 2)


def filter_elite_setups(setups: Any, context: Any = None, max_alerts: int = 3) -> Dict[str, Any]:
    rows = [_as_dict(item) for item in _as_list(setups) if isinstance(item, dict)]
    context = _as_dict(context)
    max_alerts = int(clamp(max_alerts, 0, 10))

    if not rows or max_alerts <= 0:
        return {"selected": [], "rejected": rows, "low_quality_day": True}

    scored = []
    for setup in rows:
        item = dict(setup)
        item["elite_quality_score"] = calculate_elite_quality_score(item, rows, context)
        item["elite_confluence_score"] = calculate_high_confluence_score(item)
        item["elite_uniqueness_score"] = calculate_setup_uniqueness_score(item, rows)
        scored.append(item)

    if detect_low_quality_day(scored, context):
        rejected = []
        for setup in scored:
            item = dict(setup)
            item["elite_reject_reason"] = "low_quality_day"
            rejected.append(item)
        return {"selected": [], "rejected": rejected, "low_quality_day": True}

    sector_screened = select_best_symbol_per_sector(scored)
    selected = []
    rejected = []
    screened_ids = {id(item) for item in sector_screened}

    for setup in sorted(scored, key=lambda item: item.get("elite_quality_score", 0.0), reverse=True):
        if id(setup) not in screened_ids and setup not in sector_screened:
            item = dict(setup)
            item["elite_reject_reason"] = "sector_quality_gap"
            rejected.append(item)
            continue

        duplicate = detect_duplicate_trade_idea(setup, selected)
        if duplicate.get("duplicate"):
            item = dict(setup)
            item["elite_reject_reason"] = duplicate.get("reason")
            rejected.append(item)
            continue

        if safe_float(setup.get("elite_quality_score")) < 68.0:
            item = dict(setup)
            item["elite_reject_reason"] = "below_elite_threshold"
            rejected.append(item)
            continue

        if len(selected) < max_alerts:
            selected.append(setup)
        else:
            item = dict(setup)
            item["elite_reject_reason"] = "max_alerts_reached"
            rejected.append(item)

    selected_keys = {_symbol(item) + "|" + _side(item) for item in selected}
    rejected_keys = {_symbol(item) + "|" + _side(item) for item in rejected}
    for setup in scored:
        key = _symbol(setup) + "|" + _side(setup)
        if key not in selected_keys and key not in rejected_keys:
            item = dict(setup)
            item["elite_reject_reason"] = "not_top_elite"
            rejected.append(item)

    return {"selected": selected, "rejected": rejected, "low_quality_day": False}


def _compact_setup(setup: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": _symbol(setup),
        "side": _side(setup),
        "sector": _sector(setup),
        "rank_score": round(_rank_score(setup), 2),
        "elite_quality_score": round(safe_float(setup.get("elite_quality_score")), 2),
        "elite_confluence_score": round(safe_float(setup.get("elite_confluence_score")), 2),
        "elite_uniqueness_score": round(safe_float(setup.get("elite_uniqueness_score")), 2),
        "reject_reason": setup.get("elite_reject_reason"),
    }


def build_elite_selection_report(setups: Any, context: Any = None, max_alerts: int = 3) -> Dict[str, Any]:
    rows = [_as_dict(item) for item in _as_list(setups) if isinstance(item, dict)]
    result = filter_elite_setups(rows, context=context, max_alerts=max_alerts)
    selected = result.get("selected", [])
    rejected = result.get("rejected", [])
    low_quality_day = bool(result.get("low_quality_day"))
    scarcity = calculate_trade_scarcity_score(rows, context)
    gap = calculate_confidence_gap(rows)

    explanations = []
    if low_quality_day:
        explanations.append("Overall setup quality is weak; no elite alerts selected.")
    if selected:
        explanations.append(f"{len(selected)} elite setup(s) passed quality, uniqueness, and sector filters.")
    if rejected:
        explanations.append(f"{len(rejected)} setup(s) rejected for duplication, sector crowding, or insufficient quality.")
    if scarcity >= 70:
        explanations.append("Trade scarcity is high; quality threshold remains strict.")
    if gap >= 12:
        explanations.append("Top setup has a clear confidence gap over the next candidate.")
    if not explanations:
        explanations.append("No actionable elite setup edge detected.")

    if low_quality_day:
        summary = "Low-quality day: stand aside."
    elif selected:
        summary = f"Selected {len(selected)} elite setup(s), capped at {max_alerts}."
    else:
        summary = "No setup passed the elite filter."

    return {
        "total_setups": len(rows),
        "elite_selected_count": len(selected),
        "rejected_count": len(rejected),
        "low_quality_day": low_quality_day,
        "trade_scarcity_score": scarcity,
        "confidence_gap": gap,
        "selected_elite_setups": [_compact_setup(item) for item in selected],
        "rejected_setups": [_compact_setup(item) for item in rejected],
        "selection_summary": summary,
        "explanations": explanations[:8],
    }


if __name__ == "__main__":
    sample_setups = [
        {
            "symbol": "TCS",
            "sector": "IT",
            "side": "LONG",
            "final_portfolio_rank": 86,
            "rr": 2.6,
            "decision": "TRUST",
            "confidence": "HIGH",
            "portfolio_safety_score": 82,
            "cross_asset_alignment_score": 78,
            "causal_confidence_score": 84,
            "probability_score": 81,
            "meta_quality_score": 76,
            "setup_context": {"confirmations": 6},
            "strategy_family": "Breakout",
        },
        {
            "symbol": "INFY",
            "sector": "IT",
            "side": "LONG",
            "final_portfolio_rank": 77,
            "rr": 2.1,
            "decision": "TRUST",
            "confidence": "HIGH",
            "portfolio_safety_score": 75,
            "cross_asset_alignment_score": 72,
            "setup_context": {"confirmations": 5},
            "strategy_family": "Breakout",
        },
        {
            "symbol": "HDFCBANK",
            "sector": "Banking",
            "side": "LONG",
            "final_cross_asset_rank": 73,
            "rr": 2.2,
            "decision": "TRUST",
            "confidence": "MEDIUM",
            "portfolio_safety_score": 70,
            "cross_asset_alignment_score": 68,
            "setup_context": {"confirmations": 5},
            "strategy_family": "Momentum",
        },
        {
            "symbol": "ICICIBANK",
            "sector": "Banking",
            "side": "LONG",
            "blended_rank_score": 55,
            "rr": 1.6,
            "decision": "DOWNGRADE",
            "confidence": "MEDIUM",
            "setup_context": {"confirmations": 3},
            "strategy_family": "Momentum",
        },
    ]
    sample_context = {"risk_level": "NORMAL", "market_type": "SELECTIVE"}
    print(json.dumps(build_elite_selection_report(sample_setups, sample_context), indent=2, sort_keys=True))
