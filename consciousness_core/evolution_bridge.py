from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist


BRIDGE_PATH = Path("data") / "consciousness_core" / "evolution_bridge_queue.json"


def _load_bridge_queue(path):
    try:
        import json

        with Path(path).open("r", encoding="utf-8") as bridge_file:
            payload = json.load(bridge_file)
        if isinstance(payload, list):
            return payload
    except Exception:
        pass
    return []


def write_evolution_bridge_queue(proposals, decisions, path=BRIDGE_PATH):
    queue_by_id = {
        item.get("proposal_id"): item
        for item in _load_bridge_queue(path)
        if isinstance(item, dict) and not item.get("consumed")
    }
    for proposal in proposals:
        decision = decisions.get(proposal.get("proposal_id"))
        if decision == "APPROVED_FOR_TEST":
            proposal_id = proposal.get("proposal_id")
            current = queue_by_id.get(proposal_id, {})
            queue_by_id[proposal_id] = {
                "proposal_id": proposal_id,
                "target_engine": proposal.get("target_engine"),
                "suggested_action": proposal.get("suggested_action"),
                "parameter_hint": proposal.get("parameter_hint"),
                "evidence": proposal.get("evidence", []),
                "safety_decision": decision,
                "created_at": current.get("created_at", now_ist()),
                "consumed": False,
            }
    queue = list(queue_by_id.values())[-200:]
    atomic_write_json(path, queue)
    return queue
