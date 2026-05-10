"""
TITAN Phase 10 - Master Shadow Intelligence Command Center.

Read-only observer-of-observers for existing TITAN shadow intelligence.

Safety:
- No ranking, execution, Telegram, broker/API, Supabase, scanner, or live-price
  integration.
- No network imports or calls.
- Uses compact local memory artifacts only.
- Never mutates caller inputs.
- Fails open on every exception.
"""

from __future__ import annotations

import ast
import json
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "reports" / "master_shadow_command_center.txt"
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "master_shadow_memory.json"

PHASE5_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "strategy_family_memory.json"
PHASE6_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "phase6_shadow_memory.json"
PHASE7_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "lifecycle_memory.json"
PHASE8_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "market_narrative_memory.json"
PHASE9_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "cross_setup_memory.json"

STATE_VERSION = "10.0"
PHASE10_SHADOW_MODE = True
MAX_FILE_BYTES = 1_000_000
MAX_REPORT_ITEMS = 10
REPORT_REFRESH_SECONDS = 3600
RUNTIME_BUDGET_SECONDS = 0.25

FORBIDDEN_IMPORTS = {
    "requests",
    "websocket",
    "websockets",
    "yfinance",
    "supabase",
    "data.live_price",
    "scanners",
    "alerts",
    "notifications",
    "titan_master_brain.input_aggregator",
    "engines.setup_engine",
}


def _now_text() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _top(items: Iterable[Any], limit: int = MAX_REPORT_ITEMS) -> List[Any]:
    return list(items or [])[:limit]


def _file_age_seconds(path: Path) -> float | None:
    try:
        if not path.exists():
            return None
        return max(0.0, datetime.now(IST).timestamp() - path.stat().st_mtime)
    except Exception:
        return None


def _read_json_limited(path: Path, layer_name: str) -> tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    try:
        display_path = str(path.relative_to(PROJECT_ROOT)) if path.is_absolute() else str(path)
    except Exception:
        display_path = str(path)

    freshness = {
        "available": False,
        "age_seconds": None,
        "path": display_path,
        "status": "MISSING",
    }
    warnings: List[str] = []

    try:
        if not path.exists():
            warnings.append(f"{layer_name}_memory_missing")
            return {}, freshness, warnings

        size = path.stat().st_size
        freshness["age_seconds"] = round(_file_age_seconds(path) or 0.0, 3)

        if size > MAX_FILE_BYTES:
            freshness["status"] = "OVERSIZED_SKIPPED"
            warnings.append(f"{layer_name}_memory_oversized")
            return {}, freshness, warnings

        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            freshness["status"] = "INVALID_SHAPE"
            warnings.append(f"{layer_name}_memory_invalid_shape")
            return {}, freshness, warnings

        freshness["available"] = True
        freshness["status"] = "OK"
        return data, freshness, warnings
    except Exception:
        freshness["status"] = "READ_ERROR"
        warnings.append(f"{layer_name}_memory_read_error")
        return {}, freshness, warnings


def _detect_forbidden_imports() -> List[str]:
    try:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        violations = []
        for item in imported:
            for forbidden in FORBIDDEN_IMPORTS:
                if item == forbidden or item.startswith(f"{forbidden}."):
                    violations.append(item)
        return sorted(set(violations))
    except Exception:
        return ["forbidden_import_check_failed_open"]


def _phase5_summary(memory: Dict[str, Any]) -> Dict[str, Any]:
    family_stats = memory.get("family_stats") or memory.get("setup_family_stats") or {}
    weak = memory.get("weak_families") or memory.get("correlated_weakness") or []
    strong = memory.get("strong_families") or memory.get("top_families") or []

    if isinstance(family_stats, dict) and family_stats:
        ranked = []
        for name, bucket in family_stats.items():
            score = 0.0
            if isinstance(bucket, dict):
                score = _safe_float(
                    bucket.get("win_rate")
                    or bucket.get("accuracy")
                    or bucket.get("avg_trade_health_score"),
                    0.0,
                )
            ranked.append({"family": str(name)[:80], "score": round(score, 4)})
        ranked.sort(key=lambda item: item["score"], reverse=True)
        strong = strong or ranked[:MAX_REPORT_ITEMS]

    return {
        "available": bool(memory),
        "total_closed_trades": _safe_int(memory.get("total_closed_trades")),
        "setup_family_strength": _top(strong),
        "weak_families": _top(weak),
    }


