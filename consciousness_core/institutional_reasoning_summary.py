from pathlib import Path

from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_JSON_PATH = Path("data") / "consciousness_core" / "institutional_reasoning_summary.json"
OUTPUT_TXT_PATH = Path("data") / "consciousness_core" / "institutional_reasoning_summary.txt"


def run_institutional_reasoning_summary(output_json_path=OUTPUT_JSON_PATH, output_txt_path=OUTPUT_TXT_PATH, **_kwargs):
    debate = load_json(CORE_DIR / "multi_agent_debate.json", {})
    causal = load_json(CORE_DIR / "deep_causal_reasoning.json", {})
    manipulation = load_json(CORE_DIR / "manipulation_intelligence.json", {})
    liquidity = load_json(CORE_DIR / "liquidity_intelligence.json", {})
    research = load_json(CORE_DIR / "autonomous_research.json", {})
    world = load_json(CORE_DIR / "world_model_expansion.json", {})
    arbitration = load_json(CORE_DIR / "contradiction_arbitration.json", {})

    caution = "HIGH"
    if debate.get("suggested_action_bias") == "NORMAL_CAUTION" and arbitration.get("overall_severity") == "LOW":
        caution = "NORMAL"
    elif arbitration.get("overall_severity") == "MEDIUM":
        caution = "ELEVATED"

    strongest_beliefs = []
    for agent in (debate.get("agents") or {}).values():
        strongest_beliefs.extend(agent.get("supporting_evidence", [])[:2])

    summary = {
        "generated_at": now_ist(),
        "market_understanding": {
            "debate_consensus": debate.get("final_consensus"),
            "causal_chains": causal.get("strongest_causal_chains", [])[:5],
            "world_memory": {
                "macro": world.get("macro_memory", {}).get("long_horizon_lesson"),
                "volatility": world.get("volatility_cycle_memory", {}).get("long_horizon_lesson"),
            },
        },
        "manipulation_risks": {
            "suspicion_score": manipulation.get("suspicion_score"),
            "trap_patterns": manipulation.get("trap_patterns", [])[:5],
        },
        "liquidity_state": {
            "regime": liquidity.get("liquidity_regime"),
            "stress": liquidity.get("liquidity_stress", {}),
            "thin_liquidity": liquidity.get("thin_liquidity"),
        },
        "strongest_beliefs": strongest_beliefs[:10],
        "strongest_contradictions": arbitration.get("contradictions", [])[:10],
        "research_discoveries": research.get("ranked_discoveries", [])[:10],
        "top_institutional_concerns": [
            "confidence calibration may be weak or proxy",
            "liquidity/trap evidence can invalidate setup quality",
            "news reaction memory may be too thin for aggression",
            "all outputs are advisory and cannot mutate live systems",
        ],
        "recommended_caution_aggression_level": caution,
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_json_path, summary)

    lines = [
        "TITAN Phase A Institutional Reasoning Summary",
        f"Generated: {summary['generated_at']}",
        "",
        "Market understanding:",
        f"- Consensus: {summary['market_understanding']['debate_consensus']}",
        f"- Causal chains reviewed: {len(summary['market_understanding']['causal_chains'])}",
        "",
        "Manipulation risks:",
        f"- Suspicion score: {summary['manipulation_risks']['suspicion_score']}",
        f"- Trap patterns: {len(summary['manipulation_risks']['trap_patterns'])}",
        "",
        "Liquidity state:",
        f"- Regime: {summary['liquidity_state']['regime']}",
        f"- Stress: {summary['liquidity_state']['stress'].get('state')} score={summary['liquidity_state']['stress'].get('score')}",
        "",
        "Strongest contradictions:",
    ]
    contradictions = summary["strongest_contradictions"]
    if contradictions:
        lines.extend(f"- {item.get('severity')}: {item.get('type')} adjustment={item.get('recommended_confidence_adjustment')}" for item in contradictions[:8])
    else:
        lines.append("- None above threshold.")
    lines.extend([
        "",
        "Research discoveries:",
    ])
    discoveries = summary["research_discoveries"]
    if discoveries:
        lines.extend(f"- {item.get('hypothesis')} confidence={item.get('confidence')} danger={item.get('danger_level')}" for item in discoveries[:5])
    else:
        lines.append("- None generated.")
    lines.extend([
        "",
        "Top institutional concerns:",
        *[f"- {item}" for item in summary["top_institutional_concerns"]],
        "",
        f"Recommended caution/aggression level: {caution}",
        "Safety scope: read-only, sandbox-safe, recommendation-only.",
    ])
    Path(output_txt_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_txt_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    run_institutional_reasoning_summary()
