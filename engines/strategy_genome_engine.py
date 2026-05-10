"""
TITAN Phase 13 - Strategy Genome Engine.

Shadow-only strategy genome compiler. It groups observed setups/outcomes into
strategy families, builds compact DNA fingerprints, and tracks family behavior
across regimes and lifecycle quality using local cached artifacts only.

Safety:
- No ranking, final decision, Telegram, execution, TP/SL, broker/API,
  live-price, scanner, Supabase, network, alert-cap, duplicate-prevention, or
  dashboard integration.
- report/memory only.
- recommended_live_weight and rank_adjustment remain 0.0.
- Fails open on every exception.
"""

from __future__ import annotations

import ast
import csv
import json
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "reports" / "strategy_genome_report.txt"
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "strategy_genome_memory.json"

REGIME_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "advanced_regime_intelligence_memory.json"
LIFECYCLE_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "lifecycle_memory.json"
PROMOTION_GATE_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "promotion_gate_memory.json"
MASTER_SHADOW_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "master_shadow_memory.json"

OUTCOME_PATHS = [
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_journal.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.csv",
    PROJECT_ROOT / "data" / "journals" / "trade_journal.csv",
    PROJECT_ROOT / "journal" / "trade_journal.json",
    PROJECT_ROOT / "journal" / "trade_journal.csv",
]

STATE_VERSION = "13.0"
PHASE13_SHADOW_MODE = True
MAX_FILE_BYTES = 1_000_000
MAX_OUTCOME_ROWS = 300
MAX_INPUT_SETUPS = 50
MAX_FAMILIES = 50
MAX_FINGERPRINTS = 100
MAX_FAILURE_CLUSTERS = 20
MAX_HISTORY = 100
MAX_REPORT_ITEMS = 10
REPORT_REFRESH_SECONDS = 3600
RUNTIME_BUDGET_SECONDS = 0.25
MIN_FAMILY_SAMPLES = 50
MIN_REGIME_FAMILY_SAMPLES = 30

STRATEGY_FAMILIES = [
    "BREAKOUT_PULLBACK",
    "EMA_CONTINUATION",
    "OPENING_RANGE_BREAKOUT",
    "MEAN_REVERSION_FADE",
    "TREND_RECLAIM",
    "FAILED_BREAKDOWN_REVERSAL",
    "VOLUME_EXPANSION_BREAKOUT",
    "SHORT_COVERING_SPIKE",
    "LIQUIDITY_SWEEP_REVERSAL",
    "TREND_EXHAUSTION_FADE",
    "UNKNOWN",
]

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


def _row_text(row: Dict[str, Any]) -> str:
    parts = []
    for key in ("strategy_family", "strategy", "setup_type", "reason", "trigger_status", "result_reason", "notes"):
        value = row.get(key)
        if value is not None:
            parts.append(str(value))
    setup_context = row.get("setup_context")
    if isinstance(setup_context, dict):
        parts.extend(str(value) for value in setup_context.values())
    return " ".join(parts).lower()


def classify_strategy_family(row: Dict[str, Any]) -> str:
    explicit = str(row.get("strategy_family") or row.get("strategy") or row.get("setup_type") or "").strip().upper()
    explicit = explicit.replace(" ", "_").replace("-", "_")
    if explicit in STRATEGY_FAMILIES:
        return explicit

    text = _row_text(row)
    if "opening range" in text or "orb" in text:
        return "OPENING_RANGE_BREAKOUT"
    if "short covering" in text or "squeeze" in text:
        return "SHORT_COVERING_SPIKE"
    if "liquidity sweep" in text or "stop hunt" in text or "wick rejection" in text:
        return "LIQUIDITY_SWEEP_REVERSAL"
    if "failed breakdown" in text or "bear trap" in text or ("breakdown" in text and "reversal" in text):
        return "FAILED_BREAKDOWN_REVERSAL"
    if "exhaustion" in text or "climax" in text or ("extended" in text and "fade" in text):
        return "TREND_EXHAUSTION_FADE"
    if "mean reversion" in text or "overbought" in text or "oversold" in text or "fade" in text:
        return "MEAN_REVERSION_FADE"
    if "reclaim" in text or "regained" in text or "above vwap" in text:
        return "TREND_RECLAIM"
    if "ema" in text and ("continuation" in text or "trend" in text):
        return "EMA_CONTINUATION"
    if "breakout" in text and ("volume" in text or "expansion" in text):
        return "VOLUME_EXPANSION_BREAKOUT"
    if "breakout" in text and ("pullback" in text or "retest" in text or "support" in text or "resistance" in text):
        return "BREAKOUT_PULLBACK"
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


