"""
TITAN Roadmap Batch 6 - Phases 54-56 advisory intelligence.

Persistent sidecars for multi-horizon alignment, capital-flow intelligence,
and dynamic risk intelligence. These engines read existing TITAN
memory/runtime/report artifacts, write local advisory artifacts only, and never
mutate scanners, ranking, execution, Telegram, broker, Supabase, dashboards, or
live order behavior.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_VERSION = "54-56.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 400

PHASE_PATHS = {
    "phase54": {
        "memory": PROJECT_ROOT / "data" / "memory" / "multi_horizon_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "multi_horizon_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "multi_horizon_intelligence_report.txt",
    },
    "phase55": {
        "memory": PROJECT_ROOT / "data" / "memory" / "capital_flow_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "capital_flow_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "capital_flow_intelligence_report.txt",
    },
    "phase56": {
        "memory": PROJECT_ROOT / "data" / "memory" / "dynamic_risk_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "dynamic_risk_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "dynamic_risk_intelligence_report.txt",
    },
}

INPUT_PATHS = {
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "temporal_intelligence": PROJECT_ROOT / "data" / "memory" / "temporal_intelligence_state.json",
    "market_breadth": PROJECT_ROOT / "data" / "memory" / "market_breadth_intelligence_state.json",
    "crowd_psychology": PROJECT_ROOT / "data" / "memory" / "crowd_psychology_state.json",
    "market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
    "strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "meta_regime": PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json",
    "accuracy_validation": PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json",
    "meta_learning": PROJECT_ROOT / "data" / "memory" / "meta_learning_state.json",
    "synthetic_market": PROJECT_ROOT / "data" / "memory" / "synthetic_market_simulator_state.json",
    "adversarial_intelligence": PROJECT_ROOT / "data" / "memory" / "adversarial_intelligence_state.json",
    "explainable_ai": PROJECT_ROOT / "data" / "memory" / "explainable_ai_engine_state.json",
    "autonomous_goal_management": PROJECT_ROOT / "data" / "memory" / "autonomous_goal_management_state.json",
    "hierarchical_brain": PROJECT_ROOT / "data" / "memory" / "hierarchical_brain_architecture_state.json",
    "no_trade_memory": PROJECT_ROOT / "data" / "memory" / "no_trade_refinement_memory.json",
    "confidence_calibration": PROJECT_ROOT / "data" / "confidence_calibration" / "latest_confidence_calibration_report.json",
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


def _text_blob(*values: Any) -> str:
    return " ".join(_safe_text(value).lower() for value in values if value is not None)


def _term_rate(rows: Iterable[Dict[str, Any]], terms: Iterable[str]) -> float:
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        return 0.0
    hits = 0
    for row in rows:
        text = _text_blob(
            row.get("semantic_labels"),
            row.get("market_context_label"),
            row.get("regime_label"),
            row.get("behavioral_pattern_label"),
            row.get("failure_reason_label"),
            row.get("success_reason_label"),
            row.get("reason"),
            row.get("strategy_family"),
            row.get("setup_type"),
        )
        if any(term in text for term in terms):
            hits += 1
    return hits / max(len(rows), 1)


def _market_context(master_input: Dict[str, Any] | None, context: Dict[str, Any] | None) -> Dict[str, Any]:
    ctx = context if isinstance(context, dict) else {}
    master = master_input if isinstance(master_input, dict) else {}
    market_packet = master.get("market") if isinstance(master.get("market"), dict) else {}
    market_data = market_packet.get("data") if isinstance(market_packet.get("data"), dict) else {}
    merged = dict(market_data)
    for key in (
        "risk_tone_score",
        "volatility_score",
        "breadth_score",
        "advance_decline_ratio",
        "market_regime",
        "regime",
        "trend_score",
        "momentum_score",
        "liquidity_score",
        "volume_score",
        "sector_strength",
        "sector_rankings",
        "sector_rotation",
    ):
        if key in ctx and key not in merged:
            merged[key] = ctx.get(key)
    return merged


def build_multi_horizon_intelligence(
    previous: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    evaluated_setups: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    market = _market_context(master_input, context)
    setups = [item for item in evaluated_setups or [] if isinstance(item, dict)]
    rows = records + setups

    temporal = payloads.get("temporal_intelligence", {})
    meta_regime = payloads.get("meta_regime", {})
    genome = payloads.get("strategy_genome", {})
    crowd = payloads.get("crowd_psychology", {})
    narrative = payloads.get("market_narrative", {})
    replay = payloads.get("historical_replay_progress", {})

    timing_quality = _payload_score(temporal, ("timing_quality_score",), 0.5)
    macro_pressure = max(
        _payload_score(meta_regime, ("global_meta_regime_risk_score", "transition_risk_score")),
        _safe_float(market.get("risk_tone_score"), 50.0) / 100.0,
        _payload_score(narrative, ("narrative_contradiction_score",)),
    )
    lower_instability = max(
        _payload_score(crowd, ("crowd_instability_score", "panic_behavior_score")),
        _term_rate(rows, ("fake breakout", "trap", "whipsaw", "late entry", "chase")),
        1.0 - timing_quality,
    )
    scalp_alignment = _score(timing_quality * 0.42 + (1.0 - lower_instability) * 0.32 + _safe_float(market.get("momentum_score"), 50.0) / 100.0 * 0.26)
    intraday_alignment = _score(timing_quality * 0.30 + _payload_score(payloads.get("market_breadth", {}), ("market_wide_confirmation_quality",), 0.5) * 0.34 + _safe_float(market.get("trend_score"), 50.0) / 100.0 * 0.36)
    swing_alignment = _score((1.0 - macro_pressure) * 0.28 + _payload_score(meta_regime, ("strategy_regime_mismatch_score",), 0.5) * 0.14 + min(1.0, _safe_float(genome.get("family_count"), 0.0) / 20.0) * 0.28 + _payload_score(narrative, ("narrative_persistence_score",), 0.3) * 0.30)
    macro_alignment = _score((1.0 - macro_pressure) * 0.46 + _payload_score(narrative, ("narrative_persistence_score",), 0.3) * 0.24 + _payload_score(meta_regime, ("transition_risk_score",), 0.0) * 0.10 + _payload_score(payloads.get("market_breadth", {}), ("market_participation_health_score",), 0.5) * 0.20)
    alignments = {
        "scalp": scalp_alignment,
        "intraday": intraday_alignment,
        "swing": swing_alignment,
        "macro": macro_alignment,
    }
    values = list(alignments.values())
    agreement = _score(1.0 - (max(values) - min(values)))
    conflict = _score(1.0 - agreement)
    synchronization = _score((timing_quality * 0.32) + (agreement * 0.28) + ((1.0 - lower_instability) * 0.22) + ((1.0 - macro_pressure) * 0.18))
    state = {
        **_phase_base("phase54", previous, sources),
        "phase": "PHASE_54_MULTI_HORIZON_INTELLIGENCE",
        "status": "OK" if rows or any(payloads.values()) or market else "WAITING_FOR_HORIZON_INPUTS",
        "connected": True,
        "horizon_alignment_scores": alignments,
        "horizon_agreement_score": agreement,
        "timeframe_conflict_score": conflict,
        "timing_synchronization_score": synchronization,
        "higher_timeframe_pressure_score": _score(macro_pressure),
        "lower_timeframe_instability_score": _score(lower_instability),
        "replay_horizon_context": {
            "records_seen": len(records),
            "evaluated_setups_seen": len(setups),
            "replay_consumed": bool(replay),
            "last_records_generated": replay.get("last_records_generated"),
        },
        "source_consumption": {
            "temporal_intelligence": bool(temporal),
            "meta_regime_intelligence": bool(meta_regime),
            "strategy_genome": bool(genome),
            "replay_intelligence": bool(records or replay),
            "crowd_psychology": bool(crowd),
            "narrative_intelligence": bool(narrative),
        },
        "feeds": {
            "master_brain": "Report-side horizon alignment context only.",
            "dynamic_risk_intelligence": "Phase 56 consumes conflict, pressure, and instability.",
            "no_trade_intelligence": "High horizon conflict is research-only no-trade context.",
            "confidence_systems": "Agreement/synchronization can explain confidence caveats without rank mutation.",
            "replay_research": "Horizon conflicts persist as replay-slicing hypotheses.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "agreement": agreement, "conflict": conflict, "synchronization": synchronization})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_capital_flow_intelligence(
    previous: Dict[str, Any] | None = None,
    multi_horizon_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    multi_horizon_state = multi_horizon_state if isinstance(multi_horizon_state, dict) else _read_json(PHASE_PATHS["phase54"]["memory"])
    market = _market_context(master_input, context)
    breadth = payloads.get("market_breadth", {})
    narrative = payloads.get("market_narrative", {})
    meta_regime = payloads.get("meta_regime", {})
    temporal = payloads.get("temporal_intelligence", {})

    sector_strength = market.get("sector_strength") if isinstance(market.get("sector_strength"), dict) else {}
    sector_rankings = market.get("sector_rankings") if isinstance(market.get("sector_rankings"), list) else []
    sector_scores = []
    sector_rotation = {}
    for sector, data in sector_strength.items():
        if isinstance(data, dict):
            score = _safe_float(data.get("strength_score") or data.get("score"), 50.0) / 100.0
            sector_scores.append(score)
            sector_rotation[str(sector)] = {"strength_score": round(score, 4), "flow_bias": "OFFENSIVE" if score >= 0.62 else "DEFENSIVE" if score <= 0.38 else "MIXED"}
    rotation_dispersion = _score((max(sector_scores) - min(sector_scores)) if len(sector_scores) >= 2 else (0.18 if sector_rankings else 0.0))
    breadth_health = _payload_score(breadth, ("market_participation_health_score", "market_wide_confirmation_quality"), 0.5)
    hidden_weakness = _payload_score(breadth, ("hidden_weakness_strength_score", "breadth_divergence_score"))
    risk_tone = _safe_float(market.get("risk_tone_score"), 50.0) / 100.0
    meta_risk = _payload_score(meta_regime, ("global_meta_regime_risk_score", "transition_risk_score"))
    narrative_contradiction = _payload_score(narrative, ("narrative_contradiction_score",))
    horizon_conflict = _safe_float(multi_horizon_state.get("timeframe_conflict_score"), 0.0)
    migration = _score(rotation_dispersion * 0.34 + hidden_weakness * 0.24 + narrative_contradiction * 0.18 + horizon_conflict * 0.24)
    risk_on = _score(risk_tone * 0.34 + breadth_health * 0.30 + (1.0 - meta_risk) * 0.22 + (1.0 - hidden_weakness) * 0.14)
    risk_off = _score((1.0 - risk_tone) * 0.22 + hidden_weakness * 0.30 + meta_risk * 0.26 + narrative_contradiction * 0.22)
    institutional_proxy = _score(migration * 0.28 + rotation_dispersion * 0.24 + _payload_score(temporal, ("timing_quality_score",), 0.5) * 0.16 + horizon_conflict * 0.16 + meta_risk * 0.16)
    exhaustion = _score(hidden_weakness * 0.34 + max(risk_on, risk_off) * 0.16 + _term_rate(records, ("exhaustion", "capitulation", "overconfidence", "fomo", "panic")) * 0.28 + horizon_conflict * 0.22)
    defensive = _score(risk_off * 0.42 + meta_risk * 0.24 + hidden_weakness * 0.20 + narrative_contradiction * 0.14)
    offensive = _score(risk_on * 0.46 + breadth_health * 0.28 + (1.0 - horizon_conflict) * 0.16 + rotation_dispersion * 0.10)
    state = {
        **_phase_base("phase55", previous, sources),
        "phase": "PHASE_55_CAPITAL_FLOW_INTELLIGENCE",
        "status": "OK" if any(payloads.values()) or market or multi_horizon_state else "WAITING_FOR_FLOW_INPUTS",
        "connected": True,
        "phase54_consumed": bool(multi_horizon_state),
        "phase54_run_count_seen": multi_horizon_state.get("run_count"),
        "sector_rotation_score": rotation_dispersion,
        "capital_migration_score": migration,
        "risk_on_score": risk_on,
        "risk_off_score": risk_off,
        "institutional_flow_proxy_score": institutional_proxy,
        "participation_exhaustion_score": exhaustion,
        "defensive_transition_score": defensive,
        "offensive_transition_score": offensive,
        "sector_flow_map": sector_rotation,
        "capital_flow_regime": "DEFENSIVE" if defensive > offensive else "OFFENSIVE" if offensive > defensive else "MIXED",
        "source_consumption": {
            "phase54_multi_horizon": bool(multi_horizon_state),
            "breadth_intelligence": bool(breadth),
            "narrative_intelligence": bool(narrative),
            "meta_regime_intelligence": bool(meta_regime),
            "temporal_intelligence": bool(temporal),
            "replay_research_memory": bool(records),
        },
        "feeds": {
            "master_brain": "Capital-flow state is advisory sidecar context only.",
            "dynamic_risk_intelligence": "Phase 56 consumes migration, exhaustion, and defensive/offensive state.",
            "strategy_adaptation": "Flow regime can guide sandbox strategy hypotheses.",
            "no_trade_intelligence": "Exhaustion and defensive flow are research-only no-trade inputs.",
            "regime_intelligence": "Risk-on/off transition is persisted for future regime research.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "migration": migration, "risk_on": risk_on, "risk_off": risk_off, "flow_regime": state["capital_flow_regime"]})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_dynamic_risk_intelligence(
    previous: Dict[str, Any] | None = None,
    multi_horizon_state: Dict[str, Any] | None = None,
    capital_flow_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    multi_horizon_state = multi_horizon_state if isinstance(multi_horizon_state, dict) else _read_json(PHASE_PATHS["phase54"]["memory"])
    capital_flow_state = capital_flow_state if isinstance(capital_flow_state, dict) else _read_json(PHASE_PATHS["phase55"]["memory"])
    ctx = context if isinstance(context, dict) else {}
    decisions = final_decisions if isinstance(final_decisions, dict) else {}

    volatility = _safe_float(ctx.get("volatility_score"), 50.0) / 100.0
    confidence_payload = payloads.get("confidence_calibration", {})
    calibrated_confidence = _payload_score(confidence_payload, ("calibrated_confidence_score", "confidence_score"), 0.5)
    accuracy_drift = _payload_score(payloads.get("accuracy_validation", {}), ("validation_drift_score", "accuracy_warning_score", "closed_records_this_run"))
    adversarial = _payload_score(payloads.get("adversarial_intelligence", {}), ("adversarial_replay_signature_score", "institutional_bait_score"))
    synthetic_stress = _payload_score(payloads.get("synthetic_market", {}), ("synthetic_market_stress_index", "regime_stress_score"))
    goal_scores = payloads.get("autonomous_goal_management", {}).get("goal_priority_scores")
    goal_scores = goal_scores if isinstance(goal_scores, dict) else {}
    survival_goal = _safe_float(goal_scores.get("survival_first"), 0.0)
    drawdown_terms = _term_rate(records, ("drawdown", "loss streak", "stoploss", "sl hit", "failed"))
    horizon_conflict = _safe_float(multi_horizon_state.get("timeframe_conflict_score"), 0.0)
    horizon_pressure = _safe_float(multi_horizon_state.get("higher_timeframe_pressure_score"), 0.0)
    lower_instability = _safe_float(multi_horizon_state.get("lower_timeframe_instability_score"), 0.0)
    flow_migration = _safe_float(capital_flow_state.get("capital_migration_score"), 0.0)
    flow_exhaustion = _safe_float(capital_flow_state.get("participation_exhaustion_score"), 0.0)
    defensive = _safe_float(capital_flow_state.get("defensive_transition_score"), 0.0)
    exposure_caution = _score(max(volatility, horizon_conflict, lower_instability, flow_exhaustion, defensive, synthetic_stress))
    confidence_risk = _score((1.0 - calibrated_confidence) * 0.46 + accuracy_drift * 0.24 + horizon_conflict * 0.16 + adversarial * 0.14)
    drawdown_caution = _score(drawdown_terms * 0.46 + survival_goal * 0.24 + accuracy_drift * 0.16 + defensive * 0.14)
    regime_risk = _score(horizon_pressure * 0.28 + defensive * 0.24 + flow_migration * 0.18 + synthetic_stress * 0.16 + adversarial * 0.14)
    instability_reduction = _score(lower_instability * 0.30 + horizon_conflict * 0.24 + flow_exhaustion * 0.22 + adversarial * 0.24)
    stress_sizing = _score(max(exposure_caution, confidence_risk, drawdown_caution, regime_risk, instability_reduction))
    theoretical_shadow_size = round(max(0.0, 1.0 - stress_sizing), 4)
    state = {
        **_phase_base("phase56", previous, sources),
        "phase": "PHASE_56_DYNAMIC_RISK_INTELLIGENCE",
        "status": "OK" if multi_horizon_state or capital_flow_state or any(payloads.values()) or ctx else "WAITING_FOR_RISK_INPUTS",
        "connected": True,
        "phase54_consumed": bool(multi_horizon_state),
        "phase54_run_count_seen": multi_horizon_state.get("run_count"),
        "phase55_consumed": bool(capital_flow_state),
        "phase55_run_count_seen": capital_flow_state.get("run_count"),
        "volatility_aware_exposure_score": exposure_caution,
        "confidence_aware_risk_score": confidence_risk,
        "drawdown_aware_caution_score": drawdown_caution,
        "regime_aware_risk_score": regime_risk,
        "instability_aware_exposure_reduction_score": instability_reduction,
        "stress_aware_theoretical_sizing_score": stress_sizing,
        "theoretical_shadow_size_multiplier": theoretical_shadow_size,
        "risk_advisory": "REDUCE_THEORETICAL_EXPOSURE_IN_RESEARCH" if stress_sizing >= 0.6 else "NORMAL_RESEARCH_RISK_CONTEXT",
        "decision_context_seen": {"final_decision_count": len(decisions.get("ranked") or decisions.get("decisions") or [])},
        "source_consumption": {
            "phase54_multi_horizon": bool(multi_horizon_state),
            "phase55_capital_flow": bool(capital_flow_state),
            "confidence_calibration": bool(confidence_payload),
            "adversarial_intelligence": bool(payloads.get("adversarial_intelligence")),
            "synthetic_simulation": bool(payloads.get("synthetic_market")),
            "goal_management": bool(payloads.get("autonomous_goal_management")),
            "hierarchy_arbitration": bool(payloads.get("hierarchical_brain")),
        },
        "feeds": {
            "master_brain": "Risk context is advisory-only sidecar reporting.",
            "execution_safety": "No live sizing or order mutation; exposes caution fields only.",
            "no_trade_intelligence": "Stress/exposure reduction can guide future research.",
            "future_risk_adaptation": "Persists risk pressure history for later promotion review.",
            "explainability": "Risk scores explain why theoretical exposure should be reviewed.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "stress_sizing": stress_sizing, "shadow_size": theoretical_shadow_size, "risk_advisory": state["risk_advisory"]})
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
    for field in ("phase54_consumed", "phase54_run_count_seen", "phase55_consumed", "phase55_run_count_seen"):
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


def run_multi_horizon_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    evaluated_setups: List[Dict[str, Any]] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase54"]["memory"])
    state = build_multi_horizon_intelligence(previous=previous, master_input=master_input, context=context, evaluated_setups=evaluated_setups)
    return _persist("phase54", state, "TITAN Phase 54 Multi-Horizon Intelligence Report", ("horizon_alignment_scores", "horizon_agreement_score", "timeframe_conflict_score", "timing_synchronization_score", "higher_timeframe_pressure_score", "lower_timeframe_instability_score", "source_consumption"), ("horizon_alignment_scores", "horizon_agreement_score", "timeframe_conflict_score", "timing_synchronization_score", "higher_timeframe_pressure_score", "lower_timeframe_instability_score", "source_consumption"), write_files)


def run_capital_flow_intelligence(
    multi_horizon_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase55"]["memory"])
    state = build_capital_flow_intelligence(previous=previous, multi_horizon_state=multi_horizon_state, master_input=master_input, context=context)
    return _persist("phase55", state, "TITAN Phase 55 Capital Flow Intelligence Report", ("phase54_consumed", "phase54_run_count_seen", "sector_rotation_score", "capital_migration_score", "risk_on_score", "risk_off_score", "institutional_flow_proxy_score", "participation_exhaustion_score", "defensive_transition_score", "offensive_transition_score", "capital_flow_regime"), ("phase54_consumed", "phase54_run_count_seen", "sector_rotation_score", "capital_migration_score", "risk_on_score", "risk_off_score", "institutional_flow_proxy_score", "participation_exhaustion_score", "defensive_transition_score", "offensive_transition_score", "capital_flow_regime"), write_files)


def run_dynamic_risk_intelligence(
    multi_horizon_state: Dict[str, Any] | None = None,
    capital_flow_state: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase56"]["memory"])
    state = build_dynamic_risk_intelligence(previous=previous, multi_horizon_state=multi_horizon_state, capital_flow_state=capital_flow_state, context=context, final_decisions=final_decisions)
    return _persist("phase56", state, "TITAN Phase 56 Dynamic Risk Intelligence Report", ("phase54_consumed", "phase55_consumed", "phase54_run_count_seen", "phase55_run_count_seen", "volatility_aware_exposure_score", "confidence_aware_risk_score", "drawdown_aware_caution_score", "regime_aware_risk_score", "instability_aware_exposure_reduction_score", "stress_aware_theoretical_sizing_score", "theoretical_shadow_size_multiplier", "risk_advisory", "source_consumption"), ("phase54_consumed", "phase55_consumed", "phase54_run_count_seen", "phase55_run_count_seen", "volatility_aware_exposure_score", "confidence_aware_risk_score", "drawdown_aware_caution_score", "regime_aware_risk_score", "instability_aware_exposure_reduction_score", "stress_aware_theoretical_sizing_score", "theoretical_shadow_size_multiplier", "risk_advisory", "source_consumption"), write_files)


def run_roadmap_batch6_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase54 = run_multi_horizon_intelligence(master_input=master_input, context=context, evaluated_setups=evaluated_setups, write_files=write_files)
    phase55 = run_capital_flow_intelligence(multi_horizon_state=phase54, master_input=master_input, context=context, write_files=write_files)
    phase56 = run_dynamic_risk_intelligence(multi_horizon_state=phase54, capital_flow_state=phase55, context=context, final_decisions=final_decisions, write_files=write_files)
    return {
        "phase54_multi_horizon_intelligence": phase54,
        "phase55_capital_flow_intelligence": phase55,
        "phase56_dynamic_risk_intelligence": phase56,
        **_safety_flags(),
    }


if __name__ == "__main__":
    result = run_roadmap_batch6_intelligence(write_files=True)
    print("TITAN Roadmap Batch 6 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
