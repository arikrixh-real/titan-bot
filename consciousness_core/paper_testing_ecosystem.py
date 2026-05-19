from consciousness_core.experience_utils import load_json, load_trade_rows
from consciousness_core.institutional_utils import CORE_DIR, clamp
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = CORE_DIR / "paper_testing_ecosystem.json"


def _mutation_lookup(mutations):
    items = mutations.get("mutations", []) if isinstance(mutations, dict) else []
    return {item.get("mutation_id"): item for item in items if isinstance(item, dict)}


def _test_entry(recommendation, sandbox_by_id, mutation_by_id, current_sample_size):
    proposal_id = recommendation.get("proposal_id")
    sandbox = sandbox_by_id.get(proposal_id, {})
    related_mutations = [mutation_by_id.get(mid, {"mutation_id": mid}) for mid in recommendation.get("related_mutations", [])]
    priority = "HIGH" if recommendation.get("status") in {"PAPER_TEST_ONLY", "READY_FOR_HUMAN_REVIEW"} else "MEDIUM"
    required_sample_size = 50 if recommendation.get("target_engine") in {"setup_engine", "confidence_calibration"} else 30
    risk_score = clamp((recommendation.get("risk_score") or sandbox.get("risk_score") or 0) * 100, 0, 100)
    return {
        "proposal_id": proposal_id,
        "target_engine": recommendation.get("target_engine"),
        "status": recommendation.get("status"),
        "test_priority": priority,
        "required_sample_size": required_sample_size,
        "current_sample_size": current_sample_size,
        "pass_conditions": [
            f"at least {required_sample_size} paper/outcome observations",
            "positive benefit/risk spread after costs and no-trade filters",
            "no live promotion; human review remains required",
        ],
        "fail_conditions": [
            "drawdown or risk score increases materially",
            "edge disappears in choppy/liquidity-trap scenarios",
            "sample remains too small after repeated cycles",
        ],
        "promotion_blockers": [
            "live_apply_allowed is false by design",
            "requires out-of-sample and paper validation depth",
        ]
        + (["risk score above paper threshold"] if risk_score >= 35 else []),
        "related_mutations": related_mutations,
        "sandbox_recommendation": recommendation.get("sandbox_recommendation") or sandbox.get("recommendation"),
    }


def run_paper_testing_ecosystem(output_path=OUTPUT_PATH, **_kwargs):
    promotions = load_json(CORE_DIR / "promotion_recommendations.json", {})
    mutations = load_json(CORE_DIR / "strategy_mutations.json", {})
    genomes = load_json(CORE_DIR / "strategy_genomes.json", {})
    sandbox = load_json(CORE_DIR / "sandbox_results.json", [])
    trades = load_trade_rows()

    recommendations = promotions.get("recommendations", []) if isinstance(promotions, dict) else []
    sandbox_by_id = {item.get("proposal_id"): item for item in sandbox if isinstance(item, dict)}
    mutation_by_id = _mutation_lookup(mutations)
    current_sample_size = len(trades)
    active = []
    pending = []
    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            continue
        entry = _test_entry(recommendation, sandbox_by_id, mutation_by_id, current_sample_size)
        if recommendation.get("status") in {"PAPER_TEST_ONLY", "READY_FOR_HUMAN_REVIEW"}:
            active.append(entry)
        else:
            pending.append(entry)

    highest_required = max([item["required_sample_size"] for item in active + pending] or [30])
    health_score = clamp((current_sample_size / highest_required) * 65 + (10 if active else 0) + (10 if sandbox else 0), 0, 100)
    payload = {
        "generated_at": now_ist(),
        "safety_scope": "read_only_recommendation_only_no_live_trading_changes",
        "active_paper_tests": active,
        "pending_paper_tests": pending,
        "test_priority": "HIGH" if active else "MEDIUM" if pending else "LOW",
        "required_sample_size": highest_required,
        "current_sample_size": current_sample_size,
        "pass_conditions": [
            "sample size reaches requirement",
            "paper outcomes stay positive across multiple regimes",
            "validation_depth_engine allows human review only",
        ],
        "fail_conditions": [
            "insufficient paper sample",
            "sandbox score weakens or risk rises",
            "data_quality_intelligence marks source unreliable",
        ],
        "promotion_blockers": [
            "live promotion is blocked",
            "Supabase, broker, Telegram, and master-brain internals are untouched",
            "human review required even when paper tests pass",
        ],
        "paper_test_health": {
            "score": round(health_score, 2),
            "state": "MATURE_ENOUGH_FOR_REVIEW" if health_score >= 75 else "IMMATURE_NEEDS_MORE_SAMPLE",
            "active_count": len(active),
            "pending_count": len(pending),
            "sandbox_result_count": len(sandbox),
            "genome_count": len(genomes.get("genomes", [])) if isinstance(genomes, dict) else 0,
        },
    }
    atomic_write_json(output_path, payload)
    return payload