def _score_bucket(value: Any) -> str:
    score = _safe_float(value)
    if score >= 3.0 or score >= 70.0:
        return "score_high"
    if score >= 2.0 or score >= 50.0:
        return "score_medium"
    if score > 0:
        return "score_low"
    return "score_unknown"


def _rr_bucket(value: Any) -> str:
    rr = _safe_float(value)
    if rr >= 2.0:
        return "rr_2_plus"
    if rr >= 1.5:
        return "rr_1_5_to_2"
    if rr > 0:
        return "rr_sub_1_5"
    return "rr_unknown"


def _health_bucket(value: float | None) -> str:
    if value is None:
        return "health_unknown"
    if value >= 0.65:
        return "health_strong"
    if value >= 0.40:
        return "health_normal"
    return "health_weak"


def _volume_tag(row: Dict[str, Any]) -> str:
    text = _row_text(row)
    if "volume expansion" in text or "high volume" in text or "volume" in text:
        return "volume_expansion"
    return "volume_unknown"


def _failure_tag(row: Dict[str, Any]) -> str:
    value = str(row.get("failure_cause_classification") or row.get("result_reason") or "").strip().lower()
    if not value:
        return "none"
    for key in ("bad_entry", "time_decay", "market_reversal", "news_shock", "liquidity_issue", "sector_weakness"):
        if key in value:
            return key
    return value[:40].replace(" ", "_")


def build_dna_fingerprint(row: Dict[str, Any], family: str, regime: str, health: float | None = None) -> str:
    side = str(row.get("side") or row.get("direction") or "UNKNOWN").strip().upper()
    if side not in {"LONG", "SHORT"}:
        side = "UNKNOWN"
    volatility = str(row.get("volatility_bucket") or row.get("volatility") or "vol_unknown").strip().lower().replace(" ", "_")
    if volatility not in {"calm", "normal", "elevated", "vol_unknown", "unknown"}:
        volatility = "vol_unknown"
    return "|".join(
        [
            family,
            side,
            regime,
            _score_bucket(row.get("score") or row.get("rank_score")),
            _rr_bucket(row.get("rr")),
            volatility,
            _volume_tag(row),
            _health_bucket(health),
            _failure_tag(row),
        ]
    )


def _lifecycle_family_health(lifecycle: Dict[str, Any]) -> Dict[str, float]:
    stats = lifecycle.get("setup_family_stats") if isinstance(lifecycle.get("setup_family_stats"), dict) else {}
    result = {}
    for family, bucket in stats.items():
        if isinstance(bucket, dict):
            result[str(family).upper()] = _clamp01(_safe_float(bucket.get("avg_trade_health_score"), 50.0) / 100.0)
    return result


def _active_regime(regime_memory: Dict[str, Any]) -> str:
    active = regime_memory.get("active_regime") if isinstance(regime_memory.get("active_regime"), dict) else {}
    value = str(active.get("primary") or "CHOPPY_NO_EDGE").strip().upper()
    return value or "CHOPPY_NO_EDGE"


def _family_state(samples: int, dominance: float, drift: float, decay: float, failure_rate: float) -> str:
    if samples < 10:
        return "INSUFFICIENT_DATA"
    if decay >= 0.20:
        return "DECAYING_OBSERVING"
    if drift >= 0.25:
        return "DRIFTING_OBSERVING"
    if failure_rate >= 0.65:
        return "HIGH_FAILURE_OBSERVING"
    if dominance >= 0.35:
        return "DOMINANT_OBSERVING"
    return "STABLE_OBSERVING"


def _previous_family(previous: Dict[str, Any], family: str) -> Dict[str, Any]:
    families = previous.get("families") if isinstance(previous.get("families"), dict) else {}
    item = families.get(family)
    return item if isinstance(item, dict) else {}


