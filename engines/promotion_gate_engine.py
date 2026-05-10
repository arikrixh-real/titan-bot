"""
TITAN Phase 11 - Promotion Gate Engine.

Shadow-only governance layer that evaluates whether existing shadow
intelligence appears useful and stable over time.

Safety:
- Governance/reporting only.
- No ranking, alerts, execution, Telegram, broker/API, TP/SL, scanner,
  Supabase, live-price, or network integration.
- Reads bounded local artifacts only.
- recommended_live_weight is pinned to 0.00 until a future explicit promotion.
- Never mutates caller inputs.
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
REPORT_PATH = PROJECT_ROOT / "reports" / "promotion_gate_report.txt"
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "promotion_gate_memory.json"

PHASE6_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "phase6_shadow_memory.json"
PHASE7_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "lifecycle_memory.json"
PHASE8_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "market_narrative_memory.json"
PHASE9_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "cross_setup_memory.json"
PHASE10_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "master_shadow_memory.json"

OUTCOME_PATHS = [
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.json",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.csv",
    PROJECT_ROOT / "journal" / "trade_journal.json",
    PROJECT_ROOT / "journal" / "trade_journal.csv",
]

STATE_VERSION = "11.0"
PHASE11_SHADOW_MODE = True
MAX_FILE_BYTES = 1_000_000
MAX_OUTCOME_ROWS = 300
MAX_REPORT_ITEMS = 10
REPORT_REFRESH_SECONDS = 3600
RUNTIME_BUDGET_SECONDS = 0.25
MIN_PROMOTION_SAMPLES = 50

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


def _round_score(value: float) -> float:
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
    if text in {"MARKET_CLOSED", "CLOSED"}:
        return "OTHER"
    return text or "UNKNOWN"


def _outcome_from_row(row: Dict[str, Any]) -> str:
    for key in ("outcome", "result", "status", "trade_result", "Outcome", "Result", "STATUS"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return _normalize_outcome(value)
    return "UNKNOWN"


def _read_outcome_rows_from_json(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)][-MAX_OUTCOME_ROWS:]
    if isinstance(data, dict):
        for key in ("trades", "outcomes", "records", "data", "items"):
            items = data.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)][-MAX_OUTCOME_ROWS:]
    return []


def _read_outcome_rows_from_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    lines = path.read_text(encoding="utf-8").splitlines()[-MAX_OUTCOME_ROWS:]
    for line in lines:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            continue
    return rows


def _read_outcome_rows_from_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    return rows[-MAX_OUTCOME_ROWS:]


def _read_actual_outcomes() -> tuple[Dict[str, Any], List[str]]:
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

            if path.suffix.lower() == ".jsonl":
                rows = _read_outcome_rows_from_jsonl(path)
            elif path.suffix.lower() == ".json":
                rows = _read_outcome_rows_from_json(path)
            elif path.suffix.lower() == ".csv":
                rows = _read_outcome_rows_from_csv(path)

            if rows:
                source = _display_path(path)
                break
        except Exception:
            warnings.append(f"outcome_source_read_error:{_display_path(path)}")
            continue

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
    win_rate = wins / closed if closed else 0.0
    loss_rate = losses / closed if closed else 0.0

    if not source:
        warnings.append("outcome_memory_missing")

    return {
        "source": source,
        "rows": len(rows),
        "closed_samples": closed,
        "wins": wins,
        "losses": losses,
        "open": open_count,
        "other": other,
        "win_rate": round(win_rate, 4),
        "loss_rate": round(loss_rate, 4),
    }, warnings


def _history_stability(values: List[float]) -> float:
    clean = [_clamp01(_safe_float(value)) for value in values if value is not None]
    if len(clean) < 2:
        return 0.5
    mean = sum(clean) / len(clean)
    variance = sum((value - mean) ** 2 for value in clean) / len(clean)
    return _round_score(1.0 - min(1.0, variance ** 0.5))


def _sample_factor(samples: int) -> float:
    if samples <= 0:
        return 0.0
    return _clamp01(samples / float(MIN_PROMOTION_SAMPLES))


def _phase6_metrics(memory: Dict[str, Any], outcomes: Dict[str, Any]) -> Dict[str, Any]:
    samples = max(_safe_int(memory.get("observed_setup_count")), _safe_int(outcomes.get("closed_samples")))
    win_rate = _safe_float(outcomes.get("win_rate"))
    loss_rate = _safe_float(outcomes.get("loss_rate"))
    consensus = _clamp01(_safe_float(memory.get("average_consensus_score")) / 100.0)
    conflict = _clamp01(_safe_float(memory.get("average_conflict_score")) / 100.0)
    contradiction_frequency = _clamp01(_safe_float(memory.get("contradiction_frequency")))

    contradiction_accuracy = _round_score(1.0 - abs(contradiction_frequency - loss_rate))
    agreement_quality = _round_score(1.0 - abs(consensus - win_rate))
    confidence_quality = _round_score((agreement_quality * 0.65) + ((1.0 - conflict) * 0.35))
    false_positive_rate = _round_score(consensus * loss_rate)
    false_negative_rate = _round_score((1.0 - consensus) * win_rate)
    stability_score = _round_score(1.0 - abs(consensus - conflict) * 0.5)
    usefulness_score = _round_score(
        ((contradiction_accuracy + agreement_quality + confidence_quality) / 3.0)
        * (0.5 + (_sample_factor(samples) * 0.5))
    )
    drift_score = _round_score(1.0 - stability_score)
    regime_consistency = 0.5
    promotion_score = _round_score(
        (usefulness_score * 0.35)
        + (stability_score * 0.25)
        + (contradiction_accuracy * 0.15)
        + (agreement_quality * 0.15)
        + ((1.0 - false_positive_rate) * 0.10)
    )

    return _phase_result(
        samples=samples,
        usefulness_score=usefulness_score,
        stability_score=stability_score,
        contradiction_accuracy=contradiction_accuracy,
        agreement_quality=agreement_quality,
        confidence_quality=confidence_quality,
        false_positive_rate=false_positive_rate,
        false_negative_rate=false_negative_rate,
        drift_score=drift_score,
        regime_consistency=regime_consistency,
        promotion_score=promotion_score,
    )


def _phase7_metrics(memory: Dict[str, Any], outcomes: Dict[str, Any]) -> Dict[str, Any]:
    trades = memory.get("trade_lifecycle") if isinstance(memory.get("trade_lifecycle"), dict) else {}
    symbol_stats = memory.get("symbol_stats") if isinstance(memory.get("symbol_stats"), dict) else {}
    samples = max(len(trades), _safe_int(outcomes.get("closed_samples")))
    win_rate = _safe_float(outcomes.get("win_rate"))
    loss_rate = _safe_float(outcomes.get("loss_rate"))

    health_values = []
    drift_values = []
    for bucket in symbol_stats.values():
        if isinstance(bucket, dict):
            health_values.append(_clamp01(_safe_float(bucket.get("avg_trade_health_score"), 50.0) / 100.0))
            drift_values.append(_safe_float(bucket.get("avg_confidence_drift"), 0.0))

    avg_health = sum(health_values) / len(health_values) if health_values else 0.5
    normalized_drift = _clamp01(0.5 + ((sum(drift_values) / len(drift_values)) / 100.0)) if drift_values else 0.5
    agreement_quality = _round_score(1.0 - abs(avg_health - win_rate))
    confidence_quality = _round_score((avg_health * 0.65) + (normalized_drift * 0.35))
    contradiction_accuracy = _round_score(1.0 - abs((1.0 - avg_health) - loss_rate))
    stability_score = _history_stability(health_values)
    false_positive_rate = _round_score(avg_health * loss_rate)
    false_negative_rate = _round_score((1.0 - avg_health) * win_rate)
    drift_score = _round_score(abs(normalized_drift - 0.5) * 2.0)
    regime_consistency = 0.5
    usefulness_score = _round_score(
        ((agreement_quality + confidence_quality + contradiction_accuracy) / 3.0)
        * (0.5 + (_sample_factor(samples) * 0.5))
    )
    promotion_score = _round_score(
        (usefulness_score * 0.35)
        + (stability_score * 0.20)
        + (confidence_quality * 0.20)
        + ((1.0 - false_positive_rate) * 0.15)
        + ((1.0 - drift_score) * 0.10)
    )

    return _phase_result(
        samples=samples,
        usefulness_score=usefulness_score,
        stability_score=stability_score,
        contradiction_accuracy=contradiction_accuracy,
        agreement_quality=agreement_quality,
        confidence_quality=confidence_quality,
        false_positive_rate=false_positive_rate,
        false_negative_rate=false_negative_rate,
        drift_score=drift_score,
        regime_consistency=regime_consistency,
        promotion_score=promotion_score,
    )


def _phase8_metrics(memory: Dict[str, Any], outcomes: Dict[str, Any]) -> Dict[str, Any]:
    current = memory.get("current_narrative") if isinstance(memory.get("current_narrative"), dict) else memory
    history = memory.get("history") if isinstance(memory.get("history"), list) else []
    samples = max(len(history), _safe_int(outcomes.get("closed_samples")))
    win_rate = _safe_float(outcomes.get("win_rate"))
    loss_rate = _safe_float(outcomes.get("loss_rate"))
    confidence = _clamp01(_safe_float(current.get("narrative_confidence")))
    risk_state = str(current.get("risk_on_risk_off_state") or current.get("risk_state") or "UNKNOWN").upper()
    contradiction_count = len(current.get("contradiction_flags") or [])

    if risk_state == "RISK_ON":
        regime_consistency = _round_score(win_rate)
    elif risk_state == "RISK_OFF":
        regime_consistency = _round_score(loss_rate)
    elif risk_state == "NEUTRAL":
        regime_consistency = _round_score(1.0 - abs(win_rate - loss_rate))
    else:
        regime_consistency = 0.5

    hist_conf = [
        _safe_float(item.get("narrative_confidence"))
        for item in history
        if isinstance(item, dict) and item.get("narrative_confidence") is not None
    ]
    stability_score = _history_stability(hist_conf)
    agreement_quality = _round_score(1.0 - abs(confidence - regime_consistency))
    contradiction_accuracy = _round_score(1.0 - min(1.0, contradiction_count / 10.0) * (1.0 - loss_rate))
    confidence_quality = _round_score((confidence * 0.50) + (agreement_quality * 0.50))
    false_positive_rate = _round_score(confidence * (1.0 - regime_consistency))
    false_negative_rate = _round_score((1.0 - confidence) * regime_consistency)
    drift_score = _round_score(1.0 - stability_score)
    usefulness_score = _round_score(
        ((agreement_quality + confidence_quality + regime_consistency) / 3.0)
        * (0.5 + (_sample_factor(samples) * 0.5))
    )
    promotion_score = _round_score(
        (usefulness_score * 0.35)
        + (stability_score * 0.20)
        + (regime_consistency * 0.20)
        + ((1.0 - false_positive_rate) * 0.15)
        + (contradiction_accuracy * 0.10)
    )

    return _phase_result(
        samples=samples,
        usefulness_score=usefulness_score,
        stability_score=stability_score,
        contradiction_accuracy=contradiction_accuracy,
        agreement_quality=agreement_quality,
        confidence_quality=confidence_quality,
        false_positive_rate=false_positive_rate,
        false_negative_rate=false_negative_rate,
        drift_score=drift_score,
        regime_consistency=regime_consistency,
        promotion_score=promotion_score,
    )


def _phase9_metrics(memory: Dict[str, Any], outcomes: Dict[str, Any]) -> Dict[str, Any]:
    current = memory.get("current_snapshot") if isinstance(memory.get("current_snapshot"), dict) else memory
    history = memory.get("history") if isinstance(memory.get("history"), list) else []
    samples = max(_safe_int(current.get("observed_setup_count")), _safe_int(outcomes.get("closed_samples")))
    win_rate = _safe_float(outcomes.get("win_rate"))
    loss_rate = _safe_float(outcomes.get("loss_rate"))
    heat = _clamp01(_safe_float(current.get("portfolio_heat_score")) / 100.0)
    contradiction_count = len(current.get("systemic_contradiction_flags") or [])
    heat_history = [
        _safe_float(item.get("portfolio_heat_score")) / 100.0
        for item in history
        if isinstance(item, dict) and item.get("portfolio_heat_score") is not None
    ]

    contradiction_accuracy = _round_score(1.0 - abs(heat - loss_rate))
    agreement_quality = _round_score(1.0 - abs((1.0 - heat) - win_rate))
    confidence_quality = _round_score((agreement_quality * 0.60) + ((1.0 - heat) * 0.40))
    false_positive_rate = _round_score(heat * win_rate)
    false_negative_rate = _round_score((1.0 - heat) * loss_rate)
    stability_score = _history_stability(heat_history)
    drift_score = _round_score(1.0 - stability_score)
    regime_consistency = _round_score(1.0 - min(1.0, contradiction_count / 10.0))
    usefulness_score = _round_score(
        ((contradiction_accuracy + agreement_quality + confidence_quality) / 3.0)
        * (0.5 + (_sample_factor(samples) * 0.5))
    )
    promotion_score = _round_score(
        (usefulness_score * 0.35)
        + (stability_score * 0.20)
        + (contradiction_accuracy * 0.20)
        + ((1.0 - false_positive_rate) * 0.15)
        + (regime_consistency * 0.10)
    )

    return _phase_result(
        samples=samples,
        usefulness_score=usefulness_score,
        stability_score=stability_score,
        contradiction_accuracy=contradiction_accuracy,
        agreement_quality=agreement_quality,
        confidence_quality=confidence_quality,
        false_positive_rate=false_positive_rate,
        false_negative_rate=false_negative_rate,
        drift_score=drift_score,
        regime_consistency=regime_consistency,
        promotion_score=promotion_score,
    )


def _phase_result(
    samples: int,
    usefulness_score: float,
    stability_score: float,
    contradiction_accuracy: float,
    agreement_quality: float,
    confidence_quality: float,
    false_positive_rate: float,
    false_negative_rate: float,
    drift_score: float,
    regime_consistency: float,
    promotion_score: float,
) -> Dict[str, Any]:
    sample_factor = _sample_factor(samples)
    gated_promotion_score = _round_score(promotion_score * sample_factor)

    if samples < MIN_PROMOTION_SAMPLES:
        recommendation = "INSUFFICIENT_SAMPLE_SHADOW_ONLY"
    elif gated_promotion_score >= 0.70 and stability_score >= 0.65:
        recommendation = "PROMOTION_CANDIDATE_REVIEW_ONLY"
    elif gated_promotion_score >= 0.55:
        recommendation = "KEEP_OBSERVING"
    else:
        recommendation = "DO_NOT_PROMOTE"

    return {
        "samples": int(max(0, samples)),
        "usefulness_score": _round_score(usefulness_score),
        "stability_score": _round_score(stability_score),
        "contradiction_accuracy": _round_score(contradiction_accuracy),
        "agreement_quality": _round_score(agreement_quality),
        "confidence_quality": _round_score(confidence_quality),
        "false_positive_rate": _round_score(false_positive_rate),
        "false_negative_rate": _round_score(false_negative_rate),
        "drift_score": _round_score(drift_score),
        "regime_consistency": _round_score(regime_consistency),
        "promotion_score": gated_promotion_score,
        "recommended_live_weight": 0.0,
        "recommendation": recommendation,
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
        "phase11_shadow_mode": PHASE11_SHADOW_MODE,
        "ranking_changes": False,
        "alert_changes": False,
        "execution_changes": False,
        "telegram_changes": False,
        "broker_api_changes": False,
        "tp_sl_changes": False,
        "live_price_calls": False,
        "network_calls": False,
        "supabase_imports_or_writes": False,
        "scanner_calls": False,
        "evaluated_setups_mutated": False,
        "final_decisions_mutated": False,
        "alert_caps_mutated": False,
        "execution_packets_mutated": False,
        "recommended_live_weight_pinned_zero": True,
        "forbidden_imports_detected": violations,
        "no_forbidden_imports_detected": not violations,
    }


def _neutral_snapshot(error: str | None = None, started_at: float | None = None) -> Dict[str, Any]:
    elapsed_ms = round(((time.monotonic() - started_at) if started_at else 0.0) * 1000.0, 3)
    warnings = ["phase11_failed_open"]
    if error:
        warnings.append(str(error)[:160])
    return {
        "version": STATE_VERSION,
        "phase11_shadow_mode": PHASE11_SHADOW_MODE,
        "generated_at": _now_text(),
        "runtime_ms": elapsed_ms,
        "runtime_bounded": elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0,
        "status": "NEUTRAL_OBSERVING",
        "warnings": warnings[:MAX_REPORT_ITEMS],
        "actual_outcomes": {
            "source": None,
            "rows": 0,
            "closed_samples": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "loss_rate": 0.0,
        },
        "phase6": _phase_result(0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.5, 0.5, 0.0),
        "phase7": _phase_result(0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.5, 0.5, 0.0),
        "phase8": _phase_result(0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.5, 0.5, 0.0),
        "phase9": _phase_result(0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.5, 0.5, 0.0),
        "promotion_summary": {
            "best_candidate": None,
            "max_promotion_score": 0.0,
            "any_live_influence": False,
            "recommended_live_weight": 0.0,
        },
        "safety": _safety_block(),
    }


def build_promotion_gate_snapshot(
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    phase_results: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build deterministic promotion-gate metrics from local shadow artifacts.
    Caller inputs are copied only for mutation protection and lightweight context.
    """

    started_at = time.monotonic()
    try:
        setup_snapshot = deepcopy(evaluated_setups if isinstance(evaluated_setups, list) else [])
        decision_snapshot = deepcopy(final_decisions if isinstance(final_decisions, dict) else {})
        phase_snapshot = deepcopy(phase_results if isinstance(phase_results, dict) else {})

        memories: Dict[str, Dict[str, Any]] = {}
        freshness: Dict[str, Dict[str, Any]] = {}
        warnings: List[str] = []

        for name, path in {
            "phase6": PHASE6_MEMORY_PATH,
            "phase7": PHASE7_MEMORY_PATH,
            "phase8": PHASE8_MEMORY_PATH,
            "phase9": PHASE9_MEMORY_PATH,
            "phase10": PHASE10_MEMORY_PATH,
        }.items():
            if time.monotonic() - started_at > RUNTIME_BUDGET_SECONDS:
                warnings.append("phase11_runtime_budget_reached")
                break
            data, info, layer_warnings = _read_json_limited(path, name)
            memories[name] = data
            freshness[name] = info
            warnings.extend(layer_warnings)

        outcomes, outcome_warnings = _read_actual_outcomes()
        warnings.extend(outcome_warnings)

        phase6 = _phase6_metrics(memories.get("phase6", {}), outcomes)
        phase7 = _phase7_metrics(memories.get("phase7", {}), outcomes)
        phase8 = _phase8_metrics(memories.get("phase8", {}), outcomes)
        phase9 = _phase9_metrics(memories.get("phase9", {}), outcomes)

        phase_scores = {
            "phase6": phase6.get("promotion_score", 0.0),
            "phase7": phase7.get("promotion_score", 0.0),
            "phase8": phase8.get("promotion_score", 0.0),
            "phase9": phase9.get("promotion_score", 0.0),
        }
        best_candidate = max(phase_scores.items(), key=lambda item: item[1])[0] if phase_scores else None
        max_score = max(phase_scores.values()) if phase_scores else 0.0

        elapsed_ms = round((time.monotonic() - started_at) * 1000.0, 3)
        runtime_bounded = elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0
        if not runtime_bounded:
            warnings.append("phase11_runtime_budget_exceeded")

        snapshot = {
            "version": STATE_VERSION,
            "phase11_shadow_mode": PHASE11_SHADOW_MODE,
            "generated_at": _now_text(),
            "runtime_ms": elapsed_ms,
            "runtime_bounded": runtime_bounded,
            "status": "ACTIVE" if outcomes.get("closed_samples", 0) > 0 else "NEUTRAL_OBSERVING",
            "warnings": _top(warnings),
            "actual_outcomes": outcomes,
            "layer_freshness": freshness,
            "phase6": phase6,
            "phase7": phase7,
            "phase8": phase8,
            "phase9": phase9,
            "promotion_summary": {
                "best_candidate": best_candidate,
                "max_promotion_score": _round_score(max_score),
                "any_live_influence": False,
                "recommended_live_weight": 0.0,
                "minimum_samples_required": MIN_PROMOTION_SAMPLES,
            },
            "runtime_context": {
                "observed_setups_count": len(setup_snapshot),
                "selected_decisions_count": len(decision_snapshot.get("selected") or []),
                "phase_result_keys": sorted(phase_snapshot.keys())[:MAX_REPORT_ITEMS],
            },
            "safety": _safety_block(),
        }
        return snapshot
    except Exception as exc:
        return _neutral_snapshot(str(exc), started_at)


