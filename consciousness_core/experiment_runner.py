from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = CORE_DIR / "experiments.json"
ELIGIBLE_STATUSES = {"PAPER_TEST_ONLY", "READY_FOR_HUMAN_REVIEW"}


def _experiment_for_recommendation(recommendation, sandbox_by_id, paper_by_id):
    proposal_id = recommendation.get("proposal_id")
    sandbox = sandbox_by_id.get(proposal_id, {})
    paper = paper_by_id.get(proposal_id, {})
    target_engine = recommendation.get("target_engine") or "unknown_engine"
    required_sample_size = int(paper.get("required_sample_size") or (50 if target_engine == "confidence_calibration" else 30))
    experiment_id = "experiment_" + stable_hash([proposal_id, recommendation.get("recommendation_id"), target_engine])[:16]
    action = sandbox.get("suggested_action") or recommendation.get("sandbox_recommendation") or "paper-test recommendation"
    return {
        "experiment_id": experiment_id,
        "created_at": now_ist(),
        "proposal_id": proposal_id,
        "recommendation_id": recommendation.get("recommendation_id"),
        "target_engine": target_engine,
        "source_status": recommendation.get("status"),
        "hypothesis": f"{target_engine} recommendation improves paper/backtest outcomes without increasing risk: {action}",
        "test_method": "paper_and_sandbox_observation_only",
        "required_sample_size": required_sample_size,
        "success_condition": {
            "minimum_sample_size": required_sample_size,
            "minimum_win_rate": 52.0,
            "minimum_total_pnl": 0.0,
            "maximum_risk_score": 0.25,
            "requires_human_review": True,
        },
        "fail_condition": {
            "maximum_loss_rate": 55.0,
            "negative_total_pnl_allowed": False,
            "risk_score_above": 0.35,
            "insufficient_sample_result": "UNCERTAIN",
        },
        "control_group": "current production logic, observed in paper/backtest only",
        "treatment_group": "approved recommendation tracked in paper/sandbox only",
        "evidence_sources": [
            "data/paper_trading/paper_processed_results.json",
            "data/paper_trading/paper_closed_positions.json",
            "data/journals/trade_outcomes.csv",
            "data/research/backtesting_validation_report.json",
            "data/consciousness_core/sandbox_results.json",
        ],
        "live_apply_allowed": False,
        "broker_execution_allowed": False,
        "telegram_change_allowed": False,
        "supabase_schema_change_allowed": False,
        "master_brain_live_mutation_allowed": False,
        "reasons": recommendation.get("reasons", []),
        "sandbox_snapshot": {
            "recommendation": sandbox.get("recommendation"),
            "promotion_score": sandbox.get("promotion_score", recommendation.get("promotion_score")),
            "risk_score": sandbox.get("risk_score", recommendation.get("risk_score")),
            "evidence_quality": sandbox.get("evidence_quality"),
        },
    }


def run_experiment_runner(output_path=OUTPUT_PATH, **_kwargs):
    promotions = load_json(CORE_DIR / "promotion_recommendations.json", {})
    sandbox_results = load_json(CORE_DIR / "sandbox_results.json", [])
    paper_tests = load_json(CORE_DIR / "paper_testing_ecosystem.json", {})

    recommendations = promotions.get("recommendations", []) if isinstance(promotions, dict) else []
    sandbox_by_id = {item.get("proposal_id"): item for item in sandbox_results if isinstance(item, dict)}
    active_tests = paper_tests.get("active_paper_tests", []) if isinstance(paper_tests, dict) else []
    paper_by_id = {item.get("proposal_id"): item for item in active_tests if isinstance(item, dict)}

    experiments = []
    skipped = []
    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            continue
        if recommendation.get("status") in ELIGIBLE_STATUSES:
            experiments.append(_experiment_for_recommendation(recommendation, sandbox_by_id, paper_by_id))
        else:
            skipped.append(
                {
                    "proposal_id": recommendation.get("proposal_id"),
                    "status": recommendation.get("status"),
                    "reason": "not approved for paper experiment",
                }
            )

    payload = {
        "generated_at": now_ist(),
        "safety_scope": "paper_sandbox_only_no_live_execution",
        "eligible_statuses": sorted(ELIGIBLE_STATUSES),
        "experiments": experiments[-500:],
        "skipped_recommendations": skipped[-200:],
        "summary": {
            "experiment_count": len(experiments),
            "skipped_count": len(skipped),
            "live_apply_allowed": False,
            "broker_execution_allowed": False,
        },
    }
    atomic_write_json(output_path, payload)
    return payload