def _compile_genome(
    rows: List[Dict[str, Any]],
    evaluated_setups: List[Dict[str, Any]],
    memories: Dict[str, Dict[str, Any]],
    previous: Dict[str, Any],
) -> Dict[str, Any]:
    regime = _active_regime(memories.get("regime", {}))
    family_health = _lifecycle_family_health(memories.get("lifecycle", {}))
    family_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    fingerprint_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    failure_counter: Counter = Counter()

    combined_rows = list(rows[-MAX_OUTCOME_ROWS:]) + list(evaluated_setups[:MAX_INPUT_SETUPS])
    for row in combined_rows:
        if not isinstance(row, dict):
            continue
        family = classify_strategy_family(row)
        health = family_health.get(family)
        fingerprint = build_dna_fingerprint(row, family, regime, health)
        family_rows[family].append(row)
        fingerprint_rows[fingerprint].append(row)
        failure = _failure_tag(row)
        if failure != "none":
            failure_counter[failure] += 1

    total_rows = max(1, sum(len(items) for items in family_rows.values()))
    families: Dict[str, Any] = {}
    for family, items in sorted(family_rows.items(), key=lambda item: len(item[1]), reverse=True)[:MAX_FAMILIES]:
        wins = losses = open_or_other = 0
        scores = []
        rrs = []
        for row in items:
            outcome = _outcome_from_row(row)
            if outcome == "WIN":
                wins += 1
            elif outcome == "LOSS":
                losses += 1
            else:
                open_or_other += 1
            scores.append(_safe_float(row.get("score") or row.get("rank_score"), 0.0))
            rrs.append(_safe_float(row.get("rr"), 0.0))
        samples = wins + losses
        win_rate = wins / samples if samples else 0.0
        loss_rate = losses / samples if samples else 0.0
        avg_health = family_health.get(family, 0.5)
        previous_family = _previous_family(previous, family)
        previous_win_rate = _safe_float(previous_family.get("win_rate"), win_rate)
        confidence = _clamp01(samples / float(MIN_FAMILY_SAMPLES))
        drift = _score(abs(win_rate - previous_win_rate) * confidence)
        decay = _score(max(0.0, previous_win_rate - win_rate) * confidence)
        dominance = _score(len(items) / total_rows)
        stability = _score((1.0 - drift) * 0.55 + avg_health * 0.25 + (1.0 - loss_rate) * 0.20)
        families[family] = {
            "samples": samples,
            "wins": wins,
            "losses": losses,
            "open_or_other": open_or_other,
            "win_rate": round(win_rate, 4),
            "loss_rate": round(loss_rate, 4),
            "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "avg_rr": round(sum(rrs) / len(rrs), 4) if rrs else 0.0,
            "avg_lifecycle_health": round(avg_health, 4),
            "stability_score": stability,
            "drift_score": drift,
            "decay_score": decay,
            "dominance_score": dominance,
            "family_state": _family_state(samples, dominance, drift, decay, loss_rate),
            "recommended_live_weight": 0.0,
            "rank_adjustment": 0.0,
        }

    fingerprints: Dict[str, Any] = {}
    for fingerprint, items in sorted(fingerprint_rows.items(), key=lambda item: len(item[1]), reverse=True)[:MAX_FINGERPRINTS]:
        wins = sum(1 for row in items if _outcome_from_row(row) == "WIN")
        losses = sum(1 for row in items if _outcome_from_row(row) == "LOSS")
        samples = wins + losses
        failures = Counter(_failure_tag(row) for row in items if _failure_tag(row) != "none")
        family = fingerprint.split("|", 1)[0] if "|" in fingerprint else "UNKNOWN"
        fingerprints[fingerprint] = {
            "family": family,
            "samples": samples,
            "win_rate": round(wins / samples, 4) if samples else 0.0,
            "failure_patterns": [name for name, _ in failures.most_common(MAX_REPORT_ITEMS)],
        }

    regime_family: Dict[str, Dict[str, Any]] = {regime: {}}
    for family, stats in families.items():
        samples = _safe_int(stats.get("samples"))
        compatibility = _score(
            (_safe_float(stats.get("win_rate")) * 0.45)
            + (_safe_float(stats.get("avg_lifecycle_health"), 0.5) * 0.35)
            + ((1.0 - _safe_float(stats.get("loss_rate"))) * 0.20)
        )
        regime_family[regime][family] = {
            "samples": samples,
            "compatibility_score": compatibility,
            "confidence": _score(samples / float(MIN_REGIME_FAMILY_SAMPLES)),
        }

    failure_clusters = {
        name: {"count": count}
        for name, count in failure_counter.most_common(MAX_FAILURE_CLUSTERS)
    }
    dominant = [family for family, stats in families.items() if stats.get("family_state") == "DOMINANT_OBSERVING"]
    decaying = [family for family, stats in families.items() if stats.get("family_state") == "DECAYING_OBSERVING"]

    return {
        "active_regime": regime,
        "families": families,
        "dna_fingerprints": fingerprints,
        "regime_family_compatibility": regime_family,
        "failure_clusters": failure_clusters,
        "dominant_families": dominant[:MAX_REPORT_ITEMS],
        "decaying_families": decaying[:MAX_REPORT_ITEMS],
    }


