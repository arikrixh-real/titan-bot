from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from consciousness_core.experience_utils import safe_float
from consciousness_core.safety_gate import evaluate_proposal
from consciousness_core.state import atomic_write_json, now_ist, stable_hash


PROPOSALS_PATH = Path("data") / "evolution" / "proposals" / "self_improvement_proposals.json"
RUNTIME_STATUS_PATH = Path("data") / "runtime" / "self_improvement_status.json"

SOURCE_PATHS = {
    "report_vault": Path("data") / "report_vault" / "latest_aggregated_packet.json",
    "consciousness_core": Path("data") / "consciousness_core" / "consciousness_context.json",
    "experience_intelligence": Path("data") / "experience_vault" / "reports" / "experience_intelligence_summary.json",
    "contradiction_summary": Path("data") / "consciousness_core" / "contradiction_arbitration.json",
    "confidence_calibration": Path("data") / "confidence_calibration" / "latest_confidence_calibration_report.json",
    "no_trade_intelligence": Path("data") / "no_trade" / "latest_no_trade_intelligence_report.json",
    "backtesting_validation": Path("data") / "research" / "backtesting_validation_report.json",
    "promotion_gate": Path("data") / "memory" / "promotion_gate_memory.json",
}

ALLOWED_STATUSES = {
    "PROPOSED",
    "REJECTED",
    "PAPER_TEST",
    "VALIDATED",
    "PROMOTED",
    "BLOCKED",
}
MAX_PROPOSALS = 200
MAX_EVIDENCE_ITEMS = 8
SAFE_PROMOTION_SCORE = 0.70


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, type(default)) else default
    except Exception:
        return default


def _compact(value: Any, limit: int = 500) -> Any:
    if isinstance(value, dict):
        return {str(key): _compact(item, limit=limit) for key, item in list(value.items())[:20]}
    if isinstance(value, list):
        return [_compact(item, limit=limit) for item in value[:MAX_EVIDENCE_ITEMS]]
    text = str(value)
    return text[:limit]


def _proposal_id(source: str, affected_area: str, proposed_change: str) -> str:
    return "sip_" + stable_hash(
        {
            "source": source,
            "affected_area": affected_area,
            "proposed_change": proposed_change,
        }
    )[:16]


def _proposal(
    *,
    source: str,
    reason: str,
    evidence: Iterable[Any],
    affected_area: str,
    proposed_change: str,
    risk_level: str,
    validation_required: bool = True,
    paper_test_required: bool = True,
) -> Dict[str, Any]:
    evidence_items = [_compact(item) for item in list(evidence or [])[:MAX_EVIDENCE_ITEMS]]
    proposal = {
        "proposal_id": _proposal_id(source, affected_area, proposed_change),
        "source": source,
        "reason": str(reason)[:700],
        "evidence": evidence_items,
        "affected_area": affected_area,
        "proposed_change": str(proposed_change)[:700],
        "risk_level": str(risk_level or "MEDIUM").upper(),
        "validation_required": bool(validation_required),
        "paper_test_required": bool(paper_test_required),
        "live_apply_allowed": False,
        "status": "PROPOSED",
        "created_at": now_ist(),
    }
    return proposal


def _source_names(evidence: Iterable[Any], source: str) -> List[str]:
    names = {source}
    for item in evidence or []:
        if isinstance(item, dict):
            raw = item.get("source") or item.get("source_path") or item.get("source_worker")
            if raw:
                names.add(str(raw))
    return sorted(names)


def _is_external_simulated_only(proposal: Dict[str, Any]) -> bool:
    source = str(proposal.get("source") or "").lower()
    evidence_text = json.dumps(proposal.get("evidence") or [], sort_keys=True, default=str).lower()
    external_markers = ("external", "imported_unvalidated", "simulated", "unvalidated")
    native_markers = ("trade_outcomes", "trade_journal", "paper_trade", "confidence_calibration", "backtesting_validation")
    has_external = source == "experience_intelligence" or any(marker in evidence_text for marker in external_markers)
    has_native = any(marker in evidence_text for marker in native_markers)
    return has_external and not has_native


