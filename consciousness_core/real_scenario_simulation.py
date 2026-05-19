from consciousness_core.experience_utils import load_json, load_standard_reports, load_trade_rows
from consciousness_core.institutional_utils import CORE_DIR, clamp, text_blob
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = CORE_DIR / "real_scenario_simulation.json"


SCENARIO_DEFINITIONS = (
    ("bullish_continuation", "bullish continuation", "controlled upside continuation after confirmation"),
    ("bearish_breakdown", "bearish breakdown", "downside expansion or failed support recovery"),
    ("choppy_no_edge", "choppy/no-edge", "rotation without clean directional edge"),
    ("liquidity_trap", "liquidity trap", "price movement distorted by thin liquidity or clustered stop risk"),
    ("fake_breakout", "fake breakout", "initial breakout fails and reverses after weak participation"),
    ("macro_shock", "macro shock", "macro or calendar event overwhelms local setup quality"),
    ("news_contradiction", "news contradiction", "headline context conflicts with confidence or price evidence"),
    ("high_volatility_reversal", "high-volatility reversal", "fast move reverses under elevated volatility or trap risk"),
    ("low_liquidity_drift", "low-liquidity drift", "slow directional drift with poor participation and weak fills"),
)


def _score_inputs(context, world, institutional, recursive_world, no_trade, confidence, liquidity, manipulation, trades, news):
    blob = text_blob(context, world, institutional, recursive_world, no_trade, confidence, liquidity, manipulation, trades[-50:], news)
    confidence_sample = int(confidence.get("predicted_vs_actual", {}).get("sample_size") or 0)
    liquidity_stress = clamp(liquidity.get("liquidity_stress", {}).get("score") or 0)
    manipulation_score = clamp(manipulation.get("suspicion_score") or 0)
    choppy_score = clamp(
        recursive_world.get("volatility_cycles", {}).get("current_choppy_market", {}).get("danger_score") or 0
    )
    news_warning = "review" in str(news.get("warning") or news.get("memory_warning") or news.get("event_classification") or "").lower()
    confidence_weak = (
        confidence_sample < 20
        or "review" in str(confidence.get("calibration_warning") or "").lower()
        or bool(confidence.get("sample_size_warning"))
    )
    no_trade_risk = "no trade" in blob or "no_trade" in blob or "avoid" in blob
    macro_seen = "economic_calendar" in blob or "macro" in blob or "event" in blob
    thin_liquidity = bool(liquidity.get("thin_liquidity")) or "thin" in str(liquidity.get("liquidity_regime") or "").lower()
    strong_participation = bool(liquidity.get("strong_participation"))
    trap_active = any(item.get("active") for item in manipulation.get("trap_patterns", []) if isinstance(item, dict))
    recent_rows = len(trades[-50:])
    return {
        "bullish_continuation": 28 + (14 if strong_participation else 0) + (8 if not no_trade_risk else -8) + (6 if not confidence_weak else -6),
        "bearish_breakdown": 24 + (10 if no_trade_risk else 0) + (8 if liquidity_stress >= 50 else 0),
        "choppy_no_edge": 30 + choppy_score * 0.25 + (12 if no_trade_risk else 0) + (10 if confidence_weak else 0),
        "liquidity_trap": 25 + liquidity_stress * 0.35 + manipulation_score * 0.25 + (10 if trap_active else 0),
        "fake_breakout": 24 + manipulation_score * 0.32 + (8 if thin_liquidity else 0) + (8 if confidence_weak else 0),
        "macro_shock": 18 + (18 if macro_seen else 0) + (10 if news_warning else 0),
        "news_contradiction": 20 + (18 if news_warning else 0) + (12 if confidence_weak else 0) + (8 if "contradiction" in blob else 0),
        "high_volatility_reversal": 22 + choppy_score * 0.3 + manipulation_score * 0.2 + (8 if trap_active else 0),
        "low_liquidity_drift": 24 + liquidity_stress * 0.25 + (16 if thin_liquidity else 0) + (6 if recent_rows < 20 else 0),
    }


def _risk_level(probability, score):
    if score >= 65 or probability >= 18:
        return "HIGH"
    if score >= 45 or probability >= 12:
        return "MEDIUM"
    return "LOW"


def _affected_engines(scenario_type):
    mapping = {
        "bullish_continuation": ["setup_engine", "confidence_calibration", "paper_engine"],
        "bearish_breakdown": ["setup_engine", "risk_watchdog", "no_trade"],
        "choppy_no_edge": ["setup_engine", "no_trade", "scanner"],
        "liquidity_trap": ["liquidity_intelligence", "risk_watchdog", "setup_engine"],
        "fake_breakout": ["manipulation_intelligence", "setup_engine", "no_trade"],
        "macro_shock": ["news_intelligence", "market_regime_update", "risk_watchdog"],
        "news_contradiction": ["news_intelligence", "confidence_calibration", "no_trade"],
        "high_volatility_reversal": ["volatility_check", "risk_watchdog", "setup_engine"],
        "low_liquidity_drift": ["liquidity_intelligence", "scanner", "paper_engine"],
    }
    return mapping.get(scenario_type, ["consciousness_core"])


