"""
TITAN Roadmap Batch 4 - Phases 48-50 advisory intelligence.

Persistent sidecars for synthetic market simulation, adversarial market
behavior, and explainable AI introspection. These engines read existing TITAN
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
STATE_VERSION = "48-50.0"
MAX_HISTORY = 100
MAX_ITEMS = 12
MAX_FILE_BYTES = 1_500_000
MAX_RECORDS = 400

PHASE_PATHS = {
    "phase48": {
        "memory": PROJECT_ROOT / "data" / "memory" / "synthetic_market_simulator_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "synthetic_market_simulator_status.json",
        "report": PROJECT_ROOT / "reports" / "synthetic_market_simulator_report.txt",
    },
    "phase49": {
        "memory": PROJECT_ROOT / "data" / "memory" / "adversarial_intelligence_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "adversarial_intelligence_status.json",
        "report": PROJECT_ROOT / "reports" / "adversarial_intelligence_report.txt",
    },
    "phase50": {
        "memory": PROJECT_ROOT / "data" / "memory" / "explainable_ai_engine_state.json",
        "runtime": PROJECT_ROOT / "data" / "runtime" / "explainable_ai_engine_status.json",
        "report": PROJECT_ROOT / "reports" / "explainable_ai_engine_report.txt",
    },
}

INPUT_PATHS = {
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
    "historical_experience_jsonl": PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    "strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "meta_regime": PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json",
    "crowd_psychology": PROJECT_ROOT / "data" / "memory" / "crowd_psychology_state.json",
    "temporal_intelligence": PROJECT_ROOT / "data" / "memory" / "temporal_intelligence_state.json",
    "market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_intelligence_state.json",
    "market_breadth": PROJECT_ROOT / "data" / "memory" / "market_breadth_intelligence_state.json",
    "trap_memory": PROJECT_ROOT / "data" / "memory" / "trap_fakeout_memory.json",
    "liquidity_memory": PROJECT_ROOT / "data" / "memory" / "institutional_liquidity_map_memory.json",
    "no_trade_memory": PROJECT_ROOT / "data" / "memory" / "no_trade_refinement_memory.json",
    "confidence_calibration": PROJECT_ROOT / "data" / "confidence_calibration" / "latest_confidence_calibration_report.json",
    "meta_learning": PROJECT_ROOT / "data" / "memory" / "meta_learning_state.json",
    "master_shadow": PROJECT_ROOT / "data" / "memory" / "master_shadow_memory.json",
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


def _text_blob(*values: Any) -> str:
    return " ".join(_safe_text(value).lower() for value in values if value is not None)


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
        text = _text_blob(
            row.get("semantic_labels"),
            row.get("trap_label"),
            row.get("fake_breakout_label"),
            row.get("liquidity_sweep_label"),
            row.get("failure_reason_label"),
            row.get("behavioral_pattern_label"),
            row.get("reason"),
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
    ):
        if key in ctx and key not in merged:
            merged[key] = ctx.get(key)
    return merged


def build_synthetic_market_simulator(
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
    losses = sum(1 for row in rows if _outcome(row) == "LOSS")
    loss_rate = losses / max(sum(1 for row in rows if _outcome(row) in {"WIN", "LOSS"}), 1)
    volatility_proxy = max(
        _safe_float(market.get("volatility_score"), 50.0) / 100.0,
        _safe_float((payloads.get("temporal_intelligence").get("timing_quality_score") if payloads.get("temporal_intelligence") else 0.5), 0.5),
    )
    breadth_weakness = _safe_float(payloads.get("market_breadth", {}).get("hidden_weakness_strength_score"), 0.0)
    crowd_instability = _safe_float(payloads.get("crowd_psychology", {}).get("crowd_instability_score"), 0.0)
    meta_risk = _safe_float(payloads.get("meta_regime", {}).get("global_meta_regime_risk_score"), 0.0)
    rare_event_rate = _term_rate(rows, ("panic", "crash", "gap", "shock", "capitulation", "liquidity sweep"))
    fakeout_rate = _term_rate(rows, ("fake breakout", "fakeout", "failed breakout", "trap", "whipsaw"))
    shock = _score(volatility_proxy * 0.36 + rare_event_rate * 0.24 + meta_risk * 0.24 + loss_rate * 0.16)
    liquidity = _score((1.0 - (_safe_float(market.get("liquidity_score"), 50.0) / 100.0)) * 0.30 + breadth_weakness * 0.36 + rare_event_rate * 0.18 + loss_rate * 0.16)
    fake_breakout = _score(fakeout_rate * 0.44 + crowd_instability * 0.20 + breadth_weakness * 0.16 + loss_rate * 0.20)
    panic = _score(crowd_instability * 0.34 + shock * 0.24 + rare_event_rate * 0.22 + meta_risk * 0.20)
    regime_stress = _score(meta_risk * 0.40 + shock * 0.22 + liquidity * 0.18 + fake_breakout * 0.10 + panic * 0.10)
    rare_replay = _score(rare_event_rate * 0.50 + loss_rate * 0.20 + shock * 0.30)
    aggregate = _score((shock + liquidity + fake_breakout + panic + regime_stress + rare_replay) / 6.0)
    state = {
        **_phase_base("phase48", previous, sources),
        "phase": "PHASE_48_SYNTHETIC_MARKET_SIMULATOR",
        "status": "OK" if rows or any(payloads.values()) or market else "WAITING_FOR_REPLAY_AND_CONTEXT_INPUTS",
        "connected": True,
        "simulation_count": _safe_int(previous.get("simulation_count"), 0) + 6,
        "volatility_shock_score": shock,
        "liquidity_collapse_score": liquidity,
        "fake_breakout_environment_score": fake_breakout,
        "panic_simulation_score": panic,
        "regime_stress_score": regime_stress,
        "rare_event_replay_score": rare_replay,
        "synthetic_market_stress_index": aggregate,
        "scenario_scores": {
            "volatility_shock": shock,
            "liquidity_collapse": liquidity,
            "fake_breakout_environment": fake_breakout,
            "panic_simulation": panic,
            "regime_stress": regime_stress,
            "rare_event_replay": rare_replay,
        },
        "input_context": {
            "replay_records_seen": len(records),
            "evaluated_setups_seen": len(setups),
            "strategy_genome_consumed": bool(payloads.get("strategy_genome")),
            "meta_regime_consumed": bool(payloads.get("meta_regime")),
            "crowd_psychology_consumed": bool(payloads.get("crowd_psychology")),
            "temporal_intelligence_consumed": bool(payloads.get("temporal_intelligence")),
            "narrative_intelligence_consumed": bool(payloads.get("market_narrative")),
        },
        "feeds": {
            "replay_learning": "Prioritize rare-event, stress, and fakeout slices.",
            "no_trade_intelligence": "Review high synthetic stress as no-trade research context.",
            "confidence_systems": "Expose stress confidence caveats without ranking mutation.",
            "master_brain": "Synthetic stress remains advisory sidecar context.",
            "evolution_systems": "Use stress-index drift for sandbox genome evaluation.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "stress_index": aggregate, "simulation_count": state["simulation_count"]})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_adversarial_intelligence(
    previous: Dict[str, Any] | None = None,
    synthetic_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, records = _load_inputs()
    synthetic_state = synthetic_state if isinstance(synthetic_state, dict) else _read_json(PHASE_PATHS["phase48"]["memory"])
    market = _market_context(master_input, context)
    trap = payloads.get("trap_memory", {})
    pattern_buckets = trap.get("pattern_buckets") if isinstance(trap.get("pattern_buckets"), dict) else {}
    trap_loss_pressure = 0.0
    for bucket in pattern_buckets.values():
        if isinstance(bucket, dict):
            trap_loss_pressure = max(trap_loss_pressure, _safe_float(bucket.get("loss_rate"), 0.0) * min(1.0, _safe_float(bucket.get("samples"), 0.0) / 20.0))
    stop_hunt_rate = _term_rate(records, ("stop hunt", "stop run", "stoploss hunt", "liquidity sweep", "sweep"))
    trap_rate = _term_rate(records, ("trap", "bull trap", "bear trap", "fakeout", "fake breakout"))
    fake_momentum_rate = _term_rate(records, ("fake momentum", "failed follow", "exhaustion", "chase", "overconfidence"))
    liquidity_weakness = max(
        1.0 - (_safe_float(market.get("liquidity_score"), 50.0) / 100.0),
        _safe_float(payloads.get("market_breadth", {}).get("hidden_weakness_strength_score"), 0.0),
    )
    synthetic_fakeout = _safe_float(synthetic_state.get("fake_breakout_environment_score"), 0.0)
    synthetic_liquidity = _safe_float(synthetic_state.get("liquidity_collapse_score"), 0.0)
    stop_hunt = _score(stop_hunt_rate * 0.46 + liquidity_weakness * 0.24 + synthetic_liquidity * 0.20 + trap_loss_pressure * 0.10)
    trap_structure = _score(trap_rate * 0.38 + trap_loss_pressure * 0.28 + synthetic_fakeout * 0.24 + liquidity_weakness * 0.10)
    manipulation = _score(liquidity_weakness * 0.28 + stop_hunt * 0.24 + trap_structure * 0.24 + _safe_float(synthetic_state.get("panic_simulation_score"), 0.0) * 0.24)
    fake_momentum = _score(fake_momentum_rate * 0.42 + synthetic_fakeout * 0.28 + _safe_float(payloads.get("crowd_psychology", {}).get("overconfidence_score"), 0.0) * 0.30)
    bait = _score((stop_hunt + trap_structure + fake_momentum + manipulation) / 4.0)
    signature = _score(bait * 0.46 + _safe_float(synthetic_state.get("rare_event_replay_score"), 0.0) * 0.24 + trap_loss_pressure * 0.30)
    state = {
        **_phase_base("phase49", previous, sources),
        "phase": "PHASE_49_ADVERSARIAL_INTELLIGENCE",
        "status": "OK" if records or trap or synthetic_state else "WAITING_FOR_TRAP_REPLAY_AND_SYNTHETIC_INPUTS",
        "connected": True,
        "phase48_consumed": bool(synthetic_state),
        "phase48_run_count_seen": synthetic_state.get("run_count"),
        "stop_hunt_risk_score": stop_hunt,
        "trap_structure_score": trap_structure,
        "liquidity_manipulation_score": manipulation,
        "fake_momentum_score": fake_momentum,
        "institutional_bait_score": bait,
        "adversarial_replay_signature_score": signature,
        "deception_patterns": {
            "trap_memory_pattern_count": len(pattern_buckets),
            "stop_hunt_term_rate": round(stop_hunt_rate, 4),
            "trap_term_rate": round(trap_rate, 4),
            "fake_momentum_term_rate": round(fake_momentum_rate, 4),
        },
        "feeds": {
            "execution_safety": "Expose deceptive-market warnings as advisory inputs only.",
            "no_trade_intelligence": "Use trap/signature clusters for no-trade research.",
            "strategy_adaptation": "Sandbox strategy families against adversarial replay signatures.",
            "regime_intelligence": "Treat deception pressure as regime context, not ranking authority.",
            "master_brain": "Adversarial state remains a report sidecar.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "signature": signature, "bait": bait})
    state["history"] = history[-MAX_HISTORY:]
    return state


def build_explainable_ai_engine(
    previous: Dict[str, Any] | None = None,
    synthetic_state: Dict[str, Any] | None = None,
    adversarial_state: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources, _records = _load_inputs()
    synthetic_state = synthetic_state if isinstance(synthetic_state, dict) else _read_json(PHASE_PATHS["phase48"]["memory"])
    adversarial_state = adversarial_state if isinstance(adversarial_state, dict) else _read_json(PHASE_PATHS["phase49"]["memory"])
    decisions = final_decisions if isinstance(final_decisions, dict) else {}
    contradiction_terms = Counter()
    confidence = payloads.get("confidence_calibration", {})
    narrative = payloads.get("market_narrative", {})
    crowd = payloads.get("crowd_psychology", {})
    genome = payloads.get("strategy_genome", {})
    meta = payloads.get("meta_learning", {}) or payloads.get("meta_regime", {})
    no_trade = payloads.get("no_trade_memory", {})
    if _safe_float(synthetic_state.get("synthetic_market_stress_index"), 0.0) >= 0.55:
        contradiction_terms["high_synthetic_stress"] += 1
    if _safe_float(adversarial_state.get("adversarial_replay_signature_score"), 0.0) >= 0.55:
        contradiction_terms["adversarial_signature_pressure"] += 1
    if _safe_float(confidence.get("calibrated_confidence_score"), 50.0) < 45:
        contradiction_terms["weak_calibrated_confidence"] += 1
    if _safe_float(narrative.get("narrative_contradiction_score"), 0.0) >= 0.45:
        contradiction_terms["narrative_contradiction"] += 1
    decision_count = len(decisions.get("ranked") or decisions.get("decisions") or []) if decisions else 0
    contribution = {
        "synthetic_market_simulator": _safe_float(synthetic_state.get("synthetic_market_stress_index"), 0.0),
        "adversarial_intelligence": _safe_float(adversarial_state.get("adversarial_replay_signature_score"), 0.0),
        "confidence_calibration": _safe_float(confidence.get("calibrated_confidence_score"), 50.0) / 100.0 if confidence else 0.0,
        "narrative_intelligence": _safe_float(narrative.get("narrative_persistence_score"), 0.0),
        "crowd_psychology": _safe_float(crowd.get("crowd_instability_score"), 0.0),
        "strategy_genome": min(1.0, _safe_float(genome.get("family_count") or len(genome.get("families", {}) if isinstance(genome.get("families"), dict) else {}), 0.0) / 20.0),
        "meta_learning": _safe_float(meta.get("learning_pressure_score") or meta.get("global_meta_regime_risk_score"), 0.0),
        "no_trade_intelligence": _safe_float(no_trade.get("danger_score") or no_trade.get("no_trade_score"), 0.0) / 100.0 if no_trade else 0.0,
    }
    explanation_depth = _score(sum(1 for value in contribution.values() if value > 0.0) / max(len(contribution), 1))
    contradiction_score = _score(len(contradiction_terms) / 6.0)
    confidence_explanation = "CALIBRATED_CONFIDENCE_AVAILABLE" if confidence else "CONFIDENCE_INPUT_MISSING_NEUTRAL"
    if contradiction_score >= 0.5:
        reasoning_summary = "Multiple advisory systems disagree or report elevated stress; explanation layer recommends research review only."
    elif explanation_depth >= 0.5:
        reasoning_summary = "Advisory inputs are sufficiently populated for introspection; no live authority is assigned."
    else:
        reasoning_summary = "Explanation layer is connected but waiting for richer advisory inputs."
    state = {
        **_phase_base("phase50", previous, sources),
        "phase": "PHASE_50_EXPLAINABLE_AI_ENGINE",
        "status": "OK" if synthetic_state or adversarial_state or any(payloads.values()) or decisions else "WAITING_FOR_ADVISORY_CONTEXT",
        "connected": True,
        "phase48_consumed": bool(synthetic_state),
        "phase48_run_count_seen": synthetic_state.get("run_count"),
        "phase49_consumed": bool(adversarial_state),
        "phase49_run_count_seen": adversarial_state.get("run_count"),
        "engine_contribution_trace": contribution,
        "reasoning_summary": reasoning_summary,
        "contradiction_explanations": dict(contradiction_terms.most_common(MAX_ITEMS)),
        "contradiction_score": contradiction_score,
        "confidence_explanation": confidence_explanation,
        "regime_explanation": "META_REGIME_AVAILABLE" if payloads.get("meta_regime") else "META_REGIME_MISSING_NEUTRAL",
        "narrative_explanation": narrative.get("dominant_narrative") or "NARRATIVE_INPUT_MISSING_NEUTRAL",
        "strategy_genome_explanation": "STRATEGY_GENOME_AVAILABLE" if genome else "STRATEGY_GENOME_MISSING_NEUTRAL",
        "no_trade_explanation": "NO_TRADE_MEMORY_AVAILABLE" if no_trade else "NO_TRADE_MEMORY_MISSING_NEUTRAL",
        "explanation_depth_score": explanation_depth,
        "decision_context_seen": {"final_decision_count": decision_count, "context_mode": (context or {}).get("trading_mode") if isinstance(context, dict) else None},
        "feeds": {
            "consciousness_meta_reasoning": "Turns advisory disagreement into explicit introspection.",
            "replay_interpretation": "Labels why stress/deception mattered in replay review.",
            "evolution_systems": "Explains which advisory engines influenced sandbox hypotheses.",
            "debugging_introspection": "Surfaces missing, contradictory, and high-pressure inputs.",
            "future_learning_systems": "Persists explanation traces for later research.",
        },
    }
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append({"generated_at": state["generated_at"], "explanation_depth": explanation_depth, "contradiction_score": contradiction_score})
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
    for field in ("phase48_consumed", "phase48_run_count_seen", "phase49_consumed", "phase49_run_count_seen"):
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


def run_synthetic_market_simulator(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    evaluated_setups: List[Dict[str, Any]] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase48"]["memory"])
    state = build_synthetic_market_simulator(previous=previous, master_input=master_input, context=context, evaluated_setups=evaluated_setups)
    return _persist(
        "phase48",
        state,
        "TITAN Phase 48 Synthetic Market Simulator Report",
        ("simulation_count", "volatility_shock_score", "liquidity_collapse_score", "fake_breakout_environment_score", "panic_simulation_score", "regime_stress_score", "rare_event_replay_score", "synthetic_market_stress_index"),
        ("simulation_count", "volatility_shock_score", "liquidity_collapse_score", "fake_breakout_environment_score", "panic_simulation_score", "regime_stress_score", "rare_event_replay_score", "synthetic_market_stress_index"),
        write_files,
    )


def run_adversarial_intelligence(
    synthetic_state: Dict[str, Any] | None = None,
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase49"]["memory"])
    state = build_adversarial_intelligence(previous=previous, synthetic_state=synthetic_state, master_input=master_input, context=context)
    return _persist(
        "phase49",
        state,
        "TITAN Phase 49 Adversarial Intelligence Report",
        ("stop_hunt_risk_score", "trap_structure_score", "liquidity_manipulation_score", "fake_momentum_score", "institutional_bait_score", "adversarial_replay_signature_score"),
        ("phase48_consumed", "phase48_run_count_seen", "stop_hunt_risk_score", "trap_structure_score", "liquidity_manipulation_score", "fake_momentum_score", "institutional_bait_score", "adversarial_replay_signature_score"),
        write_files,
    )


def run_explainable_ai_engine(
    synthetic_state: Dict[str, Any] | None = None,
    adversarial_state: Dict[str, Any] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    previous = _read_json(PHASE_PATHS["phase50"]["memory"])
    state = build_explainable_ai_engine(previous=previous, synthetic_state=synthetic_state, adversarial_state=adversarial_state, final_decisions=final_decisions, context=context)
    return _persist(
        "phase50",
        state,
        "TITAN Phase 50 Explainable AI Engine Report",
        ("engine_contribution_trace", "reasoning_summary", "contradiction_explanations", "contradiction_score", "confidence_explanation", "regime_explanation", "narrative_explanation", "strategy_genome_explanation", "no_trade_explanation", "explanation_depth_score"),
        ("phase48_consumed", "phase49_consumed", "phase48_run_count_seen", "phase49_run_count_seen", "engine_contribution_trace", "reasoning_summary", "contradiction_score", "explanation_depth_score"),
        write_files,
    )


def run_roadmap_batch4_intelligence(
    master_input: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    phase48 = run_synthetic_market_simulator(master_input=master_input, context=context, evaluated_setups=evaluated_setups, write_files=write_files)
    phase49 = run_adversarial_intelligence(synthetic_state=phase48, master_input=master_input, context=context, write_files=write_files)
    phase50 = run_explainable_ai_engine(synthetic_state=phase48, adversarial_state=phase49, final_decisions=final_decisions, context=context, write_files=write_files)
    return {
        "phase48_synthetic_market_simulator": phase48,
        "phase49_adversarial_intelligence": phase49,
        "phase50_explainable_ai_engine": phase50,
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
    result = run_roadmap_batch4_intelligence(write_files=True)
    print("TITAN Roadmap Batch 4 refreshed")
    for key, state in result.items():
        if isinstance(state, dict) and state.get("phase"):
            print(key, state.get("status"), state.get("run_count"))
