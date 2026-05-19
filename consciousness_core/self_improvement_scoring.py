from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR, clamp
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "self_improvement_score.json"


def _avg(values):
    values = [clamp(value) for value in values]
    return round(sum(values) / len(values), 2) if values else 0.0


def run_self_improvement_scoring(output_path=OUTPUT_PATH, **_kwargs):
    meta = load_json(CORE_DIR / "recursive_meta_learning.json", {})
    ecosystem = load_json(CORE_DIR / "evolution_ecosystem.json", {})
    amplification = load_json(CORE_DIR / "intelligence_amplification.json", {})
    memory = load_json(CORE_DIR / "world_model_memory.json", {})
    institutional = load_json(CORE_DIR / "institutional_reasoning_summary.json", {})

    proposal_success = clamp(meta.get("evolution_quality", {}).get("score"))
    sandbox_quality = clamp(len(ecosystem.get("paper_test_recommendations", [])) * 12 + 45)
    research_usefulness = clamp(meta.get("research_quality", {}).get("score"))
    belief_accuracy = clamp(meta.get("learning_quality", {}).get("score"))
    causal_reliability = clamp(meta.get("reasoning_quality", {}).get("score"))
    debate_effectiveness = clamp(meta.get("debate_quality", {}).get("score"))
    adaptation_quality = clamp(amplification.get("adaptation_velocity"))
    memory_usefulness = clamp(45 + len(memory.get("market_laws", [])) * 8 + len(memory.get("engine_memory", {})) * 3)

    evolution_score = _avg([proposal_success, sandbox_quality, adaptation_quality])
    reasoning_score = _avg([belief_accuracy, causal_reliability, debate_effectiveness])
    adaptation_score = _avg([adaptation_quality, amplification.get("amplification_score")])
    memory_score = memory_usefulness
    institutional_score = _avg([
        institutional.get("manipulation_risks", {}).get("suspicion_score", 50),
        institutional.get("liquidity_state", {}).get("stress", {}).get("score", 50),
        reasoning_score,
    ])
    overall = _avg([evolution_score, reasoning_score, adaptation_score, memory_score, institutional_score, research_usefulness])
    status = "STRONG_RECURSIVE_GROWTH" if overall >= 70 else "CONTROLLED_RECURSIVE_GROWTH" if overall >= 50 else "EARLY_RECURSIVE_GROWTH"

    payload = {
        "generated_at": now_ist(),
        "overall_recursive_score": overall,
        "evolution_score": evolution_score,
        "reasoning_score": reasoning_score,
        "adaptation_score": adaptation_score,
        "memory_score": memory_score,
        "institutional_intelligence_score": institutional_score,
        "recursive_growth_status": status,
        "component_scores": {
            "proposal_success": proposal_success,
            "sandbox_quality": sandbox_quality,
            "research_usefulness": research_usefulness,
            "belief_accuracy": belief_accuracy,
            "causal_reliability": causal_reliability,
            "debate_effectiveness": debate_effectiveness,
            "adaptation_quality": adaptation_quality,
            "memory_usefulness": memory_usefulness,
        },
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_self_improvement_scoring()
