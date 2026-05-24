"""
TITAN Phase 41 - Meta-Learning Engine.

Consumes Phase 40 accuracy state plus replay, reinforcement, adaptive, and
memory artifacts to create advisory learning priorities. It persists state and
never changes live ranking, execution, alerts, scanners, broker state,
Telegram, Supabase, dashboards, or live orders.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACCURACY_STATE_PATH = PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json"
META_STATE_PATH = PROJECT_ROOT / "data" / "memory" / "meta_learning_state.json"
RUNTIME_STATUS_PATH = PROJECT_ROOT / "data" / "runtime" / "meta_learning_status.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "meta_learning_report.txt"

STATE_VERSION = "41.0"
MAX_PRIORITIES = 24

MEMORY_INPUTS = {
    "reinforcement_learning": PROJECT_ROOT / "data" / "memory" / "reinforcement_learning_memory.json",
    "adaptive_intelligence": PROJECT_ROOT / "data" / "memory" / "adaptive_intelligence_state.json",
    "historical_adaptive_intelligence": PROJECT_ROOT / "data" / "memory" / "historical_adaptive_intelligence_state.json",
    "strategy_family": PROJECT_ROOT / "data" / "memory" / "strategy_family_memory.json",
    "strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
    "meta_evolution": PROJECT_ROOT / "data" / "memory" / "meta_evolution_memory.json",
    "memory_consolidation_index": PROJECT_ROOT / "data" / "memory_consolidation" / "strategic_memory_index.json",
    "historical_replay_progress": PROJECT_ROOT / "data" / "runtime" / "historical_replay_progress.json",
}


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


def _memory_freshness() -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    payloads: Dict[str, Any] = {}
    freshness: Dict[str, Dict[str, Any]] = {}
    now_ts = datetime.now(timezone.utc).timestamp()
    for name, path in MEMORY_INPUTS.items():
        payload = _read_json(path)
        payloads[name] = payload
        info = {
            "path": _relative(path),
            "available": bool(payload),
            "age_seconds": None,
            "status": "MISSING",
        }
        try:
            if path.exists():
                info["age_seconds"] = round(max(0.0, now_ts - path.stat().st_mtime), 3)
                info["status"] = "OK" if payload else "EMPTY_OR_INVALID"
        except Exception:
            info["status"] = "STAT_ERROR"
        freshness[name] = info
    return payloads, freshness


def _bucket_priority(area: str, item: Dict[str, Any], memory_factor: float = 0.0) -> Dict[str, Any]:
    samples = int(_safe_float(item.get("closed_samples") or item.get("samples"), 0.0))
    accuracy = _safe_float(item.get("accuracy"), 0.0)
    fp = _safe_float(item.get("false_positive_rate"), 0.0)
    fn = _safe_float(item.get("false_negative_rate"), 0.0)
    weakness = max(0.0, 1.0 - accuracy)
    sample_conf = min(1.0, samples / 50.0)
    score = _clamp01((weakness * 0.48) + (fp * 0.22) + (fn * 0.18) + (sample_conf * 0.07) + (memory_factor * 0.05))
    name = _safe_text(item.get("name"), "UNKNOWN")
    if score >= 0.65:
        urgency = "HIGH"
    elif score >= 0.35:
        urgency = "MEDIUM"
    else:
        urgency = "LOW"
    return {
        "area": area,
        "name": name,
        "priority_score": round(score, 4),
        "urgency": urgency,
        "closed_samples": samples,
        "accuracy": accuracy,
        "false_positive_rate": fp,
        "false_negative_rate": fn,
        "advisory_action": f"Study {area}={name} in replay/paper memory before any promotion.",
        "affects_live_ranking": False,
        "affects_execution": False,
    }


def _memory_importance(memory_payloads: Dict[str, Any], accuracy_state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    total_closed = int(_safe_float((accuracy_state.get("overall_accuracy") or {}).get("closed_samples"), 0.0))
    base_conf = min(1.0, total_closed / 100.0)
    weights: Dict[str, Dict[str, Any]] = {}
    for name, payload in memory_payloads.items():
        available = bool(payload)
        sample_hint = 0.0
        if isinstance(payload, dict):
            for key in ("records_processed", "total_trades", "total_closed_trades", "records_loaded", "last_records_generated"):
                sample_hint = max(sample_hint, _safe_float(payload.get(key), 0.0))
            runtime = payload.get("runtime_status") if isinstance(payload.get("runtime_status"), dict) else {}
            sample_hint = max(sample_hint, _safe_float(runtime.get("records_processed"), 0.0))
        sample_conf = min(1.0, sample_hint / 100.0)
        importance = _clamp01((0.35 if available else 0.0) + (base_conf * 0.30) + (sample_conf * 0.35))
        weights[name] = {
            "importance_weight": round(importance, 4),
            "sample_hint": round(sample_hint, 3),
            "available": available,
            "advisory_only": True,
            "live_weight": 0.0,
            "rank_adjustment": 0.0,
        }
    return weights


def _weak_groups(accuracy_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    for area, key in (("strategy", "strategy_accuracy"), ("regime", "regime_accuracy"), ("sector", "sector_accuracy")):
        payload = accuracy_state.get(key) if isinstance(accuracy_state.get(key), dict) else {}
        for name, bucket in payload.items():
            if not isinstance(bucket, dict):
                continue
            row = dict(bucket)
            row["name"] = name
            groups.append(_bucket_priority(area, row))
    groups.sort(key=lambda item: (item["priority_score"], item["closed_samples"]), reverse=True)
    return groups[:MAX_PRIORITIES]


def _derive_priorities(accuracy_state: Dict[str, Any], memory_weights: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    priorities = []
    weak_areas = accuracy_state.get("weak_areas") if isinstance(accuracy_state.get("weak_areas"), list) else []
    memory_factor = max((_safe_float(item.get("importance_weight")) for item in memory_weights.values()), default=0.0)
    for item in weak_areas:
        if isinstance(item, dict):
            priorities.append(_bucket_priority(_safe_text(item.get("area"), "unknown"), item, memory_factor))
    priorities.extend(_weak_groups(accuracy_state))

    if not priorities:
        closed = int(_safe_float((accuracy_state.get("overall_accuracy") or {}).get("closed_samples"), 0.0))
        priorities.append({
            "area": "global",
            "name": "OUTCOME_SAMPLE_COLLECTION",
            "priority_score": 0.55 if closed < 30 else 0.25,
            "urgency": "MEDIUM" if closed < 30 else "LOW",
            "closed_samples": closed,
            "accuracy": (accuracy_state.get("overall_accuracy") or {}).get("accuracy", 0.0),
            "advisory_action": "Increase validated paper/replay outcome samples before promotion review.",
            "affects_live_ranking": False,
            "affects_execution": False,
        })

    deduped = {}
    for item in priorities:
        key = f"{item.get('area')}|{item.get('name')}"
        existing = deduped.get(key)
        if not existing or _safe_float(item.get("priority_score")) > _safe_float(existing.get("priority_score")):
            deduped[key] = item
    ordered = list(deduped.values())
    ordered.sort(key=lambda item: (_safe_float(item.get("priority_score")), _safe_float(item.get("closed_samples"))), reverse=True)
    return ordered[:MAX_PRIORITIES]


def build_meta_learning_state(
    accuracy_state: Dict[str, Any] | None = None,
    previous: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    accuracy = accuracy_state if isinstance(accuracy_state, dict) and accuracy_state else _read_json(ACCURACY_STATE_PATH)
    memory_payloads, memory_sources = _memory_freshness()
    weights = _memory_importance(memory_payloads, accuracy)
    priorities = _derive_priorities(accuracy, weights)
    weak_strategy_areas = [item for item in priorities if item.get("area") == "strategy"][:10]
    weak_regime_areas = [item for item in priorities if item.get("area") == "regime"][:10]

    run_count = int(_safe_float(previous.get("run_count"), 0.0)) + 1
    previous_priority_count = int(_safe_float(previous.get("priority_count"), 0.0))
    now = _now_utc()
    state = {
        "version": STATE_VERSION,
        "phase": "PHASE_41_META_LEARNING_ENGINE",
        "status": "OK" if accuracy else "WAITING_FOR_PHASE40",
        "generated_at": now,
        "first_seen_at": previous.get("first_seen_at") or now,
        "previous_generated_at": previous.get("generated_at"),
        "run_count": run_count,
        "continued_from_previous_state": bool(previous),
        "previous_run_count": previous.get("run_count", 0),
        "phase40_run_count_seen": accuracy.get("run_count"),
        "phase40_state_path": _relative(ACCURACY_STATE_PATH),
        "priority_count": len(priorities),
        "previous_priority_count": previous_priority_count,
        "learning_priorities": priorities,
        "memory_importance_weights": weights,
        "weak_strategy_areas": weak_strategy_areas,
        "weak_regime_areas": weak_regime_areas,
        "memory_sources": memory_sources,
        "state_path": _relative(META_STATE_PATH),
        "runtime_status_path": _relative(RUNTIME_STATUS_PATH),
        "report_path": _relative(REPORT_PATH),
        "safety_flags": _safety_flags(),
        **_safety_flags(),
    }
    return state


def render_meta_learning_report(state: Dict[str, Any]) -> str:
    lines = [
        "TITAN PHASE 41 META-LEARNING REPORT",
        "=" * 60,
        f"Updated: {state.get('generated_at')}",
        f"Status: {state.get('status')}",
        f"Run count: {state.get('run_count')} | Continued: {state.get('continued_from_previous_state')} | Phase40 run seen: {state.get('phase40_run_count_seen')}",
        "",
        "Safety",
        "- advisory_only=true research_only=true shadow_mode=true",
        "- affects_live_ranking=false affects_execution=false broker_mutation=false telegram_mutation=false supabase_mutation=false",
        "- recommended_live_weight=0.0 rank_adjustment=0.0",
        "",
        "Top Learning Priorities",
    ]
    for item in state.get("learning_priorities", [])[:12]:
        lines.append(
            f"- {item.get('urgency')} {item.get('area')} {item.get('name')}: "
            f"priority={item.get('priority_score')}, accuracy={item.get('accuracy')}, samples={item.get('closed_samples')}"
        )
    if not state.get("learning_priorities"):
        lines.append("- Waiting for Phase 40 accuracy state")
    lines.extend(["", "Memory Importance"])
    for name, item in sorted((state.get("memory_importance_weights") or {}).items()):
        lines.append(f"- {name}: weight={item.get('importance_weight')}, available={item.get('available')}, live_weight=0.0")
    return "\n".join(lines) + "\n"


def refresh_meta_learning(accuracy_state: Dict[str, Any] | None = None, write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(META_STATE_PATH)
    state = build_meta_learning_state(accuracy_state=accuracy_state, previous=previous)
    runtime_status = {
        "phase": state["phase"],
        "status": state["status"],
        "generated_at": state["generated_at"],
        "run_count": state["run_count"],
        "continued_from_previous_state": state["continued_from_previous_state"],
        "phase40_run_count_seen": state.get("phase40_run_count_seen"),
        "priority_count": state["priority_count"],
        "learning_priorities": state["learning_priorities"][:8],
        "weak_strategy_areas": state["weak_strategy_areas"],
        "weak_regime_areas": state["weak_regime_areas"],
        "state_path": state["state_path"],
        "report_path": state["report_path"],
        "safety_flags": state["safety_flags"],
        **_safety_flags(),
    }
    state["runtime_status"] = runtime_status
    if write_files:
        _write_json(META_STATE_PATH, state)
        _write_json(RUNTIME_STATUS_PATH, runtime_status)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_meta_learning_report(state), encoding="utf-8")
    return state


if __name__ == "__main__":
    result = refresh_meta_learning(write_files=True)
    print("TITAN Phase 41 Meta-Learning refreshed")
    print("Status:", result.get("status"))
    print("Run count:", result.get("run_count"))
