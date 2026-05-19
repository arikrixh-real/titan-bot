from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "evolution_memory_civilization.json"


def run_evolution_memory_civilization(output_path=OUTPUT_PATH, **_kwargs):
    daily = load_json(CORE_DIR / "daily_review.json", {})
    experience = load_json(CORE_DIR / "experience_memory.json", {})
    real = load_json(CORE_DIR / "real_experience_memory.json", {})
    research = load_json(CORE_DIR / "autonomous_research.json", {})
    world = load_json(CORE_DIR / "recursive_world_model.json", {})
    ecosystem = load_json(CORE_DIR / "evolution_ecosystem.json", {})
    genomes = load_json(CORE_DIR / "strategy_genomes.json", {})

    failed_mutations = [
        item for item in genomes.get("genomes", [])
        if isinstance(item, dict) and item.get("status") == "RETIRED_SANDBOX"
    ]
    payload = {
        "generated_at": now_ist(),
        "short_term_memory": {
            "validated_discoveries": research.get("ranked_discoveries", [])[:10],
            "failed_ideas": daily.get("what_failed", [])[:10],
            "recurring_traps": world.get("manipulation_memory", {}).get("trap_patterns", [])[:10],
        },
        "medium_term_memory": {
            "validated_behaviors": experience.get("repeated_success_patterns", [])[:15],
            "recurring_traps": experience.get("repeated_failure_patterns", [])[:15],
            "dangerous_regimes": daily.get("what_should_be_avoided_tomorrow", [])[:15],
        },
        "long_term_memory": {
            "strong_strategies": ecosystem.get("strongest_mutations", [])[:15],
            "failed_mutations": failed_mutations[-15:],
            "validated_behaviors": real.get("repeated_success_patterns", [])[:15],
            "failed_ideas": real.get("repeated_failure_patterns", [])[:15],
        },
        "permanent_market_laws": world.get("institutional_behavior", {}).get("market_laws", [])[:30],
        "memory_governance": {
            "write_policy": "local_artifact_only",
            "promotion_policy": "validated_by_repeated_evidence_or_paper_test_recommendation",
            "live_mutation_allowed": False,
        },
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_evolution_memory_civilization()
