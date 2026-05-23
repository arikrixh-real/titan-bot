"""
TITAN Phase 12 - Advanced Regime Intelligence.

Shadow-only regime observer that classifies the active market environment and
tracks setup-family behavior by regime using local cached artifacts only.

Safety:
- No ranking, final decision, Telegram, execution, broker/API, live-price,
  scanner, Supabase, network, alert-cap, or duplicate-prevention integration.
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
REPORT_PATH = PROJECT_ROOT / "reports" / "advanced_regime_intelligence_report.txt"
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "advanced_regime_intelligence_memory.json"

MARKET_NARRATIVE_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "market_narrative_memory.json"
CROSS_SETUP_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "cross_setup_memory.json"
LIFECYCLE_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "lifecycle_memory.json"
STRATEGY_FAMILY_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "strategy_family_memory.json"
PROMOTION_GATE_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "promotion_gate_memory.json"
MASTER_SHADOW_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "master_shadow_memory.json"
HISTORICAL_EVOLUTION_STATE_PATH = PROJECT_ROOT / "data" / "memory" / "historical_evolution_state.json"
HISTORICAL_ADAPTIVE_INTELLIGENCE_STATE_PATH = PROJECT_ROOT / "data" / "memory" / "historical_adaptive_intelligence_state.json"
HISTORICAL_REGIME_TRANSITION_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "historical_regime_transition_memory.json"

OUTCOME_PATHS = [
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_journal.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.csv",
    PROJECT_ROOT / "data" / "journals" / "trade_journal.csv",
    PROJECT_ROOT / "journal" / "trade_journal.json",
    PROJECT_ROOT / "journal" / "trade_journal.csv",
]

REQUIRED_REGIMES = [
    "TRENDING_BREAKOUT",
    "MEAN_REVERSION",
    "PANIC_VOLATILITY",
    "LOW_LIQUIDITY",
    "RISK_ON",
    "RISK_OFF",
    "SECTOR_ROTATION",
    "INDEX_DRIVEN",
    "NEWS_SHOCK",
    "CHOPPY_NO_EDGE",
]

STATE_VERSION = "12.0"
PHASE12_SHADOW_MODE = True
MAX_FILE_BYTES = 1_000_000
MAX_OUTCOME_ROWS = 300
MAX_HISTORY = 100
MAX_REPORT_ITEMS = 10
REPORT_REFRESH_SECONDS = 3600
RUNTIME_BUDGET_SECONDS = 0.25
MIN_FAMILY_REGIME_SAMPLES = 20

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


def _empty_historical_replay_context() -> Dict[str, Any]:
    return {
        "historical_win_rate": 0.0,
        "historical_filter_strictness": 0.0,
        "historical_score_boost": 0.0,
        "top_historical_symbols": [],
        "top_historical_setup_tags": [],
        "advisory_only": True,
    }


def _bucket_samples(bucket: Dict[str, Any]) -> int:
    samples = _safe_int(bucket.get("trades") or bucket.get("samples") or bucket.get("observations"))
    if samples:
        return samples
    return _safe_int(bucket.get("wins")) + _safe_int(bucket.get("losses"))


def _bucket_win_rate(bucket: Dict[str, Any]) -> float:
    for key in ("posterior_win_rate", "win_rate"):
        if key in bucket:
            return round(_clamp01(_safe_float(bucket.get(key))), 4)
    wins = _safe_int(bucket.get("wins"))
    losses = _safe_int(bucket.get("losses"))
    total = wins + losses
    return round(wins / total, 4) if total else 0.0


def _rank_historical_buckets(memories: Iterable[Dict[str, Any]], keys: Iterable[str], label: str) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for memory in memories:
        if not isinstance(memory, dict):
            continue
        for key in keys:
            source = memory.get(key)
            if not isinstance(source, dict):
                continue
            for name, raw_bucket in source.items():
                if not isinstance(raw_bucket, dict):
                    continue
                clean_name = str(name or "").strip().upper() if label == "symbol" else str(name or "").strip()
                if not clean_name:
                    continue
                current = buckets.setdefault(clean_name, {"samples": 0, "win_rate": 0.0})
                samples = _bucket_samples(raw_bucket)
                win_rate = _bucket_win_rate(raw_bucket)
                if samples > current["samples"] or (samples == current["samples"] and win_rate > current["win_rate"]):
                    current["samples"] = samples
                    current["win_rate"] = win_rate

    ranked = sorted(buckets.items(), key=lambda item: (item[1]["samples"], item[1]["win_rate"], item[0]), reverse=True)
    return [
        {
            label: name,
            "samples": stats["samples"],
            "win_rate": stats["win_rate"],
        }
        for name, stats in ranked[:MAX_REPORT_ITEMS]
    ]


def _historical_replay_context(started_at: float, warnings: List[str]) -> Dict[str, Any]:
    context = _empty_historical_replay_context()
    historical_memories: Dict[str, Dict[str, Any]] = {}
    paths = {
        "historical_evolution": HISTORICAL_EVOLUTION_STATE_PATH,
        "historical_adaptive_intelligence": HISTORICAL_ADAPTIVE_INTELLIGENCE_STATE_PATH,
        "historical_regime_transition": HISTORICAL_REGIME_TRANSITION_MEMORY_PATH,
    }

    for name, path in paths.items():
        if time.monotonic() - started_at > RUNTIME_BUDGET_SECONDS:
            warnings.append("historical_replay_runtime_budget_reached")
            break
        data, info, layer_warnings = _read_json_limited(path, name)
        historical_memories[name] = data
        if info.get("status") != "MISSING":
            warnings.extend(layer_warnings)

    evolution = historical_memories.get("historical_evolution", {})
    adaptive = historical_memories.get("historical_adaptive_intelligence", {})
    global_confidence = adaptive.get("global_confidence") if isinstance(adaptive.get("global_confidence"), dict) else {}

    context["historical_win_rate"] = round(
        _clamp01(_safe_float(evolution.get("win_rate"), _safe_float(global_confidence.get("win_rate"), 0.0))),
        4,
    )
    context["historical_filter_strictness"] = round(_safe_float(evolution.get("filter_strictness"), 0.0), 4)
    context["historical_score_boost"] = round(_safe_float(evolution.get("score_boost"), 0.0), 4)
    context["top_historical_symbols"] = _rank_historical_buckets(
        historical_memories.values(),
        ("symbol_memory", "symbols", "symbol_stats"),
        "symbol",
    )
    context["top_historical_setup_tags"] = _rank_historical_buckets(
        historical_memories.values(),
        ("reason_memory", "feature_memory", "setup_tag_memory", "setup_tags", "tags"),
        "setup_tag",
    )
    return context


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


def _strategy_family(row: Dict[str, Any]) -> str:
    for key in ("strategy_family", "strategy", "setup_type", "family"):
        value = str(row.get(key) or "").strip()
        if value:
            return value[:80]
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


def _read_outcome_rows() -> tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    for path in OUTCOME_PATHS:
        try:
            if not path.exists():
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                warnings.append(f"outcome_source_oversized:{_display_path(path)}")
                continue
            suffix = path.suffix.lower()
            if suffix == ".jsonl":
                return _read_jsonl_rows(path), warnings
            if suffix == ".json":
                return _read_json_rows(path), warnings
            if suffix == ".csv":
                return _read_csv_rows(path), warnings
        except Exception:
            warnings.append(f"outcome_source_read_error:{_display_path(path)}")
            continue
    warnings.append("outcome_memory_missing")
    return [], warnings


def _current_narrative(memory: Dict[str, Any]) -> Dict[str, Any]:
    current = memory.get("current_narrative")
    return current if isinstance(current, dict) else memory


def _current_cross_setup(memory: Dict[str, Any]) -> Dict[str, Any]:
    current = memory.get("current_snapshot")
    return current if isinstance(current, dict) else memory


def _score_regimes(memories: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    narrative = _current_narrative(memories.get("market_narrative", {}))
    cross = _current_cross_setup(memories.get("cross_setup", {}))
    lifecycle = memories.get("lifecycle", {})

    risk_state = str(narrative.get("risk_on_risk_off_state") or narrative.get("risk_state") or "UNKNOWN").upper()
    narrative_type = str(narrative.get("narrative_type") or "UNKNOWN").upper()
    risk_tone = _clamp01(_safe_float(narrative.get("risk_tone_score"), 50.0) / 100.0)
    confidence = _clamp01(_safe_float(narrative.get("narrative_confidence"), 0.0))
    contradiction_count = len(narrative.get("contradiction_flags") or [])
    event = narrative.get("event_pressure") if isinstance(narrative.get("event_pressure"), dict) else {}
    volatility = narrative.get("volatility_pressure") if isinstance(narrative.get("volatility_pressure"), dict) else {}
    breadth = narrative.get("breadth_pressure") if isinstance(narrative.get("breadth_pressure"), dict) else {}

    event_score = _clamp01(_safe_float(event.get("score"), 0.0) / 100.0)
    volatility_score = _clamp01(_safe_float(volatility.get("score"), 50.0) / 100.0)
    breadth_score = _clamp01(_safe_float(breadth.get("score"), 50.0) / 100.0)
    event_state = str(event.get("state") or "").upper()
    volatility_state = str(volatility.get("state") or "").upper()
    breadth_state = str(breadth.get("state") or "").upper()

    portfolio_heat = _clamp01(_safe_float(cross.get("portfolio_heat_score"), 0.0) / 100.0)
    relational_state = str(cross.get("relational_state") or "UNKNOWN").upper()
    concentration = cross.get("sector_concentration") if isinstance(cross.get("sector_concentration"), dict) else {}
    crowding = cross.get("directional_crowding") if isinstance(cross.get("directional_crowding"), dict) else {}
    sector_concentration = _clamp01(_safe_float(concentration.get("score"), 0.0) / 100.0)
    directional_crowding = _clamp01(_safe_float(crowding.get("score"), 0.0) / 100.0)
    systemic_contradictions = len(cross.get("systemic_contradiction_flags") or [])

    failure_causes = lifecycle.get("failure_cause_counts") if isinstance(lifecycle.get("failure_cause_counts"), dict) else {}
    news_failures = _safe_int(failure_causes.get("news_shock"))
    liquidity_failures = _safe_int(failure_causes.get("liquidity_issue"))
    time_decay = _safe_int(failure_causes.get("time_decay"))
    market_reversal = _safe_int(failure_causes.get("market_reversal"))
    failure_total = max(1, sum(_safe_int(value) for value in failure_causes.values()))

    scores = {regime: 0.0 for regime in REQUIRED_REGIMES}
    scores["RISK_ON"] = _score((0.55 if risk_state == "RISK_ON" else 0.0) + (risk_tone * 0.30) + (breadth_score * 0.15))
    scores["RISK_OFF"] = _score((0.55 if risk_state == "RISK_OFF" else 0.0) + ((1.0 - risk_tone) * 0.25) + (volatility_score * 0.20))
    scores["TRENDING_BREAKOUT"] = _score(
        (0.35 if "TREND" in narrative_type or "RISK_ON_TREND" in narrative_type else 0.0)
        + (scores["RISK_ON"] * 0.30)
        + (breadth_score * 0.20)
        + ((1.0 - min(1.0, contradiction_count / 5.0)) * 0.15)
    )
    scores["MEAN_REVERSION"] = _score(
        (0.30 if "CHOPPY" in narrative_type else 0.0)
        + (time_decay / failure_total * 0.25)
        + (market_reversal / failure_total * 0.20)
        + ((1.0 - confidence) * 0.25)
    )
    scores["PANIC_VOLATILITY"] = _score(
        (0.35 if volatility_state == "ELEVATED" else 0.0)
        + (volatility_score * 0.30)
        + (scores["RISK_OFF"] * 0.25)
        + (portfolio_heat * 0.10)
    )
    scores["LOW_LIQUIDITY"] = _score((liquidity_failures / failure_total * 0.55) + ((1.0 - confidence) * 0.25) + (portfolio_heat * 0.20))
    scores["SECTOR_ROTATION"] = _score(
        (0.35 if "SECTOR_ROTATION" in narrative_type else 0.0)
        + (sector_concentration * 0.35)
        + (portfolio_heat * 0.15)
        + (0.15 if relational_state in {"HIGH_CONCENTRATION", "MODERATE_CONCENTRATION"} else 0.0)
    )
    scores["INDEX_DRIVEN"] = _score((directional_crowding * 0.45) + (breadth_score * 0.25) + (risk_tone * 0.15) + ((1.0 - sector_concentration) * 0.15))
    scores["NEWS_SHOCK"] = _score((0.35 if event_state == "HIGH" else 0.0) + (event_score * 0.35) + (news_failures / failure_total * 0.30))
    scores["CHOPPY_NO_EDGE"] = _score(
        (0.30 if "CHOPPY" in narrative_type or "DATA_INSUFFICIENT" in narrative_type else 0.0)
        + ((1.0 - confidence) * 0.30)
        + (min(1.0, (contradiction_count + systemic_contradictions) / 8.0) * 0.25)
        + ((1.0 - abs(breadth_score - 0.5) * 2.0) * 0.15)
    )
    return scores


def _active_regime(scores: Dict[str, float], previous_memory: Dict[str, Any]) -> Dict[str, Any]:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary, primary_score = ordered[0] if ordered else ("CHOPPY_NO_EDGE", 0.0)
    if primary_score < 0.25:
        primary = "CHOPPY_NO_EDGE"
    secondary = [name for name, value in ordered[1:4] if value >= 0.25]

    previous = previous_memory.get("active_regime") if isinstance(previous_memory.get("active_regime"), dict) else {}
    previous_primary = previous.get("primary")
    previous_score = _safe_float((previous_memory.get("regime_scores") or {}).get(previous_primary), 0.0)
    transition = bool(previous_primary and previous_primary != primary)
    transition_strength = abs(primary_score - previous_score) if transition else 0.0

    history = previous_memory.get("history") if isinstance(previous_memory.get("history"), list) else []
    recent_same = 0
    for item in reversed(history[-3:]):
        if isinstance(item, dict) and item.get("primary") == primary:
            recent_same += 1
        else:
            break
    confirmed = transition and recent_same >= 1

    return {
        "primary": primary,
        "secondary": secondary,
        "confidence": _score(primary_score),
        "transition_detected": transition,
        "transition_confirmed": confirmed,
        "transition_strength": round(transition_strength, 4),
        "previous_primary": previous_primary,
    }


def _family_regime_performance(rows: List[Dict[str, Any]], active_primary: str) -> Dict[str, Any]:
    buckets: Dict[str, Dict[str, Dict[str, int]]] = {}
    for row in rows[-MAX_OUTCOME_ROWS:]:
        family = _strategy_family(row)
        regime = str(row.get("regime") or row.get("market_regime") or active_primary or "CHOPPY_NO_EDGE").upper()
        if regime not in REQUIRED_REGIMES:
            regime = active_primary if active_primary in REQUIRED_REGIMES else "CHOPPY_NO_EDGE"
        outcome = _outcome_from_row(row)

        family_bucket = buckets.setdefault(family, {})
        regime_bucket = family_bucket.setdefault(regime, {"samples": 0, "wins": 0, "losses": 0, "other": 0})
        if outcome in {"WIN", "LOSS"}:
            regime_bucket["samples"] += 1
            if outcome == "WIN":
                regime_bucket["wins"] += 1
            else:
                regime_bucket["losses"] += 1
        else:
            regime_bucket["other"] += 1

    result: Dict[str, Any] = {}
    for family, regimes in sorted(buckets.items()):
        result[family] = {}
        for regime, stats in sorted(regimes.items()):
            samples = stats["samples"]
            win_rate = stats["wins"] / samples if samples else 0.0
            confidence = _score(samples / float(MIN_FAMILY_REGIME_SAMPLES))
            result[family][regime] = {
                "samples": samples,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(win_rate, 4),
                "confidence": confidence,
            }
    return result


def _promotion_features(active: Dict[str, Any], family_perf: Dict[str, Any]) -> Dict[str, Any]:
    samples = 0
    best_confidence = 0.0
    for regimes in family_perf.values():
        if not isinstance(regimes, dict):
            continue
        for stats in regimes.values():
            if isinstance(stats, dict):
                samples += _safe_int(stats.get("samples"))
                best_confidence = max(best_confidence, _safe_float(stats.get("confidence")))
    stability = _safe_float(active.get("confidence"))
    return {
        "samples": samples,
        "stability_score": _score(stability),
        "regime_prediction_quality": 0.0,
        "family_regime_edge_quality": _score(best_confidence),
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
        "phase12_shadow_mode": PHASE12_SHADOW_MODE,
        "rank_adjustment": 0.0,
        "recommended_live_weight": 0.0,
        "ranking_changes": False,
        "final_decision_changes": False,
        "telegram_changes": False,
        "execution_changes": False,
        "broker_api_changes": False,
        "live_price_calls": False,
        "network_calls": False,
        "scanner_calls": False,
        "alert_cap_changes": False,
        "duplicate_prevention_changes": False,
        "evaluated_setups_mutated": False,
        "final_decisions_mutated": False,
        "context_mutated": False,
        "forbidden_imports_detected": violations,
        "no_forbidden_imports_detected": not violations,
    }


def _neutral_snapshot(error: str | None = None, started_at: float | None = None) -> Dict[str, Any]:
    elapsed_ms = round(((time.monotonic() - started_at) if started_at else 0.0) * 1000.0, 3)
    warnings = ["phase12_failed_open"]
    if error:
        warnings.append(str(error)[:160])
    return {
        "version": STATE_VERSION,
        "phase12_shadow_mode": PHASE12_SHADOW_MODE,
        "generated_at": _now_text(),
        "runtime_ms": elapsed_ms,
        "runtime_bounded": elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0,
        "active_regime": {
            "primary": "CHOPPY_NO_EDGE",
            "secondary": [],
            "confidence": 0.0,
            "transition_detected": False,
            "transition_confirmed": False,
            "previous_primary": None,
        },
        "regime_scores": {regime: 0.0 for regime in REQUIRED_REGIMES},
        "strategy_family_regime_performance": {},
        "history": [],
        "promotion_gate_features": {
            "samples": 0,
            "stability_score": 0.0,
            "regime_prediction_quality": 0.0,
            "family_regime_edge_quality": 0.0,
            "recommended_live_weight": 0.0,
            "promotion_eligible": False,
        },
        "historical_replay_context": _empty_historical_replay_context(),
        "warnings": warnings[:MAX_REPORT_ITEMS],
        "safety": _safety_block(),
        "rank_adjustment": 0.0,
        "recommended_live_weight": 0.0,
    }


def build_advanced_regime_snapshot(
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
        freshness: Dict[str, Dict[str, Any]] = {}
        memories: Dict[str, Dict[str, Any]] = {}

        paths = {
            "market_narrative": MARKET_NARRATIVE_MEMORY_PATH,
            "cross_setup": CROSS_SETUP_MEMORY_PATH,
            "lifecycle": LIFECYCLE_MEMORY_PATH,
            "strategy_family": STRATEGY_FAMILY_MEMORY_PATH,
            "promotion_gate": PROMOTION_GATE_MEMORY_PATH,
            "master_shadow": MASTER_SHADOW_MEMORY_PATH,
        }
        for name, path in paths.items():
            if time.monotonic() - started_at > RUNTIME_BUDGET_SECONDS:
                warnings.append("phase12_runtime_budget_reached")
                break
            data, info, layer_warnings = _read_json_limited(path, name)
            memories[name] = data
            freshness[name] = info
            warnings.extend(layer_warnings)

        previous_memory, previous_info, previous_warnings = _read_json_limited(MEMORY_PATH, "phase12_previous")
        if previous_info.get("status") not in {"MISSING", "OVERSIZED_SKIPPED"}:
            warnings.extend(previous_warnings)

        outcome_rows, outcome_warnings = _read_outcome_rows()
        warnings.extend(outcome_warnings)

        scores = _score_regimes(memories)
        active = _active_regime(scores, previous_memory)
        family_perf = _family_regime_performance(outcome_rows, active.get("primary", "CHOPPY_NO_EDGE"))
        promotion_features = _promotion_features(active, family_perf)
        historical_context = _historical_replay_context(started_at, warnings)

        history = previous_memory.get("history") if isinstance(previous_memory.get("history"), list) else []
        history.append(
            {
                "generated_at": _now_text(),
                "primary": active.get("primary"),
                "confidence": active.get("confidence"),
            }
        )
        history = history[-MAX_HISTORY:]

        elapsed_ms = round((time.monotonic() - started_at) * 1000.0, 3)
        runtime_bounded = elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0
        if not runtime_bounded:
            warnings.append("phase12_runtime_budget_exceeded")

        return {
            "version": STATE_VERSION,
            "phase12_shadow_mode": PHASE12_SHADOW_MODE,
            "generated_at": _now_text(),
            "runtime_ms": elapsed_ms,
            "runtime_bounded": runtime_bounded,
            "active_regime": active,
            "regime_scores": scores,
            "strategy_family_regime_performance": family_perf,
            "history": history,
            "layer_freshness": freshness,
            "promotion_gate_features": promotion_features,
            "historical_replay_context": historical_context,
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


def render_advanced_regime_report(snapshot: Dict[str, Any]) -> str:
    active = snapshot.get("active_regime") if isinstance(snapshot.get("active_regime"), dict) else {}
    scores = snapshot.get("regime_scores") if isinstance(snapshot.get("regime_scores"), dict) else {}
    promotion = snapshot.get("promotion_gate_features") if isinstance(snapshot.get("promotion_gate_features"), dict) else {}
    historical = snapshot.get("historical_replay_context") if isinstance(snapshot.get("historical_replay_context"), dict) else {}
    safety = snapshot.get("safety") if isinstance(snapshot.get("safety"), dict) else {}

    ordered = sorted(scores.items(), key=lambda item: _safe_float(item[1]), reverse=True)
    lines = [
        "TITAN Phase 12 Advanced Regime Intelligence Report",
        "===================================================",
        "",
        "Safety",
        "- Shadow regime intelligence only.",
        "- No ranking, final decision, Telegram, execution, broker/API, live-price, scanner, alert-cap, duplicate-prevention, Supabase, or network integration.",
        f"- rank_adjustment: {safety.get('rank_adjustment', 0.0)}",
        f"- recommended_live_weight: {safety.get('recommended_live_weight', 0.0)}",
        f"- No forbidden imports detected: {safety.get('no_forbidden_imports_detected', False)}",
        "",
        f"Updated: {snapshot.get('generated_at')}",
        f"Runtime Ms: {snapshot.get('runtime_ms')} | Bounded: {snapshot.get('runtime_bounded')}",
        "",
        "Active Regime:",
        f"- Primary: {active.get('primary')}",
        f"- Secondary: {active.get('secondary')}",
        f"- Confidence: {active.get('confidence')}",
        f"- Transition detected: {active.get('transition_detected')} | Confirmed: {active.get('transition_confirmed')}",
        f"- Previous primary: {active.get('previous_primary')}",
        "",
        "Top Regime Scores:",
    ]
    for regime, value in ordered[:MAX_REPORT_ITEMS]:
        lines.append(f"- {regime}: {value}")

    lines.extend(
        [
            "",
            "Promotion Gate Compatibility:",
            f"- Samples: {promotion.get('samples', 0)}",
            f"- Stability score: {promotion.get('stability_score', 0.0)}",
            f"- Family regime edge quality: {promotion.get('family_regime_edge_quality', 0.0)}",
            f"- Promotion eligible: {promotion.get('promotion_eligible', False)}",
            f"- Recommended live weight: {promotion.get('recommended_live_weight', 0.0)}",
            "",
            "Historical Replay Advisory Context:",
            f"- Advisory only: {historical.get('advisory_only', True)}",
            f"- Historical win rate: {historical.get('historical_win_rate', 0.0)}",
            f"- Historical filter strictness: {historical.get('historical_filter_strictness', 0.0)}",
            f"- Historical score boost: {historical.get('historical_score_boost', 0.0)}",
            "- Top historical symbols:",
        ]
    )
    for item in (historical.get("top_historical_symbols") or [])[:MAX_REPORT_ITEMS]:
        if isinstance(item, dict):
            lines.append(f"  - {item.get('symbol')}: samples={item.get('samples')}, win_rate={item.get('win_rate')}")
    if not historical.get("top_historical_symbols"):
        lines.append("  - None observed")

    lines.append("- Top historical setup tags:")
    for item in (historical.get("top_historical_setup_tags") or [])[:MAX_REPORT_ITEMS]:
        if isinstance(item, dict):
            lines.append(f"  - {item.get('setup_tag')}: samples={item.get('samples')}, win_rate={item.get('win_rate')}")
    if not historical.get("top_historical_setup_tags"):
        lines.append("  - None observed")

    lines.extend(
        [
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


def refresh_advanced_regime_intelligence(
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    phase_results: Dict[str, Any] | None = None,
    force: bool = False,
) -> Dict[str, Any]:
    try:
        snapshot = build_advanced_regime_snapshot(
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
        REPORT_PATH.write_text(render_advanced_regime_report(snapshot), encoding="utf-8")
        return snapshot
    except Exception as exc:
        return _neutral_snapshot(str(exc))


if __name__ == "__main__":
    result = refresh_advanced_regime_intelligence(force=True)
    active = result.get("active_regime", {})
    print("TITAN Phase 12 Advanced Regime Intelligence refreshed")
    print("Regime:", active.get("primary"))
    print("Report:", REPORT_PATH)
