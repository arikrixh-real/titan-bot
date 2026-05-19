import json
from pathlib import Path

from consciousness_core.state import atomic_write_json, now_ist


BRIDGE_PATH = Path("data") / "consciousness_core" / "evolution_bridge_queue.json"
RESULTS_PATH = Path("data") / "consciousness_core" / "sandbox_results.json"


def _load_json(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def _evidence_items(proposal):
    evidence = proposal.get("evidence") or []
    return [item for item in evidence if isinstance(item, dict)]


def _evidence_quality(evidence):
    if not evidence:
        return "LOW", ["no direct evidence attached"]
    sources = {item.get("source") for item in evidence if item.get("source")}
    actionability = [
        float(item.get("actionability_score") or 0.0)
        for item in evidence
        if isinstance(item.get("actionability_score"), (int, float))
    ]
    avg_actionability = sum(actionability) / len(actionability) if actionability else 0.35
    if len(evidence) >= 2 and len(sources) >= 2 and avg_actionability >= 0.55:
        return "HIGH", []
    if sources and avg_actionability >= 0.35:
        return "MEDIUM", []
    return "LOW", ["evidence is sparse or low actionability"]


def _benefit_score(proposal, evidence):
    action = f"{proposal.get('suggested_action', '')} {proposal.get('target_engine', '')}".lower()
    score = 0.25
    if any(word in action for word in ("block", "hold", "insufficient", "validation")):
        score += 0.25
    if any(word in action for word in ("confidence", "calibration", "sector", "filter", "no-trade", "regime")):
        score += 0.2
    if evidence:
        score += min(0.2, len(evidence) * 0.04)
    return round(min(score, 1.0), 3)


def _risk_score(proposal, evidence):
    action = f"{proposal.get('suggested_action', '')} {proposal.get('target_engine', '')}".lower()
    risk = 0.2
    if any(word in action for word in ("live", "broker", "order", "execution", "risk")):
        risk += 0.35
    if any(word in action for word in ("block", "hold", "paper", "backtest", "study")):
        risk -= 0.08
    if any((item.get("severity") or "").upper() == "HIGH" for item in evidence):
        risk += 0.08
    return round(max(0.0, min(risk, 1.0)), 3)


def _recommendation(evidence_quality, expected_benefit, risk_score, reasons):
    if risk_score >= 0.65:
        return "REJECT", reasons + ["risk score too high for sandbox promotion"]
    if evidence_quality == "LOW":
        return "NEEDS_MORE_DATA", reasons + ["needs stronger evidence before paper testing"]
    promotion_score = expected_benefit - risk_score
    if promotion_score >= 0.35 and evidence_quality in {"MEDIUM", "HIGH"}:
        return "PROMOTE_TO_PAPER", reasons + ["sandbox read-only evidence supports paper testing"]
    return "NEEDS_MORE_DATA", reasons + ["benefit/risk spread is not strong enough yet"]


def _evaluate(proposal):
    evidence = _evidence_items(proposal)
    evidence_quality, reasons = _evidence_quality(evidence)
    expected_benefit = _benefit_score(proposal, evidence)
    risk_score = _risk_score(proposal, evidence)
    promotion_score = round(expected_benefit - risk_score, 3)
    recommendation, reasons = _recommendation(evidence_quality, expected_benefit, risk_score, reasons)
    return {
        "proposal_id": proposal.get("proposal_id"),
        "tested_at": now_ist(),
        "test_status": "READ_ONLY_EVALUATED",
        "evidence_quality": evidence_quality,
        "expected_benefit": expected_benefit,
        "risk_score": risk_score,
        "promotion_score": promotion_score,
        "recommendation": recommendation,
        "target_engine": proposal.get("target_engine"),
        "suggested_action": proposal.get("suggested_action"),
        "reasons": reasons,
    }


def run_sandbox_evolution(queue_path=BRIDGE_PATH, results_path=RESULTS_PATH):
    queue = _load_json(queue_path, [])
    previous = _load_json(results_path, [])
    previous_by_id = {
        item.get("proposal_id"): item
        for item in previous
        if isinstance(item, dict) and item.get("proposal_id")
    }
    result_by_id = dict(previous_by_id)
    evaluated_ids = []

    for proposal in queue:
        if not isinstance(proposal, dict):
            continue
        if proposal.get("consumed") or proposal.get("safety_decision") != "APPROVED_FOR_TEST":
            continue
        proposal_id = proposal.get("proposal_id")
        if not proposal_id:
            continue
        result_by_id[proposal_id] = _evaluate(proposal)
        evaluated_ids.append(proposal_id)

    results = list(result_by_id.values())[-500:]
    atomic_write_json(results_path, results)

    if evaluated_ids:
        written = _load_json(results_path, [])
        written_ids = {
            item.get("proposal_id")
            for item in written
            if isinstance(item, dict) and item.get("proposal_id")
        }
        if set(evaluated_ids).issubset(written_ids):
            for proposal in queue:
                if isinstance(proposal, dict) and proposal.get("proposal_id") in evaluated_ids:
                    proposal["consumed"] = True
                    proposal["consumed_at"] = now_ist()
                    proposal["consumed_by"] = "sandbox_evolution"
            atomic_write_json(queue_path, queue)

    return {
        "evaluated_count": len(evaluated_ids),
        "result_count": len(results),
        "results": results[-20:],
    }
