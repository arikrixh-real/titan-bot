"""
TITAN Roadmap Batch 8 - Phases 60-62 advisory intelligence.

Persistent sidecars for AGI transition planning, neuro-symbolic reasoning, and
meta-cognition. These engines consume existing TITAN memory/runtime/report
artifacts only. They never mutate scanners, ranking, execution, Telegram,
broker, Supabase, dashboards, code, or live order behavior.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_VERSION = "60-62.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 500

PHASE_PATHS = {
    "phase60": {
        "memory": PROJECT_ROOT / "data" / "memory" / "agi_transition_layer_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "agi_transition_layer_status.json",
        "report": PROJECT_ROOT / "reports" / "agi_transition_layer_report.txt",
    },
    "phase61": {
        "memory": PROJECT_ROOT / "data" / "memory" / "neuro_symbolic_reasoning_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "neuro_symbolic_reasoning_status.json",
        "report": PROJECT_ROOT / "reports" / "neuro_symbolic_reasoning_report.txt",
    },
    "phase62": {
        "memory": PROJECT_ROOT / "data" / "memory" / "meta_cognition_engine_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "meta_cognition_engine_status.json",
        "report": PROJECT_ROOT / "reports" / "meta_cognition_engine_report.txt",
    },
}

INPUT_PATHS = {
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "hierarchical_brain": PROJECT_ROOT / "data" / "memory" / "hierarchical_brain_architecture_state.json",
    "autonomous_goal_management": PROJECT_ROOT / "data" / "memory" / "autonomous_goal_management_state.json",
    "knowledge_distillation": PROJECT_ROOT / "data" / "memory" / "knowledge_distillation_engine_state.json",
    "recursive_self_reflection": PROJECT_ROOT / "data" / "memory" / "recursive_self_reflection_state.json",
    "long_term_market_memory": PROJECT_ROOT / "data" / "memory" / "long_term_market_memory_state.json",
    "institutional_coordination": PROJECT_ROOT / "data" / "memory" / "institutional_coordination_intelligence_state.json",
    "explainable_ai": PROJECT_ROOT / "data" / "memory" / "explainable_ai_engine_state.json",
    "causal_engine": PROJECT_ROOT / "data" / "memory" / "causal_market_reasoning_state.json",
    "meta_regime": PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json",
    "market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
    "crowd_psychology": PROJECT_ROOT / "data" / "memory" / "crowd_psychology_state.json",
    "confidence_calibration": PROJECT_ROOT / "data" / "confidence_calibration" / "latest_confidence_calibration_report.json",
    "accuracy_validation": PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json",
    "multi_horizon": PROJECT_ROOT / "data" / "memory" / "multi_horizon_intelligence_state.json",
    "dynamic_risk": PROJECT_ROOT / "data" / "memory" / "dynamic_risk_intelligence_state.json",
    "capital_flow": PROJECT_ROOT / "data" / "memory" / "capital_flow_intelligence_state.json",
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


def build_agi_transition_layer(
    previous: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    market = _market_context(master_input, context)
    decisions = final_decisions if isinstance(final_decisions, dict) else {}

    hierarchy = payloads.get("hierarchical_brain", {})
    goals = payloads.get("autonomous_goal_management", {})
    distillation = payloads.get("knowledge_distillation", {})
    reflection = payloads.get("recursive_self_reflection", {})
    long_memory = payloads.get("long_term_market_memory", {})
    institutional = payloads.get("institutional_coordination", {})
    meta_regime = payloads.get("meta_regime", {})
    risk = payloads.get("dynamic_risk", {})

    world_model = _score(
        _payload_score(long_memory, ("historical_analog_quality_score", "crisis_memory_score", "rare_event_archive_score")) * 0.28
        + _payload_score(meta_regime, ("global_meta_regime_risk_score", "transition_risk_score"), 0.3) * 0.18
        + _payload_score(payloads.get("capital_flow", {}), ("capital_migration_score", "institutional_flow_proxy_score"), 0.2) * 0.16
        + _term_rate(records, ("regime", "macro", "cycle", "transition", "liquidity")) * 0.20
        + min(1.0, len(records) / 250.0) * 0.18
    )
    autonomy_readiness = _score(
        _payload_score(hierarchy, ("hierarchy_balance_score", "supervisor_layer_score", "arbitration_layer_score"), 0.3) * 0.30
        + _payload_score(goals, ("goal_priority_scores",), 0.4) * 0.18
        + _payload_score(distillation, ("distillation_scores",), 0.3) * 0.18
        + _payload_score(reflection, ("reflection_evolution_score",), 0.2) * 0.18
        + (1.0 - _payload_score(risk, ("stress_aware_theoretical_sizing_score",), 0.5)) * 0.16
    )
    improvement_planning = _score(
        _payload_score(goals, ("goal_priority_scores",), 0.3) * 0.24
        + _payload_score(reflection, ("repeated_reasoning_mistake_score", "recurring_failure_chain_score"), 0.0) * 0.22
        + _payload_score(distillation, ("distillation_scores",), 0.3) * 0.18
        + _payload_score(payloads.get("accuracy_validation", {}), ("validation_drift_score", "confidence_mismatch_score"), 0.0) * 0.18
        + _term_rate(records, ("failed", "mistake", "missed", "bias", "overconfidence")) * 0.18
    )
    governance_alignment = _score(
        _payload_score(hierarchy, ("supervisor_layer_score", "arbitration_layer_score"), 0.4) * 0.30
        + _payload_score(institutional, ("institutional_coordination_score",), 0.3) * 0.22
        + (1.0 - _payload_score(reflection, ("self_bias_detection_score", "contradiction_persistence_score"), 0.4)) * 0.22
        + (1.0 - _payload_score(risk, ("stress_aware_theoretical_sizing_score",), 0.5)) * 0.26
    )
    agi_transition = _score((world_model + autonomy_readiness + improvement_planning + governance_alignment) / 4.0)

    state = {
        **_phase_base("phase60", previous, sources),
        "phase": "PHASE_60_AGI_TRANSITION_LAYER",
        "status": "OK" if any(payloads.values()) or records or market else "WAITING_FOR_AGI_TRANSITION_INPUTS",
        "connected": True,
        "world_model_signal_score": world_model,
        "autonomy_readiness_shadow_score": autonomy_readiness,
        "improvement_planning_shadow_score": improvement_planning,
        "governance_alignment_score": governance_alignment,
        "agi_transition_readiness_score": agi_transition,
        "autonomous_improvement_plan": [
            "study_high_contradiction_cases_in_replay_only",
            "distill_recurring_failure_patterns_before_any_promotion",
            "route_uncertain_context_to_supervision_review",
        ],
        "decision_context_seen": {"final_decision_count": len(decisions.get("ranked") or decisions.get("decisions") or [])},
        "world_model_terms": _term_counts(records, ("regime", "macro", "cycle", "transition", "liquidity", "risk_off")),
        "source_consumption": {
            "hierarchical_brain": bool(hierarchy),
            "autonomous_goal_management": bool(goals),
            "knowledge_distillation": bool(distillation),
            "recursive_self_reflection": bool(reflection),
            "long_term_market_memory": bool(long_memory),
            "institutional_coordination": bool(institutional),
            "replay_research_memory": bool(records),
        },
        "feeds": {
            "master_brain": "Unified cognition summary is advisory sidecar reporting only.",
            "consciousness_meta_layers": "World-model and governance scores feed future self-supervision.",
            "memory": "Progressive AGI transition history is persisted under data/memory.",
            "evolution": "Improvement plan remains shadow/research-only and cannot mutate code.",
            "runtime_observability": "Readiness and safety values are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "world_model": world_model, "readiness": agi_transition, "governance": governance_alignment})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_neuro_symbolic_reasoning_engine(
    previous: Dict[str, Any] | None = None,
    agi_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    agi_state = agi_state if isinstance(agi_state, dict) else _read_json(PHASE_PATHS["phase60"]["memory"])
    market = _market_context(master_input, context)
    decisions = final_decisions if isinstance(final_decisions, dict) else {}

    explainable = payloads.get("explainable_ai", {})
    reflection = payloads.get("recursive_self_reflection", {})
    distillation = payloads.get("knowledge_distillation", {})
    meta_regime = payloads.get("meta_regime", {})
    narrative = payloads.get("market_narrative", {})
    crowd = payloads.get("crowd_psychology", {})
    risk = payloads.get("dynamic_risk", {})

    contradiction = _score(
        _payload_score(explainable, ("contradiction_score",), 0.0) * 0.30
        + _payload_score(reflection, ("contradiction_persistence_score", "confidence_mismatch_score"), 0.0) * 0.26
        + _payload_score(narrative, ("narrative_contradiction_score",), 0.0) * 0.18
        + _term_rate(records, ("contradiction", "conflict", "mismatch", "disagreement")) * 0.26
    )
    causal_consistency = _score(
        (1.0 - contradiction) * 0.28
        + _payload_score(payloads.get("causal_engine", {}), ("causal_consistency_score", "causal_strength_score"), 0.35) * 0.26
        + _payload_score(meta_regime, ("transition_risk_score",), 0.4) * 0.12
        + _payload_score(agi_state, ("world_model_signal_score",), 0.3) * 0.22
        + (1.0 - _payload_score(risk, ("regime_aware_risk_score",), 0.4)) * 0.12
    )
    symbolic_abstraction = _score(
        _payload_score(distillation, ("distillation_scores",), 0.3) * 0.28
        + _payload_score(explainable, ("explanation_depth_score",), 0.3) * 0.22
        + _payload_score(agi_state, ("agi_transition_readiness_score",), 0.2) * 0.20
        + min(1.0, len(_term_counts(records, ("trap", "trend", "macro", "liquidity", "risk_off", "cycle"))) / 6.0) * 0.30
    )
    rule_coverage = _score(
        _payload_score(payloads.get("hierarchical_brain", {}), ("arbitration_layer_score", "supervisor_layer_score"), 0.3) * 0.22
        + _payload_score(payloads.get("autonomous_goal_management", {}), ("goal_priority_scores",), 0.3) * 0.18
        + symbolic_abstraction * 0.30
        + causal_consistency * 0.30
    )
    neuro_symbolic_conflict = _score(
        max(contradiction, _payload_score(crowd, ("crowd_instability_score", "overconfidence_score"), 0.0))
        * 0.44
        + (1.0 - causal_consistency) * 0.30
        + _payload_score(risk, ("stress_aware_theoretical_sizing_score",), 0.0) * 0.26
    )
    reasoning_integrity = _score((causal_consistency + symbolic_abstraction + rule_coverage + (1.0 - neuro_symbolic_conflict)) / 4.0)

    state = {
        **_phase_base("phase61", previous, sources),
        "phase": "PHASE_61_NEURO_SYMBOLIC_REASONING_ENGINE",
        "status": "OK" if agi_state or any(payloads.values()) or records or market else "WAITING_FOR_NEURO_SYMBOLIC_INPUTS",
        "connected": True,
        "phase60_consumed": bool(agi_state),
        "phase60_run_count_seen": agi_state.get("run_count"),
        "contradiction_check_score": contradiction,
        "causal_consistency_score": causal_consistency,
        "symbolic_abstraction_score": symbolic_abstraction,
        "logic_rule_coverage_score": rule_coverage,
        "neuro_symbolic_conflict_score": neuro_symbolic_conflict,
        "reasoning_integrity_score": reasoning_integrity,
        "symbolic_rules": [
            "high_contradiction_requires_supervision_review",
            "high_stress_plus_low_causal_consistency_blocks_promotion_research",
            "symbolic_abstraction_must_be_supported_by_replay_or_distillation",
        ],
        "decision_context_seen": {"final_decision_count": len(decisions.get("ranked") or decisions.get("decisions") or [])},
        "symbolic_abstractions": _term_counts(records, ("trap", "trend", "macro", "liquidity", "risk_off", "transition", "cycle")),
        "source_consumption": {
            "phase60_agi_transition": bool(agi_state),
            "explainability": bool(explainable),
            "causal_engine": bool(payloads.get("causal_engine")),
            "knowledge_distillation": bool(distillation),
            "recursive_reflection": bool(reflection),
            "meta_regime": bool(meta_regime),
            "narrative_or_crowd_intelligence": bool(narrative or crowd),
        },
        "feeds": {
            "phase62_meta_cognition": "Reasoning integrity and conflict are consumed by Phase 62.",
            "master_brain": "Neuro-symbolic report is advisory sidecar context only.",
            "reflection": "Contradiction and rule failures feed future reflection.",
            "knowledge_distillation": "Stable symbolic abstractions are distillation candidates.",
            "research_replay": "Rules identify replay cases for future research only.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "integrity": reasoning_integrity, "contradiction": contradiction, "conflict": neuro_symbolic_conflict})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_meta_cognition_engine(
    previous: Dict[str, Any] | None = None,
    agi_state: Dict[str, Any] | None = None,
    neuro_symbolic_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    agi_state = agi_state if isinstance(agi_state, dict) else _read_json(PHASE_PATHS["phase60"]["memory"])
    neuro_symbolic_state = neuro_symbolic_state if isinstance(neuro_symbolic_state, dict) else _read_json(PHASE_PATHS["phase61"]["memory"])
    ctx = context if isinstance(context, dict) else {}

    reflection = payloads.get("recursive_self_reflection", {})
    confidence = payloads.get("confidence_calibration", {})
    explainable = payloads.get("explainable_ai", {})
    goals = payloads.get("autonomous_goal_management", {})
    hierarchy = payloads.get("hierarchical_brain", {})
    accuracy = payloads.get("accuracy_validation", {})

    uncertainty = _score(
        (1.0 - _payload_score(confidence, ("calibrated_confidence_score", "confidence_score"), 0.5)) * 0.28
        + _payload_score(accuracy, ("validation_drift_score", "confidence_mismatch_score"), 0.0) * 0.24
        + _payload_score(neuro_symbolic_state, ("neuro_symbolic_conflict_score", "contradiction_check_score"), 0.0) * 0.24
        + _term_rate(records, ("uncertain", "hesitation", "mismatch", "failed", "missed")) * 0.24
    )
    self_doubt = _score(
        _payload_score(reflection, ("self_bias_detection_score", "repeated_reasoning_mistake_score"), 0.0) * 0.26
        + uncertainty * 0.24
        + _payload_score(agi_state, ("improvement_planning_shadow_score",), 0.2) * 0.18
        + (1.0 - _payload_score(neuro_symbolic_state, ("reasoning_integrity_score",), 0.4)) * 0.32
    )
    cognitive_conflict = _score(
        _payload_score(neuro_symbolic_state, ("neuro_symbolic_conflict_score",), 0.0) * 0.36
        + _payload_score(explainable, ("contradiction_score",), 0.0) * 0.24
        + _payload_score(reflection, ("contradiction_persistence_score",), 0.0) * 0.22
        + _payload_score(payloads.get("multi_horizon", {}), ("timeframe_conflict_score",), 0.0) * 0.18
    )
    confidence_of_reasoning = _score(
        _payload_score(neuro_symbolic_state, ("reasoning_integrity_score",), 0.3) * 0.30
        + _payload_score(agi_state, ("governance_alignment_score", "agi_transition_readiness_score"), 0.3) * 0.22
        + _payload_score(hierarchy, ("supervisor_layer_score", "hierarchy_balance_score"), 0.3) * 0.18
        + (1.0 - max(uncertainty, cognitive_conflict)) * 0.30
    )
    reliability = _score(
        confidence_of_reasoning * 0.34
        + _payload_score(reflection, ("reflection_evolution_score",), 0.2) * 0.18
        + _payload_score(goals, ("goal_priority_scores",), 0.3) * 0.12
        + (1.0 - self_doubt) * 0.18
        + (1.0 - _payload_score(accuracy, ("validation_drift_score",), 0.0)) * 0.18
    )
    supervision_need = _score(max(uncertainty, self_doubt, cognitive_conflict, 1.0 - reliability))

    state = {
        **_phase_base("phase62", previous, sources),
        "phase": "PHASE_62_META_COGNITION_ENGINE",
        "status": "OK" if agi_state or neuro_symbolic_state or any(payloads.values()) or records or ctx else "WAITING_FOR_META_COGNITION_INPUTS",
        "connected": True,
        "phase60_consumed": bool(agi_state),
        "phase60_run_count_seen": agi_state.get("run_count"),
        "phase61_consumed": bool(neuro_symbolic_state),
        "phase61_run_count_seen": neuro_symbolic_state.get("run_count"),
        "reasoning_reliability_score": reliability,
        "self_doubt_score": self_doubt,
        "uncertainty_introspection_score": uncertainty,
        "cognitive_conflict_score": cognitive_conflict,
        "confidence_of_reasoning_score": confidence_of_reasoning,
        "supervision_need_score": supervision_need,
        "meta_cognition_advisory": "REQUIRE_SHADOW_SUPERVISION_REVIEW" if supervision_need >= 0.6 else "NORMAL_SHADOW_REASONING_MONITOR",
        "source_consumption": {
            "phase60_agi_transition": bool(agi_state),
            "phase61_neuro_symbolic": bool(neuro_symbolic_state),
            "explainability": bool(explainable),
            "confidence_calibration": bool(confidence),
            "recursive_reflection": bool(reflection),
            "goal_management": bool(goals),
            "hierarchy_arbitration": bool(hierarchy),
        },
        "feeds": {
            "master_brain": "Reasoning-quality proxy is advisory sidecar context only.",
            "consciousness_meta_layers": "Self-doubt, uncertainty, and conflict support meta reasoning.",
            "future_autonomous_supervision": "Supervision need is persisted for later governance review.",
            "reflection": "Reliability and conflict history can seed recursive reflection.",
            "runtime_observability": "Meta-cognition scores are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "reliability": reliability, "self_doubt": self_doubt, "supervision_need": supervision_need})
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
    for field in ("phase60_consumed", "phase60_run_count_seen", "phase61_consumed", "phase61_run_count_seen"):
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


def run_agi_transition_layer(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase60"]["memory"])
    state = build_agi_transition_layer(previous=previous, master_input=master_input, context=context, final_decisions=final_decisions)
    fields = ("world_model_signal_score", "autonomy_readiness_shadow_score", "improvement_planning_shadow_score", "governance_alignment_score", "agi_transition_readiness_score", "autonomous_improvement_plan", "source_consumption")
    return _persist("phase60", state, "TITAN Phase 60 AGI Transition Layer Report", fields, fields, write_files)


def run_neuro_symbolic_reasoning_engine(
    agi_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase61"]["memory"])
    state = build_neuro_symbolic_reasoning_engine(previous=previous, agi_state=agi_state, master_input=master_input, context=context, final_decisions=final_decisions)
    fields = ("phase60_consumed", "phase60_run_count_seen", "contradiction_check_score", "causal_consistency_score", "symbolic_abstraction_score", "logic_rule_coverage_score", "neuro_symbolic_conflict_score", "reasoning_integrity_score", "symbolic_rules", "source_consumption")
    return _persist("phase61", state, "TITAN Phase 61 Neuro-Symbolic Reasoning Report", fields, fields, write_files)


def run_meta_cognition_engine(
    agi_state: Dict[str, Any] | None = None,
    neuro_symbolic_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase62"]["memory"])
    state = build_meta_cognition_engine(previous=previous, agi_state=agi_state, neuro_symbolic_state=neuro_symbolic_state, context=context)
    fields = ("phase60_consumed", "phase61_consumed", "phase60_run_count_seen", "phase61_run_count_seen", "reasoning_reliability_score", "self_doubt_score", "uncertainty_introspection_score", "cognitive_conflict_score", "confidence_of_reasoning_score", "supervision_need_score", "meta_cognition_advisory", "source_consumption")
    return _persist("phase62", state, "TITAN Phase 62 Meta-Cognition Engine Report", fields, fields, write_files)


def run_roadmap_batch8_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase60 = run_agi_transition_layer(master_input=master_input, context=context, final_decisions=final_decisions, write_files=write_files)
    phase61 = run_neuro_symbolic_reasoning_engine(agi_state=phase60, master_input=master_input, context=context, final_decisions=final_decisions, write_files=write_files)
    phase62 = run_meta_cognition_engine(agi_state=phase60, neuro_symbolic_state=phase61, context=context, write_files=write_files)
    return {
        "phase60_agi_transition_layer": phase60,
        "phase61_neuro_symbolic_reasoning_engine": phase61,
        "phase62_meta_cognition_engine": phase62,
        **_safety_flags(),
    }


if __name__ == "__main__":
    result = run_roadmap_batch8_intelligence(write_files=True)
    print("TITAN Roadmap Batch 8 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
