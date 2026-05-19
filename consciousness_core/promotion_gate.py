import json
from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = Path("data") / "consciousness_core" / "promotion_recommendations.json"


def _load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def _status_for_result(result):
    if result.get("recommendation") == "REJECT":
        return "REJECT"
    if result.get("recommendation") == "NEEDS_MORE_DATA":
        return "NEEDS_MORE_DATA"
    if result.get("promotion_score", 0) >= 0.5 and result.get("risk_score", 1) <= 0.25:
        return "READY_FOR_HUMAN_REVIEW"
    return "PAPER_TEST_ONLY"


def run_promotion_gate(output_path=OUTPUT_PATH):
    sandbox_results = _load_json(Path("data/consciousness_core/sandbox_results.json"), [])
    mutations_payload = _load_json(Path("data/consciousness_core/strategy_mutations.json"), {})
    mutations = mutations_payload.get("mutations", []) if isinstance(mutations_payload, dict) else []
    recommendations = []
    for result in sandbox_results:
        if not isinstance(result, dict):
            continue
        status = _status_for_result(result)
        matching_mutations = [
            item.get("mutation_id")
            for item in mutations
            if isinstance(item, dict) and item.get("target_engine") == result.get("target_engine")
        ]
        recommendations.append(
            {
                "recommendation_id": "promotion_" + stable_hash([result.get("proposal_id"), status])[:16],
                "created_at": now_ist(),
                "proposal_id": result.get("proposal_id"),
                "status": status,
                "target_engine": result.get("target_engine"),
                "sandbox_recommendation": result.get("recommendation"),
                "promotion_score": result.get("promotion_score"),
                "risk_score": result.get("risk_score"),
                "related_mutations": matching_mutations,
                "live_apply_allowed": False,
                "reasons": result.get("reasons", []) + ["never auto-apply live"],
            }
        )
    payload = {
        "generated_at": now_ist(),
        "allowed_statuses": ["REJECT", "NEEDS_MORE_DATA", "PAPER_TEST_ONLY", "READY_FOR_HUMAN_REVIEW"],
        "recommendations": recommendations[-500:],
    }
    atomic_write_json(output_path, payload)
    return payload