def _promotion_features(genome: Dict[str, Any]) -> Dict[str, Any]:
    families = genome.get("families") if isinstance(genome.get("families"), dict) else {}
    samples = sum(_safe_int(stats.get("samples")) for stats in families.values() if isinstance(stats, dict))
    stability_values = [_safe_float(stats.get("stability_score")) for stats in families.values() if isinstance(stats, dict)]
    drift_values = [_safe_float(stats.get("drift_score")) for stats in families.values() if isinstance(stats, dict)]
    stability = sum(stability_values) / len(stability_values) if stability_values else 0.0
    drift_control = 1.0 - (sum(drift_values) / len(drift_values)) if drift_values else 0.0
    compatibility_scores = []
    regime_family = genome.get("regime_family_compatibility") if isinstance(genome.get("regime_family_compatibility"), dict) else {}
    for families_by_regime in regime_family.values():
        if not isinstance(families_by_regime, dict):
            continue
        for stats in families_by_regime.values():
            if isinstance(stats, dict):
                compatibility_scores.append(_safe_float(stats.get("compatibility_score")))
    compatibility = sum(compatibility_scores) / len(compatibility_scores) if compatibility_scores else 0.0
    failure_quality = 1.0 - min(1.0, len(genome.get("failure_clusters") or {}) / float(MAX_FAILURE_CLUSTERS))
    return {
        "samples": samples,
        "family_stability_score": _score(stability),
        "drift_control_score": _score(drift_control),
        "regime_compatibility_quality": _score(compatibility),
        "failure_cluster_quality": _score(failure_quality),
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
        "phase13_shadow_mode": PHASE13_SHADOW_MODE,
        "rank_adjustment": 0.0,
        "recommended_live_weight": 0.0,
        "ranking_changes": False,
        "final_decision_changes": False,
        "telegram_changes": False,
        "execution_changes": False,
        "tp_sl_changes": False,
        "broker_api_changes": False,
        "live_price_calls": False,
        "network_calls": False,
        "scanner_calls": False,
        "alert_cap_changes": False,
        "duplicate_prevention_changes": False,
        "dashboard_changes": False,
        "evaluated_setups_mutated": False,
        "final_decisions_mutated": False,
        "context_mutated": False,
        "forbidden_imports_detected": violations,
        "no_forbidden_imports_detected": not violations,
    }


def _neutral_snapshot(error: str | None = None, started_at: float | None = None) -> Dict[str, Any]:
    elapsed_ms = round(((time.monotonic() - started_at) if started_at else 0.0) * 1000.0, 3)
    warnings = ["phase13_failed_open"]
    if error:
        warnings.append(str(error)[:160])
    return {
        "version": STATE_VERSION,
        "phase13_shadow_mode": PHASE13_SHADOW_MODE,
        "generated_at": _now_text(),
        "runtime_ms": elapsed_ms,
        "runtime_bounded": elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0,
        "active_regime": "CHOPPY_NO_EDGE",
        "families": {},
        "dna_fingerprints": {},
        "regime_family_compatibility": {},
        "failure_clusters": {},
        "dominant_families": [],
        "decaying_families": [],
        "history": [],
        "promotion_gate_features": {
            "samples": 0,
            "family_stability_score": 0.0,
            "drift_control_score": 0.0,
            "regime_compatibility_quality": 0.0,
            "failure_cluster_quality": 0.0,
            "recommended_live_weight": 0.0,
            "promotion_eligible": False,
        },
        "warnings": warnings[:MAX_REPORT_ITEMS],
        "safety": _safety_block(),
        "rank_adjustment": 0.0,
        "recommended_live_weight": 0.0,
    }


