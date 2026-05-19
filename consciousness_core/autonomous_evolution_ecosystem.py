from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR, clamp
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "evolution_ecosystem.json"


def _rank(item):
    return clamp(item.get("sandbox_score")) + clamp(item.get("regime_fit")) - clamp(item.get("risk_score"))


def run_autonomous_evolution_ecosystem(output_path=OUTPUT_PATH, **_kwargs):
    previous = load_json(output_path, {})
    genomes = load_json(CORE_DIR / "strategy_genomes.json", {})
    sandbox = load_json(CORE_DIR / "sandbox_results.json", [])
    memory = load_json(CORE_DIR / "experience_memory.json", {})
    meta = load_json(CORE_DIR / "recursive_meta_learning.json", {})
    attention = load_json(CORE_DIR / "adaptive_attention.json", {})

    genome_items = genomes.get("genomes", [])
    active = [item for item in genome_items if isinstance(item, dict) and item.get("status") != "RETIRED_SANDBOX"]
    retired = [item for item in genome_items if isinstance(item, dict) and item.get("status") == "RETIRED_SANDBOX"]
    strongest = sorted(active, key=_rank, reverse=True)[:10]
    weakest = sorted(active, key=_rank)[:10]
    cycles = int(previous.get("evolution_cycles", 0) if isinstance(previous, dict) else 0) + 1

    recurring_failures = memory.get("repeated_failure_patterns", [])[:10]
    recurring_successes = memory.get("repeated_success_patterns", [])[:10]
    focus = attention.get("attention_items", [{}])[0].get("focus_area", "baseline_recursive_monitoring")
    next_direction = meta.get("next_self_improvement_focus") or f"allocate sandbox tests to {focus}"

    payload = {
        "generated_at": now_ist(),
        "evolution_cycles": cycles,
        "active_mutations": active[:50],
        "retired_mutations": retired[-50:],
        "strongest_mutations": strongest,
        "weakest_mutations": weakest,
        "recurring_failures": recurring_failures,
        "recurring_successes": recurring_successes,
        "next_evolution_direction": next_direction,
        "paper_test_recommendations": [
            item for item in sandbox if isinstance(item, dict) and item.get("recommendation") == "PROMOTE_TO_PAPER"
        ][:10],
        "memory_integration": {
            "failed_patterns_seen": len(recurring_failures),
            "success_patterns_seen": len(recurring_successes),
        },
        "safety_scope": "read_only_sandbox_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_autonomous_evolution_ecosystem()
