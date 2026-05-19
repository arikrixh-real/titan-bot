from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = CORE_DIR / "promotion_memory.json"


def _decision_from_validation(validation):
    status = validation.get("validation_status")
    if status == "PROVED":
        return "PROMOTE_TO_HUMAN_REVIEW"
    if status == "DISPROVED":
        return "REJECT"
    return "CONTINUE_PAPER_TEST"


def run_promotion_memory(output_path=OUTPUT_PATH, **_kwargs):
    existing = load_json(output_path, {})
    validations_payload = load_json(CORE_DIR / "belief_validation.json", {})
    feedback_payload = load_json(CORE_DIR / "paper_feedback.json", {})
    validations = validations_payload.get("belief_validations", []) if isinstance(validations_payload, dict) else []
    feedback_by_experiment = {
        item.get("experiment_id"): item
        for item in feedback_payload.get("feedback", [])
        if isinstance(item, dict)
    } if isinstance(feedback_payload, dict) else {}

    history = existing.get("history", []) if isinstance(existing, dict) else []
    seen = {item.get("memory_id") for item in history if isinstance(item, dict)}
    new_items = []
    for validation in validations:
        if not isinstance(validation, dict):
            continue
        decision = _decision_from_validation(validation)
        memory_id = "promotion_memory_" + stable_hash(
            [validation.get("experiment_id"), validation.get("validation_status"), decision]
        )[:16]
        if memory_id in seen:
            continue
        feedback = feedback_by_experiment.get(validation.get("experiment_id"), {})
        new_items.append(
            {
                "memory_id": memory_id,
                "recorded_at": now_ist(),
                "experiment_id": validation.get("experiment_id"),
                "proposal_id": validation.get("proposal_id"),
                "target_engine": validation.get("target_engine"),
                "validation_status": validation.get("validation_status"),
                "promotion_decision": decision,
                "confidence": validation.get("confidence"),
                "observed_sample_size": feedback.get("observed_sample_size"),
                "observed_win_rate": feedback.get("observed_win_rate"),
                "observed_total_pnl": feedback.get("observed_total_pnl"),
                "allowed_next_step": "human_review_only" if decision == "PROMOTE_TO_HUMAN_REVIEW" else "paper_or_reject_only",
                "live_apply_allowed": False,
                "risk_override_allowed": False,
            }
        )

    history = (history + new_items)[-1000:]
    payload = {
        "generated_at": now_ist(),
        "safety_scope": "promotion_memory_only_no_live_apply",
        "history": history,
        "latest_decisions": history[-100:],
        "summary": {
            "total_records": len(history),
            "new_records": len(new_items),
            "promote_to_human_review": sum(1 for item in history if item.get("promotion_decision") == "PROMOTE_TO_HUMAN_REVIEW"),
            "rejected": sum(1 for item in history if item.get("promotion_decision") == "REJECT"),
            "continue_paper_test": sum(1 for item in history if item.get("promotion_decision") == "CONTINUE_PAPER_TEST"),
            "live_apply_allowed": False,
        },
    }
    atomic_write_json(output_path, payload)
    return payload
