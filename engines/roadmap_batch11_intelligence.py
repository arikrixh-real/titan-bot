"""
TITAN Roadmap Batch 11 - Phases 69-71 advisory intelligence.

Persistent sidecars for unified portfolio awareness, shadow capital allocation
research, and top-level AGI trading orchestration. These layers consume existing
TITAN memory/runtime/report artifacts only. They never mutate scanners, ranking,
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
STATE_VERSION = "69-71.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 500

PHASE_PATHS = {
    "phase69": {
        "memory": PROJECT_ROOT / "data" / "memory" / "portfolio_consciousness_engine_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "portfolio_consciousness_engine_status.json",
        "report": PROJECT_ROOT / "reports" / "portfolio_consciousness_engine_report.txt",
    },
    "phase70": {
        "memory": PROJECT_ROOT / "data" / "memory" / "autonomous_capital_allocation_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "autonomous_capital_allocation_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "autonomous_capital_allocation_intelligence_report.txt",
    },
    "phase71": {
        "memory": PROJECT_ROOT / "data" / "memory" / "master_agi_trading_orchestrator_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "master_agi_trading_orchestrator_status.json",
        "report": PROJECT_ROOT / "reports" / "master_agi_trading_orchestrator_report.txt",
    },
}

INPUT_PATHS = {
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "trade_journal": PROJECT_ROOT / "data" / "trade_journal.csv",
    "portfolio_brain": PROJECT_ROOT / "data" / "memory" / "portfolio_brain_memory.json",
    "dynamic_risk": PROJECT_ROOT / "data" / "memory" / "dynamic_risk_intelligence_state.json",
    "capital_flow": PROJECT_ROOT / "data" / "memory" / "capital_flow_intelligence_state.json",
    "meta_regime": PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json",
    "macro_mesh": PROJECT_ROOT / "data" / "memory" / "global_macro_intelligence_mesh_state.json",
    "institutional_coordination": PROJECT_ROOT / "data" / "memory" / "institutional_coordination_intelligence_state.json",
    "multi_horizon": PROJECT_ROOT / "data" / "memory" / "multi_horizon_intelligence_state.json",
    "long_term_market_memory": PROJECT_ROOT / "data" / "memory" / "long_term_market_memory_state.json",
    "advanced_optimization": PROJECT_ROOT / "data" / "memory" / "advanced_optimization_framework_state.json",
    "meta_cognition": PROJECT_ROOT / "data" / "memory" / "meta_cognition_engine_state.json",
    "swarm_intelligence": PROJECT_ROOT / "data" / "memory" / "swarm_intelligence_architecture_state.json",
    "research_lab": PROJECT_ROOT / "data" / "memory" / "autonomous_strategy_research_lab_state.json",
    "synthetic_evolution": PROJECT_ROOT / "data" / "memory" / "synthetic_market_evolution_engine_state.json",
    "recursive_reflection": PROJECT_ROOT / "data" / "memory" / "recursive_self_reflection_state.json",
    "strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
    "crowd_psychology": PROJECT_ROOT / "data" / "memory" / "crowd_psychology_state.json",
    "reinforcement_learning": PROJECT_ROOT / "data" / "memory" / "reinforcement_learning_memory.json",
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "agi_transition": PROJECT_ROOT / "data" / "memory" / "agi_transition_layer_state.json",
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
        if name in {"historical_experience_jsonl", "trade_journal"}:
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


def _market_context(master_input: Dict[str, Any] | None, context: Dict[str, Any] | None) -> Dict[str, Any]:
    ctx = context if isinstance(context, dict) else {}
    master = master_input if isinstance(master_input, dict) else {}
    market_packet = master.get("market") if isinstance(master.get("market"), dict) else {}
    market_data = market_packet.get("data") if isinstance(market_packet.get("data"), dict) else {}
    merged = dict(market_data)
    for key, value in ctx.items():
        merged.setdefault(key, value)
    return merged


def _row_text(row: Dict[str, Any]) -> str:
    return " ".join(
        _safe_text(row.get(key)).lower()
        for key in (
            "symbol",
            "sector",
            "industry",
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


def _history_average(previous: Dict[str, Any], key: str, default: float = 0.0) -> float:
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    values = [_safe_float(item.get(key), 0.0) for item in history[-10:] if isinstance(item, dict)]
    return sum(values) / max(len(values), 1) if values else default


def _decision_rows(final_decisions: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not isinstance(final_decisions, dict):
        return []
    for key in ("ranked", "decisions", "final_decisions", "candidates"):
        rows = final_decisions.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _sector_counts(rows: List[Dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        sector = _safe_text(row.get("sector") or row.get("industry") or row.get("category"), "unknown").lower()
        counts[sector] += 1
    return counts


def build_portfolio_consciousness_engine(
    previous: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    market = _market_context(master_input, context)
    decisions = _decision_rows(final_decisions)

    risk = payloads.get("dynamic_risk", {})
    capital = payloads.get("capital_flow", {})
    regime = payloads.get("meta_regime", {})
    macro = payloads.get("macro_mesh", {})
    institutional = payloads.get("institutional_coordination", {})
    multi = payloads.get("multi_horizon", {})
    long_memory = payloads.get("long_term_market_memory", {})
    portfolio = payloads.get("portfolio_brain", {})

    total_positions = max(len(decisions), _safe_int(portfolio.get("open_position_count"), 0), 1)
    sector_counts = _sector_counts(decisions)
    largest_sector_share = max(sector_counts.values(), default=0) / total_positions
    correlation_terms = _term_rate(records, ("correlation", "cluster", "same sector", "rotation", "synchronized"))
    fragility_terms = _term_rate(records, ("fragile", "drawdown", "shock", "stress", "crowded", "liquidity"))
    macro_terms = _term_rate(records, ("macro", "rates", "currency", "global", "risk_off", "risk_on"))
    defensive_terms = _term_rate(records, ("defensive", "hedge", "capital preservation", "risk_off"))
    offensive_terms = _term_rate(records, ("offensive", "momentum", "breakout", "risk_on", "expansion"))

    risk_pressure = _payload_score(risk, ("stress_aware_theoretical_sizing_score", "regime_aware_risk_score"), 0.25)
    capital_migration = _payload_score(capital, ("capital_migration_score", "sector_rotation_score"), 0.25)
    macro_pressure = _payload_score(macro, ("global_macro_mesh_pressure_score", "macro_divergence_score"), 0.25)
    institutional_pressure = _payload_score(institutional, ("institutional_coordination_score",), 0.25)
    horizon_conflict = _payload_score(multi, ("timeframe_conflict_score", "lower_timeframe_instability_score"), 0.2)
    historical_stress = _payload_score(long_memory, ("crisis_memory_score", "structural_failure_memory_score"), 0.2)

    sector_concentration = _score(largest_sector_share * 0.42 + capital_migration * 0.24 + macro_pressure * 0.16 + correlation_terms * 0.18)
    exposure_clustering = _score(correlation_terms * 0.32 + sector_concentration * 0.24 + institutional_pressure * 0.18 + horizon_conflict * 0.16 + capital_migration * 0.10)
    cross_position_correlation = _score(exposure_clustering * 0.38 + correlation_terms * 0.28 + macro_pressure * 0.18 + institutional_pressure * 0.16)
    macro_exposure_imbalance = _score(macro_pressure * 0.32 + abs(_payload_score(capital, ("risk_on_score",), 0.25) - _payload_score(capital, ("risk_off_score",), 0.25)) * 0.22 + macro_terms * 0.22 + risk_pressure * 0.24)
    hidden_fragility = _score(fragility_terms * 0.28 + risk_pressure * 0.24 + historical_stress * 0.18 + cross_position_correlation * 0.16 + horizon_conflict * 0.14)
    stress_synchronization = _score(cross_position_correlation * 0.30 + macro_exposure_imbalance * 0.22 + hidden_fragility * 0.22 + institutional_pressure * 0.14 + horizon_conflict * 0.12)
    defensive_offensive_balance = _score(1.0 - min(1.0, abs(defensive_terms - offensive_terms) + abs(_payload_score(capital, ("risk_on_score",), 0.25) - _payload_score(capital, ("risk_off_score",), 0.25))))
    portfolio_consciousness = _score((sector_concentration + exposure_clustering + cross_position_correlation + macro_exposure_imbalance + hidden_fragility + stress_synchronization + defensive_offensive_balance) / 7.0)

    state = {
        **_phase_base("phase69", previous, sources),
        "phase": "PHASE_69_PORTFOLIO_CONSCIOUSNESS_ENGINE",
        "status": "OK" if any(payloads.values()) or records or market or decisions else "WAITING_FOR_PORTFOLIO_CONSCIOUSNESS_INPUTS",
        "connected": True,
        "sector_concentration_pressure_score": sector_concentration,
        "exposure_clustering_score": exposure_clustering,
        "cross_position_correlation_score": cross_position_correlation,
        "macro_exposure_imbalance_score": macro_exposure_imbalance,
        "hidden_portfolio_fragility_score": hidden_fragility,
        "portfolio_stress_synchronization_score": stress_synchronization,
        "defensive_offensive_balance_score": defensive_offensive_balance,
        "portfolio_consciousness_score": portfolio_consciousness,
        "position_relationship_map": {
            "decision_count_seen": len(decisions),
            "largest_sector_share": round(largest_sector_share, 4),
            "sector_clusters": dict(sector_counts.most_common(MAX_ITEMS)),
            "stress_terms": _term_counts(records, ("correlation", "cluster", "fragile", "stress", "macro", "defensive", "offensive")),
        },
        "source_consumption": {
            "dynamic_risk": bool(risk),
            "capital_flow": bool(capital),
            "meta_regime": bool(regime),
            "macro_mesh": bool(macro),
            "institutional_coordination": bool(institutional),
            "multi_horizon": bool(multi),
            "long_term_market_memory": bool(long_memory),
            "portfolio_brain": bool(portfolio),
        },
        "feeds": {
            "master_brain": "Portfolio awareness is advisory sidecar context only.",
            "agi_orchestrator": "System-wide exposure pressure and balance feed Phase 71.",
            "optimization_systems": "Fragility and clustering guide future shadow optimization research.",
            "capital_allocation_intelligence": "Phase 70 consumes concentration, balance, and stress synchronization.",
            "future_unified_consciousness": "Portfolio-wide relationship memory is persisted for Phase 72 readiness.",
            "runtime_observability": "Portfolio consciousness values are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "portfolio_consciousness": portfolio_consciousness, "fragility": hidden_fragility, "stress_sync": stress_synchronization})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_autonomous_capital_allocation_intelligence(
    previous: Dict[str, Any] | None = None,
    portfolio_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    portfolio_state = portfolio_state if isinstance(portfolio_state, dict) else _read_json(PHASE_PATHS["phase69"]["memory"])
    market = _market_context(master_input, context)

    risk = payloads.get("dynamic_risk", {})
    optimization = payloads.get("advanced_optimization", {})
    macro = payloads.get("macro_mesh", {})
    cognition = payloads.get("meta_cognition", {})
    swarm = payloads.get("swarm_intelligence", {})
    institutional = payloads.get("institutional_coordination", {})

    efficiency_terms = _term_rate(records, ("efficient", "inefficient", "opportunity cost", "rotation", "capital"))
    preservation_terms = _term_rate(records, ("preservation", "defensive", "drawdown", "risk_off", "protect"))
    rotation_terms = _term_rate(records, ("rotation", "migration", "sector", "risk_on", "risk_off"))
    portfolio_pressure = _payload_score(portfolio_state, ("portfolio_consciousness_score", "hidden_portfolio_fragility_score"), 0.25)
    concentration = _payload_score(portfolio_state, ("sector_concentration_pressure_score",), 0.0)
    stress_sync = _payload_score(portfolio_state, ("portfolio_stress_synchronization_score",), 0.0)
    balance = _payload_score(portfolio_state, ("defensive_offensive_balance_score",), 0.4)

    risk_pressure = _payload_score(risk, ("stress_aware_theoretical_sizing_score", "theoretical_shadow_size_multiplier"), 0.25)
    optimization_readiness = _payload_score(optimization, ("optimization_readiness_score", "resource_allocation_hint_score"), 0.25)
    macro_divergence = _payload_score(macro, ("macro_divergence_score", "global_macro_mesh_pressure_score"), 0.25)
    cognition_need = _payload_score(cognition, ("supervision_need_score", "uncertainty_introspection_score"), 0.2)
    swarm_consensus = _payload_score(swarm, ("specialist_consensus_score", "swarm_coordination_score"), 0.25)
    institutional_alignment = _payload_score(institutional, ("institutional_coordination_score",), 0.25)

    capital_efficiency = _score(optimization_readiness * 0.28 + swarm_consensus * 0.18 + institutional_alignment * 0.16 + efficiency_terms * 0.18 + (1.0 - stress_sync) * 0.12 + balance * 0.08)
    adaptive_allocation_balance = _score(balance * 0.30 + (1.0 - concentration) * 0.20 + optimization_readiness * 0.18 + swarm_consensus * 0.14 + (1.0 - macro_divergence) * 0.10 + institutional_alignment * 0.08)
    allocation_stress_pressure = _score(portfolio_pressure * 0.28 + stress_sync * 0.24 + risk_pressure * 0.20 + macro_divergence * 0.16 + cognition_need * 0.12)
    concentration_advisory = _score(concentration * 0.38 + stress_sync * 0.20 + macro_divergence * 0.16 + risk_pressure * 0.14 + (1.0 - balance) * 0.12)
    rotation_hypothesis = _score(rotation_terms * 0.24 + _payload_score(payloads.get("capital_flow", {}), ("capital_migration_score", "sector_rotation_score"), 0.25) * 0.28 + macro_divergence * 0.16 + institutional_alignment * 0.16 + portfolio_pressure * 0.16)
    preservation_regime = _score(preservation_terms * 0.24 + risk_pressure * 0.26 + macro_divergence * 0.20 + stress_sync * 0.18 + cognition_need * 0.12)
    research_resource_hint = _score(optimization_readiness * 0.24 + allocation_stress_pressure * 0.22 + concentration_advisory * 0.18 + rotation_hypothesis * 0.16 + cognition_need * 0.12 + (1.0 - swarm_consensus) * 0.08)
    shadow_allocation_intelligence = _score((capital_efficiency + adaptive_allocation_balance + allocation_stress_pressure + concentration_advisory + rotation_hypothesis + preservation_regime + research_resource_hint) / 7.0)

    state = {
        **_phase_base("phase70", previous, sources),
        "phase": "PHASE_70_AUTONOMOUS_CAPITAL_ALLOCATION_INTELLIGENCE",
        "status": "OK" if portfolio_state or any(payloads.values()) or records or market else "WAITING_FOR_ALLOCATION_INPUTS",
        "connected": True,
        "phase69_consumed": bool(portfolio_state),
        "phase69_run_count_seen": portfolio_state.get("run_count"),
        "capital_efficiency_hypothesis_score": capital_efficiency,
        "adaptive_allocation_balance_score": adaptive_allocation_balance,
        "allocation_stress_pressure_score": allocation_stress_pressure,
        "portfolio_concentration_advisory_score": concentration_advisory,
        "capital_rotation_hypothesis_score": rotation_hypothesis,
        "capital_preservation_regime_score": preservation_regime,
        "research_resource_allocation_hint_score": research_resource_hint,
        "shadow_allocation_intelligence_score": shadow_allocation_intelligence,
        "shadow_allocation_hypotheses": [
            "increase_research_attention_when_portfolio_stress_synchronizes",
            "prefer_hypothetical_rotation_study_when_macro_and_capital_flow_diverge",
            "prioritize_capital_preservation_research_when_fragility_and_risk_pressure_rise",
        ],
        "source_consumption": {
            "phase69_portfolio_consciousness": bool(portfolio_state),
            "dynamic_risk": bool(risk),
            "advanced_optimization": bool(optimization),
            "macro_mesh": bool(macro),
            "meta_cognition": bool(cognition),
            "swarm_intelligence": bool(swarm),
            "institutional_coordination": bool(institutional),
        },
        "feeds": {
            "master_orchestrator": "Shadow allocation intelligence feeds Phase 71 without live sizing authority.",
            "optimization_systems": "Research-resource and rotation hints support future advisory optimization.",
            "future_unified_consciousness": "Allocation pressure and hypotheses persist for Phase 72 readiness.",
            "runtime_observability": "Shadow allocation values and Phase 69 consumption are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "shadow_allocation": shadow_allocation_intelligence, "stress": allocation_stress_pressure, "preservation": preservation_regime})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_master_agi_trading_orchestrator(
    previous: Dict[str, Any] | None = None,
    portfolio_state: Dict[str, Any] | None = None,
    allocation_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    portfolio_state = portfolio_state if isinstance(portfolio_state, dict) else _read_json(PHASE_PATHS["phase69"]["memory"])
    allocation_state = allocation_state if isinstance(allocation_state, dict) else _read_json(PHASE_PATHS["phase70"]["memory"])
    market = _market_context(master_input, context)

    research = payloads.get("research_lab", {})
    replay = payloads.get("historical_replay_progress", {})
    macro = payloads.get("macro_mesh", {})
    cognition = payloads.get("meta_cognition", {})
    swarm = payloads.get("swarm_intelligence", {})
    optimization = payloads.get("advanced_optimization", {})
    institutional = payloads.get("institutional_coordination", {})
    genome = payloads.get("strategy_genome", {})
    risk = payloads.get("dynamic_risk", {})
    narrative = payloads.get("market_narrative", {})
    crowd = payloads.get("crowd_psychology", {})
    reflection = payloads.get("recursive_reflection", {})
    agi = payloads.get("agi_transition", {})

    available_core = sum(1 for item in (research, replay, macro, portfolio_state, allocation_state, cognition, swarm, optimization, institutional, genome, risk, narrative, crowd) if item) / 13.0
    disagreement_terms = _term_rate(records, ("disagreement", "contradiction", "conflict", "divergence", "mismatch"))
    bottleneck_terms = _term_rate(records, ("bottleneck", "stagnation", "delay", "blocked", "uncertain"))
    convergence_terms = _term_rate(records, ("converge", "agreement", "coherence", "alignment", "synchronized"))

    portfolio_quality = _payload_score(portfolio_state, ("portfolio_consciousness_score", "defensive_offensive_balance_score"), 0.25)
    allocation_quality = _payload_score(allocation_state, ("shadow_allocation_intelligence_score", "adaptive_allocation_balance_score"), 0.25)
    cognition_quality = _payload_score(cognition, ("reasoning_reliability_score", "confidence_of_reasoning_score"), 0.25)
    swarm_quality = _payload_score(swarm, ("swarm_coordination_score", "specialist_consensus_score"), 0.25)
    optimization_quality = _payload_score(optimization, ("optimization_readiness_score",), 0.25)
    research_quality = _payload_score(research, ("research_lab_intelligence_score", "strategy_hypothesis_confidence_score"), 0.25)
    macro_pressure = _payload_score(macro, ("global_macro_mesh_pressure_score", "macro_divergence_score"), 0.25)
    risk_pressure = _payload_score(risk, ("regime_aware_risk_score", "stress_aware_theoretical_sizing_score"), 0.25)
    narrative_instability = _payload_score(narrative, ("narrative_contradiction_score",), 0.15) + _payload_score(crowd, ("crowd_instability_score",), 0.15) / 2.0
    reflection_pressure = _payload_score(reflection, ("contradiction_persistence_score", "recurring_failure_chain_score"), 0.15)

    orchestration_coherence = _score((portfolio_quality + allocation_quality + cognition_quality + swarm_quality + optimization_quality + research_quality + available_core + convergence_terms) / 8.0)
    subsystem_disagreement = _score(disagreement_terms * 0.26 + abs(macro_pressure - risk_pressure) * 0.18 + reflection_pressure * 0.18 + narrative_instability * 0.14 + (1.0 - swarm_quality) * 0.12 + _payload_score(cognition, ("cognitive_conflict_score",), 0.15) * 0.12)
    cognitive_bottleneck = _score(bottleneck_terms * 0.24 + _payload_score(cognition, ("supervision_need_score", "uncertainty_introspection_score"), 0.2) * 0.24 + reflection_pressure * 0.18 + (1.0 - research_quality) * 0.14 + _payload_score(allocation_state, ("research_resource_allocation_hint_score",), 0.2) * 0.20)
    orchestration_stability = _score((1.0 - subsystem_disagreement) * 0.24 + (1.0 - cognitive_bottleneck) * 0.20 + swarm_quality * 0.18 + cognition_quality * 0.16 + portfolio_quality * 0.12 + allocation_quality * 0.10)
    autonomous_coordination = _score(swarm_quality * 0.22 + optimization_quality * 0.18 + institutional.get("institutional_coordination_score", 0.25) * 0.10 + research_quality * 0.16 + _payload_score(agi, ("agi_transition_readiness_score", "autonomy_readiness_shadow_score"), 0.2) * 0.18 + available_core * 0.16)
    convergence_readiness = _score(orchestration_coherence * 0.24 + orchestration_stability * 0.22 + autonomous_coordination * 0.18 + portfolio_quality * 0.12 + allocation_quality * 0.12 + (1.0 - subsystem_disagreement) * 0.12)
    master_agi_orchestration = _score((orchestration_coherence + (1.0 - subsystem_disagreement) + (1.0 - cognitive_bottleneck) + orchestration_stability + autonomous_coordination + convergence_readiness) / 6.0)

    state = {
        **_phase_base("phase71", previous, sources),
        "phase": "PHASE_71_MASTER_AGI_TRADING_ORCHESTRATOR",
        "status": "OK" if portfolio_state or allocation_state or any(payloads.values()) or records or market else "WAITING_FOR_ORCHESTRATOR_INPUTS",
        "connected": True,
        "phase69_consumed": bool(portfolio_state),
        "phase69_run_count_seen": portfolio_state.get("run_count"),
        "phase70_consumed": bool(allocation_state),
        "phase70_run_count_seen": allocation_state.get("run_count"),
        "orchestration_coherence_score": orchestration_coherence,
        "subsystem_disagreement_score": subsystem_disagreement,
        "cognitive_bottleneck_score": cognitive_bottleneck,
        "orchestration_stability_score": orchestration_stability,
        "autonomous_coordination_quality_score": autonomous_coordination,
        "consciousness_convergence_readiness_score": convergence_readiness,
        "master_agi_orchestration_score": master_agi_orchestration,
        "orchestration_intelligence_map": {
            "research": research_quality,
            "replay_records": _safe_int(replay.get("total_records_generated"), 0),
            "macro_pressure": macro_pressure,
            "portfolio_consciousness": portfolio_quality,
            "shadow_allocation": allocation_quality,
            "meta_cognition": cognition_quality,
            "swarm": swarm_quality,
            "optimization": optimization_quality,
            "risk_pressure": risk_pressure,
            "strategy_genome": _payload_score(genome, ("genome_quality_score", "family_count"), 0.25),
        },
        "source_consumption": {
            "phase69_portfolio_consciousness": bool(portfolio_state),
            "phase70_capital_allocation": bool(allocation_state),
            "research_systems": bool(research),
            "replay_reinforcement_systems": bool(replay or payloads.get("reinforcement_learning")),
            "macro_mesh": bool(macro),
            "meta_cognition": bool(cognition),
            "swarm_intelligence": bool(swarm),
            "optimization_framework": bool(optimization),
            "institutional_coordination": bool(institutional),
            "strategy_genome": bool(genome),
            "dynamic_risk": bool(risk),
            "narrative_crowd_systems": bool(narrative or crowd),
        },
        "feeds": {
            "phase72_unified_consciousness": "Convergence readiness and orchestration map are persisted for future Phase 72.",
            "master_brain_observability": "Top-level advisory orchestration status is visible through runtime_status.",
            "future_autonomous_supervision": "Bottlenecks and subsystem disagreement identify supervision targets.",
            "final_decision_engine": "No ownership transfer; final_decision_engine remains the only live ranking owner.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "orchestration": master_agi_orchestration, "coherence": orchestration_coherence, "convergence": convergence_readiness})
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
    for field in ("phase69_consumed", "phase69_run_count_seen", "phase70_consumed", "phase70_run_count_seen"):
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


def run_portfolio_consciousness_engine(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase69"]["memory"])
    state = build_portfolio_consciousness_engine(previous=previous, master_input=master_input, context=context, final_decisions=final_decisions)
    fields = ("sector_concentration_pressure_score", "exposure_clustering_score", "cross_position_correlation_score", "macro_exposure_imbalance_score", "hidden_portfolio_fragility_score", "portfolio_stress_synchronization_score", "defensive_offensive_balance_score", "portfolio_consciousness_score", "position_relationship_map", "source_consumption")
    return _persist("phase69", state, "TITAN Phase 69 Portfolio Consciousness Engine Report", fields, fields, write_files)


def run_autonomous_capital_allocation_intelligence(
    portfolio_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase70"]["memory"])
    state = build_autonomous_capital_allocation_intelligence(previous=previous, portfolio_state=portfolio_state, master_input=master_input, context=context)
    fields = ("phase69_consumed", "phase69_run_count_seen", "capital_efficiency_hypothesis_score", "adaptive_allocation_balance_score", "allocation_stress_pressure_score", "portfolio_concentration_advisory_score", "capital_rotation_hypothesis_score", "capital_preservation_regime_score", "research_resource_allocation_hint_score", "shadow_allocation_intelligence_score", "shadow_allocation_hypotheses", "source_consumption")
    return _persist("phase70", state, "TITAN Phase 70 Autonomous Capital Allocation Intelligence Report", fields, fields, write_files)


def run_master_agi_trading_orchestrator(
    portfolio_state: Dict[str, Any] | None = None,
    allocation_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase71"]["memory"])
    state = build_master_agi_trading_orchestrator(previous=previous, portfolio_state=portfolio_state, allocation_state=allocation_state, master_input=master_input, context=context)
    fields = ("phase69_consumed", "phase70_consumed", "phase69_run_count_seen", "phase70_run_count_seen", "orchestration_coherence_score", "subsystem_disagreement_score", "cognitive_bottleneck_score", "orchestration_stability_score", "autonomous_coordination_quality_score", "consciousness_convergence_readiness_score", "master_agi_orchestration_score", "orchestration_intelligence_map", "source_consumption")
    return _persist("phase71", state, "TITAN Phase 71 Master AGI Trading Orchestrator Report", fields, fields, write_files)


def run_roadmap_batch11_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase69 = run_portfolio_consciousness_engine(master_input=master_input, context=context, final_decisions=final_decisions, write_files=write_files)
    phase70 = run_autonomous_capital_allocation_intelligence(portfolio_state=phase69, master_input=master_input, context=context, write_files=write_files)
    phase71 = run_master_agi_trading_orchestrator(portfolio_state=phase69, allocation_state=phase70, master_input=master_input, context=context, write_files=write_files)
    return {
        "phase69_portfolio_consciousness_engine": phase69,
        "phase70_autonomous_capital_allocation_intelligence": phase70,
        "phase71_master_agi_trading_orchestrator": phase71,
        **_safety_flags(),
    }


if __name__ == "__main__":
    result = run_roadmap_batch11_intelligence(write_files=True)
    print("TITAN Roadmap Batch 11 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