def _phase6_summary(memory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "available": bool(memory),
        "observed_setups": _safe_int(memory.get("observed_setup_count")),
        "average_consensus_score": _safe_float(memory.get("average_consensus_score")),
        "average_conflict_score": _safe_float(memory.get("average_conflict_score")),
        "contradiction_frequency": _safe_float(memory.get("contradiction_frequency")),
        "contradiction_count": len(memory.get("top_contradiction_types") or []),
    }


def _phase7_summary(memory: Dict[str, Any]) -> Dict[str, Any]:
    trades = memory.get("trade_lifecycle") if isinstance(memory.get("trade_lifecycle"), dict) else {}
    causes = memory.get("failure_cause_counts") if isinstance(memory.get("failure_cause_counts"), dict) else {}
    symbol_stats = memory.get("symbol_stats") if isinstance(memory.get("symbol_stats"), dict) else {}

    degrading = []
    for symbol, bucket in symbol_stats.items():
        if not isinstance(bucket, dict):
            continue
        health = _safe_float(bucket.get("avg_trade_health_score"), 50.0)
        drift = _safe_float(bucket.get("avg_confidence_drift"), 0.0)
        if health < 45.0 or drift < -8.0:
            degrading.append({"symbol": str(symbol)[:40], "health": round(health, 2), "drift": round(drift, 2)})
    degrading.sort(key=lambda item: (item["health"], item["drift"]))

    return {
        "available": bool(memory),
        "tracked_trades": len(trades),
        "failure_cause_counts": dict(_top(causes.items())),
        "lifecycle_degradation": degrading[:MAX_REPORT_ITEMS],
    }


def _phase8_summary(memory: Dict[str, Any]) -> Dict[str, Any]:
    current = memory.get("current_narrative") if isinstance(memory.get("current_narrative"), dict) else memory
    return {
        "available": bool(memory),
        "narrative_type": current.get("narrative_type", "UNKNOWN"),
        "risk_state": current.get("risk_on_risk_off_state", "UNKNOWN"),
        "risk_tone_score": _safe_float(current.get("risk_tone_score"), 50.0),
        "narrative_confidence": _safe_float(current.get("narrative_confidence")),
        "contradiction_count": len(current.get("contradiction_flags") or []),
        "market_direction": current.get("market_direction", "UNKNOWN"),
    }


def _phase9_summary(memory: Dict[str, Any]) -> Dict[str, Any]:
    current = memory.get("current_snapshot") if isinstance(memory.get("current_snapshot"), dict) else memory
    return {
        "available": bool(memory),
        "relational_state": current.get("relational_state", "UNKNOWN"),
        "portfolio_heat_score": _safe_float(current.get("portfolio_heat_score")),
        "observed_setup_count": _safe_int(current.get("observed_setup_count")),
        "systemic_contradiction_count": len(current.get("systemic_contradiction_flags") or []),
        "concentration_warnings": _top(current.get("systemic_contradiction_flags") or []),
    }


def _confidence_stability(phase6: Dict[str, Any], phase8: Dict[str, Any], phase9: Dict[str, Any]) -> Dict[str, Any]:
    consensus = _safe_float(phase6.get("average_consensus_score"), 50.0)
    narrative = _safe_float(phase8.get("narrative_confidence"), 0.0) * 100.0
    heat = _safe_float(phase9.get("portfolio_heat_score"), 0.0)
    stability = _clamp((consensus * 0.45) + (narrative * 0.35) + ((100.0 - heat) * 0.20))
    if stability >= 65:
        state = "STABLE"
    elif stability >= 40:
        state = "MIXED"
    else:
        state = "FRAGILE"
    return {"state": state, "score": round(stability, 2)}


