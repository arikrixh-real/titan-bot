"""
TITAN Phase 14 - Meta Evolution Intelligence.

Shadow-only meta-auditor for TITAN intelligence layers. It evaluates layer
usefulness, drift, overfit risk, contradictions, and stability using local
cached artifacts only.

Safety:
- No ranking, final decision, Telegram, execution, broker/API, live-price,
  scanner, Supabase, network, self-modifying code, automatic parameter changes,
  dashboard, alert-cap, or duplicate-prevention integration.
- report/memory only.
- recommended_live_weight and rank_adjustment remain 0.0.
- Fails open on every exception.
"""

from __future__ import annotations

import ast
import csv
import json
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "reports" / "meta_evolution_report.txt"
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "meta_evolution_memory.json"

LAYER_PATHS = {
    "phase5_strategy_family": PROJECT_ROOT / "data" / "memory" / "strategy_family_memory.json",
    "phase6_multi_agent": PROJECT_ROOT / "data" / "memory" / "phase6_shadow_memory.json",
    "phase7_lifecycle": PROJECT_ROOT / "data" / "memory" / "lifecycle_memory.json",
    "phase8_market_narrative": PROJECT_ROOT / "data" / "memory" / "market_narrative_memory.json",
    "phase9_cross_setup": PROJECT_ROOT / "data" / "memory" / "cross_setup_memory.json",
    "phase10_master_shadow": PROJECT_ROOT / "data" / "memory" / "master_shadow_memory.json",
    "phase11_promotion_gate": PROJECT_ROOT / "data" / "memory" / "promotion_gate_memory.json",
    "phase12_regime": PROJECT_ROOT / "data" / "memory" / "advanced_regime_intelligence_memory.json",
    "phase13_strategy_genome": PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json",
}

OUTCOME_PATHS = [
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_journal.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.csv",
    PROJECT_ROOT / "data" / "journals" / "trade_journal.csv",
    PROJECT_ROOT / "journal" / "trade_journal.json",
    PROJECT_ROOT / "journal" / "trade_journal.csv",
]

STATE_VERSION = "14.0"
PHASE14_SHADOW_MODE = True
MAX_FILE_BYTES = 1_000_000
MAX_OUTCOME_ROWS = 300
MAX_HISTORY = 100
MAX_CONTRADICTIONS = 20
MAX_REPORT_ITEMS = 10
REPORT_REFRESH_SECONDS = 3600
RUNTIME_BUDGET_SECONDS = 0.25
MIN_LAYER_SAMPLES = 100

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
    "titan_master_brain.execution_engine",
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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score(value: float) -> float:
    return round(_clamp01(value), 4)


def _top(items: Iterable[Any], limit: int = MAX_REPORT_ITEMS) -> List[Any]:
    return list(items or [])[:limit]


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)) if path.is_absolute() else str(path)
    except Exception:
        return str(path)


def _read_json_limited(path: Path, name: str) -> tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    freshness = {
        "available": False,
        "path": _display_path(path),
        "status": "MISSING",
        "age_seconds": None,
    }
    warnings: List[str] = []
    try:
        if not path.exists():
            warnings.append(f"{name}_missing")
            return {}, freshness, warnings
        stat = path.stat()
        freshness["age_seconds"] = round(max(0.0, datetime.now(IST).timestamp() - stat.st_mtime), 3)
        if stat.st_size > MAX_FILE_BYTES:
            freshness["status"] = "OVERSIZED_SKIPPED"
            warnings.append(f"{name}_oversized")
            return {}, freshness, warnings
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            freshness["status"] = "INVALID_SHAPE"
            warnings.append(f"{name}_invalid_shape")
            return {}, freshness, warnings
        freshness["available"] = True
        freshness["status"] = "OK"
        return data, freshness, warnings
    except Exception:
        freshness["status"] = "READ_ERROR"
        warnings.append(f"{name}_read_error")
        return {}, freshness, warnings


