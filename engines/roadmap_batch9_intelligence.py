"""
TITAN Roadmap Batch 9 - Phases 63-65 advisory intelligence.

Persistent sidecars for swarm coordination, local federated-readiness, and
advanced research optimization. These engines consume existing TITAN memory,
runtime, and report artifacts only. They never mutate scanners, ranking,
execution, Telegram, broker, Supabase, dashboards, or live order behavior.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_VERSION = "63-65.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 500

PHASE_PATHS = {
    "phase63": {
        "memory": PROJECT_ROOT / "data" / "memory" / "swarm_intelligence_architecture_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "swarm_intelligence_architecture_status.json",
        "report": PROJECT_ROOT / "reports" / "swarm_intelligence_architecture_report.txt",
    },
    "phase64": {
        "memory": PROJECT_ROOT / "data" / "memory" / "federated_intelligence_system_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "federated_intelligence_system_status.json",
        "report": PROJECT_ROOT / "reports" / "federated_intelligence_system_report.txt",
    },
    "phase65": {
        "memory": PROJECT_ROOT / "data" / "memory" / "advanced_optimization_framework_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "advanced_optimization_framework_status.json",
        "report": PROJECT_ROOT / "reports" / "advanced_optimization_framework_report.txt",
    },
}

INPUT_PATHS = {
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "meta_cognition": PROJECT_ROOT / "data" / "memory" / "meta_cognition_engine_state.json",
    "agi_transition": PROJECT_ROOT / "data" / "memory" / "agi_transition_layer_state.json",
    "neuro_symbolic": PROJECT_ROOT / "data" / "memory" / "neuro_symbolic_reasoning_state.json",
    "institutional_coordination": PROJECT_ROOT / "data" / "memory" / "institutional_coordination_intelligence_state.json",
    "knowledge_distillation": PROJECT_ROOT / "data" / "memory" / "knowledge_distillation_engine_state.json",
    "memory_consolidation": PROJECT_ROOT / "data" / "memory_consolidation" / "latest_memory_consolidation_report.json",
    "long_term_market_memory": PROJECT_ROOT / "data" / "memory" / "long_term_market_memory_state.json",
    "meta_learning": PROJECT_ROOT / "data" / "memory" / "meta_learning_state.json",
    "goal_management": PROJECT_ROOT / "data" / "memory" / "autonomous_goal_management_state.json",
    "dynamic_risk": PROJECT_ROOT / "data" / "memory" / "dynamic_risk_intelligence_state.json",
    "strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
    "crowd_psychology": PROJECT_ROOT / "data" / "memory" / "crowd_psychology_state.json",
    "explainable_ai": PROJECT_ROOT / "data" / "memory" / "explainable_ai_engine_state.json",
    "accuracy_validation": PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json",
    "synthetic_market": PROJECT_ROOT / "data" / "memory" / "synthetic_market_simulator_state.json",
    "recursive_reflection": PROJECT_ROOT / "data" / "memory" / "recursive_self_reflection_state.json",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, dict):
            values = [_safe_float(item, 0.0) for item in value.values()]
            return sum(values) / max(len(values), 1) if values else default
        if isinstance(value, list):
            values = [_safe_float(item, 0.0) for item in value]
            return sum(values) / max(len(values), 1) if values else default
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(_safe_float(value, default))
    except Exception:
        return default


def _safe_text(value: Any, default: str = "") -> str:
    try:
        text = str(value if value is not None else default).strip()
        return text if text else default
    except Exception:
        return default


def _score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size == 0 or path.stat().st_size > MAX_FILE_BYTES:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _read_jsonl(path: Path, limit: int = MAX_RECORDS) -> List[Dict[str, Any]]:
    try:
        if not path.exists() or path.stat().st_size > MAX_FILE_BYTES:
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                continue
        return rows
    except Exception:
        return []


def _load_inputs() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    payloads: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, Dict[str, Any]] = {}
    now_ts = datetime.now(timezone.utc).timestamp()
    for name, path in INPUT_PATHS.items():
        if name == "historical_experience_jsonl":
            continue
        payload = _read_json(path)
        payloads[name] = payload
        status = "MISSING"
        age_seconds = None
        try:
            if path.exists():
                age_seconds = round(max(0.0, now_ts - path.stat().st_mtime), 3)
                status = "OK" if payload else "EMPTY_OR_INVALID"
        except Exception:
            status = "STAT_ERROR"
        sources[name] = {
            "path": _relative(path),
            "available": bool(payload),
            "status": status,
            "age_seconds": age_seconds,
        }
    records = _read_jsonl(INPUT_PATHS["historical_experience_jsonl"])
    sources["historical_experience_jsonl"] = {
        "path": _relative(INPUT_PATHS["historical_experience_jsonl"]),
        "available": bool(records),
        "status": "OK" if records else "MISSING_OR_EMPTY",
        "record_count": len(records),
    }
    return payloads, sources, records


def _safety_flags() -> Dict[str, Any]:
    return {
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
        "affects_live_ranking": False,
        "affects_execution": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "supabase_mutation": False,
        "dashboard_mutation": False,
        "scanner_mutation": False,
        "live_order_behavior": False,
        "recommended_live_weight": 0.0,
        "rank_adjustment": 0.0,
    }


def _phase_base(phase: str, previous: Dict[str, Any], sources: Dict[str, Any]) -> Dict[str, Any]:
    paths = PHASE_PATHS[phase]
    now = _now()
    return {
        "version": STATE_VERSION,
        "generated_at": now,
        "first_seen_at": previous.get("first_seen_at") or now,
        "previous_generated_at": previous.get("generated_at"),
        "run_count": _safe_int(previous.get("run_count"), 0) + 1,
        "continued_from_previous_state": bool(previous),
        "previous_run_count": previous.get("run_count", 0),
        "memory_sources": sources,
        "state_path": _relative(paths["memory"]),
        "runtime_status_path": _relative(paths["runtime"]),
        "report_path": _relative(paths["report"]),
        "safety_flags": _safety_flags(),
        **_safety_flags(),
    }


def _payload_score(payload: Dict[str, Any], keys: Iterable[str], default: float = 0.0) -> float:
    for key in keys:
        if key in payload:
            value = _safe_float(payload.get(key), default)
            return value / 100.0 if value > 1.0 else value
    return default


def _row_text(row: Dict[str, Any]) -> str:
    return " ".join(
        _safe_text(row.get(key)).lower()
        for key in (
            "semantic_labels",
            "market_context_label",
            "regime_label",
            "behavioral_pattern_label",
            "failure_reason_label",
            "success_reason_label",
            "reason",
            "strategy_family",
            "setup_type",
            "event_label",
            "macro_event",
        )
    )


def _term_rate(rows: Iterable[Dict[str, Any]], terms: Iterable[str]) -> float:
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        return 0.0
    hits = sum(1 for row in rows if any(term in _row_text(row) for term in terms))
    return hits / max(len(rows), 1)


def _term_counts(rows: Iterable[Dict[str, Any]], terms: Iterable[str]) -> List[Dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        text = _row_text(row)
        for term in terms:
            if term in text:
                counts[term] += 1
    return [{"pattern": term, "count": count} for term, count in counts.most_common(MAX_ITEMS)]


def _market_context(master_input: Dict[str, Any] | None, context: Dict[str, Any] | None) -> Dict[str, Any]:
    ctx = context if isinstance(context, dict) else {}
    master = master_input if isinstance(master_input, dict) else {}
    market_packet = master.get("market") if isinstance(master.get("market"), dict) else {}
    market_data = market_packet.get("data") if isinstance(market_packet.get("data"), dict) else {}
    merged = dict(market_data)
    for key, value in ctx.items():
        merged.setdefault(key, value)
    return merged


def build_swarm_intelligence_architecture(
    previous: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    market = _market_context(master_input, context)
    decisions = final_decisions if isinstance(final_decisions, dict) else {}

    debate = _payload_score(payloads.get("neuro_symbolic", {}), ("reasoning_integrity_score",), 0.3)
    institutional = _payload_score(payloads.get("institutional_coordination", {}), ("institutional_coordination_score",), 0.3)
    meta = _payload_score(payloads.get("meta_cognition", {}), ("reasoning_reliability_score", "confidence_of_reasoning_score"), 0.3)
    explainability = _payload_score(payloads.get("explainable_ai", {}), ("explanation_depth_score",), 0.25)
    genome = _payload_score(payloads.get("strategy_genome", {}), ("family_count", "genome_quality_score"), 0.35)
    risk = _payload_score(payloads.get("dynamic_risk", {}), ("regime_aware_risk_score", "stress_aware_theoretical_sizing_score"), 0.3)
    narrative = _payload_score(payloads.get("market_narrative", {}), ("narrative_persistence_score",), 0.25)
    crowd = _payload_score(payloads.get("crowd_psychology", {}), ("crowd_instability_score", "overconfidence_score"), 0.15)

    role_scores = {
        "strategy_agent": _score(genome * 0.34 + _payload_score(payloads.get("meta_learning", {}), ("priority_count", "learning_velocity_score"), 0.25) * 0.24 + debate * 0.20 + _term_rate(records, ("strategy", "setup", "family", "breakout", "pullback")) * 0.22),
        "risk_agent": _score(risk * 0.38 + _payload_score(payloads.get("accuracy_validation", {}), ("validation_drift_score", "confidence_mismatch_score"), 0.2) * 0.20 + meta * 0.20 + _term_rate(records, ("risk", "drawdown", "loss", "stress")) * 0.22),
        "regime_agent": _score(_payload_score(payloads.get("long_term_market_memory", {}), ("historical_analog_quality_score", "volatility_regime_transition_score"), 0.25) * 0.30 + _payload_score(payloads.get("agi_transition", {}), ("world_model_signal_score",), 0.3) * 0.24 + _term_rate(records, ("regime", "macro", "cycle", "transition")) * 0.28 + institutional * 0.18),
        "narrative_agent": _score(narrative * 0.34 + (1.0 - crowd) * 0.18 + explainability * 0.20 + _term_rate(records, ("narrative", "sentiment", "crowd", "panic", "euphoria")) * 0.28),
        "execution_quality_agent": _score(explainability * 0.22 + _term_rate(records, ("slippage", "entry", "exit", "execution", "timing")) * 0.30 + _payload_score(payloads.get("recursive_reflection", {}), ("missed_opportunity_pattern_score", "reflection_evolution_score"), 0.25) * 0.22 + meta * 0.26),
        "reflection_agent": _score(_payload_score(payloads.get("recursive_reflection", {}), ("reflection_evolution_score", "self_bias_detection_score"), 0.25) * 0.34 + meta * 0.28 + debate * 0.18 + _term_rate(records, ("mistake", "bias", "missed", "uncertain", "contradiction")) * 0.20),
    }
    coordination = _score(sum(role_scores.values()) / max(len(role_scores), 1))
    disagreement = _score(max(role_scores.values()) - min(role_scores.values())) if role_scores else 0.0
    swarm_signal = _score(coordination * 0.42 + institutional * 0.18 + meta * 0.18 + debate * 0.12 + (1.0 - disagreement) * 0.10)

    state = {
        **_phase_base("phase63", previous, sources),
        "phase": "PHASE_63_SWARM_INTELLIGENCE_ARCHITECTURE",
        "status": "OK" if any(payloads.values()) or records or market else "WAITING_FOR_SWARM_INPUTS",
        "connected": True,
        "agent_roles": role_scores,
        "swarm_coordination_score": coordination,
        "agent_disagreement_score": disagreement,
        "specialist_consensus_score": swarm_signal,
        "swarm_memory_signal_count": len(records),
        "coordination_advisory": "SWARM_REVIEW_PRIORITY" if disagreement >= 0.35 else "SWARM_CONSENSUS_STABLE",
        "decision_context_seen": {"final_decision_count": len(decisions.get("ranked") or decisions.get("decisions") or [])},
        "swarm_evidence_terms": _term_counts(records, ("strategy", "risk", "regime", "narrative", "execution", "reflection", "contradiction")),
        "source_consumption": {
            "multi_agent_or_neuro_symbolic_reasoning": bool(payloads.get("neuro_symbolic")),
            "institutional_coordination": bool(payloads.get("institutional_coordination")),
            "meta_cognition": bool(payloads.get("meta_cognition")),
            "explainable_ai": bool(payloads.get("explainable_ai")),
            "strategy_genome": bool(payloads.get("strategy_genome")),
            "dynamic_risk": bool(payloads.get("dynamic_risk")),
            "narrative_or_crowd_intelligence": bool(payloads.get("market_narrative") or payloads.get("crowd_psychology")),
        },
        "feeds": {
            "master_brain": "Specialist consensus is advisory sidecar context only.",
            "institutional_coordination": "Role disagreement can guide future desk coordination research.",
            "meta_cognition": "Swarm disagreement becomes an introspection signal.",
            "optimization_framework": "Role scores are consumed by Phase 65 for research priority allocation.",
            "runtime_observability": "Agent roles and consensus are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "coordination": coordination, "consensus": swarm_signal, "disagreement": disagreement})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_federated_intelligence_system(
    previous: Dict[str, Any] | None = None,
    swarm_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    swarm_state = swarm_state if isinstance(swarm_state, dict) else _read_json(PHASE_PATHS["phase63"]["memory"])
    ctx = context if isinstance(context, dict) else {}

    source_health = sum(1 for payload in payloads.values() if payload) / max(len(payloads), 1)
    node_readiness = _score(source_health * 0.26 + _payload_score(payloads.get("memory_consolidation", {}), ("memory_quality_score",), 0.25) * 0.24 + _payload_score(payloads.get("knowledge_distillation", {}), ("distillation_scores",), 0.3) * 0.20 + _payload_score(swarm_state, ("specialist_consensus_score",), 0.25) * 0.30)
    sync_health = _score(_payload_score(payloads.get("long_term_market_memory", {}), ("historical_analog_quality_score",), 0.25) * 0.25 + _payload_score(payloads.get("meta_learning", {}), ("priority_count", "learning_velocity_score"), 0.2) * 0.18 + min(1.0, len(records) / 250.0) * 0.22 + _payload_score(payloads.get("knowledge_distillation", {}), ("distillation_scores",), 0.25) * 0.20 + source_health * 0.15)
    sharing = _score(_payload_score(payloads.get("knowledge_distillation", {}), ("distillation_scores",), 0.25) * 0.28 + _payload_score(swarm_state, ("swarm_coordination_score",), 0.25) * 0.24 + _payload_score(payloads.get("meta_cognition", {}), ("reasoning_reliability_score",), 0.25) * 0.18 + _term_rate(records, ("principle", "pattern", "lesson", "memory", "distill")) * 0.30)
    compatibility = _score(_payload_score(payloads.get("meta_learning", {}), ("priority_count", "learning_velocity_score"), 0.25) * 0.22 + _payload_score(payloads.get("agi_transition", {}), ("governance_alignment_score", "agi_transition_readiness_score"), 0.25) * 0.22 + node_readiness * 0.24 + sync_health * 0.16 + sharing * 0.16)
    privacy_safety = _score(1.0 - max(_payload_score(payloads.get("dynamic_risk", {}), ("stress_aware_theoretical_sizing_score",), 0.15), _payload_score(swarm_state, ("agent_disagreement_score",), 0.0) * 0.5))
    readiness = _score((node_readiness + sync_health + sharing + compatibility + privacy_safety) / 5.0)

    state = {
        **_phase_base("phase64", previous, sources),
        "phase": "PHASE_64_FEDERATED_INTELLIGENCE_SYSTEM",
        "status": "OK" if swarm_state or any(payloads.values()) or records or ctx else "WAITING_FOR_FEDERATED_INPUTS",
        "connected": True,
        "phase63_consumed": bool(swarm_state),
        "phase63_run_count_seen": swarm_state.get("run_count"),
        "node_readiness_score": node_readiness,
        "memory_synchronization_health_score": sync_health,
        "cross_module_knowledge_sharing_score": sharing,
        "distributed_learning_compatibility_score": compatibility,
        "privacy_safety_constraint_score": privacy_safety,
        "federated_readiness_score": readiness,
        "local_federation_nodes": {
            "memory_node": bool(payloads.get("memory_consolidation") or payloads.get("long_term_market_memory")),
            "distillation_node": bool(payloads.get("knowledge_distillation")),
            "meta_learning_node": bool(payloads.get("meta_learning")),
            "swarm_node": bool(swarm_state),
            "replay_research_node": bool(records),
        },
        "federation_advisory": "LOCAL_READY_FOR_FUTURE_PLANNING" if readiness >= 0.55 else "CONTINUE_LOCAL_ALIGNMENT",
        "source_consumption": {
            "phase63_swarm": bool(swarm_state),
            "memory_consolidation": bool(payloads.get("memory_consolidation")),
            "long_term_memory": bool(payloads.get("long_term_market_memory")),
            "knowledge_distillation": bool(payloads.get("knowledge_distillation")),
            "meta_learning": bool(payloads.get("meta_learning")),
            "replay_research_memory": bool(records),
        },
        "feeds": {
            "master_brain": "Federated readiness is infrastructure planning context only.",
            "optimization_framework": "Readiness and sync health are consumed by Phase 65.",
            "future_infrastructure_planning": "Local node readiness is persisted without networking.",
            "runtime_observability": "Readiness and safety constraints are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "readiness": readiness, "sync_health": sync_health, "sharing": sharing})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_advanced_optimization_framework(
    previous: Dict[str, Any] | None = None,
    swarm_state: Dict[str, Any] | None = None,
    federated_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    swarm_state = swarm_state if isinstance(swarm_state, dict) else _read_json(PHASE_PATHS["phase63"]["memory"])
    federated_state = federated_state if isinstance(federated_state, dict) else _read_json(PHASE_PATHS["phase64"]["memory"])
    ctx = context if isinstance(context, dict) else {}

    swarm = _payload_score(swarm_state, ("specialist_consensus_score",), 0.25)
    disagreement = _payload_score(swarm_state, ("agent_disagreement_score",), 0.0)
    federation = _payload_score(federated_state, ("federated_readiness_score",), 0.25)
    sync = _payload_score(federated_state, ("memory_synchronization_health_score",), 0.25)
    meta_learning = _payload_score(payloads.get("meta_learning", {}), ("priority_count", "learning_velocity_score"), 0.25)
    goals = _payload_score(payloads.get("goal_management", {}), ("goal_priority_scores",), 0.25)
    risk = _payload_score(payloads.get("dynamic_risk", {}), ("regime_aware_risk_score", "stress_aware_theoretical_sizing_score"), 0.25)
    distillation = _payload_score(payloads.get("knowledge_distillation", {}), ("distillation_scores",), 0.25)
    agi = _payload_score(payloads.get("agi_transition", {}), ("agi_transition_readiness_score", "improvement_planning_shadow_score"), 0.25)

    research_priority = _score(meta_learning * 0.22 + goals * 0.18 + (1.0 - disagreement) * 0.16 + _term_rate(records, ("uncertain", "missed", "failed", "contradiction")) * 0.24 + agi * 0.20)
    memory_compression_priority = _score((1.0 - sync) * 0.32 + distillation * 0.24 + _payload_score(payloads.get("memory_consolidation", {}), ("memory_quality_score",), 0.25) * 0.18 + _term_rate(records, ("repeat", "duplicate", "principle", "pattern")) * 0.26)
    strategy_sandbox_priority = _score(_payload_score(payloads.get("strategy_genome", {}), ("family_count", "genome_quality_score"), 0.25) * 0.25 + swarm * 0.18 + federation * 0.14 + _term_rate(records, ("strategy", "setup", "sandbox", "mutation")) * 0.25 + goals * 0.18)
    risk_hypothesis_priority = _score(risk * 0.28 + disagreement * 0.22 + _payload_score(payloads.get("accuracy_validation", {}), ("validation_drift_score", "confidence_mismatch_score"), 0.2) * 0.20 + _term_rate(records, ("risk", "drawdown", "loss", "stress", "volatility")) * 0.30)
    resource_allocation_hint_score = _score(federation * 0.24 + swarm * 0.22 + goals * 0.18 + distillation * 0.18 + (1.0 - risk) * 0.18)
    scenario_optimization_score = _score(_payload_score(payloads.get("synthetic_market", {}), ("synthetic_market_stress_index", "regime_stress_score"), 0.25) * 0.24 + _term_rate(records, ("scenario", "regime", "macro", "shock", "stress")) * 0.28 + agi * 0.18 + federation * 0.14 + swarm * 0.16)
    constraint_aware_planning_score = _score(_payload_score(payloads.get("meta_cognition", {}), ("supervision_need_score", "reasoning_reliability_score"), 0.25) * 0.18 + _payload_score(payloads.get("agi_transition", {}), ("governance_alignment_score",), 0.25) * 0.24 + _payload_score(federated_state, ("privacy_safety_constraint_score",), 0.5) * 0.24 + (1.0 - risk) * 0.18 + distillation * 0.16)
    optimization_readiness = _score((research_priority + strategy_sandbox_priority + resource_allocation_hint_score + scenario_optimization_score + constraint_aware_planning_score + (1.0 - memory_compression_priority * 0.4) + (1.0 - risk_hypothesis_priority * 0.3)) / 7.0)

    state = {
        **_phase_base("phase65", previous, sources),
        "phase": "PHASE_65_ADVANCED_OPTIMIZATION_FRAMEWORK",
        "status": "OK" if swarm_state or federated_state or any(payloads.values()) or records or ctx else "WAITING_FOR_OPTIMIZATION_INPUTS",
        "connected": True,
        "phase63_consumed": bool(swarm_state),
        "phase63_run_count_seen": swarm_state.get("run_count"),
        "phase64_consumed": bool(federated_state),
        "phase64_run_count_seen": federated_state.get("run_count"),
        "research_priority_optimization_score": research_priority,
        "memory_compression_priority_score": memory_compression_priority,
        "strategy_sandbox_priority_score": strategy_sandbox_priority,
        "risk_hypothesis_priority_score": risk_hypothesis_priority,
        "resource_allocation_hint_score": resource_allocation_hint_score,
        "scenario_optimization_score": scenario_optimization_score,
        "constraint_aware_planning_score": constraint_aware_planning_score,
        "optimization_readiness_score": optimization_readiness,
        "optimization_plan": [
            "prioritize_replay_cases_with_uncertainty_or_contradiction",
            "compress_repeated_memory_patterns_before_promotion_review",
            "allocate_sandbox_attention_to_strategy_families_with_swarm_support",
            "keep_all_outputs_research_shadow_only",
        ],
        "source_consumption": {
            "phase63_swarm": bool(swarm_state),
            "phase64_federated_readiness": bool(federated_state),
            "meta_learning": bool(payloads.get("meta_learning")),
            "goal_management": bool(payloads.get("goal_management")),
            "dynamic_risk": bool(payloads.get("dynamic_risk")),
            "knowledge_distillation": bool(payloads.get("knowledge_distillation")),
            "agi_transition": bool(payloads.get("agi_transition")),
        },
        "feeds": {
            "master_brain": "Optimization plan is advisory sidecar context only.",
            "future_roadmap_planning": "Priorities identify research and infrastructure planning focus.",
            "evolution_systems": "Sandbox priority is shadow-only and cannot promote live behavior.",
            "runtime_observability": "Optimization scores and cross-phase consumption are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "readiness": optimization_readiness, "research_priority": research_priority, "scenario": scenario_optimization_score})
    state["history"] = history[-MAX_HISTORY:]
    return state


def _runtime_status(state: Dict[str, Any], phase_key: str, extra_fields: Iterable[str]) -> Dict[str, Any]:
    status = {
        "phase": state.get("phase"),
        "status": state.get("status"),
        "connected": True,
        "generated_at": state.get("generated_at"),
        "run_count": state.get("run_count"),
        "continued_from_previous_state": state.get("continued_from_previous_state"),
        "state_path": state.get("state_path"),
        "report_path": state.get("report_path"),
        "safety_flags": state.get("safety_flags"),
        "pyramid_placement": f"master_controller_{phase_key}_sidecar",
        **_safety_flags(),
    }
    for field in extra_fields:
        if field in state:
            status[field] = state.get(field)
    return status


def _render_report(title: str, state: Dict[str, Any], fields: Iterable[str]) -> str:
    lines = [
        title,
        "=" * len(title),
        f"Updated: {state.get('generated_at')}",
        f"Status: {state.get('status')} | Connected: {state.get('connected')}",
        f"Run count: {state.get('run_count')} | Continued: {state.get('continued_from_previous_state')}",
        "",
        "Safety",
        "- advisory_only=true research_only=true shadow_mode=true",
        "- affects_live_ranking=false affects_execution=false broker_mutation=false telegram_mutation=false supabase_mutation=false",
        "- live_order_behavior=false recommended_live_weight=0.0 rank_adjustment=0.0",
        "",
        "Values",
    ]
    for field in fields:
        lines.append(f"- {field}: {state.get(field)}")
    lines.extend(["", "Cross-Phase Consumption"])
    for field in ("phase63_consumed", "phase63_run_count_seen", "phase64_consumed", "phase64_run_count_seen"):
        if field in state:
            lines.append(f"- {field}: {state.get(field)}")
    lines.extend(["", "Memory Sources"])
    for name, item in sorted((state.get("memory_sources") or {}).items()):
        lines.append(f"- {name}: available={item.get('available')}, status={item.get('status')}, path={item.get('path')}")
    return "\n".join(lines) + "\n"


def _persist(
    phase_key: str,
    state: Dict[str, Any],
    report_title: str,
    report_fields: Iterable[str],
    status_fields: Iterable[str],
    write_files: bool,
) -> Dict[str, Any]:
    paths = PHASE_PATHS[phase_key]
    runtime = _runtime_status(state, phase_key, status_fields)
    state["runtime_status"] = runtime
    if write_files:
        _write_json(paths["memory"], state)
        _write_json(paths["runtime"], runtime)
        paths["report"].parent.mkdir(parents=True, exist_ok=True)
        paths["report"].write_text(_render_report(report_title, state, report_fields), encoding="utf-8")
    return state


def run_swarm_intelligence_architecture(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase63"]["memory"])
    state = build_swarm_intelligence_architecture(previous=previous, master_input=master_input, context=context, final_decisions=final_decisions)
    fields = ("agent_roles", "swarm_coordination_score", "agent_disagreement_score", "specialist_consensus_score", "swarm_memory_signal_count", "coordination_advisory", "source_consumption")
    return _persist("phase63", state, "TITAN Phase 63 Swarm Intelligence Architecture Report", fields, fields, write_files)


def run_federated_intelligence_system(
    swarm_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase64"]["memory"])
    state = build_federated_intelligence_system(previous=previous, swarm_state=swarm_state, context=context)
    fields = ("phase63_consumed", "phase63_run_count_seen", "node_readiness_score", "memory_synchronization_health_score", "cross_module_knowledge_sharing_score", "distributed_learning_compatibility_score", "privacy_safety_constraint_score", "federated_readiness_score", "local_federation_nodes", "federation_advisory", "source_consumption")
    return _persist("phase64", state, "TITAN Phase 64 Federated Intelligence System Report", fields, fields, write_files)


def run_advanced_optimization_framework(
    swarm_state: Dict[str, Any] | None = None,
    federated_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase65"]["memory"])
    state = build_advanced_optimization_framework(previous=previous, swarm_state=swarm_state, federated_state=federated_state, context=context)
    fields = ("phase63_consumed", "phase64_consumed", "phase63_run_count_seen", "phase64_run_count_seen", "research_priority_optimization_score", "memory_compression_priority_score", "strategy_sandbox_priority_score", "risk_hypothesis_priority_score", "resource_allocation_hint_score", "scenario_optimization_score", "constraint_aware_planning_score", "optimization_readiness_score", "optimization_plan", "source_consumption")
    return _persist("phase65", state, "TITAN Phase 65 Advanced Optimization Framework Report", fields, fields, write_files)


def run_roadmap_batch9_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase63 = run_swarm_intelligence_architecture(master_input=master_input, context=context, final_decisions=final_decisions, write_files=write_files)
    phase64 = run_federated_intelligence_system(swarm_state=phase63, context=context, write_files=write_files)
    phase65 = run_advanced_optimization_framework(swarm_state=phase63, federated_state=phase64, context=context, write_files=write_files)
    return {
        "phase63_swarm_intelligence_architecture": phase63,
        "phase64_federated_intelligence_system": phase64,
        "phase65_advanced_optimization_framework": phase65,
        **_safety_flags(),
    }


if __name__ == "__main__":
    result = run_roadmap_batch9_intelligence(write_files=True)
    print("TITAN Roadmap Batch 9 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