def _neutral_snapshot(error: str | None = None, started_at: float | None = None) -> Dict[str, Any]:
    elapsed_ms = round(((time.monotonic() - started_at) if started_at else 0.0) * 1000.0, 3)
    warnings = ["phase10_failed_open"]
    if error:
        warnings.append(str(error)[:160])
    return {
        "version": STATE_VERSION,
        "phase10_shadow_mode": PHASE10_SHADOW_MODE,
        "generated_at": _now_text(),
        "runtime_ms": elapsed_ms,
        "runtime_bounded": elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0,
        "command_status": {
            "overall_state": "NEUTRAL_OBSERVING",
            "confidence": 0.0,
            "warnings": warnings[:MAX_REPORT_ITEMS],
            "failed_open": True,
        },
        "layer_freshness": {},
        "intelligence_layers": {},
        "risk_observations": {
            "systemic_flags": [],
            "lifecycle_flags": [],
            "narrative_flags": [],
            "data_quality_flags": warnings[:MAX_REPORT_ITEMS],
        },
        "dashboard_cards": {
            "master_shadow_state": "NEUTRAL_OBSERVING",
            "narrative": "UNKNOWN",
            "cross_setup_heat": 0.0,
            "tracked_lifecycle_trades": 0,
            "shadow_warnings": len(warnings),
        },
        "safety": _safety_block(),
        "phase10_rank_adjustment": 0.0,
    }


def _safety_block() -> Dict[str, Any]:
    violations = _detect_forbidden_imports()
    return {
        "phase10_rank_adjustment": 0.0,
        "ranking_changes": False,
        "execution_changes": False,
        "telegram_changes": False,
        "broker_api_changes": False,
        "live_price_calls": False,
        "network_calls": False,
        "supabase_imports_or_writes": False,
        "scanner_calls": False,
        "build_master_input_calls": False,
        "scan_for_setups_calls": False,
        "evaluated_setups_mutated": False,
        "final_decisions_mutated": False,
        "context_mutated": False,
        "forbidden_imports_detected": violations,
        "no_forbidden_imports_detected": not violations,
    }


