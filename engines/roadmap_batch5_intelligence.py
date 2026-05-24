"""
TITAN Roadmap Batch 5 - Phases 51-53 advisory intelligence.

Persistent sidecars for hierarchical brain organization, autonomous goal
priority memory, and knowledge distillation. These engines organize existing
TITAN intelligence artifacts only. They never mutate scanners, ranking,
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
STATE_VERSION = "51-53.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 400

PHASE_PATHS = {
    "phase51": {
        "memory": PROJECT_ROOT / "data" / "memory" / "hierarchical_brain_architecture_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "hierarchical_brain_architecture_status.json",
        "report": PROJECT_ROOT / "reports" / "hierarchical_brain_architecture_report.txt",
    },
    "phase52": {
        "memory": PROJECT_ROOT / "data" / "memory" / "autonomous_goal_management_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "autonomous_goal_management_status.json",
        "report": PROJECT_ROOT / "reports" / "autonomous_goal_management_report.txt",
    },
    "phase53": {
        "memory": PROJECT_ROOT / "data" / "memory" / "knowledge_distillation_engine_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "knowledge_distillation_engine_status.json",
        "report": PROJECT_ROOT / "reports" / "knowledge_distillation_engine_report.txt",
    },
}

INPUT_PATHS = {
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "accuracy_validation": PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json",
    "meta_learning": PROJECT_ROOT / "data" / "memory" / "meta_learning_state.json",
    "strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "meta_regime": PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json",
    "temporal_intelligence": PROJECT_ROOT / "data" / "memory" / "temporal_intelligence_state.json",
    "market_breadth": PROJECT_ROOT / "data" / "memory" / "market_breadth_intelligence_state.json",
    "crowd_psychology": PROJECT_ROOT / "data" / "memory" / "crowd_psychology_state.json",
    "market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
    "synthetic_market": PROJECT_ROOT / "data" / "memory" / "synthetic_market_simulator_state.json",
    "adversarial_intelligence": PROJECT_ROOT / "data" / "memory" / "adversarial_intelligence_state.json",
    "explainable_ai": PROJECT_ROOT / "data" / "memory" / "explainable_ai_engine_state.json",
    "memory_consolidation": PROJECT_ROOT / "data" / "memory_consolidation" / "latest_memory_consolidation_report.json",
    "strategic_memory_index": PROJECT_ROOT / "data" / "memory_consolidation" / "strategic_memory_index.json",
    "master_shadow": PROJECT_ROOT / "data" / "memory" / "master_shadow_memory.json",
    "promotion_gate": PROJECT_ROOT / "data" / "memory" / "promotion_gate_memory.json",
    "meta_evolution": PROJECT_ROOT / "data" / "memory" / "meta_evolution_memory.json",
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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score(value: float) -> float:
    return round(_clamp01(value), 4)


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


def _outcome(row: Dict[str, Any]) -> str:
    text = _safe_text(row.get("outcome") or row.get("result") or row.get("status") or row.get("trade_result")).upper()
    if text in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if text in {"LOSS", "LOST", "SL", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}:
        return "LOSS"
    return "UNKNOWN"


def _term_rate(rows: Iterable[Dict[str, Any]], terms: Iterable[str]) -> float:
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        return 0.0
    hits = 0
    for row in rows:
        text = " ".join(
            _safe_text(row.get(key)).lower()
            for key in (
                "semantic_labels",
                "trap_label",
                "failure_reason_label",
                "success_reason_label",
                "behavioral_pattern_label",
                "market_context_label",
                "reason",
            )
        )
        if any(term in text for term in terms):
            hits += 1
    return hits / max(len(rows), 1)


def _payload_score(payload: Dict[str, Any], keys: Iterable[str], default: float = 0.0) -> float:
    for key in keys:
        if key in payload:
            value = _safe_float(payload.get(key), default)
            return value / 100.0 if value > 1.0 else value
    return default


def _layer(name: str, role: str, inputs: List[str], score: float, directives: List[str]) -> Dict[str, Any]:
    return {
        "name": name,
        "role": role,
        "source_inputs": inputs,
        "activation_score": _score(score),
        "advisory_directives": directives[:MAX_ITEMS],
    }


def build_hierarchical_brain_architecture(
    previous: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    losses = sum(1 for row in records if _outcome(row) == "LOSS")
    decided = final_decisions if isinstance(final_decisions, dict) else {}
    decision_count = len(decided.get("ranked") or decided.get("decisions") or [])
    market = (master_input or {}).get("market", {}) if isinstance(master_input, dict) else {}
    market_data = market.get("data") if isinstance(market, dict) and isinstance(market.get("data"), dict) else {}
    ctx = context if isinstance(context, dict) else {}

    synthetic = _payload_score(payloads.get("synthetic_market", {}), ("synthetic_market_stress_index", "regime_stress_score"))
    adversarial = _payload_score(payloads.get("adversarial_intelligence", {}), ("adversarial_replay_signature_score", "institutional_bait_score"))
    explainability = _payload_score(payloads.get("explainable_ai", {}), ("explanation_depth_score", "contradiction_score"))
    meta_regime = _payload_score(payloads.get("meta_regime", {}), ("global_meta_regime_risk_score", "transition_risk_score"))
    meta_learning = _payload_score(payloads.get("meta_learning", {}), ("learning_pressure_score", "priority_count"))
    genome = min(1.0, _safe_float(payloads.get("strategy_genome", {}).get("family_count"), 0.0) / 20.0)
    temporal = _payload_score(payloads.get("temporal_intelligence", {}), ("timing_quality_score",), 0.5)
    breadth = _payload_score(payloads.get("market_breadth", {}), ("hidden_weakness_strength_score", "breadth_divergence_score"))
    crowd = _payload_score(payloads.get("crowd_psychology", {}), ("crowd_instability_score", "panic_behavior_score"))
    narrative = _payload_score(payloads.get("market_narrative", {}), ("narrative_contradiction_score", "narrative_persistence_score"))
    accuracy = _payload_score(payloads.get("accuracy_validation", {}), ("validation_drift_score", "accuracy_warning_score", "closed_records_this_run"))
    replay_failure = losses / max(sum(1 for row in records if _outcome(row) in {"WIN", "LOSS"}), 1)
    risk_tone = _safe_float(ctx.get("risk_tone_score") or market_data.get("risk_tone_score"), 50.0) / 100.0

    reflex_score = _score(max(synthetic, adversarial, breadth, replay_failure))
    tactical_score = _score((temporal * 0.25) + (breadth * 0.25) + (crowd * 0.25) + (risk_tone * 0.25))
    strategic_score = _score((genome * 0.36) + (meta_learning * 0.24) + (accuracy * 0.20) + (explainability * 0.20))
    macro_score = _score((meta_regime * 0.34) + (narrative * 0.24) + (crowd * 0.18) + (synthetic * 0.24))
    supervisor_score = _score((reflex_score * 0.25) + (tactical_score * 0.20) + (strategic_score * 0.20) + (macro_score * 0.25) + (explainability * 0.10))
    arbitration_score = _score(abs(reflex_score - strategic_score) * 0.28 + abs(tactical_score - macro_score) * 0.24 + explainability * 0.24 + adversarial * 0.24)

    layers = {
        "reflex_layer": _layer("reflex_layer", "Immediate stress, deception, drawdown, and replay-loss awareness.", ["synthetic_market", "adversarial_intelligence", "market_breadth", "historical_replay"], reflex_score, ["raise_caution_when_stress_or_deception_is_high", "send_only_advisory_context_to_master_brain"]),
        "tactical_layer": _layer("tactical_layer", "Near-term timing, breadth, crowd, and market-mode organization.", ["temporal_intelligence", "market_breadth", "crowd_psychology", "runtime_context"], tactical_score, ["prefer_research_on_weak_timing_or_hidden_breadth", "preserve_final_decision_engine_as_ranking_owner"]),
        "strategic_layer": _layer("strategic_layer", "Strategy family, validation, and meta-learning organization.", ["strategy_genome", "accuracy_validation", "meta_learning", "explainable_ai"], strategic_score, ["route_strategy_lessons_to_evolution_memory", "promote_no_live_weight_from_this_sidecar"]),
        "macro_layer": _layer("macro_layer", "Regime, narrative, crowd, and synthetic macro pressure organization.", ["meta_regime", "market_narrative", "crowd_psychology", "synthetic_market"], macro_score, ["surface_regime_mismatch_for_meta_reasoning", "tag_macro_context_for_replay_research"]),
        "supervisor_layer": _layer("supervisor_layer", "Cross-layer health summary for master brain and consciousness/meta layers.", ["reflex_layer", "tactical_layer", "strategic_layer", "macro_layer"], supervisor_score, ["coordinate_advisory_sidecars", "persist_progressive_state_for_future_cycles"]),
        "arbitration_layer": _layer("arbitration_layer", "Contradiction and disagreement organization without ranking authority.", ["explainable_ai", "adversarial_intelligence", "all_hierarchy_layers"], arbitration_score, ["flag_layer_conflicts_for_goal_management", "keep_arbitration_shadow_only"]),
    }
    hierarchy_balance_score = _score(sum(layer["activation_score"] for layer in layers.values()) / len(layers))
    state = {
        **_phase_base("phase51", previous, sources),
        "phase": "PHASE_51_HIERARCHICAL_BRAIN_ARCHITECTURE",
        "status": "OK" if any(payloads.values()) or records or master_input or context else "WAITING_FOR_INTELLIGENCE_INPUTS",
        "connected": True,
        "decision_context_seen": {"final_decision_count": decision_count, "context_mode": ctx.get("trading_mode")},
        "hierarchy_layers": layers,
        "reflex_layer_score": reflex_score,
        "tactical_layer_score": tactical_score,
        "strategic_layer_score": strategic_score,
        "macro_layer_score": macro_score,
        "supervisor_layer_score": supervisor_score,
        "arbitration_layer_score": arbitration_score,
        "hierarchy_balance_score": hierarchy_balance_score,
        "organized_existing_outputs": {
            name: bool(payloads.get(name))
            for name in (
                "meta_regime",
                "strategy_genome",
                "temporal_intelligence",
                "market_breadth",
                "crowd_psychology",
                "market_narrative",
                "synthetic_market",
                "adversarial_intelligence",
                "explainable_ai",
                "meta_learning",
                "memory_consolidation",
            )
        },
        "feeds": {
            "master_brain": "Layered advisory context for master_controller sidecar reports only.",
            "consciousness_meta_layers": "Supervisor and arbitration layers expose contradictions for reflection.",
            "goal_management": "Phase 52 consumes all layer scores and directives.",
            "knowledge_distillation": "Phase 53 consumes hierarchy organization and cross-layer pressures.",
            "memory_systems": "Progressive hierarchy history is persisted under data/memory.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "hierarchy_balance_score": hierarchy_balance_score, "supervisor_layer_score": supervisor_score, "arbitration_layer_score": arbitration_score})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_autonomous_goal_management(
    previous: Dict[str, Any] | None = None,
    hierarchy_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    hierarchy_state = hierarchy_state if isinstance(hierarchy_state, dict) else _read_json(PHASE_PATHS["phase51"]["memory"])
    ctx = context if isinstance(context, dict) else {}
    reflex = _safe_float(hierarchy_state.get("reflex_layer_score"), 0.0)
    tactical = _safe_float(hierarchy_state.get("tactical_layer_score"), 0.0)
    strategic = _safe_float(hierarchy_state.get("strategic_layer_score"), 0.0)
    macro = _safe_float(hierarchy_state.get("macro_layer_score"), 0.0)
    supervisor = _safe_float(hierarchy_state.get("supervisor_layer_score"), 0.0)
    arbitration = _safe_float(hierarchy_state.get("arbitration_layer_score"), 0.0)
    meta_learning = _payload_score(payloads.get("meta_learning", {}), ("learning_pressure_score", "priority_count"))
    accuracy = _payload_score(payloads.get("accuracy_validation", {}), ("validation_drift_score", "accuracy_warning_score", "closed_records_this_run"))
    drawdown_terms = _term_rate(records, ("drawdown", "sl hit", "stoploss", "loss streak", "failed"))
    exploration = _score((strategic * 0.32) + (meta_learning * 0.28) + ((1.0 - reflex) * 0.20) + ((1.0 - macro) * 0.20))
    exploitation = _score((supervisor * 0.32) + (tactical * 0.24) + ((1.0 - arbitration) * 0.24) + ((1.0 - accuracy) * 0.20))
    survival = _score(max(reflex, macro, arbitration, drawdown_terms) * 0.70 + accuracy * 0.30)
    learning = _score(max(meta_learning, strategic, accuracy) * 0.60 + arbitration * 0.25 + min(1.0, len(records) / 100.0) * 0.15)
    capital = _score(max(survival, drawdown_terms, reflex) * 0.62 + macro * 0.20 + arbitration * 0.18)
    drawdown = _score(max(drawdown_terms, reflex * 0.55 + arbitration * 0.45))
    research = _score((learning * 0.34) + (strategic * 0.22) + (macro * 0.18) + (arbitration * 0.26))
    execution_caution = _score(max(reflex, arbitration, macro) * 0.64 + (0.16 if ctx.get("trading_mode") == "SELECTIVE" else 0.0) + accuracy * 0.20)
    goals = {
        "survival_first": survival,
        "learning_priority": learning,
        "exploration_priority": exploration,
        "exploitation_priority": exploitation,
        "capital_preservation": capital,
        "drawdown_caution": drawdown,
        "research_focus": research,
        "execution_caution": execution_caution,
    }
    ordered = sorted(goals.items(), key=lambda item: item[1], reverse=True)
    objectives = [
        {"goal": name, "priority_score": score, "advisory_objective": f"maintain_{name}_as_shadow_priority"}
        for name, score in ordered[:MAX_ITEMS]
    ]
    state = {
        **_phase_base("phase52", previous, sources),
        "phase": "PHASE_52_AUTONOMOUS_GOAL_MANAGEMENT",
        "status": "OK" if hierarchy_state or any(payloads.values()) or records else "WAITING_FOR_HIERARCHY_AND_PRIOR_STATES",
        "connected": True,
        "phase51_consumed": bool(hierarchy_state),
        "phase51_run_count_seen": hierarchy_state.get("run_count"),
        "goal_priority_scores": goals,
        "advisory_objectives": objectives,
        "dominant_goal": ordered[0][0] if ordered else "survival_first",
        "exploration_vs_exploitation": {
            "exploration_priority": exploration,
            "exploitation_priority": exploitation,
            "recommended_bias": "EXPLORE_IN_RESEARCH" if exploration > exploitation else "EXPLOIT_KNOWN_EDGES_IN_RESEARCH",
        },
        "prior_state_consumption": {
            "phase40_accuracy_validation": bool(payloads.get("accuracy_validation")),
            "phase41_meta_learning": bool(payloads.get("meta_learning")),
            "phase42_strategy_genome": bool(payloads.get("strategy_genome")),
            "phase43_meta_regime": bool(payloads.get("meta_regime")),
            "phase44_50_batch3_batch4": any(bool(payloads.get(name)) for name in ("temporal_intelligence", "market_breadth", "crowd_psychology", "market_narrative", "synthetic_market", "adversarial_intelligence", "explainable_ai")),
        },
        "feeds": {
            "master_brain": "Advisory objectives are report-side context only.",
            "hierarchical_brain": "Goal priorities are derived from Phase 51 layer scores.",
            "knowledge_distillation": "Phase 53 consumes dominant goals and priorities.",
            "evolution_systems": "Research/exploration objectives guide sandbox hypotheses only.",
            "runtime_observability": "Goal scores are exposed through runtime_status.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "dominant_goal": state["dominant_goal"], "survival_first": survival, "learning_priority": learning})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_knowledge_distillation_engine(
    previous: Dict[str, Any] | None = None,
    hierarchy_state: Dict[str, Any] | None = None,
    goal_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    hierarchy_state = hierarchy_state if isinstance(hierarchy_state, dict) else _read_json(PHASE_PATHS["phase51"]["memory"])
    goal_state = goal_state if isinstance(goal_state, dict) else _read_json(PHASE_PATHS["phase52"]["memory"])
    losses = sum(1 for row in records if _outcome(row) == "LOSS")
    wins = sum(1 for row in records if _outcome(row) == "WIN")
    failure_terms = Counter()
    regime_terms = Counter()
    strategy_terms = Counter()
    for row in records[-MAX_RECORDS:]:
        text = " ".join(_safe_text(row.get(key)).lower() for key in ("failure_reason_label", "behavioral_pattern_label", "semantic_labels", "market_context_label", "regime_label", "strategy", "setup_type", "strategy_family"))
        for term in ("fake breakout", "trap", "liquidity sweep", "late entry", "chase", "overconfidence", "drawdown", "volatility shock"):
            if term in text:
                failure_terms[term] += 1
        for term in ("trend", "range", "volatile", "risk_off", "risk_on", "transition", "macro"):
            if term in text:
                regime_terms[term] += 1
        for term in ("breakout", "pullback", "momentum", "mean reversion", "reversal", "gap"):
            if term in text:
                strategy_terms[term] += 1
    hierarchy_pressure = _safe_float(hierarchy_state.get("supervisor_layer_score"), 0.0)
    arbitration = _safe_float(hierarchy_state.get("arbitration_layer_score"), 0.0)
    goals = goal_state.get("goal_priority_scores") if isinstance(goal_state.get("goal_priority_scores"), dict) else {}
    learning_goal = _safe_float(goals.get("learning_priority"), 0.0)
    survival_goal = _safe_float(goals.get("survival_first"), 0.0)
    meta_regime = _payload_score(payloads.get("meta_regime", {}), ("global_meta_regime_risk_score", "transition_risk_score"))
    genome = _payload_score(payloads.get("strategy_genome", {}), ("family_count",))
    explanation = _payload_score(payloads.get("explainable_ai", {}), ("explanation_depth_score", "contradiction_score"))
    replay_density = _score(min(1.0, len(records) / 100.0))
    principle_score = _score((hierarchy_pressure * 0.24) + (learning_goal * 0.22) + (explanation * 0.18) + (replay_density * 0.18) + (meta_regime * 0.18))
    failure_score = _score((losses / max(wins + losses, 1)) * 0.40 + arbitration * 0.25 + survival_goal * 0.20 + (sum(failure_terms.values()) / max(len(records), 1)) * 0.15)
    compression_score = _score((replay_density * 0.25) + (principle_score * 0.25) + (failure_score * 0.25) + (genome * 0.25))
    high_value_principles = [
        "treat_high_reflex_or_arbitration_pressure_as_research_caution",
        "route_regime_mismatch_and_narrative_contradiction_to_meta_reasoning",
        "prefer_strategy_lessons_with_replay_and_explainability_support",
        "keep_goal_priorities_advisory_until_explicit_promotion",
    ]
    failure_summaries = [
        {"pattern": name, "count": count, "lesson": f"review_{name.replace(' ', '_')}_in_replay_before_strategy_promotion"}
        for name, count in failure_terms.most_common(MAX_ITEMS)
    ]
    if not failure_summaries:
        failure_summaries = [
            {
                "pattern": "insufficient_replay_failure_terms",
                "count": 0,
                "lesson": "preserve_failure_summary_slot_and_prioritize_replay_enrichment",
            }
        ]
    regime_lessons = [
        {"regime_signal": name, "count": count, "lesson": f"compare_{name}_outcomes_against_meta_regime_state"}
        for name, count in regime_terms.most_common(MAX_ITEMS)
    ]
    if not regime_lessons:
        regime_lessons = [
            {
                "regime_signal": "insufficient_replay_regime_terms",
                "count": 0,
                "lesson": "use_meta_regime_state_until_replay_regime_terms_are_populated",
            }
        ]
    strategy_lessons = [
        {"strategy_signal": name, "count": count, "lesson": f"distill_{name}_conditions_into_strategy_genome_research"}
        for name, count in strategy_terms.most_common(MAX_ITEMS)
    ]
    if not strategy_lessons:
        strategy_lessons = [
            {
                "strategy_signal": "insufficient_replay_strategy_terms",
                "count": 0,
                "lesson": "use_strategy_genome_family_memory_until_replay_strategy_terms_are_populated",
            }
        ]
    memory_compression_candidates = [
        {"candidate": "hierarchy_history", "reason": "compress_layer_score_drift_for_consciousness_meta_reasoning"},
        {"candidate": "goal_priority_history", "reason": "compress_dominant_goal_changes_for_future_roadmap_intelligence"},
        {"candidate": "failure_pattern_terms", "reason": "compress_repeated_failure_terms_into_replay_tags"},
    ]
    state = {
        **_phase_base("phase53", previous, sources),
        "phase": "PHASE_53_KNOWLEDGE_DISTILLATION_ENGINE",
        "status": "OK" if hierarchy_state or goal_state or any(payloads.values()) or records else "WAITING_FOR_REPLAY_AND_GOAL_INPUTS",
        "connected": True,
        "phase51_consumed": bool(hierarchy_state),
        "phase51_run_count_seen": hierarchy_state.get("run_count"),
        "phase52_consumed": bool(goal_state),
        "phase52_run_count_seen": goal_state.get("run_count"),
        "prior_intelligence_consumed": {
            "replay": bool(records),
            "accuracy_validation": bool(payloads.get("accuracy_validation")),
            "meta_learning": bool(payloads.get("meta_learning")),
            "strategy_genome": bool(payloads.get("strategy_genome")),
            "meta_regime": bool(payloads.get("meta_regime")),
            "crowd_narrative_adversarial_explainability": any(bool(payloads.get(name)) for name in ("crowd_psychology", "market_narrative", "adversarial_intelligence", "explainable_ai")),
        },
        "high_value_principles": high_value_principles,
        "failure_summaries": failure_summaries,
        "regime_lessons": regime_lessons,
        "strategy_lessons": strategy_lessons,
        "memory_compression_candidates": memory_compression_candidates,
        "distillation_scores": {
            "principle_quality_score": principle_score,
            "failure_learning_score": failure_score,
            "memory_compression_candidate_score": compression_score,
        },
        "feeds": {
            "evolution_systems": "Lessons are sandbox inputs for future strategy evolution only.",
            "memory_systems": "Compression candidates are advisory memory-consolidation targets.",
            "consciousness_meta_reasoning": "Principles and failures support reflective reasoning.",
            "future_roadmap_intelligence": "Distilled lessons persist as reusable roadmap context.",
            "replay_research": "Failure and regime summaries identify replay slices to inspect.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "principle_quality_score": principle_score, "failure_learning_score": failure_score, "compression_score": compression_score})
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
        "",
        "Values",
    ]
    for field in fields:
        lines.append(f"- {field}: {state.get(field)}")
    lines.extend(["", "Cross-Phase Consumption"])
    for field in ("phase51_consumed", "phase51_run_count_seen", "phase52_consumed", "phase52_run_count_seen"):
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


def run_hierarchical_brain_architecture(master_input: Dict[str, Any] | None = None, context: Dict[str, Any] | None = None, final_decisions: Dict[str, Any] | None = None, write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase51"]["memory"])
    state = build_hierarchical_brain_architecture(previous=previous, master_input=master_input, context=context, final_decisions=final_decisions)
    return _persist("phase51", state, "TITAN Phase 51 Hierarchical Brain Architecture Report", ("reflex_layer_score", "tactical_layer_score", "strategic_layer_score", "macro_layer_score", "supervisor_layer_score", "arbitration_layer_score", "hierarchy_balance_score", "organized_existing_outputs"), ("reflex_layer_score", "tactical_layer_score", "strategic_layer_score", "macro_layer_score", "supervisor_layer_score", "arbitration_layer_score", "hierarchy_balance_score", "organized_existing_outputs"), write_files)


def run_autonomous_goal_management(hierarchy_state: Dict[str, Any] | None = None, context: Dict[str, Any] | None = None, write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase52"]["memory"])
    state = build_autonomous_goal_management(previous=previous, hierarchy_state=hierarchy_state, context=context)
    return _persist("phase52", state, "TITAN Phase 52 Autonomous Goal Management Report", ("phase51_consumed", "phase51_run_count_seen", "dominant_goal", "goal_priority_scores", "advisory_objectives", "exploration_vs_exploitation"), ("phase51_consumed", "phase51_run_count_seen", "dominant_goal", "goal_priority_scores", "advisory_objectives", "exploration_vs_exploitation"), write_files)


def run_knowledge_distillation_engine(hierarchy_state: Dict[str, Any] | None = None, goal_state: Dict[str, Any] | None = None, context: Dict[str, Any] | None = None, write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase53"]["memory"])
    state = build_knowledge_distillation_engine(previous=previous, hierarchy_state=hierarchy_state, goal_state=goal_state, context=context)
    return _persist("phase53", state, "TITAN Phase 53 Knowledge Distillation Engine Report", ("phase51_consumed", "phase52_consumed", "prior_intelligence_consumed", "high_value_principles", "failure_summaries", "regime_lessons", "strategy_lessons", "memory_compression_candidates", "distillation_scores"), ("phase51_consumed", "phase52_consumed", "phase51_run_count_seen", "phase52_run_count_seen", "prior_intelligence_consumed", "high_value_principles", "failure_summaries", "distillation_scores"), write_files)


def run_roadmap_batch5_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase51 = run_hierarchical_brain_architecture(master_input=master_input, context=context, final_decisions=final_decisions, write_files=write_files)
    phase52 = run_autonomous_goal_management(hierarchy_state=phase51, context=context, write_files=write_files)
    phase53 = run_knowledge_distillation_engine(hierarchy_state=phase51, goal_state=phase52, context=context, write_files=write_files)
    return {
        "phase51_hierarchical_brain_architecture": phase51,
        "phase52_autonomous_goal_management": phase52,
        "phase53_knowledge_distillation_engine": phase53,
        "advisory_only": True,
        "research_only": True,
        "shadow_mode": True,
        "affects_live_ranking": False,
        "affects_execution": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "supabase_mutation": False,
    }


if __name__ == "__main__":
    result = run_roadmap_batch5_intelligence(write_files=True)
    print("TITAN Roadmap Batch 5 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
