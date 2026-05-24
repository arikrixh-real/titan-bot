"""
TITAN Phase 43 - Meta-Regime Intelligence.

Higher-order advisory intelligence for regime transitions, instability, hidden
market-state changes, and strategy/regime mismatch. It reads only persisted
local artifacts and never mutates live ranking, scanner output, execution,
broker state, Telegram, Supabase, dashboards, or live order behavior.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "meta_regime_intelligence_state.json"
RUNTIME_STATUS_PATH = PROJECT_ROOT / "data" / "runtime" / "meta_regime_intelligence_status.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "meta_regime_intelligence_report.txt"

MEMORY_INPUTS = {
    "phase42_strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "advanced_regime": PROJECT_ROOT / "data" / "memory" / "advanced_regime_intelligence_memory.json",
    "historical_regime_transition": PROJECT_ROOT / "data" / "memory" / "historical_regime_transition_memory.json",
    "transition_instability": PROJECT_ROOT / "data" / "memory" / "transition_instability_memory.json",
    "volatility_memory": PROJECT_ROOT / "data" / "memory" / "volatility_expansion_compression_memory.json",
    "trap_memory": PROJECT_ROOT / "data" / "memory" / "trap_fakeout_memory.json",
    "no_trade_refinement": PROJECT_ROOT / "data" / "memory" / "no_trade_refinement_memory.json",
    "accuracy_validation": PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json",
    "meta_learning": PROJECT_ROOT / "data" / "memory" / "meta_learning_state.json",
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
}

STATE_VERSION = "43.0"
MAX_SIGNALS = 24
MAX_HISTORY = 100


def _now_utc() -> str:
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
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score(value: float) -> float:
    return round(_clamp01(value), 4)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


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
        "alert_filter_mutation": False,
        "live_order_behavior": False,
        "recommended_live_weight": 0.0,
        "rank_adjustment": 0.0,
    }


def _load_inputs() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    payloads: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, Dict[str, Any]] = {}
    now_ts = datetime.now(timezone.utc).timestamp()
    for name, path in MEMORY_INPUTS.items():
        payload = _read_json(path)
        payloads[name] = payload
        info = {
            "path": _relative(path),
            "available": bool(payload),
            "status": "MISSING",
            "age_seconds": None,
        }
        try:
            if path.exists():
                info["age_seconds"] = round(max(0.0, now_ts - path.stat().st_mtime), 3)
                info["status"] = "OK" if payload else "EMPTY_OR_INVALID"
        except Exception:
            info["status"] = "STAT_ERROR"
        sources[name] = info
    return payloads, sources


def _active_regime(advanced: Dict[str, Any]) -> Dict[str, Any]:
    active = advanced.get("active_regime") if isinstance(advanced.get("active_regime"), dict) else {}
    return {
        "primary": _safe_text(active.get("primary"), "UNKNOWN").upper(),
        "previous_primary": _safe_text(active.get("previous_primary"), "UNKNOWN").upper(),
        "confidence": _score(_safe_float(active.get("confidence"), 0.0)),
        "transition_detected": bool(active.get("transition_detected")),
        "transition_confirmed": bool(active.get("transition_confirmed")),
        "transition_strength": _score(_safe_float(active.get("transition_strength"), 0.0)),
    }


def _instability_score(transition_instability: Dict[str, Any]) -> float:
    buckets = transition_instability.get("instability_buckets") if isinstance(transition_instability.get("instability_buckets"), dict) else {}
    if not buckets:
        return 0.0
    values = []
    for name, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        weight = 1.0
        if str(name).upper() in {"WHIPSAW", "UNCONFIRMED"}:
            weight = 1.25
        values.append(_safe_float(bucket.get("loss_rate"), 0.0) * min(1.0, _safe_float(bucket.get("samples"), 0.0) / 20.0) * weight)
    return _score(max(values or [0.0]))


def _volatility_shift_score(volatility: Dict[str, Any]) -> float:
    buckets = volatility.get("phase_buckets") if isinstance(volatility.get("phase_buckets"), dict) else {}
    expansion = buckets.get("EXPANSION") if isinstance(buckets.get("EXPANSION"), dict) else {}
    compression = buckets.get("COMPRESSION") if isinstance(buckets.get("COMPRESSION"), dict) else {}
    expansion_pressure = min(1.0, _safe_float(expansion.get("samples"), 0.0) / 30.0)
    compression_pressure = min(1.0, _safe_float(compression.get("samples"), 0.0) / 30.0)
    expansion_loss = _safe_float(expansion.get("loss_rate"), 1.0 - _safe_float(expansion.get("win_rate"), 0.0))
    compression_loss = _safe_float(compression.get("loss_rate"), 1.0 - _safe_float(compression.get("win_rate"), 0.0))
    return _score(max(expansion_pressure * expansion_loss, compression_pressure * compression_loss))


def _trap_pressure_score(trap: Dict[str, Any]) -> float:
    buckets = trap.get("pattern_buckets") if isinstance(trap.get("pattern_buckets"), dict) else {}
    return _score(max((_safe_float(item.get("loss_rate"), 0.0) * min(1.0, _safe_float(item.get("samples"), 0.0) / 20.0)) for item in buckets.values() if isinstance(item, dict)) if buckets else 0.0)


def _no_trade_pressure_score(no_trade: Dict[str, Any]) -> float:
    if not no_trade:
        return 0.0
    score = 0.0
    for key in ("danger_score", "no_trade_score", "memory_quality_score", "risk_score"):
        score = max(score, _safe_float(no_trade.get(key), 0.0) / 100.0)
    buckets = no_trade.get("refinement_buckets") if isinstance(no_trade.get("refinement_buckets"), dict) else {}
    for item in buckets.values():
        if isinstance(item, dict):
            score = max(score, _safe_float(item.get("loss_rate"), 0.0))
    return _score(score)


def _genome_mismatch(payloads: Dict[str, Dict[str, Any]], active: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    genome = payloads.get("phase42_strategy_genome", {})
    current = active.get("primary") or genome.get("active_regime") or "UNKNOWN"
    compatibility = genome.get("regime_family_compatibility") if isinstance(genome.get("regime_family_compatibility"), dict) else {}
    current_families = compatibility.get(current) if isinstance(compatibility.get(current), dict) else {}
    families = genome.get("families") if isinstance(genome.get("families"), dict) else {}
    signals: List[Dict[str, Any]] = []
    worst = 0.0
    for family, stats in families.items():
        if not isinstance(stats, dict):
            continue
        affinity = current_families.get(family) if isinstance(current_families.get(family), dict) else {}
        compat = _safe_float(affinity.get("compatibility_score"), 0.0)
        decay = _safe_float(stats.get("decay_score"), 0.0)
        drift = _safe_float(stats.get("drift_score"), 0.0)
        durability = _safe_float(stats.get("durability_score") or stats.get("stability_score"), 0.0)
        mismatch = _score((1.0 - compat) * 0.42 + decay * 0.24 + drift * 0.19 + (1.0 - durability) * 0.15)
        worst = max(worst, mismatch)
        if mismatch >= 0.35:
            signals.append(
                {
                    "family": family,
                    "active_regime": current,
                    "mismatch_score": mismatch,
                    "compatibility_score": round(compat, 4),
                    "decay_score": round(decay, 4),
                    "drift_score": round(drift, 4),
                    "advisory_action": "Review this strategy/regime pairing in replay before promotion.",
                    "affects_live_ranking": False,
                    "affects_execution": False,
                }
            )
    signals.sort(key=lambda item: item["mismatch_score"], reverse=True)
    return _score(worst), signals[:MAX_SIGNALS]


def build_meta_regime_state(previous: Dict[str, Any] | None = None) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    payloads, sources = _load_inputs()
    active = _active_regime(payloads.get("advanced_regime", {}))
    instability = _instability_score(payloads.get("transition_instability", {}))
    volatility = _volatility_shift_score(payloads.get("volatility_memory", {}))
    trap = _trap_pressure_score(payloads.get("trap_memory", {}))
    no_trade = _no_trade_pressure_score(payloads.get("no_trade_refinement", {}))
    mismatch, mismatch_signals = _genome_mismatch(payloads, active)
    hidden_state = _score((volatility * 0.32) + (trap * 0.25) + (no_trade * 0.20) + (instability * 0.23))
    transition = _score((_safe_float(active.get("transition_strength")) * 0.42) + (instability * 0.33) + (volatility * 0.25))
    regime_mismatch = _score((mismatch * 0.72) + (no_trade * 0.15) + (trap * 0.13))
    global_risk = _score(max(transition, hidden_state, regime_mismatch) * 0.70 + ((transition + hidden_state + regime_mismatch) / 3.0) * 0.30)

    run_count = _safe_int(previous.get("run_count"), 0) + 1
    now = _now_utc()
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    history.append(
        {
            "generated_at": now,
            "active_regime": active.get("primary"),
            "transition_risk_score": transition,
            "hidden_state_change_score": hidden_state,
            "strategy_regime_mismatch_score": regime_mismatch,
            "global_meta_regime_risk_score": global_risk,
        }
    )
    history = history[-MAX_HISTORY:]

    phase42 = payloads.get("phase42_strategy_genome", {})
    state = {
        "version": STATE_VERSION,
        "phase": "PHASE_43_META_REGIME_INTELLIGENCE",
        "status": "OK" if phase42 else "WAITING_FOR_PHASE42",
        "generated_at": now,
        "first_seen_at": previous.get("first_seen_at") or now,
        "previous_generated_at": previous.get("generated_at"),
        "run_count": run_count,
        "continued_from_previous_state": bool(previous),
        "previous_run_count": previous.get("run_count", 0),
        "phase42_consumed": bool(phase42),
        "phase42_run_count_seen": phase42.get("run_count"),
        "phase42_state_path": _relative(MEMORY_INPUTS["phase42_strategy_genome"]),
        "active_regime": active,
        "transition_risk_score": transition,
        "hidden_state_change_score": hidden_state,
        "strategy_regime_mismatch_score": regime_mismatch,
        "global_meta_regime_risk_score": global_risk,
        "instability_transition_score": instability,
        "volatility_shift_score": volatility,
        "trap_pressure_score": trap,
        "no_trade_pressure_score": no_trade,
        "strategy_regime_mismatch_signals": mismatch_signals,
        "advisory_context": {
            "master_brain": "Use as report-side context only; final_decision_engine remains ranking owner.",
            "consciousness_meta_layers": "Highlight unstable state changes and mismatch hypotheses for review.",
            "evolution_systems": "Route weak regime/strategy pairings to sandbox research only.",
            "replay_learning": "Prioritize replay slices around transition and mismatch signals.",
            "strategy_genome_adaptation": "Phase 43 consumed Phase 42 durability/affinity state.",
        },
        "history": history,
        "memory_sources": sources,
        "state_path": _relative(MEMORY_PATH),
        "runtime_status_path": _relative(RUNTIME_STATUS_PATH),
        "report_path": _relative(REPORT_PATH),
        "safety_flags": _safety_flags(),
        **_safety_flags(),
    }
    return state


def render_meta_regime_report(state: Dict[str, Any]) -> str:
    lines = [
        "TITAN PHASE 43 META-REGIME INTELLIGENCE REPORT",
        "=" * 60,
        f"Updated: {state.get('generated_at')}",
        f"Status: {state.get('status')}",
        f"Run count: {state.get('run_count')} | Continued: {state.get('continued_from_previous_state')}",
        f"Phase42 consumed: {state.get('phase42_consumed')} | Phase42 run seen: {state.get('phase42_run_count_seen')}",
        "",
        "Safety",
        "- advisory_only=true research_only=true shadow_mode=true",
        "- affects_live_ranking=false affects_execution=false broker_mutation=false telegram_mutation=false supabase_mutation=false",
        "- recommended_live_weight=0.0 rank_adjustment=0.0",
        "",
        "Scores",
        f"- transition_risk_score={state.get('transition_risk_score')}",
        f"- hidden_state_change_score={state.get('hidden_state_change_score')}",
        f"- strategy_regime_mismatch_score={state.get('strategy_regime_mismatch_score')}",
        f"- global_meta_regime_risk_score={state.get('global_meta_regime_risk_score')}",
        "",
        "Strategy/Regime Mismatch Signals",
    ]
    for item in state.get("strategy_regime_mismatch_signals", [])[:12]:
        lines.append(
            f"- {item.get('family')} in {item.get('active_regime')}: "
            f"mismatch={item.get('mismatch_score')}, compatibility={item.get('compatibility_score')}, "
            f"decay={item.get('decay_score')}, drift={item.get('drift_score')}"
        )
    if not state.get("strategy_regime_mismatch_signals"):
        lines.append("- None observed")
    lines.extend(["", "Memory Sources"])
    for name, item in sorted((state.get("memory_sources") or {}).items()):
        lines.append(f"- {name}: available={item.get('available')}, status={item.get('status')}, path={item.get('path')}")
    return "\n".join(lines) + "\n"


def refresh_meta_regime_intelligence(write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(MEMORY_PATH)
    state = build_meta_regime_state(previous=previous)
    runtime_status = {
        "phase": state["phase"],
        "status": state["status"],
        "generated_at": state["generated_at"],
        "run_count": state["run_count"],
        "continued_from_previous_state": state["continued_from_previous_state"],
        "phase42_consumed": state["phase42_consumed"],
        "phase42_run_count_seen": state.get("phase42_run_count_seen"),
        "transition_risk_score": state["transition_risk_score"],
        "hidden_state_change_score": state["hidden_state_change_score"],
        "strategy_regime_mismatch_score": state["strategy_regime_mismatch_score"],
        "global_meta_regime_risk_score": state["global_meta_regime_risk_score"],
        "state_path": state["state_path"],
        "report_path": state["report_path"],
        "safety_flags": state["safety_flags"],
        **_safety_flags(),
    }
    state["runtime_status"] = runtime_status
    if write_files:
        _write_json(MEMORY_PATH, state)
        _write_json(RUNTIME_STATUS_PATH, runtime_status)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_meta_regime_report(state), encoding="utf-8")
    return state


def run_meta_regime_intelligence(write_files: bool = True) -> Dict[str, Any]:
    return refresh_meta_regime_intelligence(write_files=write_files)


if __name__ == "__main__":
    result = run_meta_regime_intelligence(write_files=True)
    print("TITAN Phase 43 Meta-Regime Intelligence refreshed")
    print("Status:", result.get("status"))
    print("Run count:", result.get("run_count"))
