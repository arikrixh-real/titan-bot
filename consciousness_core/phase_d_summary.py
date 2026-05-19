from consciousness_core.experience_utils import load_json
from consciousness_core.institutional_utils import CORE_DIR
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_JSON_PATH = CORE_DIR / "phase_d_summary.json"
OUTPUT_TXT_PATH = CORE_DIR / "phase_d_summary.txt"


def run_phase_d_summary(output_json_path=OUTPUT_JSON_PATH, output_txt_path=OUTPUT_TXT_PATH, **_kwargs):
    experiments = load_json(CORE_DIR / "experiments.json", {})
    feedback = load_json(CORE_DIR / "paper_feedback.json", {})
    validation = load_json(CORE_DIR / "belief_validation.json", {})
    memory = load_json(CORE_DIR / "promotion_memory.json", {})

    exp_summary = experiments.get("summary", {}) if isinstance(experiments, dict) else {}
    feedback_summary = feedback.get("summary", {}) if isinstance(feedback, dict) else {}
    validation_summary = validation.get("summary", {}) if isinstance(validation, dict) else {}
    memory_summary = memory.get("summary", {}) if isinstance(memory, dict) else {}
    blockers = []
    if feedback_summary.get("uncertain_count", 0):
        blockers.append("some experiments need more paper sample before belief promotion")
    if validation_summary.get("disproved", 0):
        blockers.append("some hypotheses were disproved and must remain rejected")
    if not exp_summary.get("experiment_count"):
        blockers.append("no eligible recommendations were available for Phase D experiments")

    payload = {
        "generated_at": now_ist(),
        "safety_scope": "autonomous_experiment_feedback_only_no_live_execution",
        "experiment_summary": exp_summary,
        "paper_feedback_summary": feedback_summary,
        "belief_validation_summary": validation_summary,
        "promotion_memory_summary": memory_summary,
        "latest_decisions": memory.get("latest_decisions", [])[-20:] if isinstance(memory, dict) else [],
        "remaining_blockers": blockers,
        "hard_safety_guards": [
            "no live broker execution",
            "no Telegram changes",
            "no Supabase schema changes",
            "no live risk override",
            "no direct master brain live decision mutation",
        ],
    }
    atomic_write_json(output_json_path, payload)
    lines = [
        "TITAN Phase D Summary",
        f"Generated: {payload['generated_at']}",
        "",
        f"Experiments created: {exp_summary.get('experiment_count', 0)}",
        f"Feedback records: {feedback_summary.get('feedback_count', 0)} pass={feedback_summary.get('pass_count', 0)} fail={feedback_summary.get('fail_count', 0)} uncertain={feedback_summary.get('uncertain_count', 0)}",
        f"Beliefs: proved={validation_summary.get('proved', 0)} disproved={validation_summary.get('disproved', 0)} uncertain={validation_summary.get('uncertain', 0)}",
        f"Promotion memory: total={memory_summary.get('total_records', 0)} new={memory_summary.get('new_records', 0)}",
        "",
        "Remaining blockers:",
    ]
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- None beyond mandatory human review and paper-only promotion scope.")
    lines.append("")
    lines.append("Safety: Phase D is paper/sandbox-only and cannot execute broker orders, change Telegram/Supabase, override risk, or mutate master-brain live decisions.")
    output_txt_path.parent.mkdir(parents=True, exist_ok=True)
    output_txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload
