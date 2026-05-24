"""
TITAN Roadmap Batch 10 - Phases 66-68 advisory intelligence.

Persistent sidecars for unified strategy research lab coordination, evolving
synthetic market worlds, and global macro mesh awareness. These layers consume
existing TITAN memory/runtime/report artifacts only. They never mutate scanners,
ranking, execution, Telegram, broker, Supabase, dashboards, or live order
behavior.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_VERSION = "66-68.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 500

PHASE_PATHS = {
    "phase66": {
        "memory": PROJECT_ROOT / "data" / "memory" / "autonomous_strategy_research_lab_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "autonomous_strategy_research_lab_status.json",
        "report": PROJECT_ROOT / "reports" / "autonomous_strategy_research_lab_report.txt",
    },
    "phase67": {
        "memory": PROJECT_ROOT / "data" / "memory" / "synthetic_market_evolution_engine_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "synthetic_market_evolution_engine_status.json",
        "report": PROJECT_ROOT / "reports" / "synthetic_market_evolution_engine_report.txt",
    },
    "phase68": {
        "memory": PROJECT_ROOT / "data" / "memory" / "global_macro_intelligence_mesh_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "global_macro_intelligence_mesh_status.json",
        "report": PROJECT_ROOT / "reports" / "global_macro_intelligence_mesh_report.txt",
    },
}

INPUT_PATHS = {
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "meta_learning": PROJECT_ROOT / "data" / "memory" / "meta_learning_state.json",
    "autonomous_research": PROJECT_ROOT / "data" / "research" / "autonomous_research_report.json",
    "backtesting_validation": PROJECT_ROOT / "data" / "research" / "backtesting_validation_report.json",
    "advanced_optimization": PROJECT_ROOT / "data" / "memory" / "advanced_optimization_framework_state.json",
    "swarm_intelligence": PROJECT_ROOT / "data" / "memory" / "swarm_intelligence_architecture_state.json",
    "recursive_reflection": PROJECT_ROOT / "data" / "memory" / "recursive_self_reflection_state.json",
    "meta_cognition": PROJECT_ROOT / "data" / "memory" / "meta_cognition_engine_state.json",
    "knowledge_distillation": PROJECT_ROOT / "data" / "memory" / "knowledge_distillation_engine_state.json",
    "synthetic_market": PROJECT_ROOT / "data" / "memory" / "synthetic_market_simulator_state.json",
    "adversarial_intelligence": PROJECT_ROOT / "data" / "memory" / "adversarial_intelligence_state.json",
    "dynamic_risk": PROJECT_ROOT / "data" / "memory" / "dynamic_risk_intelligence_state.json",
    "multi_horizon": PROJECT_ROOT / "data" / "memory" / "multi_horizon_intelligence_state.json",
    "scenario_simulation": PROJECT_ROOT / "data" / "scenario_simulation" / "latest_scenario_simulation_report.json",
    "meta_regime": PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json",
    "capital_flow": PROJECT_ROOT / "data" / "memory" / "capital_flow_intelligence_state.json",
    "institutional_coordination": PROJECT_ROOT / "data" / "memory" / "institutional_coordination_intelligence_state.json",
    "temporal_intelligence": PROJECT_ROOT / "data" / "memory" / "temporal_intelligence_state.json",
    "long_term_market_memory": PROJECT_ROOT / "data" / "memory" / "long_term_market_memory_state.json",
    "market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
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
            "narrative",
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


def _history_average(previous: Dict[str, Any], key: str, default: float = 0.0) -> float:
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    values = [_safe_float(item.get(key), 0.0) for item in history[-10:] if isinstance(item, dict)]
    return sum(values) / max(len(values), 1) if values else default


def build_autonomous_strategy_research_lab(
    previous: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    market = _market_context(master_input, context)
    decisions = final_decisions if isinstance(final_decisions, dict) else {}

    genome = payloads.get("strategy_genome", {})
    meta = payloads.get("meta_learning", {})
    autonomous = payloads.get("autonomous_research", {})
    validation = payloads.get("backtesting_validation", {})
    optimization = payloads.get("advanced_optimization", {})
    swarm = payloads.get("swarm_intelligence", {})
    reflection = payloads.get("recursive_reflection", {})
    cognition = payloads.get("meta_cognition", {})
    distillation = payloads.get("knowledge_distillation", {})

    source_health = sum(1 for key in ("strategy_genome", "meta_learning", "autonomous_research", "backtesting_validation", "advanced_optimization", "swarm_intelligence") if payloads.get(key)) / 6.0
    validation_quality = _payload_score(validation, ("validation_score", "validation_quality_score", "confidence_alignment_score"), 0.35)
    genome_quality = _payload_score(genome, ("genome_quality_score", "family_count"), 0.35)
    meta_quality = _payload_score(meta, ("learning_velocity_score", "priority_count", "research_priority_score"), 0.3)
    swarm_quality = _payload_score(swarm, ("specialist_consensus_score", "swarm_coordination_score"), 0.3)
    optimization_priority = _payload_score(optimization, ("research_priority_optimization_score", "optimization_readiness_score"), 0.3)
    repeat_rate = _term_rate(records, ("repeat", "duplicate", "same mistake", "stagnation", "loop", "repeated"))
    failure_rate = _term_rate(records, ("failed", "failure", "loss", "missed", "contradiction", "overfit"))
    innovation_terms = _term_rate(records, ("new", "mutation", "hypothesis", "experiment", "sandbox", "innovation"))

    experiment_quality = _score(validation_quality * 0.24 + genome_quality * 0.18 + meta_quality * 0.16 + swarm_quality * 0.16 + source_health * 0.14 + (1.0 - failure_rate) * 0.12)
    loop_failure = _score(failure_rate * 0.34 + repeat_rate * 0.26 + _payload_score(reflection, ("repeated_reasoning_mistake_score", "recurring_failure_chain_score"), 0.0) * 0.22 + _payload_score(cognition, ("uncertainty_introspection_score", "supervision_need_score"), 0.0) * 0.18)
    sandbox_priority = _score(optimization_priority * 0.26 + genome_quality * 0.22 + loop_failure * 0.18 + innovation_terms * 0.18 + swarm_quality * 0.16)
    hypothesis_confidence = _score(experiment_quality * 0.34 + validation_quality * 0.22 + _payload_score(distillation, ("distillation_scores",), 0.25) * 0.16 + (1.0 - loop_failure) * 0.16 + source_health * 0.12)
    stagnation = _score(repeat_rate * 0.34 + max(0.0, _history_average(previous, "hypothesis_confidence", hypothesis_confidence) - hypothesis_confidence) * 0.22 + (1.0 - innovation_terms) * 0.14 + loop_failure * 0.18 + (1.0 - meta_quality) * 0.12)
    innovation_pressure = _score(loop_failure * 0.28 + stagnation * 0.24 + optimization_priority * 0.18 + _payload_score(cognition, ("self_doubt_score", "supervision_need_score"), 0.0) * 0.14 + innovation_terms * 0.16)
    research_lab_intelligence = _score((experiment_quality + sandbox_priority + hypothesis_confidence + innovation_pressure + (1.0 - stagnation * 0.5) + (1.0 - loop_failure * 0.35)) / 6.0)

    state = {
        **_phase_base("phase66", previous, sources),
        "phase": "PHASE_66_AUTONOMOUS_STRATEGY_RESEARCH_LAB",
        "status": "OK" if any(payloads.values()) or records or market else "WAITING_FOR_RESEARCH_LAB_INPUTS",
        "connected": True,
        "experiment_quality_score": experiment_quality,
        "research_loop_failure_score": loop_failure,
        "sandbox_prioritization_score": sandbox_priority,
        "strategy_hypothesis_confidence_score": hypothesis_confidence,
        "research_stagnation_score": stagnation,
        "innovation_pressure_score": innovation_pressure,
        "research_lab_intelligence_score": research_lab_intelligence,
        "research_hypotheses": [
            "prioritize_strategy_families_with_validation_and_swarm_support",
            "send_repeated_failure_loops_to_replay_research_before_new_mutation",
            "increase_sandbox_attention_when_stagnation_or_loop_failure_rises",
        ],
        "failed_or_repeated_research_terms": _term_counts(records, ("failed", "repeat", "duplicate", "stagnation", "overfit", "contradiction", "missed")),
        "decision_context_seen": {"final_decision_count": len(decisions.get("ranked") or decisions.get("decisions") or [])},
        "source_consumption": {
            "strategy_genome": bool(genome),
            "replay_research": bool(records or payloads.get("historical_replay_progress")),
            "meta_learning": bool(meta),
            "autonomous_research": bool(autonomous),
            "backtesting_validation": bool(validation),
            "advanced_optimization": bool(optimization),
            "swarm_intelligence": bool(swarm),
            "meta_cognition_or_reflection": bool(cognition or reflection),
        },
        "feeds": {
            "master_brain": "Research lab score is advisory sidecar context only.",
            "optimization_systems": "Sandbox priority and loop failures guide future shadow allocation.",
            "future_strategy_evolution": "Hypothesis confidence and innovation pressure shape future research planning.",
            "meta_cognition": "Stagnation and repeated loops feed introspection without live authority.",
            "reflection_systems": "Failed or repeated research terms are persisted for future review.",
            "runtime_observability": "Research quality, stagnation, and safety flags are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "hypothesis_confidence": hypothesis_confidence, "quality": experiment_quality, "stagnation": stagnation})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_synthetic_market_evolution_engine(
    previous: Dict[str, Any] | None = None,
    research_lab_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    research_lab_state = research_lab_state if isinstance(research_lab_state, dict) else _read_json(PHASE_PATHS["phase66"]["memory"])
    market = _market_context(master_input, context)

    synthetic = payloads.get("synthetic_market", {})
    adversarial = payloads.get("adversarial_intelligence", {})
    replay = payloads.get("historical_replay_progress", {})
    risk = payloads.get("dynamic_risk", {})
    multi = payloads.get("multi_horizon", {})
    scenario = payloads.get("scenario_simulation", {})
    lab_priority = _payload_score(research_lab_state, ("sandbox_prioritization_score", "research_lab_intelligence_score"), 0.25)
    lab_loop_failure = _payload_score(research_lab_state, ("research_loop_failure_score",), 0.0)

    transition_terms = _term_rate(records, ("transition", "regime shift", "risk_off", "risk_on", "cycle", "rotation"))
    volatility_terms = _term_rate(records, ("volatility", "shock", "panic", "compression", "expansion"))
    liquidity_terms = _term_rate(records, ("liquidity", "collapse", "sweep", "illiquid", "slippage"))
    fake_stability_terms = _term_rate(records, ("fake stability", "calm", "compression", "hidden weakness", "trap"))
    adversarial_terms = _term_rate(records, ("trap", "fakeout", "stop hunt", "bait", "manipulation", "adversarial"))

    synthetic_stress = _payload_score(synthetic, ("synthetic_market_stress_index", "regime_stress_score"), 0.25)
    adversarial_pressure = _payload_score(adversarial, ("adversarial_replay_signature_score", "institutional_bait_score"), 0.0)
    risk_pressure = _payload_score(risk, ("stress_aware_theoretical_sizing_score", "regime_aware_risk_score"), 0.25)
    horizon_conflict = _payload_score(multi, ("timeframe_conflict_score", "lower_timeframe_instability_score"), 0.15)
    scenario_pressure = _payload_score(scenario, ("scenario_risk_score", "stress_score"), 0.2)

    regime_transition = _score(transition_terms * 0.26 + synthetic_stress * 0.22 + horizon_conflict * 0.18 + lab_priority * 0.16 + _payload_score(replay, ("total_records_generated", "batches_completed"), 0.0) * 0.02 + scenario_pressure * 0.16)
    volatility_evolution = _score(volatility_terms * 0.28 + _payload_score(synthetic, ("volatility_shock_score", "panic_simulation_score"), 0.25) * 0.28 + risk_pressure * 0.20 + lab_priority * 0.12 + scenario_pressure * 0.12)
    liquidity_collapse = _score(liquidity_terms * 0.30 + _payload_score(synthetic, ("liquidity_collapse_score",), 0.2) * 0.30 + adversarial_pressure * 0.18 + risk_pressure * 0.12 + lab_loop_failure * 0.10)
    fake_stability = _score(fake_stability_terms * 0.30 + (1.0 - volatility_evolution) * 0.16 + _payload_score(synthetic, ("fake_breakout_environment_score",), 0.2) * 0.24 + adversarial_terms * 0.18 + lab_priority * 0.12)
    adversarial_transition = _score(adversarial_terms * 0.28 + adversarial_pressure * 0.28 + fake_stability * 0.16 + liquidity_collapse * 0.14 + lab_loop_failure * 0.14)
    stress_escalation = _score(max(volatility_evolution, liquidity_collapse, adversarial_transition) * 0.34 + synthetic_stress * 0.22 + risk_pressure * 0.18 + lab_priority * 0.14 + horizon_conflict * 0.12)
    cognition_robustness = _score((1.0 - stress_escalation * 0.45) + _payload_score(research_lab_state, ("strategy_hypothesis_confidence_score",), 0.25) * 0.25 + _payload_score(payloads.get("meta_cognition", {}), ("reasoning_reliability_score",), 0.25) * 0.20)
    cognition_robustness = _score(cognition_robustness / 1.45)
    synthetic_evolution_score = _score((regime_transition + volatility_evolution + liquidity_collapse + fake_stability + adversarial_transition + stress_escalation + cognition_robustness) / 7.0)

    state = {
        **_phase_base("phase67", previous, sources),
        "phase": "PHASE_67_SYNTHETIC_MARKET_EVOLUTION_ENGINE",
        "status": "OK" if research_lab_state or any(payloads.values()) or records or market else "WAITING_FOR_SYNTHETIC_EVOLUTION_INPUTS",
        "connected": True,
        "phase66_consumed": bool(research_lab_state),
        "phase66_run_count_seen": research_lab_state.get("run_count"),
        "synthetic_regime_transition_score": regime_transition,
        "evolving_volatility_environment_score": volatility_evolution,
        "liquidity_collapse_simulation_score": liquidity_collapse,
        "fake_stability_environment_score": fake_stability,
        "adversarial_synthetic_transition_score": adversarial_transition,
        "synthetic_stress_escalation_score": stress_escalation,
        "cognition_robustness_under_synthetic_change_score": cognition_robustness,
        "synthetic_evolution_intelligence_score": synthetic_evolution_score,
        "evolving_world_plan": [
            "rotate_synthetic_worlds_between_volatility_liquidity_and_fake_stability",
            "escalate_adversarial_transitions_when_lab_loop_failure_rises",
            "test_strategy_hypotheses_against_changing_conditions_before_promotion_review",
        ],
        "source_consumption": {
            "phase66_research_lab": bool(research_lab_state),
            "synthetic_simulator": bool(synthetic),
            "adversarial_intelligence": bool(adversarial),
            "replay_intelligence": bool(records or replay),
            "dynamic_risk": bool(risk),
            "multi_horizon": bool(multi),
            "scenario_systems": bool(scenario),
        },
        "feeds": {
            "master_brain": "Evolving synthetic-world pressure is advisory sidecar context only.",
            "dynamic_risk": "Stress escalation is persisted for future risk research.",
            "adversarial_intelligence": "Adversarial synthetic transitions guide future deception studies.",
            "strategy_research_lab": "Changing worlds consume Phase 66 priorities and feed future lab planning.",
            "optimization_systems": "World evolution scores guide shadow-only scenario allocation.",
            "runtime_observability": "Synthetic evolution and cross-phase consumption are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "evolution": synthetic_evolution_score, "stress": stress_escalation, "robustness": cognition_robustness})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_global_macro_intelligence_mesh(
    previous: Dict[str, Any] | None = None,
    research_lab_state: Dict[str, Any] | None = None,
    synthetic_evolution_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    research_lab_state = research_lab_state if isinstance(research_lab_state, dict) else _read_json(PHASE_PATHS["phase66"]["memory"])
    synthetic_evolution_state = synthetic_evolution_state if isinstance(synthetic_evolution_state, dict) else _read_json(PHASE_PATHS["phase67"]["memory"])
    market = _market_context(master_input, context)

    meta_regime = payloads.get("meta_regime", {})
    capital = payloads.get("capital_flow", {})
    institutional = payloads.get("institutional_coordination", {})
    temporal = payloads.get("temporal_intelligence", {})
    long_memory = payloads.get("long_term_market_memory", {})
    narrative = payloads.get("market_narrative", {})
    risk = payloads.get("dynamic_risk", {})

    macro_terms = _term_rate(records, ("macro", "global", "rates", "currency", "liquidity", "risk_on", "risk_off", "sector rotation"))
    divergence_terms = _term_rate(records, ("divergence", "decoupling", "contradiction", "cross asset", "mismatch"))
    liquidity_terms = _term_rate(records, ("liquidity", "flow", "capital", "migration", "institutional"))
    risk_wave_terms = _term_rate(records, ("risk_on", "risk_off", "panic", "defensive", "offensive", "rotation"))
    synthetic_global_stress = _payload_score(synthetic_evolution_state, ("synthetic_stress_escalation_score", "synthetic_evolution_intelligence_score"), 0.2)
    lab_confidence = _payload_score(research_lab_state, ("strategy_hypothesis_confidence_score", "research_lab_intelligence_score"), 0.25)

    capital_risk_on = _payload_score(capital, ("risk_on_score", "offensive_transition_score"), 0.25)
    capital_risk_off = _payload_score(capital, ("risk_off_score", "defensive_transition_score"), 0.25)
    capital_migration = _payload_score(capital, ("capital_migration_score", "institutional_flow_proxy_score"), 0.25)
    meta_pressure = _payload_score(meta_regime, ("global_meta_regime_risk_score", "transition_risk_score"), 0.25)
    institutional_pressure = _payload_score(institutional, ("institutional_coordination_score",), 0.25)
    temporal_alignment = _payload_score(temporal, ("timing_synchronization_score", "timing_quality_score"), 0.25)
    long_macro = _payload_score(long_memory, ("macro_event_memory_score", "historical_analog_quality_score"), 0.25)
    narrative_persistence = _payload_score(narrative, ("narrative_persistence_score",), 0.25)

    synchronization = _score((1.0 - abs(capital_risk_on - capital_risk_off)) * 0.22 + temporal_alignment * 0.20 + narrative_persistence * 0.16 + long_macro * 0.16 + macro_terms * 0.14 + lab_confidence * 0.12)
    divergence = _score(divergence_terms * 0.28 + abs(capital_risk_on - capital_risk_off) * 0.22 + meta_pressure * 0.18 + synthetic_global_stress * 0.16 + _payload_score(risk, ("regime_aware_risk_score",), 0.2) * 0.16)
    global_liquidity = _score(liquidity_terms * 0.24 + capital_migration * 0.30 + institutional_pressure * 0.16 + meta_pressure * 0.14 + synthetic_global_stress * 0.16)
    risk_on_off_wave = _score(risk_wave_terms * 0.24 + max(capital_risk_on, capital_risk_off) * 0.28 + narrative_persistence * 0.14 + meta_pressure * 0.16 + synthetic_global_stress * 0.18)
    institutional_macro = _score(institutional_pressure * 0.30 + capital_migration * 0.24 + global_liquidity * 0.18 + long_macro * 0.14 + macro_terms * 0.14)
    defensive_rotation = _score(capital_risk_off * 0.34 + global_liquidity * 0.18 + meta_pressure * 0.18 + synthetic_global_stress * 0.16 + risk_wave_terms * 0.14)
    offensive_rotation = _score(capital_risk_on * 0.34 + synchronization * 0.20 + (1.0 - meta_pressure) * 0.16 + narrative_persistence * 0.14 + macro_terms * 0.16)
    macro_mesh_pressure = _score((synchronization + divergence + global_liquidity + risk_on_off_wave + institutional_macro + defensive_rotation + offensive_rotation) / 7.0)

    state = {
        **_phase_base("phase68", previous, sources),
        "phase": "PHASE_68_GLOBAL_MACRO_INTELLIGENCE_MESH",
        "status": "OK" if research_lab_state or synthetic_evolution_state or any(payloads.values()) or records or market else "WAITING_FOR_MACRO_MESH_INPUTS",
        "connected": True,
        "phase66_consumed": bool(research_lab_state),
        "phase66_run_count_seen": research_lab_state.get("run_count"),
        "phase67_consumed": bool(synthetic_evolution_state),
        "phase67_run_count_seen": synthetic_evolution_state.get("run_count"),
        "macro_synchronization_score": synchronization,
        "macro_divergence_score": divergence,
        "global_liquidity_pressure_score": global_liquidity,
        "risk_on_risk_off_wave_score": risk_on_off_wave,
        "institutional_macro_pressure_score": institutional_macro,
        "defensive_macro_rotation_score": defensive_rotation,
        "offensive_macro_rotation_score": offensive_rotation,
        "global_macro_mesh_pressure_score": macro_mesh_pressure,
        "macro_mesh_advisory": "MACRO_DIVERGENCE_RESEARCH_PRIORITY" if divergence >= 0.55 else "MACRO_MESH_NORMAL_RESEARCH_MONITOR",
        "source_consumption": {
            "phase66_research_lab": bool(research_lab_state),
            "phase67_synthetic_evolution": bool(synthetic_evolution_state),
            "meta_regime": bool(meta_regime),
            "capital_flow": bool(capital),
            "institutional_coordination": bool(institutional),
            "temporal_intelligence": bool(temporal),
            "long_term_market_memory": bool(long_memory),
            "narrative_intelligence": bool(narrative),
        },
        "feeds": {
            "master_brain": "Macro mesh pressure is advisory sidecar context only.",
            "dynamic_risk": "Global liquidity and risk waves support future risk research.",
            "portfolio_consciousness_future_layers": "Rotation pressure is persisted for future portfolio layers.",
            "institutional_coordination": "Institutional macro pressure connects flow and desk coordination.",
            "optimization_systems": "Macro synchronization and divergence can guide future sandbox planning.",
            "runtime_observability": "Macro mesh values and cross-phase consumption are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "mesh_pressure": macro_mesh_pressure, "synchronization": synchronization, "divergence": divergence})
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
    for field in ("phase66_consumed", "phase66_run_count_seen", "phase67_consumed", "phase67_run_count_seen"):
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


def run_autonomous_strategy_research_lab(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase66"]["memory"])
    state = build_autonomous_strategy_research_lab(previous=previous, master_input=master_input, context=context, final_decisions=final_decisions)
    fields = ("experiment_quality_score", "research_loop_failure_score", "sandbox_prioritization_score", "strategy_hypothesis_confidence_score", "research_stagnation_score", "innovation_pressure_score", "research_lab_intelligence_score", "research_hypotheses", "source_consumption")
    return _persist("phase66", state, "TITAN Phase 66 Autonomous Strategy Research Lab Report", fields, fields, write_files)


def run_synthetic_market_evolution_engine(
    research_lab_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase67"]["memory"])
    state = build_synthetic_market_evolution_engine(previous=previous, research_lab_state=research_lab_state, master_input=master_input, context=context)
    fields = ("phase66_consumed", "phase66_run_count_seen", "synthetic_regime_transition_score", "evolving_volatility_environment_score", "liquidity_collapse_simulation_score", "fake_stability_environment_score", "adversarial_synthetic_transition_score", "synthetic_stress_escalation_score", "cognition_robustness_under_synthetic_change_score", "synthetic_evolution_intelligence_score", "evolving_world_plan", "source_consumption")
    return _persist("phase67", state, "TITAN Phase 67 Synthetic Market Evolution Engine Report", fields, fields, write_files)


def run_global_macro_intelligence_mesh(
    research_lab_state: Dict[str, Any] | None = None,
    synthetic_evolution_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase68"]["memory"])
    state = build_global_macro_intelligence_mesh(previous=previous, research_lab_state=research_lab_state, synthetic_evolution_state=synthetic_evolution_state, master_input=master_input, context=context)
    fields = ("phase66_consumed", "phase67_consumed", "phase66_run_count_seen", "phase67_run_count_seen", "macro_synchronization_score", "macro_divergence_score", "global_liquidity_pressure_score", "risk_on_risk_off_wave_score", "institutional_macro_pressure_score", "defensive_macro_rotation_score", "offensive_macro_rotation_score", "global_macro_mesh_pressure_score", "macro_mesh_advisory", "source_consumption")
    return _persist("phase68", state, "TITAN Phase 68 Global Macro Intelligence Mesh Report", fields, fields, write_files)


def run_roadmap_batch10_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase66 = run_autonomous_strategy_research_lab(master_input=master_input, context=context, final_decisions=final_decisions, write_files=write_files)
    phase67 = run_synthetic_market_evolution_engine(research_lab_state=phase66, master_input=master_input, context=context, write_files=write_files)
    phase68 = run_global_macro_intelligence_mesh(research_lab_state=phase66, synthetic_evolution_state=phase67, master_input=master_input, context=context, write_files=write_files)
    return {
        "phase66_autonomous_strategy_research_lab": phase66,
        "phase67_synthetic_market_evolution_engine": phase67,
        "phase68_global_macro_intelligence_mesh": phase68,
        **_safety_flags(),
    }


if __name__ == "__main__":
    result = run_roadmap_batch10_intelligence(write_files=True)
    print("TITAN Roadmap Batch 10 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