def _load_sources() -> Dict[str, Any]:
    return {
        name: _read_json(path, {})
        for name, path in SOURCE_PATHS.items()
        if name != "promotion_gate"
    }


def _from_report_vault(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    proposals = []
    for finding in (payload.get("merged_findings") or [])[:12]:
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity") or "MEDIUM").upper()
        affected = "research_pipeline"
        text = str(finding.get("finding") or "").lower()
        if "confidence" in text:
            affected = "confidence_calibration"
        elif "no trade" in text or "no-trade" in text:
            affected = "no_trade"
        elif "backtest" in text or "validation" in text:
            affected = "backtesting"
        elif "setup" in text:
            affected = "setup_engine"
        proposals.append(
            _proposal(
                source="report_vault",
                reason=f"Report vault finding: {finding.get('finding')}",
                evidence=finding.get("evidence") or [finding],
                affected_area=affected,
                proposed_change=f"Create a paper/backtest validation task for: {finding.get('finding')}",
                risk_level="HIGH" if severity in {"HIGH", "CRITICAL"} else "MEDIUM",
            )
        )

    for conflict in (payload.get("contradiction_resolution_summaries") or [])[:8]:
        if not isinstance(conflict, dict):
            continue
        proposals.append(
            _proposal(
                source="contradiction_summary",
                reason=conflict.get("summary") or "Contradiction summary requires reconciliation.",
                evidence=[conflict],
                affected_area="research_pipeline",
                proposed_change="Route conflicting intelligence to manual review before any downstream strategy change.",
                risk_level="MEDIUM",
                paper_test_required=False,
            )
        )
    return proposals


def _from_consciousness(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    proposals = []
    for item in (payload.get("strategy_mutations") or [])[:20]:
        if not isinstance(item, dict):
            continue
        proposals.append(
            _proposal(
                source="consciousness_core",
                reason=item.get("description") or item.get("kind") or "Consciousness mutation candidate.",
                evidence=item.get("evidence") or [item],
                affected_area=item.get("target_engine") or "consciousness_core",
                proposed_change=item.get("description") or item.get("kind") or "Validate candidate mutation in shadow.",
                risk_level="MEDIUM",
                validation_required=True,
                paper_test_required=True,
            )
        )

    world_model = payload.get("world_model_memory") if isinstance(payload.get("world_model_memory"), dict) else {}
    engine_memory = world_model.get("engine_memory") if isinstance(world_model.get("engine_memory"), dict) else {}
    for directive in (engine_memory.get("learning_directives") or [])[:15]:
        if not isinstance(directive, dict):
            continue
        confidence = safe_float(directive.get("confidence"))
        proposals.append(
            _proposal(
                source="consciousness_core",
                reason=directive.get("reason") or "Learning directive requires controlled validation.",
                evidence=directive.get("evidence") or [directive],
                affected_area=directive.get("target_engine") or "research_pipeline",
                proposed_change=directive.get("suggested_adjustment") or directive.get("learning_type") or "Validate learning directive.",
                risk_level="LOW" if confidence is not None and confidence < 0.75 else "MEDIUM",
                validation_required=True,
                paper_test_required=True,
            )
        )
    return proposals


def _from_experience_summary(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    proposals = []
    for cluster in (payload.get("failure_clusters") or [])[:8]:
        if not isinstance(cluster, dict):
            continue
        key = cluster.get("key") or "external failure cluster"
        proposals.append(
            _proposal(
                source="experience_intelligence",
                reason=f"Imported experience failure cluster observed: {key}",
                evidence=cluster.get("sample_lessons") or [cluster],
                affected_area="research_pipeline",
                proposed_change=f"Backtest and paper-test whether this imported failure pattern is present in native TITAN data: {key}",
                risk_level="MEDIUM",
                validation_required=True,
                paper_test_required=True,
            )
        )
    return proposals


def _from_calibration(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    sample_size = safe_float((payload.get("predicted_vs_actual") or {}).get("sample_size"), 0)
    warning = str(payload.get("calibration_warning") or payload.get("calibration_bias") or "").upper()
    if sample_size and int(sample_size) >= 20 and warning not in {"REVIEW", "WARNING"}:
        return []
    return [
        _proposal(
            source="confidence_calibration",
            reason="Confidence calibration evidence is weak, proxy-based, or under-sampled.",
            evidence=[payload.get("predicted_vs_actual"), payload.get("confidence_correction"), payload.get("calibration_warning")],
            affected_area="confidence_calibration",
            proposed_change="Keep confidence reductions in paper validation until calibrated native outcome samples are populated.",
            risk_level="MEDIUM",
        )
    ]


def _from_no_trade(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    score = safe_float(payload.get("no_trade_score"), 0.0)
    warning = str(payload.get("no_trade_warning") or "").upper()
    wait_mode = payload.get("wait_mode") if isinstance(payload.get("wait_mode"), dict) else {}
    if score < 40 and warning in {"", "NONE"} and not wait_mode.get("wait_recommended"):
        return []
    return [
        _proposal(
            source="no_trade_intelligence",
            reason="No-trade intelligence raised caution or wait pressure.",
            evidence=[payload.get("no_trade_score"), payload.get("wait_mode"), payload.get("contradiction_overload"), payload.get("low_edge_day")],
            affected_area="no_trade",
            proposed_change="Paper-test stricter no-trade caution rules against skipped-trade outcomes before any live filter change.",
            risk_level="MEDIUM",
        )
    ]


def _from_backtesting(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    status = str(payload.get("validation_status") or "").upper()
    score = safe_float(payload.get("validation_score"), 0.0)
    allowed = bool(payload.get("live_deployment_allowed", False))
    if status in {"PASS", "OK"} and score >= 70 and allowed:
        return []
    return [
        _proposal(
            source="backtesting_validation",
            reason=f"Backtesting validation is not deployment-ready: status={status or 'UNKNOWN'}, score={score}.",
            evidence=[payload.get("historical_backtest"), payload.get("out_of_sample_validation"), payload.get("statistical_significance"), payload.get("explanations")],
            affected_area="backtesting",
            proposed_change="Block promotion and prioritize populated backtest, walk-forward, out-of-sample, and paper validation coverage.",
            risk_level="HIGH",
            validation_required=True,
            paper_test_required=False,
        )
    ]


def _dedupe(proposals: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for proposal in proposals:
        proposal_id = proposal.get("proposal_id")
        if not proposal_id:
            continue
        existing = by_id.get(proposal_id)
        if existing:
            existing["evidence"] = (existing.get("evidence") or []) + (proposal.get("evidence") or [])
            existing["evidence"] = existing["evidence"][:MAX_EVIDENCE_ITEMS]
            existing["source"] = ",".join(sorted(set(str(existing.get("source", "")).split(",")) | {str(proposal.get("source"))}))
            continue
        by_id[proposal_id] = dict(proposal)
    return list(by_id.values())[:MAX_PROPOSALS]


def _route(proposal: Dict[str, Any]) -> str:
    safety_status = evaluate_proposal(
        {
            "title": proposal.get("proposed_change"),
            "reason": proposal.get("reason"),
            "target_engine": proposal.get("affected_area"),
            "suggested_action": proposal.get("proposed_change"),
            "parameter_hint": "",
            "risk_level": proposal.get("risk_level"),
            "requires_backtest": bool(proposal.get("validation_required")),
            "evidence": proposal.get("evidence"),
        }
    )
    proposal["safety_gate_status"] = safety_status

    if safety_status == "REJECTED" or str(proposal.get("risk_level")).upper() == "HIGH":
        return "blocked_safety_risk" if safety_status == "REJECTED" else "needs_manual_review"
    if not proposal.get("evidence"):
        return "rejected_low_evidence"
    if _is_external_simulated_only(proposal):
        return "needs_backtest"
    if proposal.get("paper_test_required"):
        return "needs_paper_test"
    if proposal.get("validation_required"):
        return "needs_backtest"
    return "needs_manual_review"


def _route_status(route: str) -> str:
    if route == "blocked_safety_risk":
        return "BLOCKED"
    if route == "rejected_low_evidence":
        return "REJECTED"
    if route == "needs_paper_test":
        return "PAPER_TEST"
    return "PROPOSED"


def _promotion_gate_passed(promotion_memory: Dict[str, Any]) -> bool:
    summary = promotion_memory.get("promotion_summary") if isinstance(promotion_memory.get("promotion_summary"), dict) else {}
    safety = promotion_memory.get("safety") if isinstance(promotion_memory.get("safety"), dict) else {}
    return (
        bool(safety.get("no_forbidden_imports_detected", True))
        and not bool(summary.get("any_live_influence", False))
        and safe_float(summary.get("max_promotion_score"), 0.0) >= SAFE_PROMOTION_SCORE
    )


def _apply_status_and_gates(proposals: List[Dict[str, Any]], previous: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    promotion_memory = _read_json(SOURCE_PATHS["promotion_gate"], {})
    promotion_gate_passed = _promotion_gate_passed(promotion_memory)
    routed = {name: [] for name in ("needs_backtest", "needs_paper_test", "needs_manual_review", "rejected_low_evidence", "blocked_safety_risk")}

    for proposal in proposals:
        previous_item = previous.get(proposal["proposal_id"], {})
        previous_status = str(previous_item.get("status") or "").upper()
        route = _route(proposal)
        routed[route].append(proposal["proposal_id"])
        proposal["validation_route"] = route
        proposal["source_names"] = _source_names(proposal.get("evidence") or [], str(proposal.get("source") or ""))
        proposal["external_simulated_only_evidence"] = _is_external_simulated_only(proposal)
        proposal["validation_passed"] = bool(previous_item.get("validation_passed", False))
        proposal["paper_test_passed"] = bool(previous_item.get("paper_test_passed", False))
        proposal["safety_gate_passed"] = proposal.get("safety_gate_status") == "APPROVED_FOR_TEST"
        proposal["promotion_gate_passed"] = promotion_gate_passed
        proposal["live_apply_allowed"] = False

        if previous_status in ALLOWED_STATUSES:
            proposal["status"] = previous_status
        else:
            proposal["status"] = _route_status(route)

        if proposal["status"] == "PROMOTED":
            allowed = (
                proposal["validation_passed"]
                and proposal["safety_gate_passed"]
                and promotion_gate_passed
                and (proposal["paper_test_passed"] or not proposal.get("paper_test_required"))
                and not proposal["external_simulated_only_evidence"]
            )
            if not allowed:
                proposal["status"] = "BLOCKED"
                proposal["promotion_block_reason"] = "promotion_gate_requirements_not_met"

        if proposal["status"] not in ALLOWED_STATUSES:
            proposal["status"] = "BLOCKED"

    return {
        "routes": routed,
        "promotion_gate_passed": promotion_gate_passed,
        "promotion_gate_path": str(SOURCE_PATHS["promotion_gate"]).replace("\\", "/"),
    }


def _top_safe_ideas(proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    safe = [
        proposal
        for proposal in proposals
        if proposal.get("status") in {"PROPOSED", "PAPER_TEST", "VALIDATED"}
        and proposal.get("safety_gate_status") != "REJECTED"
        and not proposal.get("external_simulated_only_evidence")
    ]
    return [
        {
            "proposal_id": item.get("proposal_id"),
            "affected_area": item.get("affected_area"),
            "proposed_change": item.get("proposed_change"),
            "validation_route": item.get("validation_route"),
            "status": item.get("status"),
        }
        for item in safe[:5]
    ]


def _status_payload(proposals: List[Dict[str, Any]], routing: Dict[str, Any]) -> Dict[str, Any]:
    blocked = [item for item in proposals if item.get("status") == "BLOCKED"]
    awaiting = [
        item
        for item in proposals
        if item.get("status") in {"PROPOSED", "PAPER_TEST", "VALIDATED"}
        and item.get("status") != "PROMOTED"
    ]
    return {
        "generated_at": now_ist(),
        "status": "SHADOW_ACTIVE",
        "proposals_generated": len(proposals),
        "proposals_blocked": len(blocked),
        "proposals_awaiting_validation": len(awaiting),
        "proposal_count": len(proposals),
        "paper_test_count": sum(1 for item in proposals if item.get("status") == "PAPER_TEST" or item.get("paper_test_required")),
        "blocked_count": len(blocked),
        "promoted_count": sum(1 for item in proposals if item.get("status") == "PROMOTED"),
        "routes": routing.get("routes") or {},
        "safety_status": {
            "mode": "SHADOW_ONLY",
            "promotion_gate_passed": bool(routing.get("promotion_gate_passed")),
            "live_apply_allowed": False,
            "broker_orders": False,
            "telegram_changes": False,
            "scoring_mutation": False,
            "strategy_weight_mutation": False,
            "external_simulated_memory_mixed_with_native_live_memory": False,
        },
        "top_safe_improvement_ideas": _top_safe_ideas(proposals),
        "proposals_path": str(PROPOSALS_PATH).replace("\\", "/"),
        "live_apply_allowed": False,
    }


def generate_self_improvement_proposals(
    proposals_path: Path = PROPOSALS_PATH,
    runtime_status_path: Path = RUNTIME_STATUS_PATH,
) -> Dict[str, Any]:
    sources = _load_sources()
    previous_payload = _read_json(proposals_path, {})
    previous_items = previous_payload.get("proposals") if isinstance(previous_payload, dict) else []
    previous = {
        item.get("proposal_id"): item
        for item in previous_items or []
        if isinstance(item, dict) and item.get("proposal_id")
    }

    proposals = []
    proposals.extend(_from_report_vault(sources.get("report_vault", {})))
    proposals.extend(_from_consciousness(sources.get("consciousness_core", {})))
    proposals.extend(_from_experience_summary(sources.get("experience_intelligence", {})))
    proposals.extend(_from_calibration(sources.get("confidence_calibration", {})))
    proposals.extend(_from_no_trade(sources.get("no_trade_intelligence", {})))
    proposals.extend(_from_backtesting(sources.get("backtesting_validation", {})))
    proposals = _dedupe(proposals)
    routing = _apply_status_and_gates(proposals, previous)

    payload = {
        "generated_at": now_ist(),
        "mode": "SHADOW_ONLY_CONTROLLED_SELF_IMPROVEMENT",
        "schema_version": 1,
        "allowed_statuses": sorted(ALLOWED_STATUSES),
        "validation_routes": routing.get("routes") or {},
        "promotion_requirements": {
            "validation_passed": True,
            "safety_gate_passed": True,
            "paper_test_passed_if_required": True,
            "external_simulated_only_evidence_not_sufficient": True,
            "live_apply_allowed": False,
        },
        "safety": {
            "telegram_changes": False,
            "broker_orders": False,
            "direct_scoring_mutation": False,
            "strategy_weight_mutation": False,
            "live_apply_allowed": False,
            "external_simulated_memory_mixed_with_native_live_memory": False,
        },
        "proposals": proposals,
    }
    status = _status_payload(proposals, routing)
    atomic_write_json(proposals_path, payload)
    atomic_write_json(runtime_status_path, status)
    return {
        "status": status.get("status"),
        "proposal_count": status.get("proposal_count"),
        "paper_test_count": status.get("paper_test_count"),
        "blocked_count": status.get("blocked_count"),
        "promoted_count": status.get("promoted_count"),
        "top_safe_improvement_ideas": status.get("top_safe_improvement_ideas"),
        "proposals_path": str(proposals_path).replace("\\", "/"),
        "runtime_status_path": str(runtime_status_path).replace("\\", "/"),
        "live_apply_allowed": False,
    }


if __name__ == "__main__":
    print(json.dumps(generate_self_improvement_proposals(), indent=2, sort_keys=True))
