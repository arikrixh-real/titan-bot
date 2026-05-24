"""
TITAN Roadmap Batch 7 - Phases 57-59 advisory intelligence.

Persistent sidecars for recursive self-reflection, long-term market memory,
and institutional coordination intelligence. These engines consume existing
TITAN memory/runtime/report artifacts only. They never mutate scanners,
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
STATE_VERSION = "57-59.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 500

PHASE_PATHS = {
    "phase57": {
        "memory": PROJECT_ROOT / "data" / "memory" / "recursive_self_reflection_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "recursive_self_reflection_status.json",
        "report": PROJECT_ROOT / "reports" / "recursive_self_reflection_report.txt",
    },
    "phase58": {
        "memory": PROJECT_ROOT / "data" / "memory" / "long_term_market_memory_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "long_term_market_memory_status.json",
        "report": PROJECT_ROOT / "reports" / "long_term_market_memory_report.txt",
    },
    "phase59": {
        "memory": PROJECT_ROOT / "data" / "memory" / "institutional_coordination_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "institutional_coordination_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "institutional_coordination_intelligence_report.txt",
    },
}

INPUT_PATHS = {
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "accuracy_validation": PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json",
    "meta_learning": PROJECT_ROOT / "data" / "memory" / "meta_learning_state.json",
    "explainable_ai": PROJECT_ROOT / "data" / "memory" / "explainable_ai_engine_state.json",
    "adversarial_intelligence": PROJECT_ROOT / "data" / "memory" / "adversarial_intelligence_state.json",
    "dynamic_risk_intelligence": PROJECT_ROOT / "data" / "memory" / "dynamic_risk_intelligence_state.json",
    "hierarchical_brain": PROJECT_ROOT / "data" / "memory" / "hierarchical_brain_architecture_state.json",
    "knowledge_distillation": PROJECT_ROOT / "data" / "memory" / "knowledge_distillation_engine_state.json",
    "no_trade_memory": PROJECT_ROOT / "data" / "memory" / "no_trade_refinement_memory.json",
    "temporal_intelligence": PROJECT_ROOT / "data" / "memory" / "temporal_intelligence_state.json",
    "market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
    "meta_regime": PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json",
    "synthetic_market": PROJECT_ROOT / "data" / "memory" / "synthetic_market_simulator_state.json",
    "capital_flow": PROJECT_ROOT / "data" / "memory" / "capital_flow_intelligence_state.json",
    "multi_horizon": PROJECT_ROOT / "data" / "memory" / "multi_horizon_intelligence_state.json",
    "autonomous_goal_management": PROJECT_ROOT / "data" / "memory" / "autonomous_goal_management_state.json",
    "confidence_calibration": PROJECT_ROOT / "data" / "confidence_calibration" / "latest_confidence_calibration_report.json",
    "options_flow": PROJECT_ROOT / "data" / "options_flow" / "latest_options_flow_report.json",
    "institutional_liquidity": PROJECT_ROOT / "data" / "liquidity_map" / "latest_institutional_liquidity_report.json",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
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


def build_recursive_self_reflection_engine(
    previous: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    decisions = final_decisions if isinstance(final_decisions, dict) else {}
    rows = records + [item for item in decisions.get("ranked", []) or decisions.get("decisions", []) or [] if isinstance(item, dict)]

    accuracy = payloads.get("accuracy_validation", {})
    meta_learning = payloads.get("meta_learning", {})
    explainable = payloads.get("explainable_ai", {})
    adversarial = payloads.get("adversarial_intelligence", {})
    risk = payloads.get("dynamic_risk_intelligence", {})
    hierarchy = payloads.get("hierarchical_brain", {})
    distillation = payloads.get("knowledge_distillation", {})

    repeated_mistakes = _score(
        _term_rate(rows, ("late entry", "chase", "overconfidence", "fake breakout", "trap", "ignored risk"))
        * 0.46
        + _payload_score(meta_learning, ("learning_pressure_score", "priority_count")) * 0.18
        + _payload_score(accuracy, ("validation_drift_score", "accuracy_warning_score", "closed_records_this_run")) * 0.18
        + _payload_score(adversarial, ("adversarial_replay_signature_score", "institutional_bait_score")) * 0.18
    )
    recurring_failure = _score(
        _term_rate(rows, ("drawdown", "loss streak", "failed", "sl hit", "stoploss")) * 0.44
        + _payload_score(risk, ("drawdown_aware_caution_score", "stress_aware_theoretical_sizing_score")) * 0.28
        + _payload_score(hierarchy, ("arbitration_layer_score", "reflex_layer_score")) * 0.28
    )
    missed_opportunity = _score(
        _term_rate(rows, ("missed", "early exit", "hesitation", "no trade", "skipped")) * 0.50
        + _payload_score(payloads.get("no_trade_memory", {}), ("no_trade_regret_score", "missed_opportunity_score")) * 0.30
        + _payload_score(payloads.get("temporal_intelligence", {}), ("timing_quality_score",), 0.5) * 0.20
    )
    confidence_mismatch = _score(
        _payload_score(accuracy, ("confidence_mismatch_score", "validation_drift_score", "accuracy_warning_score")) * 0.40
        + (1.0 - _payload_score(payloads.get("confidence_calibration", {}), ("calibrated_confidence_score", "confidence_score"), 0.5)) * 0.20
        + _term_rate(rows, ("overconfidence", "low confidence win", "high confidence loss")) * 0.40
    )
    contradiction_persistence = _score(
        _payload_score(explainable, ("contradiction_score", "explanation_depth_score")) * 0.38
        + _payload_score(hierarchy, ("arbitration_layer_score",)) * 0.24
        + _term_rate(rows, ("contradiction", "conflict", "mismatch", "disagreement")) * 0.38
    )
    self_bias = _score(
        _term_rate(rows, ("confirmation bias", "recency bias", "revenge", "fomo", "anchoring", "bias")) * 0.50
        + repeated_mistakes * 0.24
        + confidence_mismatch * 0.26
    )
    evolution = _score(
        _payload_score(meta_learning, ("learning_pressure_score", "priority_count")) * 0.24
        + _payload_score(distillation, ("distillation_scores",), 0.0) * 0.10
        + min(1.0, len(previous.get("history") or []) / 20.0) * 0.22
        + (1.0 - max(repeated_mistakes, recurring_failure, contradiction_persistence)) * 0.44
    )

    state = {
        **_phase_base("phase57", previous, sources),
        "phase": "PHASE_57_RECURSIVE_SELF_REFLECTION_ENGINE",
        "status": "OK" if any(payloads.values()) or rows or master_input or context else "WAITING_FOR_REFLECTION_INPUTS",
        "connected": True,
        "repeated_reasoning_mistake_score": repeated_mistakes,
        "recurring_failure_chain_score": recurring_failure,
        "missed_opportunity_pattern_score": missed_opportunity,
        "confidence_mismatch_score": confidence_mismatch,
        "contradiction_persistence_score": contradiction_persistence,
        "self_bias_detection_score": self_bias,
        "reflection_evolution_score": evolution,
        "reflection_patterns": {
            "mistake_terms": _term_counts(rows, ("late entry", "chase", "overconfidence", "fake breakout", "trap")),
            "failure_chain_terms": _term_counts(rows, ("drawdown", "loss streak", "failed", "sl hit", "stoploss")),
            "bias_terms": _term_counts(rows, ("confirmation bias", "recency bias", "revenge", "fomo", "anchoring")),
        },
        "source_consumption": {
            "explainable_ai": bool(explainable),
            "meta_learning": bool(meta_learning),
            "accuracy_validation": bool(accuracy),
            "replay_interpretation": bool(records),
            "adversarial_intelligence": bool(adversarial),
            "dynamic_risk_intelligence": bool(risk),
            "hierarchical_arbitration": bool(hierarchy),
            "knowledge_distillation": bool(distillation),
        },
        "feeds": {
            "master_brain": "Recursive reflection is report-side advisory context only.",
            "consciousness_meta_layers": "Contradiction and bias persistence support future self-supervision.",
            "knowledge_distillation": "Repeated mistake patterns are distillation candidates.",
            "no_trade_intelligence": "Missed opportunity and failure-chain context remains research-only.",
            "future_autonomous_supervision": "Reflection history persists for later governance review.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "mistake_score": repeated_mistakes, "failure_score": recurring_failure, "bias_score": self_bias, "evolution_score": evolution})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_long_term_market_memory(
    previous: Dict[str, Any] | None = None,
    reflection_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    reflection_state = reflection_state if isinstance(reflection_state, dict) else _read_json(PHASE_PATHS["phase57"]["memory"])
    market = _market_context(master_input, context)

    meta_regime = payloads.get("meta_regime", {})
    temporal = payloads.get("temporal_intelligence", {})
    narrative = payloads.get("market_narrative", {})
    synthetic = payloads.get("synthetic_market", {})
    replay = payloads.get("historical_replay_progress", {})
    reflection_bias = _safe_float(reflection_state.get("self_bias_detection_score"), 0.0)
    reflection_failure = _safe_float(reflection_state.get("recurring_failure_chain_score"), 0.0)

    crisis = _score(
        _term_rate(records, ("crash", "panic", "crisis", "capitulation", "gap down", "risk_off")) * 0.34
        + _payload_score(synthetic, ("regime_stress_score", "synthetic_market_stress_index", "rare_event_replay_score")) * 0.30
        + _payload_score(meta_regime, ("global_meta_regime_risk_score", "transition_risk_score")) * 0.22
        + reflection_failure * 0.14
    )
    boom_bust = _score(
        _term_rate(records, ("euphoria", "bubble", "boom", "bust", "exhaustion", "risk_on")) * 0.36
        + _payload_score(narrative, ("narrative_persistence_score", "narrative_contradiction_score")) * 0.24
        + _safe_float(market.get("risk_tone_score"), 50.0) / 100.0 * 0.18
        + reflection_bias * 0.22
    )
    volatility_transition = _score(
        _term_rate(records, ("volatile", "volatility", "transition", "whipsaw", "compression", "expansion")) * 0.36
        + _payload_score(temporal, ("timing_quality_score",), 0.5) * 0.14
        + _payload_score(meta_regime, ("transition_risk_score", "strategy_regime_mismatch_score")) * 0.30
        + _safe_float(market.get("volatility_score"), 50.0) / 100.0 * 0.20
    )
    macro_event = _score(
        _term_rate(records, ("policy", "rate", "inflation", "election", "earnings", "war", "budget", "macro")) * 0.44
        + _payload_score(narrative, ("narrative_persistence_score",), 0.3) * 0.24
        + _payload_score(meta_regime, ("global_meta_regime_risk_score",), 0.0) * 0.32
    )
    structural_failure = _score(
        _term_rate(records, ("liquidity collapse", "structural", "failure", "breakdown", "trap", "fake breakout")) * 0.44
        + _payload_score(payloads.get("adversarial_intelligence", {}), ("liquidity_manipulation_score", "trap_structure_score", "adversarial_replay_signature_score")) * 0.30
        + reflection_failure * 0.26
    )
    rare_event = _score(
        _term_rate(records, ("rare", "tail", "shock", "black swan", "circuit", "gap")) * 0.38
        + _payload_score(synthetic, ("rare_event_replay_score", "volatility_shock_score", "liquidity_collapse_score")) * 0.42
        + crisis * 0.20
    )
    analog_quality = _score((crisis + boom_bust + volatility_transition + macro_event + structural_failure + rare_event) / 6.0)

    state = {
        **_phase_base("phase58", previous, sources),
        "phase": "PHASE_58_LONG_TERM_MARKET_MEMORY",
        "status": "OK" if reflection_state or any(payloads.values()) or records or market else "WAITING_FOR_LONG_TERM_MEMORY_INPUTS",
        "connected": True,
        "phase57_consumed": bool(reflection_state),
        "phase57_run_count_seen": reflection_state.get("run_count"),
        "crisis_memory_score": crisis,
        "boom_bust_cycle_score": boom_bust,
        "volatility_regime_transition_score": volatility_transition,
        "historical_analog_quality_score": analog_quality,
        "macro_event_memory_score": macro_event,
        "structural_failure_memory_score": structural_failure,
        "rare_event_archive_score": rare_event,
        "historical_analogs": {
            "crisis_terms": _term_counts(records, ("crash", "panic", "crisis", "capitulation", "risk_off")),
            "cycle_terms": _term_counts(records, ("euphoria", "bubble", "boom", "bust", "exhaustion")),
            "macro_terms": _term_counts(records, ("policy", "rate", "inflation", "election", "earnings", "budget")),
            "rare_event_terms": _term_counts(records, ("rare", "tail", "shock", "black swan", "circuit", "gap")),
        },
        "replay_context": {
            "records_seen": len(records),
            "replay_consumed": bool(replay),
            "last_records_generated": replay.get("last_records_generated"),
            "total_records_generated": replay.get("total_records_generated"),
        },
        "source_consumption": {
            "phase57_recursive_reflection": bool(reflection_state),
            "replay_history": bool(records or replay),
            "semantic_replay_labels": bool(records),
            "regime_intelligence": bool(meta_regime),
            "temporal_intelligence": bool(temporal),
            "narrative_intelligence": bool(narrative),
            "synthetic_simulation": bool(synthetic),
        },
        "feeds": {
            "master_brain": "Long-term analog context is advisory sidecar reporting only.",
            "future_replay_intelligence": "Crisis, cycle, and rare-event terms identify replay slices.",
            "adversarial_intelligence": "Structural failure memory informs future deception research.",
            "strategy_adaptation": "Regime-transition memory is sandbox-only adaptation context.",
            "recursive_reflection": "Historical failure memory gives Phase 57 future context.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "crisis": crisis, "boom_bust": boom_bust, "rare_event": rare_event, "analog_quality": analog_quality})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_institutional_coordination_intelligence(
    previous: Dict[str, Any] | None = None,
    reflection_state: Dict[str, Any] | None = None,
    market_memory_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    reflection_state = reflection_state if isinstance(reflection_state, dict) else _read_json(PHASE_PATHS["phase57"]["memory"])
    market_memory_state = market_memory_state if isinstance(market_memory_state, dict) else _read_json(PHASE_PATHS["phase58"]["memory"])
    market = _market_context(master_input, context)
    decisions = final_decisions if isinstance(final_decisions, dict) else {}

    risk = payloads.get("dynamic_risk_intelligence", {})
    flow = payloads.get("capital_flow", {})
    horizon = payloads.get("multi_horizon", {})
    adversarial = payloads.get("adversarial_intelligence", {})
    goal = payloads.get("autonomous_goal_management", {})
    explainable = payloads.get("explainable_ai", {})
    hierarchy = payloads.get("hierarchical_brain", {})
    options = payloads.get("options_flow", {})
    liquidity = payloads.get("institutional_liquidity", {})

    reflection_pressure = max(
        _safe_float(reflection_state.get("contradiction_persistence_score"), 0.0),
        _safe_float(reflection_state.get("self_bias_detection_score"), 0.0),
    )
    memory_pressure = max(
        _safe_float(market_memory_state.get("crisis_memory_score"), 0.0),
        _safe_float(market_memory_state.get("rare_event_archive_score"), 0.0),
        _safe_float(market_memory_state.get("structural_failure_memory_score"), 0.0),
    )

    risk_desk = _score(
        _payload_score(risk, ("stress_aware_theoretical_sizing_score", "drawdown_aware_caution_score", "regime_aware_risk_score")) * 0.42
        + memory_pressure * 0.28
        + reflection_pressure * 0.18
        + _safe_float(market.get("volatility_score"), 50.0) / 100.0 * 0.12
    )
    macro_desk = _score(
        _safe_float(market_memory_state.get("macro_event_memory_score"), 0.0) * 0.34
        + _payload_score(payloads.get("meta_regime", {}), ("global_meta_regime_risk_score", "transition_risk_score")) * 0.34
        + _payload_score(payloads.get("market_narrative", {}), ("narrative_persistence_score", "narrative_contradiction_score")) * 0.18
        + memory_pressure * 0.14
    )
    execution_desk = _score(
        _payload_score(adversarial, ("adversarial_replay_signature_score", "institutional_bait_score", "trap_structure_score")) * 0.34
        + _payload_score(liquidity, ("liquidity_quality_score", "institutional_accumulation_score", "liquidity_risk_score")) * 0.22
        + _payload_score(horizon, ("timeframe_conflict_score", "lower_timeframe_instability_score")) * 0.22
        + reflection_pressure * 0.22
    )
    derivatives_desk = _score(
        _payload_score(options, ("options_risk_score", "iv_pressure_score", "put_call_stress_score")) * 0.42
        + _safe_float(market_memory_state.get("volatility_regime_transition_score"), 0.0) * 0.28
        + _payload_score(payloads.get("synthetic_market", {}), ("volatility_shock_score", "synthetic_market_stress_index")) * 0.30
    )
    portfolio_manager = _score(
        _payload_score(flow, ("capital_migration_score", "defensive_transition_score", "participation_exhaustion_score")) * 0.30
        + _payload_score(goal, ("goal_priority_scores",), 0.0) * 0.08
        + risk_desk * 0.22
        + macro_desk * 0.18
        + _payload_score(horizon, ("timeframe_conflict_score", "higher_timeframe_pressure_score")) * 0.22
    )
    supervision = _score(
        _payload_score(hierarchy, ("supervisor_layer_score", "arbitration_layer_score")) * 0.24
        + _payload_score(explainable, ("contradiction_score", "explanation_depth_score")) * 0.20
        + reflection_pressure * 0.24
        + max(risk_desk, macro_desk, execution_desk, derivatives_desk, portfolio_manager) * 0.32
    )
    desk_scores = {
        "risk_desk": risk_desk,
        "macro_desk": macro_desk,
        "execution_desk": execution_desk,
        "derivatives_options_desk": derivatives_desk,
        "portfolio_manager_layer": portfolio_manager,
        "supervision_arbitration_layer": supervision,
    }
    coordination = _score(sum(desk_scores.values()) / len(desk_scores))
    disagreement = _score(max(desk_scores.values()) - min(desk_scores.values()))

    state = {
        **_phase_base("phase59", previous, sources),
        "phase": "PHASE_59_INSTITUTIONAL_COORDINATION_INTELLIGENCE",
        "status": "OK" if reflection_state or market_memory_state or any(payloads.values()) or market else "WAITING_FOR_COORDINATION_INPUTS",
        "connected": True,
        "phase57_consumed": bool(reflection_state),
        "phase57_run_count_seen": reflection_state.get("run_count"),
        "phase58_consumed": bool(market_memory_state),
        "phase58_run_count_seen": market_memory_state.get("run_count"),
        "desk_coordination_scores": desk_scores,
        "institutional_coordination_score": coordination,
        "desk_disagreement_score": disagreement,
        "coordination_advisory": "SUPERVISION_REVIEW_IN_RESEARCH" if max(supervision, disagreement) >= 0.6 else "NORMAL_RESEARCH_COORDINATION",
        "decision_context_seen": {"final_decision_count": len(decisions.get("ranked") or decisions.get("decisions") or [])},
        "source_consumption": {
            "phase57_recursive_reflection": bool(reflection_state),
            "phase58_long_term_market_memory": bool(market_memory_state),
            "hierarchical_brain": bool(hierarchy),
            "dynamic_risk_intelligence": bool(risk),
            "capital_flow_intelligence": bool(flow),
            "multi_horizon_intelligence": bool(horizon),
            "adversarial_intelligence": bool(adversarial),
            "goal_management": bool(goal),
            "explainability": bool(explainable),
            "options_or_derivatives_context": bool(options),
            "institutional_liquidity": bool(liquidity),
        },
        "feeds": {
            "master_brain": "Institutional desk simulation is advisory sidecar context only.",
            "future_portfolio_intelligence": "Portfolio-manager score persists for future research.",
            "future_execution_adaptation": "Execution desk warnings are shadow-only inputs.",
            "supervision_meta_reasoning": "Supervision layer consumes reflection and long-term memory.",
            "runtime_observability": "Desk scores are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "coordination": coordination, "disagreement": disagreement, "advisory": state["coordination_advisory"]})
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
    for field in ("phase57_consumed", "phase57_run_count_seen", "phase58_consumed", "phase58_run_count_seen"):
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


def run_recursive_self_reflection_engine(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase57"]["memory"])
    state = build_recursive_self_reflection_engine(previous=previous, master_input=master_input, context=context, final_decisions=final_decisions)
    fields = ("repeated_reasoning_mistake_score", "recurring_failure_chain_score", "missed_opportunity_pattern_score", "confidence_mismatch_score", "contradiction_persistence_score", "self_bias_detection_score", "reflection_evolution_score", "source_consumption")
    return _persist("phase57", state, "TITAN Phase 57 Recursive Self-Reflection Report", fields, fields, write_files)


def run_long_term_market_memory(
    reflection_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase58"]["memory"])
    state = build_long_term_market_memory(previous=previous, reflection_state=reflection_state, master_input=master_input, context=context)
    fields = ("phase57_consumed", "phase57_run_count_seen", "crisis_memory_score", "boom_bust_cycle_score", "volatility_regime_transition_score", "historical_analog_quality_score", "macro_event_memory_score", "structural_failure_memory_score", "rare_event_archive_score", "source_consumption")
    return _persist("phase58", state, "TITAN Phase 58 Long-Term Market Memory Report", fields, fields, write_files)


def run_institutional_coordination_intelligence(
    reflection_state: Dict[str, Any] | None = None,
    market_memory_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase59"]["memory"])
    state = build_institutional_coordination_intelligence(previous=previous, reflection_state=reflection_state, market_memory_state=market_memory_state, master_input=master_input, context=context, final_decisions=final_decisions)
    fields = ("phase57_consumed", "phase58_consumed", "phase57_run_count_seen", "phase58_run_count_seen", "desk_coordination_scores", "institutional_coordination_score", "desk_disagreement_score", "coordination_advisory", "source_consumption")
    return _persist("phase59", state, "TITAN Phase 59 Institutional Coordination Intelligence Report", fields, fields, write_files)


def run_roadmap_batch7_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase57 = run_recursive_self_reflection_engine(master_input=master_input, context=context, final_decisions=final_decisions, write_files=write_files)
    phase58 = run_long_term_market_memory(reflection_state=phase57, master_input=master_input, context=context, write_files=write_files)
    phase59 = run_institutional_coordination_intelligence(reflection_state=phase57, market_memory_state=phase58, master_input=master_input, context=context, final_decisions=final_decisions, write_files=write_files)
    return {
        "phase57_recursive_self_reflection_engine": phase57,
        "phase58_long_term_market_memory": phase58,
        "phase59_institutional_coordination_intelligence": phase59,
        **_safety_flags(),
    }


if __name__ == "__main__":
    result = run_roadmap_batch7_intelligence(write_files=True)
    print("TITAN Roadmap Batch 7 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