def _evidence_for(scenario_type, confidence, liquidity, manipulation, no_trade, news, recursive_world):
    evidence = [
        {"source": "confidence_recalibration", "signal": "sample_size", "value": confidence.get("predicted_vs_actual", {}).get("sample_size")},
        {"source": "liquidity_intelligence", "signal": "liquidity_regime", "value": liquidity.get("liquidity_regime")},
        {"source": "manipulation_intelligence", "signal": "suspicion_score", "value": manipulation.get("suspicion_score")},
    ]
    if scenario_type in {"choppy_no_edge", "high_volatility_reversal"}:
        evidence.append(
            {
                "source": "recursive_world_model",
                "signal": "current_choppy_market",
                "value": recursive_world.get("volatility_cycles", {}).get("current_choppy_market", {}),
            }
        )
    if scenario_type in {"liquidity_trap", "fake_breakout", "low_liquidity_drift"}:
        evidence.append({"source": "liquidity_intelligence", "signal": "liquidity_stress", "value": liquidity.get("liquidity_stress")})
        evidence.append({"source": "manipulation_intelligence", "signal": "trap_patterns", "value": manipulation.get("trap_patterns", [])[:3]})
    if scenario_type in {"macro_shock", "news_contradiction"}:
        evidence.append({"source": "news_intelligence", "signal": "news_context", "value": news})
    if scenario_type in {"bearish_breakdown", "choppy_no_edge", "news_contradiction"}:
        evidence.append({"source": "no_trade", "signal": "warnings", "value": no_trade})
    return evidence


def run_real_scenario_simulation(output_path=OUTPUT_PATH, **_kwargs):
    reports = load_standard_reports()
    context = load_json(CORE_DIR / "consciousness_context.json", {})
    world = load_json(CORE_DIR / "world_model_memory.json", {})
    institutional = load_json(CORE_DIR / "institutional_reasoning_summary.json", {})
    recursive_world = load_json(CORE_DIR / "recursive_world_model.json", {})
    confidence = load_json(CORE_DIR / "confidence_recalibration.json", {}) or reports.get("confidence", {})
    liquidity = load_json(CORE_DIR / "liquidity_intelligence.json", {})
    manipulation = load_json(CORE_DIR / "manipulation_intelligence.json", {})
    no_trade = reports.get("no_trade", {})
    news = reports.get("news", {})
    trades = load_trade_rows()

    raw_scores = _score_inputs(context, world, institutional, recursive_world, no_trade, confidence, liquidity, manipulation, trades, news)
    total = sum(max(1.0, score) for score in raw_scores.values()) or 1.0
    scenarios = []
    for scenario_id, scenario_label, behavior in SCENARIO_DEFINITIONS:
        score = clamp(raw_scores.get(scenario_id), 1, 100)
        probability = round((score / total) * 100, 2)
        confidence_penalty = 12 if int(confidence.get("predicted_vs_actual", {}).get("sample_size") or 0) < 20 else 0
        scenario_confidence = clamp(55 + score * 0.35 - confidence_penalty, 5, 95)
        risk_level = _risk_level(probability, score)
        no_trade_bias = risk_level == "HIGH" or scenario_id in {"choppy_no_edge", "liquidity_trap", "fake_breakout", "macro_shock", "news_contradiction"}
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": scenario_label,
                "probability": probability,
                "confidence": round(scenario_confidence, 2),
                "evidence": _evidence_for(scenario_id, confidence, liquidity, manipulation, no_trade, news, recursive_world),
                "risk_level": risk_level,
                "affected_engines": _affected_engines(scenario_id),
                "expected_market_behavior": behavior,
                "recommended_bias": "wait_for_confirmation" if no_trade_bias else "conditional_directional_only",
                "no_trade_bias": no_trade_bias,
                "paper_test_needed": True,
            }
        )
    scenarios.sort(key=lambda item: item["probability"], reverse=True)
    payload = {
        "generated_at": now_ist(),
        "safety_scope": "read_only_recommendation_only",
        "scenario_count": len(scenarios),
        "dominant_scenario": scenarios[0]["scenario_type"] if scenarios else "unknown",
        "scenarios": scenarios,
        "input_hash": stable_hash(
            {
                "context": context,
                "world": world,
                "institutional": institutional,
                "recursive_world": recursive_world,
                "confidence": confidence,
                "liquidity": liquidity,
                "manipulation": manipulation,
                "no_trade": no_trade,
                "news": news,
            }
        ),
    }
    atomic_write_json(output_path, payload)
    return payload