def render_promotion_gate_report(snapshot: Dict[str, Any]) -> str:
    summary = snapshot.get("promotion_summary") if isinstance(snapshot.get("promotion_summary"), dict) else {}
    outcomes = snapshot.get("actual_outcomes") if isinstance(snapshot.get("actual_outcomes"), dict) else {}
    safety = snapshot.get("safety") if isinstance(snapshot.get("safety"), dict) else {}

    lines = [
        "TITAN Phase 11 Promotion Gate Report",
        "=====================================",
        "",
        "Safety",
        "- Shadow governance only.",
        "- No ranking, alerts, execution, Telegram, broker/API, TP/SL, scanner, live-price, Supabase, or network integration.",
        "- recommended_live_weight remains pinned at 0.00.",
        f"- No forbidden imports detected: {safety.get('no_forbidden_imports_detected', False)}",
        "",
        f"Updated: {snapshot.get('generated_at')}",
        f"Status: {snapshot.get('status')}",
        f"Runtime Ms: {snapshot.get('runtime_ms')} | Bounded: {snapshot.get('runtime_bounded')}",
        "",
        "Actual Outcome Baseline:",
        f"- Source: {outcomes.get('source')}",
        f"- Closed samples: {outcomes.get('closed_samples', 0)}",
        f"- Wins/Losses: {outcomes.get('wins', 0)}/{outcomes.get('losses', 0)}",
        f"- Win rate: {outcomes.get('win_rate', 0.0)}",
        "",
        "Promotion Summary:",
        f"- Best candidate: {summary.get('best_candidate')}",
        f"- Max promotion score: {summary.get('max_promotion_score', 0.0)}",
        f"- Any live influence: {summary.get('any_live_influence', False)}",
        f"- Recommended live weight: {summary.get('recommended_live_weight', 0.0)}",
        "",
        "Layer Metrics:",
    ]

    for phase in ("phase6", "phase7", "phase8", "phase9"):
        data = snapshot.get(phase) if isinstance(snapshot.get(phase), dict) else {}
        lines.append(
            f"- {phase}: samples={data.get('samples', 0)}, "
            f"usefulness={data.get('usefulness_score', 0.0)}, "
            f"stability={data.get('stability_score', 0.0)}, "
            f"promotion={data.get('promotion_score', 0.0)}, "
            f"live_weight={data.get('recommended_live_weight', 0.0)}, "
            f"recommendation={data.get('recommendation')}"
        )

    warnings = snapshot.get("warnings") or []
    lines.append("")
    lines.append("Warnings:")
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


def refresh_promotion_gate(
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    phase_results: Dict[str, Any] | None = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Build and persist Phase 11 promotion-gate artifacts. Never raises.
    """

    try:
        snapshot = build_promotion_gate_snapshot(
            evaluated_setups=evaluated_setups,
            final_decisions=final_decisions,
            phase_results=phase_results,
        )

        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

        if _report_throttled(force=force):
            return {"skipped": "CACHE_FRESH", "snapshot": snapshot}

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_promotion_gate_report(snapshot), encoding="utf-8")
        return snapshot
    except Exception as exc:
        return _neutral_snapshot(str(exc))


if __name__ == "__main__":
    result = refresh_promotion_gate(force=True)
    print("TITAN Phase 11 Promotion Gate refreshed")
    print("Status:", result.get("status"))
    print("Report:", REPORT_PATH)
