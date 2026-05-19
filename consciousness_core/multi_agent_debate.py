from pathlib import Path

from consciousness_core.institutional_utils import (
    clamp,
    confidence_quality,
    evidence_item,
    load_institutional_inputs,
    recent_outcome_stats,
    recommendation,
)
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "multi_agent_debate.json"


AGENTS = (
    "bull_agent",
    "bear_agent",
    "macro_agent",
    "liquidity_agent",
    "manipulation_agent",
    "risk_agent",
    "execution_agent",
)


def _agent(name, stance, confidence, support, contradictions, recommendations, warnings):
    return {
        "agent": name,
        "stance": stance,
        "confidence": round(clamp(confidence, 0.0, 1.0), 3),
        "supporting_evidence": support,
        "contradiction_evidence": contradictions,
        "recommendations": recommendations,
        "warnings": warnings,
    }


def run_multi_agent_debate(output_path=OUTPUT_PATH, **_kwargs):
    inputs = load_institutional_inputs()
    beliefs = inputs["beliefs"]
    weaknesses = inputs["weaknesses"]
    proposals = inputs["proposals"]
    news = inputs["news"]
    no_trade = inputs["no_trade"]
    confidence = inputs["confidence"]
    world = inputs["world_model_memory"]
    causal = inputs["causal_reasoning"]
    outcomes = recent_outcome_stats(inputs["trade_rows"])

    from consciousness_core.liquidity_intelligence import run_liquidity_intelligence
    from consciousness_core.manipulation_intelligence import run_manipulation_intelligence

    liquidity = run_liquidity_intelligence()
    manipulation = run_manipulation_intelligence()
    confidence_info = confidence_quality(confidence)
    top_beliefs = sorted(
        beliefs.values() if isinstance(beliefs, dict) else [],
        key=lambda item: float(item.get("confidence") or 0),
        reverse=True,
    )[:5]
    approved_proposals = [proposal for proposal in proposals if isinstance(proposal, dict) and proposal.get("safety_decision") == "APPROVED_FOR_TEST"]
    no_trade_warning = str(no_trade.get("no_trade_warning") or "NONE").upper()
    liquidity_stress = clamp(liquidity.get("liquidity_stress", {}).get("score") or 0.0)
    manipulation_score = clamp(manipulation.get("suspicion_score") or 0.0)
    setup_quality = clamp(no_trade.get("low_edge_day", {}).get("edge_score") or no_trade.get("low_edge_day", {}).get("average_recent_setup_score") or 50.0)
    news_score = clamp(news.get("news_intelligence_score") or 50.0)

    agents = {
        "bull_agent": _agent(
            "bull_agent",
            "constructive_only_if_confirmation_improves" if setup_quality >= 50 else "not_constructive",
            0.45 if setup_quality >= 50 else 0.25,
            [
                evidence_item("beliefs", "top_beliefs", top_beliefs),
                evidence_item("proposals", "approved_test_proposals", len(approved_proposals)),
                evidence_item("news_intelligence", "news_score", news_score),
            ],
            [
                evidence_item("liquidity_intelligence", "liquidity_stress", liquidity_stress),
                evidence_item("manipulation_intelligence", "suspicion_score", manipulation_score),
            ],
            [recommendation("wait_for_breadth_and_liquidity_confirmation", "bull case needs stronger participation evidence")],
            ["bullish evidence remains recommendation-only and cannot alter live execution"],
        ),
        "bear_agent": _agent(
            "bear_agent",
            "defensive_bias" if weaknesses or no_trade_warning != "NONE" else "neutral_defensive",
            0.65 if weaknesses or no_trade_warning != "NONE" else 0.4,
            [
                evidence_item("weaknesses", "active_weakness_count", len(weaknesses)),
                evidence_item("no_trade", "warning", no_trade_warning),
            ],
            [evidence_item("outcomes", "recent_win_rate", outcomes["win_rate"])],
            [recommendation("reduce_aggression_bias", "weakness/no-trade evidence should constrain conviction")],
            ["do not convert bearish stance into execution control"],
        ),
        "macro_agent": _agent(
            "macro_agent",
            "macro_uncertain",
            0.4,
            [
                evidence_item("world_model_memory", "macro_memory", world.get("macro_memory")),
                evidence_item("economic_calendar", "available", bool(inputs["economic_calendar"])),
            ],
            [evidence_item("news_intelligence", "news_warning", news.get("news_warning"))],
            [recommendation("treat_macro_as_context_only", "macro evidence is informative but not trade-authorizing")],
            ["macro chain is low confidence when data is absent or proxy"],
        ),
        "liquidity_agent": _agent(
            "liquidity_agent",
            "liquidity_cautious" if liquidity_stress >= 45 else "liquidity_neutral",
            0.7 if liquidity_stress >= 45 else 0.5,
            [evidence_item("liquidity_intelligence", "liquidity_regime", liquidity.get("liquidity_regime"))],
            [evidence_item("microstructure", "source_mode", inputs["microstructure"].get("data_mode"))],
            liquidity.get("read_only_recommendations", []),
            ["thin or proxy liquidity should reduce institutional conviction"],
        ),
        "manipulation_agent": _agent(
            "manipulation_agent",
            "trap_risk_cautious" if manipulation_score >= 40 else "trap_risk_low",
            0.72 if manipulation_score >= 40 else 0.45,
            [evidence_item("manipulation_intelligence", "active_patterns", len(manipulation.get("trap_patterns", [])))],
            [evidence_item("news_intelligence", "memory_confidence", news.get("news_reaction_memory", {}).get("memory_confidence"))],
            manipulation.get("no_trade_recommendations", []),
            ["trap risk is advisory only and cannot block execution directly"],
        ),
        "risk_agent": _agent(
            "risk_agent",
            "confidence_reduction_required" if confidence_info["weak"] else "risk_neutral",
            0.8 if confidence_info["weak"] else 0.55,
            [
                evidence_item("confidence_calibration", "sample_size", confidence_info["sample_size"]),
                evidence_item("confidence_calibration", "score", confidence_info["score"]),
            ],
            [evidence_item("causal_reasoning", "causal_lessons", len(causal.get("causal_lessons", [])))],
            [recommendation("shrink_confidence_until_real_sample_improves", confidence_info["reason"])],
            ["no direct risk override is produced"],
        ),
        "execution_agent": _agent(
            "execution_agent",
            "execution_review_only",
            0.5,
            [
                evidence_item("no_trade", "trade_permission", no_trade.get("trade_permission")),
                evidence_item("microstructure", "execution_warning", inputs["microstructure"].get("execution_warning")),
            ],
            [evidence_item("liquidity_intelligence", "thin_liquidity", liquidity.get("thin_liquidity"))],
            [recommendation("prefer_observation_over_action", "execution analysis is read-only and advisory")],
            ["module does not send, cancel, or route orders"],
        ),
    }

    cautious_votes = sum(1 for agent in agents.values() if any(word in agent["stance"] for word in ("cautious", "defensive", "reduction", "review", "uncertain")))
    contradiction_level = "HIGH" if cautious_votes >= 5 or manipulation_score >= 65 else "MEDIUM" if cautious_votes >= 3 else "LOW"
    confidence_adjustment = -25 if contradiction_level == "HIGH" else -12 if contradiction_level == "MEDIUM" else -3
    suggested_action_bias = "NO_TRADE_OR_WAIT" if contradiction_level == "HIGH" else "REDUCE_AGGRESSION" if contradiction_level == "MEDIUM" else "NORMAL_CAUTION"

    payload = {
        "generated_at": now_ist(),
        "inputs_seen": {
            "beliefs": len(beliefs) if isinstance(beliefs, dict) else 0,
            "weaknesses": len(weaknesses),
            "proposals": len(proposals),
            "recent_outcomes": outcomes,
        },
        "agents": agents,
        "final_debate_summary": "Institutional debate favors caution until liquidity, calibration, and trap evidence improve.",
        "final_consensus": "recommendation_only_reduce_aggression_bias" if suggested_action_bias != "NORMAL_CAUTION" else "recommendation_only_normal_caution",
        "contradiction_level": contradiction_level,
        "confidence_adjustment": confidence_adjustment,
        "suggested_action_bias": suggested_action_bias,
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_multi_agent_debate()
