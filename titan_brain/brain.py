from titan_brain.brain_config import (
    BRAIN_WEIGHTS,
    MIN_BRAIN_SCORE_FOR_ALERT,
    HIGH_CONVICTION_SCORE
)

from titan_brain.institutional_engine import analyze_institutional
from titan_brain.sector_engine import analyze_sector
from titan_brain.hedge_fund_engine import analyze_hedge_fund_logic
from titan_brain.historical_event_engine import analyze_historical_events

from titan_brain.knowledge_base.market_rules import MARKET_RULES
from titan_brain.learning_adjustments import compute_learning_adjustment
from titan_brain.adaptive_learning_engine import calculate_adaptive_learning
from titan_brain.behavior_analyzer import analyze_market_behavior
from titan_brain.structure_analyzer import analyze_market_structure
from titan_brain.real_structure_engine import analyze_real_structure
from titan_brain.multi_timeframe_engine import analyze_multi_timeframe
from titan_brain.entry_timing_engine import analyze_entry_timing
from titan_brain.strict_filter import apply_strict_filters
from titan_brain.risk_management_engine import analyze_risk_management
from titan_brain.position_sizing_engine import calculate_position_size


def get_relevant_rules(engine_key, score):
    rules = MARKET_RULES.get(engine_key, [])

    if not rules:
        return []

    if score >= 70:
        return rules[:2]
    elif score >= 40:
        return rules[:1]
    else:
        return []


def calculate_conviction(total_score):
    if total_score >= HIGH_CONVICTION_SCORE:
        return "HIGH"
    elif total_score >= 60:
        return "MEDIUM"
    else:
        return "LOW"


def run_titan_brain(stock_data):
    institutional = analyze_institutional(stock_data)
    sector = analyze_sector(stock_data)
    hedge_fund = analyze_hedge_fund_logic(stock_data)
    historical_event = analyze_historical_events(stock_data)

    total_score = (
        institutional["score"] * BRAIN_WEIGHTS["institutional"] / 100 +
        sector["score"] * BRAIN_WEIGHTS["sector"] / 100 +
        hedge_fund["score"] * BRAIN_WEIGHTS["hedge_fund"] / 100 +
        historical_event["score"] * BRAIN_WEIGHTS["historical_event"] / 100
    )

    learning_score, learning_reason = compute_learning_adjustment(stock_data)
    adaptive_learning = calculate_adaptive_learning(stock_data)

    behavior = analyze_market_behavior(stock_data)
    structure = analyze_market_structure(stock_data)
    real_structure = analyze_real_structure(stock_data)
    multi_timeframe = analyze_multi_timeframe(stock_data)
    entry_timing = analyze_entry_timing(stock_data)

    total_score += learning_score
    total_score += adaptive_learning["adjustment"]
    total_score += behavior["adjustment"]
    total_score += structure["adjustment"]
    total_score += real_structure["adjustment"]
    total_score += multi_timeframe["adjustment"]
    total_score += entry_timing["adjustment"]

    total_score = max(0, min(total_score, 100))
    conviction = calculate_conviction(total_score)

    risk_management = analyze_risk_management(
        stock_data,
        {
            "brain_score": round(total_score, 2),
            "conviction": conviction
        }
    )

    total_score += risk_management["adjustment"]
    total_score = max(0, min(total_score, 100))
    conviction = calculate_conviction(total_score)

    position_sizing = calculate_position_size(stock_data, risk_management)

    knowledge = {
        "institutional": get_relevant_rules("institutional", institutional["score"]),
        "sector": get_relevant_rules("sector", sector["score"]),
        "hedge_fund": get_relevant_rules("hedge_fund", hedge_fund["score"]),
        "historical_event": get_relevant_rules("historical_event", historical_event["score"])
    }

    strict_filter = apply_strict_filters({
        "behavior": behavior,
        "structure": structure,
        "real_structure": real_structure,
        "multi_timeframe": multi_timeframe,
        "entry_timing": entry_timing,
        "risk_management": risk_management
    })

    allow_alert = (
        total_score >= MIN_BRAIN_SCORE_FOR_ALERT and
        strict_filter["passed"]
    )

    return {
        "brain_score": round(total_score, 2),
        "conviction": conviction,
        "allow_alert": allow_alert,
        "strict_filter": strict_filter,
        "learning": {
            "adjustment": learning_score,
            "reason": learning_reason
        },
        "adaptive_learning": adaptive_learning,
        "behavior": behavior,
        "structure": structure,
        "real_structure": real_structure,
        "multi_timeframe": multi_timeframe,
        "entry_timing": entry_timing,
        "risk_management": risk_management,
        "position_sizing": position_sizing,
        "engines": {
            "institutional": institutional,
            "sector": sector,
            "hedge_fund": hedge_fund,
            "historical_event": historical_event
        },
        "knowledge": knowledge
    }