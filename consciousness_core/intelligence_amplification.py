from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR, clamp
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "intelligence_amplification.json"


def run_intelligence_amplification(output_path=OUTPUT_PATH, **_kwargs):
    previous = load_json(output_path, {})
    meta = load_json(CORE_DIR / "recursive_meta_learning.json", {})
    ecosystem = load_json(CORE_DIR / "evolution_ecosystem.json", {})
    arbitration = load_json(CORE_DIR / "contradiction_arbitration.json", {})
    research = load_json(CORE_DIR / "autonomous_research.json", {})
    confidence = load_json(CORE_DIR / "confidence_recalibration.json", {})

    learning_velocity = clamp(meta.get("learning_quality", {}).get("score"))
    reasoning_velocity = clamp(meta.get("reasoning_quality", {}).get("score"))
    adaptation_velocity = clamp(ecosystem.get("evolution_cycles", 0) * 8 + len(ecosystem.get("strongest_mutations", [])) * 4)
    contradiction_score = clamp(100 - clamp(arbitration.get("aggregate_confidence_adjustment")) * 100)
    discovery_score = clamp(40 + len(research.get("ranked_discoveries", [])) * 8)
    calibration_score = clamp(confidence.get("calibrated_confidence_score") or 50)
    amplification_score = round(
        (learning_velocity + reasoning_velocity + adaptation_velocity + contradiction_score + discovery_score + calibration_score) / 6,
        2,
    )
    prev_score = clamp(previous.get("amplification_score")) if isinstance(previous, dict) else amplification_score
    trend = "IMPROVING" if amplification_score > prev_score else "STABLE" if amplification_score == prev_score else "WEAKENING"
    growth_state = "RECURSIVE_GROWTH_ACTIVE" if amplification_score >= 60 else "RECURSIVE_GROWTH_FORMING"

    payload = {
        "generated_at": now_ist(),
        "amplification_score": amplification_score,
        "learning_velocity": round(learning_velocity, 2),
        "reasoning_velocity": round(reasoning_velocity, 2),
        "adaptation_velocity": round(adaptation_velocity, 2),
        "confidence_calibration_improvement": round(calibration_score, 2),
        "contradiction_handling_improvement": round(contradiction_score, 2),
        "research_discovery_improvement": round(discovery_score, 2),
        "improvement_trend": trend,
        "intelligence_growth_state": growth_state,
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_intelligence_amplification()