def build_master_shadow_snapshot(
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    phase_results: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build a bounded, read-only Phase 10 snapshot from existing local artifacts.
    Caller inputs are deep-copied and used only for lightweight counts.
    """

    started_at = time.monotonic()
    try:
        setup_snapshot = deepcopy(evaluated_setups if isinstance(evaluated_setups, list) else [])
        decision_snapshot = deepcopy(final_decisions if isinstance(final_decisions, dict) else {})
        context_snapshot = deepcopy(context if isinstance(context, dict) else {})
        phase_snapshot = deepcopy(phase_results if isinstance(phase_results, dict) else {})

        paths = {
            "phase5": PHASE5_MEMORY_PATH,
            "phase6": PHASE6_MEMORY_PATH,
            "phase7": PHASE7_MEMORY_PATH,
            "phase8": PHASE8_MEMORY_PATH,
            "phase9": PHASE9_MEMORY_PATH,
        }

        memories: Dict[str, Dict[str, Any]] = {}
        freshness: Dict[str, Dict[str, Any]] = {}
        warnings: List[str] = []

        for layer, path in paths.items():
            if time.monotonic() - started_at > RUNTIME_BUDGET_SECONDS:
                warnings.append("phase10_runtime_budget_reached")
                break
            data, layer_freshness, layer_warnings = _read_json_limited(path, layer)
            memories[layer] = data
            freshness[layer] = layer_freshness
            warnings.extend(layer_warnings)

        phase5 = _phase5_summary(memories.get("phase5", {}))
        phase6 = _phase6_summary(memories.get("phase6", {}))
        phase7 = _phase7_summary(memories.get("phase7", {}))
        phase8 = _phase8_summary(memories.get("phase8", {}))
        phase9 = _phase9_summary(memories.get("phase9", {}))

        contradiction_count = (
            _safe_int(phase6.get("contradiction_count"))
            + _safe_int(phase8.get("contradiction_count"))
            + _safe_int(phase9.get("systemic_contradiction_count"))
        )
        confidence = _confidence_stability(phase6, phase8, phase9)

        data_quality_flags = list(warnings)
        stale_layers = [
            layer
            for layer, info in freshness.items()
            if info.get("available") and _safe_float(info.get("age_seconds")) > 6 * 3600
        ]
        data_quality_flags.extend(f"{layer}_memory_stale" for layer in stale_layers)

        systemic_flags = []
        systemic_flags.extend(str(item)[:120] for item in phase9.get("concentration_warnings") or [])
        if contradiction_count:
            systemic_flags.append(f"shadow_contradictions_detected:{contradiction_count}")
        if _safe_float(phase9.get("portfolio_heat_score")) >= 70.0:
            systemic_flags.append("portfolio_heat_high")

        lifecycle_flags = [
            f"{item.get('symbol')}:health={item.get('health')}"
            for item in phase7.get("lifecycle_degradation") or []
        ]
        narrative_flags = []
        if phase8.get("risk_state") in {"RISK_OFF", "UNKNOWN"}:
            narrative_flags.append(f"risk_state:{phase8.get('risk_state')}")

        available_layers = sum(1 for item in [phase5, phase6, phase7, phase8, phase9] if item.get("available"))
        if available_layers >= 4 and not data_quality_flags:
            overall_state = "ACTIVE"
        elif available_layers:
            overall_state = "DEGRADED_OBSERVING"
        else:
            overall_state = "NEUTRAL_OBSERVING"

        elapsed_ms = round((time.monotonic() - started_at) * 1000.0, 3)
        runtime_bounded = elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0
        if not runtime_bounded:
            data_quality_flags.append("phase10_runtime_budget_exceeded")

        snapshot = {
            "version": STATE_VERSION,
            "phase10_shadow_mode": PHASE10_SHADOW_MODE,
            "generated_at": _now_text(),
            "runtime_ms": elapsed_ms,
            "runtime_bounded": runtime_bounded,
            "command_status": {
                "overall_state": overall_state,
                "confidence": confidence.get("score", 0.0),
                "confidence_stability": confidence,
                "warnings": _top(data_quality_flags),
                "failed_open": bool(data_quality_flags and available_layers == 0),
            },
            "layer_freshness": freshness,
            "intelligence_layers": {
                "phase5_strategy_family": phase5,
                "phase6_multi_agent": phase6,
                "phase7_lifecycle": phase7,
                "phase8_market_narrative": phase8,
                "phase9_cross_setup": phase9,
            },
            "runtime_context": {
                "observed_setups_count": len(setup_snapshot),
                "selected_decisions_count": len(decision_snapshot.get("selected") or []),
                "context_mode": context_snapshot.get("trading_mode"),
                "phase_result_keys": sorted(phase_snapshot.keys())[:MAX_REPORT_ITEMS],
            },
            "risk_observations": {
                "systemic_flags": _top(systemic_flags),
                "lifecycle_flags": _top(lifecycle_flags),
                "narrative_flags": _top(narrative_flags),
                "data_quality_flags": _top(data_quality_flags),
            },
            "dashboard_cards": {
                "master_shadow_state": overall_state,
                "narrative": phase8.get("narrative_type", "UNKNOWN"),
                "cross_setup_heat": phase9.get("portfolio_heat_score", 0.0),
                "tracked_lifecycle_trades": phase7.get("tracked_trades", 0),
                "shadow_warnings": len(set(data_quality_flags + systemic_flags + lifecycle_flags + narrative_flags)),
            },
            "safety": _safety_block(),
            "phase10_rank_adjustment": 0.0,
        }
        return snapshot
    except Exception as exc:
        return _neutral_snapshot(str(exc), started_at)


def render_master_shadow_report(snapshot: Dict[str, Any]) -> str:
    layers = snapshot.get("intelligence_layers") if isinstance(snapshot.get("intelligence_layers"), dict) else {}
    risks = snapshot.get("risk_observations") if isinstance(snapshot.get("risk_observations"), dict) else {}
    cards = snapshot.get("dashboard_cards") if isinstance(snapshot.get("dashboard_cards"), dict) else {}
    safety = snapshot.get("safety") if isinstance(snapshot.get("safety"), dict) else {}

    phase8 = layers.get("phase8_market_narrative") if isinstance(layers.get("phase8_market_narrative"), dict) else {}
    phase9 = layers.get("phase9_cross_setup") if isinstance(layers.get("phase9_cross_setup"), dict) else {}
    phase7 = layers.get("phase7_lifecycle") if isinstance(layers.get("phase7_lifecycle"), dict) else {}
    phase5 = layers.get("phase5_strategy_family") if isinstance(layers.get("phase5_strategy_family"), dict) else {}

    lines = [
        "TITAN Phase 10 Master Shadow Intelligence Command Center",
        "========================================================",
        "",
        "Safety",
        "- Read-only shadow report/dashboard layer.",
        "- No ranking, execution, Telegram, broker/API, Supabase, scanner, live-price, or network integration.",
        f"- phase10_rank_adjustment: {safety.get('phase10_rank_adjustment', 0.0)}",
        f"- No forbidden imports detected: {safety.get('no_forbidden_imports_detected', False)}",
        "",
        f"Updated: {snapshot.get('generated_at')}",
        f"Overall Shadow Health: {snapshot.get('command_status', {}).get('overall_state')}",
        f"Confidence Stability: {snapshot.get('command_status', {}).get('confidence')}",
        f"Runtime Ms: {snapshot.get('runtime_ms')} | Bounded: {snapshot.get('runtime_bounded')}",
        "",
        "Dashboard Cards:",
        f"- Shadow State: {cards.get('master_shadow_state')}",
        f"- Market Narrative: {cards.get('narrative')}",
        f"- Cross-Setup Heat: {cards.get('cross_setup_heat')}",
        f"- Lifecycle Trades Tracked: {cards.get('tracked_lifecycle_trades')}",
        f"- Shadow Warnings: {cards.get('shadow_warnings')}",
        "",
        "Layer Summary:",
        f"- Phase 5 setup-family strengths: {phase5.get('setup_family_strength') or 'None observed'}",
        f"- Phase 7 lifecycle degradation: {phase7.get('lifecycle_degradation') or 'None observed'}",
        f"- Phase 8 narrative: {phase8.get('narrative_type')} | Risk: {phase8.get('risk_state')}",
        f"- Phase 9 relational state: {phase9.get('relational_state')} | Heat: {phase9.get('portfolio_heat_score')}",
        "",
        "Systemic Warnings:",
    ]

    systemic = risks.get("systemic_flags") or []
    lines.extend([f"- {item}" for item in systemic[:MAX_REPORT_ITEMS]] or ["- None observed"])

    lines.append("")
    lines.append("Lifecycle Warnings:")
    lifecycle = risks.get("lifecycle_flags") or []
    lines.extend([f"- {item}" for item in lifecycle[:MAX_REPORT_ITEMS]] or ["- None observed"])

    lines.append("")
    lines.append("Data Quality Warnings:")
    data_quality = risks.get("data_quality_flags") or []
    lines.extend([f"- {item}" for item in data_quality[:MAX_REPORT_ITEMS]] or ["- None observed"])

    return "\n".join(lines) + "\n"


def _report_throttled(force: bool = False) -> bool:
    if force:
        return False
    try:
        if not REPORT_PATH.exists():
            return False
        age_seconds = datetime.now(IST).timestamp() - REPORT_PATH.stat().st_mtime
        return age_seconds < REPORT_REFRESH_SECONDS
    except Exception:
        return False


def refresh_master_shadow_command_center(
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    phase_results: Dict[str, Any] | None = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Build and persist compact Phase 10 artifacts. Never raises to caller.
    """

    try:
        snapshot = build_master_shadow_snapshot(
            evaluated_setups=evaluated_setups,
            final_decisions=final_decisions,
            context=context,
            phase_results=phase_results,
        )

        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

        if _report_throttled(force=force):
            return {"skipped": "CACHE_FRESH", "snapshot": snapshot}

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_master_shadow_report(snapshot), encoding="utf-8")
        return snapshot
    except Exception as exc:
        return _neutral_snapshot(str(exc))


if __name__ == "__main__":
    result = refresh_master_shadow_command_center(force=True)
    print("TITAN Phase 10 Master Shadow Command Center refreshed")
    print("State:", result.get("command_status", {}).get("overall_state"))
    print("Report:", REPORT_PATH)
