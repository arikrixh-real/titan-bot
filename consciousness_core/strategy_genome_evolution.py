from pathlib import Path

from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR, clamp, text_blob
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = CORE_DIR / "strategy_genomes.json"


def _score(value, default=50.0):
    return clamp(value if value is not None else default)


def _base_genome(seed, generation):
    weak_text = text_blob(seed)
    filters = ["paper_only_validation_gate"]
    no_trade_rules = ["block_when_evidence_is_insufficient"]
    if any(term in weak_text for term in ("choppy", "sideways", "no_trade", "avoid")):
        filters.append("choppy_regime_filter")
        no_trade_rules.append("avoid_choppy_low_confirmation")
    if any(term in weak_text for term in ("confidence", "calibration", "overconfidence")):
        filters.append("confidence_calibration_filter")
    if any(term in weak_text for term in ("liquidity", "thin", "spread")):
        filters.append("liquidity_stress_filter")
    if any(term in weak_text for term in ("manipulation", "trap", "fakeout")):
        filters.append("manipulation_trap_filter")
        no_trade_rules.append("avoid_suspected_trap_regime")
    if any(term in weak_text for term in ("sector", "breadth", "confirmation")):
        filters.append("sector_confirmation_filter")

    return {
        "filters": sorted(set(filters)),
        "confidence_modifiers": {
            "weak_calibration_penalty": -0.12 if "confidence" in weak_text else -0.06,
            "multi_source_confirmation_bonus": 0.08,
            "liquidity_stress_penalty": -0.1 if "liquidity" in weak_text else -0.04,
        },
        "regime_requirements": [
            "known_market_regime",
            "avoid_unknown_high_volatility" if "volatility" in weak_text else "normal_regime_context",
        ],
        "no_trade_rules": sorted(set(no_trade_rules)),
        "liquidity_sensitivity": "HIGH" if "liquidity" in weak_text else "MEDIUM",
        "manipulation_sensitivity": "HIGH" if any(term in weak_text for term in ("trap", "manipulation", "fakeout")) else "MEDIUM",
        "sector_confirmation_rules": [
            "require_sector_alignment_for_breakout",
            "penalize_trade_against_sector_pressure",
        ],
        "mutation_generation": generation,
    }


def _genome(seed, parent_ids, reason, generation, sandbox_score, risk_score, regime_fit):
    body = _base_genome(seed, generation)
    genome = {
        "genome_id": "genome_" + stable_hash([seed, parent_ids, reason, generation])[:16],
        "parent_ids": parent_ids,
        "mutation_reason": reason,
        "sandbox_score": round(_score(sandbox_score), 2),
        "risk_score": round(_score(risk_score), 2),
        "regime_fit": round(_score(regime_fit), 2),
        "mutation_generation": generation,
        "status": "ACTIVE_SANDBOX",
        "live_apply_allowed": False,
        "safety_scope": "read_only_recommendation_only",
    }
    genome.update(body)
    return genome


def _rank(genome):
    return (
        float(genome.get("sandbox_score") or 0)
        + float(genome.get("regime_fit") or 0)
        - float(genome.get("risk_score") or 0)
    )


def run_strategy_genome_evolution(output_path=OUTPUT_PATH, **_kwargs):
    previous = load_json(output_path, {})
    previous_genomes = previous.get("genomes", []) if isinstance(previous, dict) else []
    phase_a = load_json(CORE_DIR / "institutional_reasoning_summary.json", {})
    mutations = load_json(CORE_DIR / "strategy_mutations.json", {})
    sandbox = load_json(CORE_DIR / "sandbox_results.json", [])
    context = load_json(CORE_DIR / "consciousness_context.json", {})

    generation = int(previous.get("mutation_generation", 0) if isinstance(previous, dict) else 0) + 1
    seeds = []
    seeds.extend(mutations.get("mutations", [])[:8])
    seeds.extend(context.get("top_weaknesses", [])[:8])
    seeds.extend(phase_a.get("top_institutional_concerns", [])[:5])
    if not seeds:
        seeds.append({"reason": "baseline recursive genome seed", "source": "no_prior_seed"})

    sandbox_scores = [
        clamp((item.get("promotion_score") or 0) * 100, 0, 100)
        for item in sandbox
        if isinstance(item, dict)
    ]
    avg_sandbox = sum(sandbox_scores) / len(sandbox_scores) if sandbox_scores else 50.0
    risk_seed = phase_a.get("manipulation_risks", {}).get("suspicion_score")
    risk = clamp(risk_seed if risk_seed is not None else 35.0)
    liquidity_state = str(phase_a.get("liquidity_state", {}).get("stress", {}).get("state") or "").upper()
    regime_fit = 58.0 if liquidity_state not in {"HIGH", "SEVERE"} else 42.0

    parents = sorted(previous_genomes, key=_rank, reverse=True)[:3]
    genomes = []
    for seed in seeds[:12]:
        reason = seed.get("description") if isinstance(seed, dict) else str(seed)
        if not reason:
            reason = seed.get("recommended_investigation", "recursive sandbox mutation")
        parent_ids = [parents[0]["genome_id"]] if parents else []
        genomes.append(_genome(seed, parent_ids, reason, generation, avg_sandbox + len(genomes), risk, regime_fit))

    if len(parents) >= 2:
        crossover_seed = {"parents": parents[:2], "type": "survivor_crossover"}
        genomes.append(
            _genome(
                crossover_seed,
                [parents[0]["genome_id"], parents[1]["genome_id"]],
                "crossover of highest ranked sandbox survivors",
                generation,
                max(avg_sandbox, _rank(parents[0])),
                min(risk, 40.0),
                max(regime_fit, 55.0),
            )
        )

    retained = []
    for genome in previous_genomes[-100:]:
        if not isinstance(genome, dict):
            continue
        genome = dict(genome)
        if _rank(genome) < 20 or float(genome.get("risk_score") or 0) >= 75:
            genome["status"] = "RETIRED_SANDBOX"
        retained.append(genome)

    combined = retained + genomes
    active = sorted([item for item in combined if item.get("status") != "RETIRED_SANDBOX"], key=_rank, reverse=True)
    retired = [item for item in combined if item.get("status") == "RETIRED_SANDBOX"]
    payload = {
        "generated_at": now_ist(),
        "mutation_generation": generation,
        "genomes": (active[:80] + retired[-20:])[-100:],
        "survivor_ranking": [
            {"genome_id": item.get("genome_id"), "rank_score": round(_rank(item), 2), "status": item.get("status")}
            for item in active[:20]
        ],
        "retired_count": len(retired),
        "safety_scope": "read_only_sandbox_recommendation_only",
    }
    atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    run_strategy_genome_evolution()
