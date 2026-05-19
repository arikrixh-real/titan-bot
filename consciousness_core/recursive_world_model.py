from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "recursive_world_model.json"


def run_recursive_world_model(output_path=OUTPUT_PATH, **_kwargs):
    world = load_json(CORE_DIR / "world_model_expansion.json", {})
    world_memory = load_json(CORE_DIR / "world_model_memory.json", {})
    manipulation = load_json(CORE_DIR / "manipulation_intelligence.json", {})
    liquidity = load_json(CORE_DIR / "liquidity_intelligence.json", {})
    genomes = load_json(CORE_DIR / "strategy_genomes.json", {})
    ecosystem = load_json(CORE_DIR / "evolution_ecosystem.json", {})
    context = load_json(CORE_DIR / "consciousness_context.json", {})

    payload = {
        "generated_at": now_ist(),
        "macro_memory": world.get("macro_memory", {}),
        "liquidity_cycles": world.get("liquidity_cycle_memory", {}),
        "volatility_cycles": world.get("volatility_cycle_memory", {}),
        "manipulation_memory": {
            "summary": world.get("manipulation_memory", {}),
            "current_suspicion_score": manipulation.get("suspicion_score"),
            "trap_patterns": manipulation.get("trap_patterns", [])[:20],
        },
        "institutional_behavior": {
            "liquidity_regime": liquidity.get("liquidity_regime"),
            "liquidity_stress": liquidity.get("liquidity_stress", {}),
            "market_laws": world_memory.get("market_laws", [])[:20],
        },
        "strategy_behavior": {
            "active_genomes": genomes.get("genomes", [])[:20],
            "strongest_mutations": ecosystem.get("strongest_mutations", [])[:10],
            "weakest_mutations": ecosystem.get("weakest_mutations", [])[:10],
        },
        "adaptive_regime_memory": {
            "active_regime_warnings": context.get("active_regime_warnings", [])[:20],
            "no_trade_warnings": context.get("no_trade_warnings", [])[:20],
            "confidence_warnings": context.get("confidence_warnings", [])[:20],
        },
        "recursive_update_rule": "future world-model updates must use validated memory, paper outcomes, and contradiction checks only",
        "safety_scope": "read_only_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_recursive_world_model()
