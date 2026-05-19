import json
from collections import Counter
from pathlib import Path

from consciousness_core.deduplication import proposal_key
from consciousness_core.state import atomic_write_json, now_ist


OUTPUT_PATH = Path("data") / "consciousness_core" / "meta_learning.json"


def _load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def run_meta_learning(output_path=OUTPUT_PATH):
    queue = _load_json(Path("data/consciousness_core/evolution_bridge_queue.json"), [])
    sandbox_results = _load_json(Path("data/consciousness_core/sandbox_results.json"), [])
    experience = _load_json(Path("data/consciousness_core/experience_memory.json"), {})
    proposals = [item for item in queue if isinstance(item, dict)]
    keys = [proposal_key(item) for item in proposals]
    duplicate_count = sum(count - 1 for count in Counter(keys).values() if count > 1)
    approved = sum(1 for item in proposals if item.get("safety_decision") == "APPROVED_FOR_TEST")
    rejected = sum(1 for item in proposals if item.get("safety_decision") == "REJECTED")
    sufficient = sum(
        1 for item in sandbox_results
        if isinstance(item, dict) and item.get("evidence_quality") in {"MEDIUM", "HIGH"}
    )
    proposal_quality = round(sufficient / max(1, len(sandbox_results)), 3)
    payload = {
        "generated_at": now_ist(),
        "proposal_quality": proposal_quality,
        "duplicate_rate": round(duplicate_count / max(1, len(proposals)), 3),
        "evidence_sufficiency": {
            "sufficient_results": sufficient,
            "total_results": len(sandbox_results),
            "ratio": proposal_quality,
        },
        "approved_rejected_ratio": {
            "approved": approved,
            "rejected": rejected,
            "ratio": round(approved / max(1, rejected), 3),
        },
        "recurring_weakness_count": len(experience.get("weak_engines", []))
        + len(experience.get("repeated_failure_patterns", [])),
        "learning_status": "IMPROVING" if proposal_quality >= 0.5 else "NEEDS_MORE_EVIDENCE",
    }
    atomic_write_json(output_path, payload)
    return payload
