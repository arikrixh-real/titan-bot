from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = CORE_DIR / "belief_validation.json"


def _belief_status(feedback):
    if feedback.get("outcome") == "PASS":
        return "PROVED"
    if feedback.get("outcome") == "FAIL":
        return "DISPROVED"
    return "UNCERTAIN"


def run_belief_validation(output_path=OUTPUT_PATH, **_kwargs):
    feedback_payload = load_json(CORE_DIR / "paper_feedback.json", {})
    experiments_payload = load_json(CORE_DIR / "experiments.json", {})
    feedback_items = feedback_payload.get("feedback", []) if isinstance(feedback_payload, dict) else []
    experiments = experiments_payload.get("experiments", []) if isinstance(experiments_payload, dict) else []
    experiments_by_id = {item.get("experiment_id"): item for item in experiments if isinstance(item, dict)}

    validations = []
    for feedback in feedback_items:
        if not isinstance(feedback, dict):
            continue
        experiment = experiments_by_id.get(feedback.get("experiment_id"), {})
        status = _belief_status(feedback)
        validations.append(
            {
                "belief_id": "belief_validation_" + stable_hash([feedback.get("experiment_id"), status])[:16],
                "experiment_id": feedback.get("experiment_id"),
                "proposal_id": feedback.get("proposal_id"),
                "target_engine": feedback.get("target_engine"),
                "belief_statement": experiment.get("hypothesis") or f"{feedback.get('target_engine')} paper experiment has validated edge",
                "validation_status": status,
                "confidence": feedback.get("confidence"),
                "evidence": {
                    "observed_sample_size": feedback.get("observed_sample_size"),
                    "observed_win_rate": feedback.get("observed_win_rate"),
                    "observed_loss_rate": feedback.get("observed_loss_rate"),
                    "observed_total_pnl": feedback.get("observed_total_pnl"),
                    "risk_score": feedback.get("risk_score"),
                },
                "belief_update_scope": "phase_d_validation_memory_only",
                "live_decision_mutation_allowed": False,
            }
        )

    payload = {
        "generated_at": now_ist(),
        "safety_scope": "belief_validation_only_no_master_brain_live_mutation",
        "belief_validations": validations[-500:],
        "summary": {
            "proved": sum(1 for item in validations if item.get("validation_status") == "PROVED"),
            "disproved": sum(1 for item in validations if item.get("validation_status") == "DISPROVED"),
            "uncertain": sum(1 for item in validations if item.get("validation_status") == "UNCERTAIN"),
            "live_decision_mutation_allowed": False,
        },
    }
    atomic_write_json(output_path, payload)
    return payload