def build_strategy_genome_snapshot(
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
        for name, path in {
            "regime": REGIME_MEMORY_PATH,
            "lifecycle": LIFECYCLE_MEMORY_PATH,
            "promotion_gate": PROMOTION_GATE_MEMORY_PATH,
            "master_shadow": MASTER_SHADOW_MEMORY_PATH,
        }.items():
            if time.monotonic() - started_at > RUNTIME_BUDGET_SECONDS:
                warnings.append("phase13_runtime_budget_reached")
                break
            data, info, layer_warnings = _read_json_limited(path, name)
            memories[name] = data
            freshness[name] = info
            warnings.extend(layer_warnings)

        previous, previous_info, previous_warnings = _read_json_limited(MEMORY_PATH, "phase13_previous")
        if previous_info.get("status") not in {"MISSING", "OVERSIZED_SKIPPED"}:
            warnings.extend(previous_warnings)

        rows, outcome_warnings = _read_outcome_rows()
        warnings.extend(outcome_warnings)

        genome = _compile_genome(rows, setup_snapshot, memories, previous)
        promotion_features = _promotion_features(genome)

        history = previous.get("history") if isinstance(previous.get("history"), list) else []
        history.append(
            {
                "generated_at": _now_text(),
                "dominant_family": genome.get("dominant_families", [None])[0] if genome.get("dominant_families") else None,
                "decaying_families": genome.get("decaying_families", []),
            }
        )
        history = history[-MAX_HISTORY:]

        elapsed_ms = round((time.monotonic() - started_at) * 1000.0, 3)
        runtime_bounded = elapsed_ms <= RUNTIME_BUDGET_SECONDS * 1000.0
        if not runtime_bounded:
            warnings.append("phase13_runtime_budget_exceeded")

        return {
            "version": STATE_VERSION,
            "phase13_shadow_mode": PHASE13_SHADOW_MODE,
            "generated_at": _now_text(),
            "runtime_ms": elapsed_ms,
            "runtime_bounded": runtime_bounded,
            "active_regime": genome.get("active_regime"),
            "families": genome.get("families"),
            "dna_fingerprints": genome.get("dna_fingerprints"),
            "regime_family_compatibility": genome.get("regime_family_compatibility"),
            "failure_clusters": genome.get("failure_clusters"),
            "dominant_families": genome.get("dominant_families"),
            "decaying_families": genome.get("decaying_families"),
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


def render_strategy_genome_report(snapshot: Dict[str, Any]) -> str:
    safety = snapshot.get("safety") if isinstance(snapshot.get("safety"), dict) else {}
    families = snapshot.get("families") if isinstance(snapshot.get("families"), dict) else {}
    promotion = snapshot.get("promotion_gate_features") if isinstance(snapshot.get("promotion_gate_features"), dict) else {}
    ordered = sorted(families.items(), key=lambda item: _safe_int(item[1].get("samples")) if isinstance(item[1], dict) else 0, reverse=True)

    lines = [
        "TITAN Phase 13 Strategy Genome Report",
        "======================================",
        "",
        "Safety",
        "- Shadow strategy genome only.",
        "- No ranking, final decision, Telegram, execution, TP/SL, broker/API, live-price, scanner, alert-cap, duplicate-prevention, Supabase, network, or dashboard integration.",
        f"- rank_adjustment: {safety.get('rank_adjustment', 0.0)}",
        f"- recommended_live_weight: {safety.get('recommended_live_weight', 0.0)}",
        f"- No forbidden imports detected: {safety.get('no_forbidden_imports_detected', False)}",
        "",
        f"Updated: {snapshot.get('generated_at')}",
        f"Runtime Ms: {snapshot.get('runtime_ms')} | Bounded: {snapshot.get('runtime_bounded')}",
        f"Active Regime: {snapshot.get('active_regime')}",
        "",
        "Top Strategy Families:",
    ]
    for family, stats in ordered[:MAX_REPORT_ITEMS]:
        lines.append(
            f"- {family}: samples={stats.get('samples', 0)}, "
            f"win_rate={stats.get('win_rate', 0.0)}, "
            f"stability={stats.get('stability_score', 0.0)}, "
            f"drift={stats.get('drift_score', 0.0)}, "
            f"state={stats.get('family_state')}"
        )
    if not ordered:
        lines.append("- None observed")

    lines.extend(
        [
            "",
            f"Dominant Families: {snapshot.get('dominant_families') or []}",
            f"Decaying Families: {snapshot.get('decaying_families') or []}",
            "",
            "Promotion Gate Compatibility:",
            f"- Samples: {promotion.get('samples', 0)}",
            f"- Family stability score: {promotion.get('family_stability_score', 0.0)}",
            f"- Drift control score: {promotion.get('drift_control_score', 0.0)}",
            f"- Regime compatibility quality: {promotion.get('regime_compatibility_quality', 0.0)}",
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


def refresh_strategy_genome(
    evaluated_setups: List[Dict[str, Any]] | None = None,
    final_decisions: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
    phase_results: Dict[str, Any] | None = None,
    force: bool = False,
) -> Dict[str, Any]:
    try:
        snapshot = build_strategy_genome_snapshot(
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
        REPORT_PATH.write_text(render_strategy_genome_report(snapshot), encoding="utf-8")
        return snapshot
    except Exception as exc:
        return _neutral_snapshot(str(exc))


if __name__ == "__main__":
    result = refresh_strategy_genome(force=True)
    print("TITAN Phase 13 Strategy Genome refreshed")
    print("Families:", len(result.get("families", {}) or {}))
    print("Report:", REPORT_PATH)
