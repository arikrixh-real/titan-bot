import json
from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist, stable_hash


OUTPUT_PATH = Path("data") / "consciousness_core" / "causal_reasoning.json"


def _load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def _source_type(source):
    lowered = str(source).lower()
    if "news" in lowered:
        return "news"
    if "regime" in lowered or "no_trade" in lowered:
        return "regime/no-trade"
    if "confidence" in lowered:
        return "confidence"
    if "backtest" in lowered or "research" in lowered:
        return "backtest"
    if "outcome" in lowered or "journal" in lowered:
        return "outcome"
    return "observation"


def _links_from_weaknesses():
    report = _load_json(Path("data/consciousness_core/latest_consciousness_report.json"), {})
    links = []
    for weakness in report.get("active_weaknesses", []):
        if not isinstance(weakness, dict):
            continue
        for evidence in weakness.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            source = evidence.get("source") or evidence.get("type") or "unknown"
            effect = weakness.get("type") or weakness.get("recommended_investigation")
            links.append(
                {
                    "link_id": "cause_" + stable_hash([source, effect, weakness.get("affected_engine")])[:16],
                    "cause_type": _source_type(source),
                    "cause": source,
                    "effect_type": "weakness",
                    "effect": effect,
                    "target_engine": weakness.get("affected_engine"),
                    "confidence": min(0.95, 0.45 + 0.1 * len(weakness.get("evidence") or [])),
                    "lesson": weakness.get("recommended_investigation"),
                }
            )
    return links


def _links_from_proposals():
    queue = _load_json(Path("data/consciousness_core/evolution_bridge_queue.json"), [])
    links = []
    for proposal in queue:
        if not isinstance(proposal, dict):
            continue
        for evidence in proposal.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            source = evidence.get("source") or evidence.get("type") or "unknown"
            links.append(
                {
                    "link_id": "cause_" + stable_hash([source, proposal.get("proposal_id")])[:16],
                    "cause_type": _source_type(source),
                    "cause": source,
                    "effect_type": "proposal",
                    "effect": proposal.get("suggested_action"),
                    "target_engine": proposal.get("target_engine"),
                    "confidence": 0.65 if proposal.get("safety_decision") == "APPROVED_FOR_TEST" else 0.45,
                    "lesson": "proposal remains recommendation-only until sandbox and paper evidence improves",
                }
            )
    return links


def run_causal_reasoning(output_path=OUTPUT_PATH):
    links = _links_from_weaknesses() + _links_from_proposals()
    unique = {link["link_id"]: link for link in links}
    lessons = [
        link for link in unique.values()
        if link.get("lesson") and link.get("confidence", 0) >= 0.55
    ][:100]
    payload = {
        "generated_at": now_ist(),
        "causal_links": list(unique.values())[:300],
        "causal_lessons": lessons,
    }
    atomic_write_json(output_path, payload)
    return payload
