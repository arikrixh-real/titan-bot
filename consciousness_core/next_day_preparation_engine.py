from consciousness_core.experience_utils import load_json, safe_float
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "next_day_preparation.json"


def _scenario_items(scenarios):
    if isinstance(scenarios, dict):
        return scenarios.get("scenarios", [])
    return []


def _extract_symbols(stock_personality):
    symbols = stock_personality.get("symbols", {})
    if isinstance(symbols, dict):
        ranked = sorted(
            symbols.items(),
            key=lambda item: safe_float(item[1].get("sample_size") or item[1].get("trade_count"), 0.0) if isinstance(item[1], dict) else 0,
            reverse=True,
        )
        return [symbol for symbol, _ in ranked[:12]]
    return []


def run_next_day_preparation(output_path=OUTPUT_PATH, **_kwargs):
    report = load_json(CORE_DIR / "latest_consciousness_report.json", {})
    scenarios = load_json(CORE_DIR / "real_scenario_simulation.json", {})
    missions = load_json(CORE_DIR / "research_missions.json", [])
    daily = load_json(CORE_DIR / "daily_review.json", {})
    stock_personality = load_json(CORE_DIR / "stock_personality.json", {})
    world = load_json(CORE_DIR / "world_model_memory.json", {})
    recursive_world = load_json(CORE_DIR / "recursive_world_model.json", {})
    no_trade = report.get("phase3_daily_review", {}).get("what_should_be_avoided_tomorrow", [])
    liquidity = load_json(CORE_DIR / "liquidity_intelligence.json", {})
    manipulation = load_json(CORE_DIR / "manipulation_intelligence.json", {})

    scenario_list = _scenario_items(scenarios)
    top_scenarios = scenario_list[:3]
    dominant = top_scenarios[0] if top_scenarios else {}
    top_risks = []
    for scenario in top_scenarios:
        top_risks.append(
            {
                "risk": scenario.get("scenario_type"),
                "probability": scenario.get("probability"),
                "risk_level": scenario.get("risk_level"),
                "recommended_response": scenario.get("recommended_bias"),
            }
        )
    if liquidity.get("thin_liquidity"):
        top_risks.append({"risk": "thin liquidity", "risk_level": "HIGH", "recommended_response": "avoid aggressive entries"})
    for trap in manipulation.get("trap_patterns", [])[:3]:
        if isinstance(trap, dict) and trap.get("active"):
            top_risks.append({"risk": trap.get("pattern"), "risk_level": "HIGH", "recommended_response": trap.get("warning")})

    symbols = _extract_symbols(stock_personality)
    weak_symbols = [
        item.get("symbol")
        for item in daily.get("what_failed", [])
        if isinstance(item, dict) and item.get("symbol")
    ][:8]
    setup_avoid = ["low confirmation breakout", "news-only entry", "thin-liquidity momentum chase"]
    if dominant.get("scenario_id") in {"fake_breakout", "liquidity_trap", "choppy_no_edge"}:
        setup_avoid.append("first-breakout continuation without retest")
    setup_favor = ["confirmation-after-pullback", "multi-source aligned setup", "paper-test-only validation"]
    if dominant.get("scenario_id") == "bullish_continuation":
        setup_favor.append("continuation with liquidity confirmation")

    payload = {
        "generated_at": now_ist(),
        "safety_scope": "read_only_recommendation_only",
        "expected_regime": {
            "dominant_scenario": dominant.get("scenario_type", "unknown"),
            "liquidity_regime": liquidity.get("liquidity_regime"),
            "recursive_regime": recursive_world.get("volatility_cycles", {}).get("current_choppy_market", {}),
            "market_laws": world.get("market_laws", [])[:5],
        },
        "top_risks": top_risks[:12],
        "watchlist_focus": [
            "prioritize symbols with known personality and enough outcome history",
            "downgrade setups with thin liquidity, trap, or contradiction evidence",
            "keep all improvements in paper-test recommendation mode",
        ],
        "stocks_to_watch": symbols[:10],
        "stocks_to_avoid": [symbol for symbol in weak_symbols if symbol] or [],
        "setup_types_to_favor": setup_favor,
        "setup_types_to_avoid": setup_avoid,
        "confidence_warnings": report.get("phase3_confidence_recalibration", {}).get("weak_calibration_evidence", [])[:10],
        "no_trade_conditions": (no_trade or [])[:10]
        + [
            "scenario probability is led by trap/choppy/news contradiction",
            "liquidity source mode is proxy or insufficient",
            "paper evidence sample remains below required size",
        ],
        "research_priorities": missions[:10],
        "premarket_questions": [
            "Is liquidity normal enough to trust breakouts?",
            "Are news and confidence evidence aligned or contradictory?",
            "Which paper tests still lack sample size?",
            "Did overnight macro context change the expected regime?",
        ],
        "next_day_bias": "defensive_confirmation_required"
        if any(item.get("risk_level") == "HIGH" for item in top_risks if isinstance(item, dict))
        else "conditional_selective",
    }
    atomic_write_json(output_path, payload)
    return payload