def _normalize_outcome(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"TP", "WIN", "WON", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if text in {"SL", "LOSS", "LOST", "STOPLOSS", "STOP_LOSS", "STOP_LOSS_HIT", "FAILED"}:
        return "LOSS"
    if text in {"OPEN", "ACTIVE", "LIVE", "RUNNING", "WAITING"}:
        return "OPEN"
    if text in {"NO_TRADE", "MARKET_CLOSED", "CLOSED"}:
        return "OTHER"
    return text or "UNKNOWN"


def _outcome_from_row(row: Dict[str, Any]) -> str:
    for key in ("outcome", "result", "status", "trade_result", "Outcome", "Result", "STATUS"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return _normalize_outcome(value)
    return "UNKNOWN"


def _read_json_rows(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)][-MAX_OUTCOME_ROWS:]
    if isinstance(data, dict):
        for key in ("trades", "outcomes", "records", "data", "items"):
            items = data.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)][-MAX_OUTCOME_ROWS:]
    return []


def _read_jsonl_rows(path: Path) -> List[Dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-MAX_OUTCOME_ROWS:]:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            continue
    return rows


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)][-MAX_OUTCOME_ROWS:]


def _read_outcomes() -> tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    source = None
    for path in OUTCOME_PATHS:
        try:
            if not path.exists():
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                warnings.append(f"outcome_source_oversized:{_display_path(path)}")
                continue
            suffix = path.suffix.lower()
            if suffix == ".jsonl":
                rows = _read_jsonl_rows(path)
            elif suffix == ".json":
                rows = _read_json_rows(path)
            elif suffix == ".csv":
                rows = _read_csv_rows(path)
            if rows:
                source = _display_path(path)
                break
        except Exception:
            warnings.append(f"outcome_source_read_error:{_display_path(path)}")
    if not source:
        warnings.append("outcome_memory_missing")

    wins = losses = open_count = other = 0
    for row in rows:
        outcome = _outcome_from_row(row)
        if outcome == "WIN":
            wins += 1
        elif outcome == "LOSS":
            losses += 1
        elif outcome == "OPEN":
            open_count += 1
        else:
            other += 1
    closed = wins + losses
    return {
        "source": source,
        "rows": len(rows),
        "closed_samples": closed,
        "wins": wins,
        "losses": losses,
        "open": open_count,
        "other": other,
        "win_rate": round(wins / closed, 4) if closed else 0.0,
        "loss_rate": round(losses / closed, 4) if closed else 0.0,
    }, warnings


def _sample_confidence(samples: int) -> float:
    return _score(samples / float(MIN_LAYER_SAMPLES))


def _layer_samples(layer_name: str, data: Dict[str, Any], outcomes: Dict[str, Any]) -> int:
    if layer_name == "phase5_strategy_family":
        return _safe_int(data.get("total_closed_trades"), _safe_int(outcomes.get("closed_samples")))
    if layer_name == "phase6_multi_agent":
        return _safe_int(data.get("observed_setup_count"), _safe_int(outcomes.get("closed_samples")))
    if layer_name == "phase7_lifecycle":
        trades = data.get("trade_lifecycle") if isinstance(data.get("trade_lifecycle"), dict) else {}
        return max(len(trades), _safe_int(outcomes.get("closed_samples")))
    if layer_name == "phase8_market_narrative":
        history = data.get("history") if isinstance(data.get("history"), list) else []
        return max(len(history), _safe_int(outcomes.get("closed_samples")))
    if layer_name == "phase9_cross_setup":
        current = data.get("current_snapshot") if isinstance(data.get("current_snapshot"), dict) else data
        return max(_safe_int(current.get("observed_setup_count")), _safe_int(outcomes.get("closed_samples")))
    if layer_name == "phase10_master_shadow":
        cards = data.get("dashboard_cards") if isinstance(data.get("dashboard_cards"), dict) else {}
        return _safe_int(cards.get("tracked_lifecycle_trades"), _safe_int(outcomes.get("closed_samples")))
    if layer_name == "phase11_promotion_gate":
        summary = data.get("promotion_summary") if isinstance(data.get("promotion_summary"), dict) else {}
        return _safe_int(summary.get("minimum_samples_required"), _safe_int(outcomes.get("closed_samples")))
    if layer_name == "phase12_regime":
        promo = data.get("promotion_gate_features") if isinstance(data.get("promotion_gate_features"), dict) else {}
        return _safe_int(promo.get("samples"), _safe_int(outcomes.get("closed_samples")))
    if layer_name == "phase13_strategy_genome":
        promo = data.get("promotion_gate_features") if isinstance(data.get("promotion_gate_features"), dict) else {}
        return _safe_int(promo.get("samples"), _safe_int(outcomes.get("closed_samples")))
    return _safe_int(outcomes.get("closed_samples"))


