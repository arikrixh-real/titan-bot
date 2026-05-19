from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR, clamp, text_blob
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = CORE_DIR / "autonomous_goal_hierarchy.json"


def _goal(layer, title, priority, reason):
    return {
        "goal_id": "goal_" + stable_hash([layer, title])[:12],
        "layer": layer,
        "title": title,
        "priority": priority,
        "reason": reason,
        "status": "ACTIVE",
        "live_apply_allowed": False,
    }


def run_autonomous_goal_hierarchy(output_path=OUTPUT_PATH, **_kwargs):
    attention = load_json(CORE_DIR / "adaptive_attention.json", {})
    score = load_json(CORE_DIR / "self_improvement_score.json", {})
    manipulation = load_json(CORE_DIR / "manipulation_intelligence.json", {})
    liquidity = load_json(CORE_DIR / "liquidity_intelligence.json", {})
    context = load_json(CORE_DIR / "consciousness_context.json", {})
    blob = text_blob(attention, score, manipulation, liquidity, context)

    goals = [
        _goal("survival_goals", "preserve read-only recommendation boundaries", "CRITICAL", "recursive systems must never mutate live execution"),
        _goal("safety_goals", "keep every evolution artifact sandbox-only", "CRITICAL", "Phase B is advisory infrastructure only"),
        _goal("accuracy_goals", "improve confidence calibration and belief accuracy", "HIGH", "accuracy controls false certainty"),
        _goal("adaptation_goals", "rank sandbox mutations by evidence and risk", "HIGH", "adaptation needs survivor pressure without live mutation"),
        _goal("research_goals", "validate discoveries through paper-only tests", "MEDIUM", "research must convert into testable recommendations"),
        _goal("intelligence_goals", "increase recursive learning quality", "MEDIUM", "meta-learning should improve future learning"),
    ]
    if "manipulation" in blob or clamp(manipulation.get("suspicion_score")) >= 45:
        goals.append(_goal("safety_goals", "prioritize manipulation-aware caution", "HIGH", "trap memory can invalidate normal strategy logic"))
    if "liquidity" in blob:
        goals.append(_goal("adaptation_goals", "prioritize liquidity-sensitive evolution", "HIGH", "thin liquidity changes expected strategy behavior"))
    if clamp(score.get("overall_recursive_score")) < 55:
        goals.append(_goal("intelligence_goals", "repair weakest recursive growth area", "HIGH", "recursive score is not yet strong"))

    priority_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    goals = sorted(goals, key=lambda item: priority_rank.get(item["priority"], 9))
    payload = {
        "generated_at": now_ist(),
        "reprioritization_reason": "dynamic ordering from attention, risk, liquidity, and recursive score",
        "goal_layers": {
            "survival_goals": [item for item in goals if item["layer"] == "survival_goals"],
            "accuracy_goals": [item for item in goals if item["layer"] == "accuracy_goals"],
            "adaptation_goals": [item for item in goals if item["layer"] == "adaptation_goals"],
            "research_goals": [item for item in goals if item["layer"] == "research_goals"],
            "intelligence_goals": [item for item in goals if item["layer"] == "intelligence_goals"],
            "safety_goals": [item for item in goals if item["layer"] == "safety_goals"],
        },
        "ranked_goals": goals,
        "top_goal": goals[0] if goals else None,
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_autonomous_goal_hierarchy()