def _layer_confidence(layer_name: str, data: Dict[str, Any]) -> float:
    if layer_name == "phase6_multi_agent":
        return _score(_safe_float(data.get("average_consensus_score")) / 100.0)
    if layer_name == "phase8_market_narrative":
        current = data.get("current_narrative") if isinstance(data.get("current_narrative"), dict) else data
        return _score(_safe_float(current.get("narrative_confidence")))
    if layer_name == "phase9_cross_setup":
        current = data.get("current_snapshot") if isinstance(data.get("current_snapshot"), dict) else data
        return _score(_safe_float(current.get("portfolio_heat_score")) / 100.0)
    if layer_name == "phase10_master_shadow":
        status = data.get("command_status") if isinstance(data.get("command_status"), dict) else {}
        return _score(_safe_float(status.get("confidence")) / 100.0)
    if layer_name == "phase11_promotion_gate":
        summary = data.get("promotion_summary") if isinstance(data.get("promotion_summary"), dict) else {}
        return _score(_safe_float(summary.get("max_promotion_score")))
    if layer_name == "phase12_regime":
        active = data.get("active_regime") if isinstance(data.get("active_regime"), dict) else {}
        return _score(_safe_float(active.get("confidence")))
    if layer_name == "phase13_strategy_genome":
        promo = data.get("promotion_gate_features") if isinstance(data.get("promotion_gate_features"), dict) else {}
        return _score(_safe_float(promo.get("family_stability_score")))
    return 0.5 if data else 0.0


def _layer_warning_rate(layer_name: str, data: Dict[str, Any]) -> float:
    if layer_name == "phase6_multi_agent":
        return _score(_safe_float(data.get("contradiction_frequency")))
    if layer_name == "phase8_market_narrative":
        current = data.get("current_narrative") if isinstance(data.get("current_narrative"), dict) else data
        return _score(len(current.get("contradiction_flags") or []) / 10.0)
    if layer_name == "phase9_cross_setup":
        current = data.get("current_snapshot") if isinstance(data.get("current_snapshot"), dict) else data
        return _score(len(current.get("systemic_contradiction_flags") or []) / 10.0)
    if layer_name == "phase10_master_shadow":
        cards = data.get("dashboard_cards") if isinstance(data.get("dashboard_cards"), dict) else {}
        return _score(_safe_float(cards.get("shadow_warnings")) / 10.0)
    if layer_name == "phase11_promotion_gate":
        return _score(len(data.get("warnings") or []) / 10.0)
    if layer_name == "phase12_regime":
        return _score(len(data.get("warnings") or []) / 10.0)
    if layer_name == "phase13_strategy_genome":
        return _score(len(data.get("failure_clusters") or {}) / 20.0)
    return 0.0


def _previous_layer(previous: Dict[str, Any], layer_name: str) -> Dict[str, Any]:
    layers = previous.get("layers") if isinstance(previous.get("layers"), dict) else {}
    item = layers.get(layer_name)
    return item if isinstance(item, dict) else {}


def _score_layer(layer_name: str, data: Dict[str, Any], outcomes: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
    samples = _layer_samples(layer_name, data, outcomes)
    sample_conf = _sample_confidence(samples)
    confidence = _layer_confidence(layer_name, data)
    warning_rate = _layer_warning_rate(layer_name, data)
    win_rate = _safe_float(outcomes.get("win_rate"))
    loss_rate = _safe_float(outcomes.get("loss_rate"))

    winner_alignment = _score(1.0 - abs(confidence - win_rate))
    loser_warning_quality = _score(1.0 - abs(warning_rate - loss_rate))
    usefulness = _score(((winner_alignment * 0.45) + (loser_warning_quality * 0.35) + ((1.0 - warning_rate) * 0.20)) * (0.4 + sample_conf * 0.6))
    stability = _score((1.0 - warning_rate) * 0.45 + sample_conf * 0.35 + (1.0 - abs(confidence - 0.5)) * 0.20)
    overfit = _score(max(0.0, confidence - sample_conf) * 0.65 + max(0.0, usefulness - sample_conf) * 0.35)

    prev = _previous_layer(previous, layer_name)
    drift = 0.0
    if prev:
        drift = (
            abs(usefulness - _safe_float(prev.get("usefulness_score"))) * 0.4
            + abs(stability - _safe_float(prev.get("stability_score"))) * 0.3
            + abs(overfit - _safe_float(prev.get("overfit_risk"))) * 0.3
        )
    drift = _score(drift)

    if samples < 30:
        recommendation = "INSUFFICIENT_DATA"
    elif overfit >= 0.45 or drift >= 0.35:
        recommendation = "DEMOTE_OR_OBSERVE"
    elif usefulness >= 0.65 and stability >= 0.60 and overfit < 0.25:
        recommendation = "PROMOTION_CANDIDATE_REVIEW_ONLY"
    else:
        recommendation = "KEEP_OBSERVING"

    return {
        "samples": samples,
        "sample_confidence": sample_conf,
        "usefulness_score": usefulness,
        "stability_score": stability,
        "drift_score": drift,
        "overfit_risk": overfit,
        "winner_alignment": winner_alignment,
        "loser_warning_quality": loser_warning_quality,
        "promotion_recommendation": recommendation,
        "recommended_live_weight": 0.0,
        "rank_adjustment": 0.0,
    }


def _detect_contradictions(memories: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    contradictions: List[Dict[str, Any]] = []
    phase8 = memories.get("phase8_market_narrative", {})
    phase9 = memories.get("phase9_cross_setup", {})
    phase11 = memories.get("phase11_promotion_gate", {})
    phase12 = memories.get("phase12_regime", {})
    phase13 = memories.get("phase13_strategy_genome", {})
    phase7 = memories.get("phase7_lifecycle", {})

    narrative = phase8.get("current_narrative") if isinstance(phase8.get("current_narrative"), dict) else phase8
    risk_state = str(narrative.get("risk_on_risk_off_state") or "UNKNOWN").upper()
    regime_active = phase12.get("active_regime") if isinstance(phase12.get("active_regime"), dict) else {}
    regime_primary = str(regime_active.get("primary") or "UNKNOWN").upper()
    if risk_state == "RISK_ON" and regime_primary in {"RISK_OFF", "CHOPPY_NO_EDGE", "PANIC_VOLATILITY"}:
        contradictions.append({"left": "phase8_market_narrative", "right": "phase12_regime", "type": "risk_state_conflict", "severity": 0.65})
    if risk_state == "RISK_OFF" and regime_primary in {"RISK_ON", "TRENDING_BREAKOUT"}:
        contradictions.append({"left": "phase8_market_narrative", "right": "phase12_regime", "type": "risk_state_conflict", "severity": 0.65})

    cross = phase9.get("current_snapshot") if isinstance(phase9.get("current_snapshot"), dict) else phase9
    heat = _safe_float(cross.get("portfolio_heat_score"))
    master = memories.get("phase10_master_shadow", {})
    command = master.get("command_status") if isinstance(master.get("command_status"), dict) else {}
    if heat >= 70.0 and str(command.get("overall_state") or "").upper() == "ACTIVE":
        contradictions.append({"left": "phase9_cross_setup", "right": "phase10_master_shadow", "type": "active_shadow_with_high_concentration", "severity": 0.45})

    promotion = phase11.get("promotion_summary") if isinstance(phase11.get("promotion_summary"), dict) else {}
    genome_promo = phase13.get("promotion_gate_features") if isinstance(phase13.get("promotion_gate_features"), dict) else {}
    if _safe_float(genome_promo.get("family_stability_score")) >= 0.75 and _safe_float(promotion.get("max_promotion_score")) <= 0.10:
        contradictions.append({"left": "phase11_promotion_gate", "right": "phase13_strategy_genome", "type": "family_stability_vs_insufficient_promotion", "severity": 0.35})

    lifecycle_stats = phase7.get("setup_family_stats") if isinstance(phase7.get("setup_family_stats"), dict) else {}
    weak_lifecycle = any(isinstance(v, dict) and _safe_float(v.get("avg_trade_health_score"), 50.0) < 40.0 for v in lifecycle_stats.values())
    if weak_lifecycle and _safe_float(narrative.get("narrative_confidence")) >= 0.70:
        contradictions.append({"left": "phase7_lifecycle", "right": "phase8_market_narrative", "type": "weak_lifecycle_high_narrative_confidence", "severity": 0.50})

    return contradictions[:MAX_CONTRADICTIONS]


def _regime_layer_usefulness(layers: Dict[str, Dict[str, Any]], regime_memory: Dict[str, Any], outcomes: Dict[str, Any]) -> Dict[str, Any]:
    active = regime_memory.get("active_regime") if isinstance(regime_memory.get("active_regime"), dict) else {}
    regime = str(active.get("primary") or "CHOPPY_NO_EDGE").upper()
    result: Dict[str, Any] = {regime: {}}
    samples = _safe_int(outcomes.get("closed_samples"))
    confidence = _score(samples / 30.0)
    for layer_name, layer in layers.items():
        result[regime][layer_name] = {
            "samples": samples,
            "usefulness_score": layer.get("usefulness_score", 0.0),
            "confidence": confidence,
        }
    return result


def _meta_state(layers: Dict[str, Dict[str, Any]], contradictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not layers:
        return {
            "overall_intelligence_stability": 0.0,
            "overall_usefulness_score": 0.0,
            "overall_drift_score": 0.0,
            "overall_overfit_risk": 0.0,
            "contradiction_pressure": 0.0,
            "recommended_live_weight": 0.0,
            "rank_adjustment": 0.0,
        }
    count = len(layers)
    stability = sum(_safe_float(layer.get("stability_score")) for layer in layers.values()) / count
    usefulness = sum(_safe_float(layer.get("usefulness_score")) for layer in layers.values()) / count
    drift = sum(_safe_float(layer.get("drift_score")) for layer in layers.values()) / count
    overfit = sum(_safe_float(layer.get("overfit_risk")) for layer in layers.values()) / count
    contradiction_pressure = _score(sum(_safe_float(item.get("severity")) for item in contradictions) / max(1, MAX_CONTRADICTIONS))
    return {
        "overall_intelligence_stability": _score(stability),
        "overall_usefulness_score": _score(usefulness),
        "overall_drift_score": _score(drift),
        "overall_overfit_risk": _score(overfit),
        "contradiction_pressure": contradiction_pressure,
        "recommended_live_weight": 0.0,
        "rank_adjustment": 0.0,
    }


def _promotion_features(meta_state: Dict[str, Any], outcomes: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "samples": _safe_int(outcomes.get("closed_samples")),
        "meta_stability_score": _score(_safe_float(meta_state.get("overall_intelligence_stability"))),
        "layer_usefulness_quality": _score(_safe_float(meta_state.get("overall_usefulness_score"))),
        "overfit_control_score": _score(1.0 - _safe_float(meta_state.get("overall_overfit_risk"))),
        "contradiction_control_score": _score(1.0 - _safe_float(meta_state.get("contradiction_pressure"))),
        "recommended_live_weight": 0.0,
        "promotion_eligible": False,
    }


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


def _safety_block() -> Dict[str, Any]:
    violations = _detect_forbidden_imports()
    return {
        "phase14_shadow_mode": PHASE14_SHADOW_MODE,
        "rank_adjustment": 0.0,
        "recommended_live_weight": 0.0,
        "self_modifying_code": False,
        "automatic_parameter_changes": False,
        "ranking_changes": False,
        "final_decision_changes": False,
        "telegram_changes": False,
        "execution_changes": False,
        "broker_api_changes": False,
        "live_price_calls": False,
        "network_calls": False,
        "scanner_calls": False,
        "dashboard_changes": False,
        "evaluated_setups_mutated": False,
        "final_decisions_mutated": False,
        "context_mutated": False,
        "forbidden_imports_detected": violations,
        "no_forbidden_imports_detected": not violations,
    }


def _neutral_snapshot(error: str | None = None, started_at: float | None = None) -> Dict[str, Any]:
    elapsed_ms = round(((time.monotonic() - started_at) if started_at else 0.0) * 1000.0, 3)
    warnings = ["phase14_failed_open"]
    if error:
        warnings.append(str(error)[:160])
    return {
        "version": STATE_VERSION,
        "phase14_shadow_mode": PHASE14_SHADOW_MODE,
        "generated_at": _now_text(),
        "runtime_ms": elapsed_ms,
        "runtime_bounded": elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0,
        "meta_state": _meta_state({}, []),
        "layers": {},
        "contradictions": [],
        "regime_layer_usefulness": {},
        "history": [],
        "promotion_gate_features": {
            "samples": 0,
            "meta_stability_score": 0.0,
            "layer_usefulness_quality": 0.0,
            "overfit_control_score": 0.0,
            "contradiction_control_score": 0.0,
            "recommended_live_weight": 0.0,
            "promotion_eligible": False,
        },
        "warnings": warnings[:MAX_REPORT_ITEMS],
        "safety": _safety_block(),
        "rank_adjustment": 0.0,
        "recommended_live_weight": 0.0,
    }


def build_meta_evolution_snapshot(
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    phase_results: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    started_at = time.monotonic()
    try:
        setup_snapshot = deepcopy(evaluated_setups if isinstance(evaluated_setups, list) else [])
        decision_snapshot = deepcopy(final_decisions if isinstance(final_decisions, dict) else {})
        context_snapshot = deepcopy(context if isinstance(context, dict) else {})
        phase_snapshot = deepcopy(phase_results if isinstance(phase_results, dict) else {})

        warnings: List[str] = []
        freshness: Dict[str, Any] = {}
        memories: Dict[str, Dict[str, Any]] = {}
        for name, path in LAYER_PATHS.items():
            if time.monotonic() - started_at > RUNTIME_BUDGET_SECONDS:
                warnings.append("phase14_runtime_budget_reached")
                break
            data, info, layer_warnings = _read_json_limited(path, name)
            memories[name] = data
            freshness[name] = info
            warnings.extend(layer_warnings)

        previous, previous_info, previous_warnings = _read_json_limited(MEMORY_PATH, "phase14_previous")
        if previous_info.get("status") not in {"MISSING", "OVERSIZED_SKIPPED"}:
            warnings.extend(previous_warnings)

        outcomes, outcome_warnings = _read_outcomes()
        warnings.extend(outcome_warnings)

        layers = {
            name: _score_layer(name, memories.get(name, {}), outcomes, previous)
            for name in LAYER_PATHS
        }
        contradictions = _detect_contradictions(memories)
        meta_state = _meta_state(layers, contradictions)
        regime_layer = _regime_layer_usefulness(layers, memories.get("phase12_regime", {}), outcomes)
        promotion_features = _promotion_features(meta_state, outcomes)

        history = previous.get("history") if isinstance(previous.get("history"), list) else []
        history.append(
            {
                "generated_at": _now_text(),
                "overall_usefulness_score": meta_state.get("overall_usefulness_score"),
                "overall_drift_score": meta_state.get("overall_drift_score"),
                "contradiction_pressure": meta_state.get("contradiction_pressure"),
            }
        )
        history = history[-MAX_HISTORY:]

        elapsed_ms = round((time.monotonic() - started_at) * 1000.0, 3)
        runtime_bounded = elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0
        if not runtime_bounded:
            warnings.append("phase14_runtime_budget_exceeded")

        return {
            "version": STATE_VERSION,
            "phase14_shadow_mode": PHASE14_SHADOW_MODE,
            "generated_at": _now_text(),
            "runtime_ms": elapsed_ms,
            "runtime_bounded": runtime_bounded,
            "meta_state": meta_state,
            "layers": layers,
            "contradictions": contradictions,
            "regime_layer_usefulness": regime_layer,
            "history": history,
            "layer_freshness": freshness,
            "promotion_gate_features": promotion_features,
            "runtime_context": {
                "observed_setups_count": len(setup_snapshot),
                "selected_decisions_count": len(decision_snapshot.get("selected") or []),
                "context_mode": context_snapshot.get("trading_mode"),
                "phase_result_keys": sorted(phase_snapshot.keys())[:MAX_REPORT_ITEMS],
            },
            "warnings": _top(warnings),
            "safety": _safety_block(),
            "rank_adjustment": 0.0,
            "recommended_live_weight": 0.0,
        }
    except Exception as exc:
        return _neutral_snapshot(str(exc), started_at)


def render_meta_evolution_report(snapshot: Dict[str, Any]) -> str:
    safety = snapshot.get("safety") if isinstance(snapshot.get("safety"), dict) else {}
    meta = snapshot.get("meta_state") if isinstance(snapshot.get("meta_state"), dict) else {}
    layers = snapshot.get("layers") if isinstance(snapshot.get("layers"), dict) else {}
    promotion = snapshot.get("promotion_gate_features") if isinstance(snapshot.get("promotion_gate_features"), dict) else {}
    ordered = sorted(layers.items(), key=lambda item: _safe_float(item[1].get("usefulness_score")) if isinstance(item[1], dict) else 0.0, reverse=True)

    lines = [
        "TITAN Phase 14 Meta Evolution Intelligence Report",
        "=================================================",
        "",
        "Safety",
        "- Shadow meta-evolution audit only.",
        "- No ranking, final decision, Telegram, execution, broker/API, live-price, scanner, Supabase, network, self-modifying code, automatic parameter, or dashboard integration.",
        f"- rank_adjustment: {safety.get('rank_adjustment', 0.0)}",
        f"- recommended_live_weight: {safety.get('recommended_live_weight', 0.0)}",
        f"- No forbidden imports detected: {safety.get('no_forbidden_imports_detected', False)}",
        "",
        f"Updated: {snapshot.get('generated_at')}",
        f"Runtime Ms: {snapshot.get('runtime_ms')} | Bounded: {snapshot.get('runtime_bounded')}",
        "",
        "Meta State:",
        f"- Overall usefulness: {meta.get('overall_usefulness_score', 0.0)}",
        f"- Overall stability: {meta.get('overall_intelligence_stability', 0.0)}",
        f"- Overall drift: {meta.get('overall_drift_score', 0.0)}",
        f"- Overall overfit risk: {meta.get('overall_overfit_risk', 0.0)}",
        f"- Contradiction pressure: {meta.get('contradiction_pressure', 0.0)}",
        "",
        "Layer Scores:",
    ]
    for name, layer in ordered[:MAX_REPORT_ITEMS]:
        lines.append(
            f"- {name}: usefulness={layer.get('usefulness_score', 0.0)}, "
            f"stability={layer.get('stability_score', 0.0)}, "
            f"drift={layer.get('drift_score', 0.0)}, "
            f"overfit={layer.get('overfit_risk', 0.0)}, "
            f"recommendation={layer.get('promotion_recommendation')}"
        )
    lines.extend(
        [
            "",
            f"Contradictions: {len(snapshot.get('contradictions') or [])}",
            "",
            "Promotion Gate Compatibility:",
            f"- Samples: {promotion.get('samples', 0)}",
            f"- Meta stability score: {promotion.get('meta_stability_score', 0.0)}",
            f"- Layer usefulness quality: {promotion.get('layer_usefulness_quality', 0.0)}",
            f"- Overfit control score: {promotion.get('overfit_control_score', 0.0)}",
            f"- Contradiction control score: {promotion.get('contradiction_control_score', 0.0)}",
            f"- Promotion eligible: {promotion.get('promotion_eligible', False)}",
            f"- Recommended live weight: {promotion.get('recommended_live_weight', 0.0)}",
            "",
            "Warnings:",
        ]
    )
    warnings = snapshot.get("warnings") or []
    lines.extend([f"- {item}" for item in warnings[:MAX_REPORT_ITEMS]] or ["- None observed"])
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


def refresh_meta_evolution_intelligence(
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    phase_results: Dict[str, Any] | None = None,
    force: bool = False,
) -> Dict[str, Any]:
    try:
        snapshot = build_meta_evolution_snapshot(
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
        REPORT_PATH.write_text(render_meta_evolution_report(snapshot), encoding="utf-8")
        return snapshot
    except Exception as exc:
        return _neutral_snapshot(str(exc))


if __name__ == "__main__":
    result = refresh_meta_evolution_intelligence(force=True)
    print("TITAN Phase 14 Meta Evolution Intelligence refreshed")
    print("Usefulness:", result.get("meta_state", {}).get("overall_usefulness_score"))
    print("Report:", REPORT_PATH)
