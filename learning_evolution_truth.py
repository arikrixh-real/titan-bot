from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime"
JOURNAL_DIR = PROJECT_ROOT / "data" / "journals"

EVOLUTION_MEMORY_PATH = RUNTIME_DIR / "evolution_memory.json"
STRATEGY_WEIGHT_CHANGE_LOG_PATH = RUNTIME_DIR / "strategy_weight_change_log.json"
SETUP_PERFORMANCE_HISTORY_PATH = RUNTIME_DIR / "setup_performance_history.json"
MARKET_REGIME_ACCURACY_PATH = RUNTIME_DIR / "market_regime_accuracy.json"
SYMBOL_ACCURACY_TABLE_PATH = RUNTIME_DIR / "symbol_accuracy_table.json"
FINAL_VALIDATED_SETUPS_PATH = RUNTIME_DIR / "final_validated_setups.json"

OUTCOME_PATHS = [
    JOURNAL_DIR / "trade_outcomes.csv",
    JOURNAL_DIR / "trade_results.csv",
    PROJECT_ROOT / "trade_results.csv",
    PROJECT_ROOT / "trade_outcomes.csv",
]
OUTCOME_JSONL_PATHS = [
    JOURNAL_DIR / "trade_outcomes.jsonl",
    JOURNAL_DIR / "trade_results.jsonl",
]

WIN_OUTCOMES = {"TP", "WIN", "WON", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}
LOSS_OUTCOMES = {"SL", "LOSS", "LOST", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}
DEFAULT_WEIGHTS = {"volume_weight": 1.0, "strength_weight": 1.0, "compression_weight": 1.0}
MIN_SAMPLES_FOR_WEIGHT_CHANGE = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default if default is not None else {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    try:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line.strip())
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _upper(value: Any, default: str = "UNKNOWN") -> str:
    return _text(value, default).upper()


def _normalize_outcome(row: Dict[str, Any]) -> str | None:
    for key in ("outcome", "result", "status", "trade_result"):
        raw = _upper(row.get(key), "")
        if raw in WIN_OUTCOMES:
            return "WIN"
        if raw in LOSS_OUTCOMES:
            return "LOSS"
    return None


def _is_real_outcome(row: Dict[str, Any]) -> bool:
    source = _upper(row.get("source"), "")
    trade_id = _upper(row.get("trade_id"), "")
    paper_id = _upper(row.get("paper_trade_id"), "")
    test_trade = str(row.get("test_trade") or "").strip().lower() in {"1", "true", "yes", "y"}
    if test_trade or "SYNTHETIC" in source or "SYNTHETIC" in trade_id or "SYNTHETIC" in paper_id:
        return False
    return _normalize_outcome(row) in {"WIN", "LOSS"}


def _record_id(row: Dict[str, Any], index: int) -> str:
    return "|".join(
        [
            _text(row.get("trade_id") or row.get("paper_trade_id") or str(index)),
            _upper(row.get("symbol"), "UNKNOWN"),
            _upper(row.get("side"), "UNKNOWN"),
            _text(row.get("opened_at") or row.get("created_at") or row.get("closed_at")),
        ]
    )


def _load_outcomes() -> List[Dict[str, Any]]:
    rows = []
    for path in OUTCOME_PATHS:
        rows.extend(_read_csv(path))
    for path in OUTCOME_JSONL_PATHS:
        rows.extend(_read_jsonl(path))
    deduped = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not _is_real_outcome(row):
            continue
        item = dict(row)
        item["_record_id"] = _record_id(item, index)
        deduped[item["_record_id"]] = item
    return list(deduped.values())


def _parse_market_regime(row: Dict[str, Any]) -> str:
    for key in ("market_regime", "regime", "regime_label"):
        if _text(row.get(key)):
            return _upper(row.get(key))
    raw = row.get("market_status")
    if isinstance(raw, dict):
        return _upper(raw.get("regime") or raw.get("status") or raw.get("direction"))
    if _text(raw):
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                return _upper(parsed.get("regime") or parsed.get("status") or parsed.get("direction"))
        except Exception:
            return _upper(raw)
    return "UNKNOWN"


def _setup_type(row: Dict[str, Any]) -> str:
    explicit = _upper(row.get("setup_type") or row.get("strategy") or row.get("strategy_family"), "")
    if explicit:
        return explicit
    reason = _upper(row.get("reason") or row.get("result_reason") or row.get("reinforcement_regime_key"), "")
    tags = _filter_tags(reason)
    if "compression" in tags:
        return "COMPRESSION_BREAKOUT"
    if "relative_strength" in tags:
        return "RELATIVE_STRENGTH_BREAKOUT"
    if "breakout" in tags:
        return "BREAKOUT"
    if "momentum" in tags:
        return "MOMENTUM_CONTINUATION"
    return "UNKNOWN"


def _filter_tags(text: str) -> List[str]:
    text = _upper(text, "")
    tags = []
    keywords = {
        "trend": ("TREND", "EMA", "BULLISH", "BEARISH"),
        "momentum": ("MOMENTUM", "RSI", "STRENGTH"),
        "structure": ("STRUCTURE", "SUPPORT", "RESISTANCE"),
        "breakout": ("BREAKOUT", "ENTRY=PASS", "TARGET"),
        "volume": ("VOLUME", "VOL"),
        "compression": ("COMPRESSION", "SQUEEZE"),
        "relative_strength": ("RELATIVE", "RS"),
    }
    for tag, words in keywords.items():
        if any(word in text for word in words):
            tags.append(tag)
    return tags or ["general"]


def _achieved_rr(row: Dict[str, Any], outcome: str) -> float:
    rr = _safe_float(row.get("rr") or row.get("risk_reward"), 0.0)
    risk_per_share = _safe_float(row.get("risk_per_share"), 0.0)
    pnl_points = _safe_float(row.get("pnl_points"), 0.0)
    if risk_per_share > 0 and pnl_points:
        return round(pnl_points / risk_per_share, 4)
    if outcome == "WIN" and rr > 0:
        return round(rr, 4)
    if outcome == "LOSS":
        return -1.0
    return 0.0


def _new_bucket() -> Dict[str, Any]:
    return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "average_rr_achieved": 0.0, "_rr_total": 0.0}


def _update_bucket(bucket: Dict[str, Any], outcome: str, rr_achieved: float) -> None:
    bucket["trades"] += 1
    if outcome == "WIN":
        bucket["wins"] += 1
    elif outcome == "LOSS":
        bucket["losses"] += 1
    bucket["_rr_total"] += rr_achieved


def _finalize_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    trades = int(bucket.get("trades") or 0)
    wins = int(bucket.get("wins") or 0)
    public = {key: value for key, value in bucket.items() if not key.startswith("_")}
    public["win_rate"] = round(wins / trades, 4) if trades else 0.0
    public["average_rr_achieved"] = round(float(bucket.get("_rr_total") or 0.0) / trades, 4) if trades else 0.0
    public["sample_confidence"] = round(min(1.0, trades / 30.0), 4)
    return public


def _rank_best(items: Dict[str, Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    ranked = [{"name": key, **value} for key, value in items.items() if int(value.get("trades") or 0) > 0]
    ranked.sort(key=lambda row: (row.get("win_rate", 0), row.get("average_rr_achieved", 0), row.get("trades", 0)), reverse=True)
    return ranked[:limit]


def _rank_worst(items: Dict[str, Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    ranked = [{"name": key, **value} for key, value in items.items() if int(value.get("trades") or 0) > 0]
    ranked.sort(key=lambda row: (row.get("win_rate", 0), row.get("average_rr_achieved", 0), -row.get("trades", 0)))
    return ranked[:limit]


def _recommended_weights(filter_stats: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    mapping = {"volume": "volume_weight", "momentum": "strength_weight", "compression": "compression_weight"}
    weights = dict(DEFAULT_WEIGHTS)
    for tag, weight_key in mapping.items():
        stats = filter_stats.get(tag)
        if not stats or int(stats.get("trades") or 0) < MIN_SAMPLES_FOR_WEIGHT_CHANGE:
            continue
        edge = _safe_float(stats.get("win_rate"), 0.5) - 0.5
        confidence = min(1.0, int(stats.get("trades") or 0) / 30.0)
        weights[weight_key] = round(max(0.7, min(1.3, 1.0 + edge * confidence)), 4)
    return weights


def _append_weight_log(previous_memory: Dict[str, Any], current_weights: Dict[str, float], generated_at: str, closed_count: int) -> Dict[str, Any]:
    existing = _read_json(STRATEGY_WEIGHT_CHANGE_LOG_PATH, {"changes": []})
    changes = existing.get("changes") if isinstance(existing.get("changes"), list) else []
    previous_weights = (
        previous_memory.get("recommended_strategy_weights")
        if isinstance(previous_memory.get("recommended_strategy_weights"), dict)
        else DEFAULT_WEIGHTS
    )
    changed = {
        key: {"from": previous_weights.get(key), "to": current_weights.get(key)}
        for key in sorted(current_weights)
        if current_weights.get(key) != previous_weights.get(key)
    }
    if changed:
        changes.append(
            {
                "timestamp_utc": generated_at,
                "closed_outcome_count": closed_count,
                "changes": changed,
                "basis": "Outcome-backed bucket win rates; advisory log only.",
            }
        )
    payload = {
        "generated_at_utc": generated_at,
        "change_count": len(changes),
        "changes_today": sum(1 for item in changes if str(item.get("timestamp_utc", "")).startswith(generated_at[:10])),
        "latest_recommended_weights": current_weights,
        "changes": changes[-200:],
        "safety": _safety(),
    }
    _write_json(STRATEGY_WEIGHT_CHANGE_LOG_PATH, payload)
    return payload


def _score_change_proofs(setups: List[Dict[str, Any]], memory: Dict[str, Any], previous_memory: Dict[str, Any]) -> List[Dict[str, Any]]:
    previous_weights = previous_memory.get("recommended_strategy_weights") if isinstance(previous_memory.get("recommended_strategy_weights"), dict) else DEFAULT_WEIGHTS
    current_weights = memory.get("recommended_strategy_weights") if isinstance(memory.get("recommended_strategy_weights"), dict) else DEFAULT_WEIGHTS
    proofs = []
    for setup in setups:
        base_score = _safe_float(setup.get("base_score") or setup.get("final_score") or setup.get("score"), 0.0)
        symbol = _upper(setup.get("symbol"))
        setup_type = _setup_type(setup)
        symbol_bucket = (memory.get("symbol_accuracy") or {}).get(symbol, {})
        setup_bucket = (memory.get("setup_type_performance") or {}).get(setup_type, {})
        confidence = _safe_float(memory.get("learning_confidence"), 0.0)
        weight_delta = round(sum(current_weights.values()) - sum(previous_weights.values()), 4)
        advisory_delta = round(
            weight_delta
            + (_safe_float(symbol_bucket.get("win_rate"), 0.5) - 0.5) * confidence
            + (_safe_float(setup_bucket.get("win_rate"), 0.5) - 0.5) * confidence,
            4,
        )
        proofs.append(
            {
                "symbol": symbol,
                "setup_type": setup_type,
                "base_score": base_score,
                "advisory_score_delta": advisory_delta,
                "advisory_score_after_learning": round(max(0.0, min(100.0, base_score + advisory_delta)), 4),
                "why_this_score_changed_from_previous_cycles": [
                    f"strategy_weight_delta_sum={weight_delta}",
                    f"symbol_win_rate={symbol_bucket.get('win_rate', 'insufficient_outcomes')}",
                    f"setup_type_win_rate={setup_bucket.get('win_rate', 'insufficient_outcomes')}",
                    f"learning_confidence={confidence}",
                    "advisory proof only; scanner thresholds and broker behavior unchanged",
                ],
            }
        )
    return proofs


def _safety() -> Dict[str, Any]:
    return {
        "outcome_backed_only": True,
        "synthetic_rows_excluded": True,
        "affects_execution": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "threshold_change": False,
        "fake_learning": False,
    }


def refresh_learning_evolution_truth(write_files: bool = True) -> Dict[str, Any]:
    generated_at = _now()
    previous_memory = _read_json(EVOLUTION_MEMORY_PATH, {})
    outcomes = _load_outcomes()
    setup_buckets: Dict[str, Dict[str, Any]] = defaultdict(_new_bucket)
    symbol_buckets: Dict[str, Dict[str, Any]] = defaultdict(_new_bucket)
    regime_buckets: Dict[str, Dict[str, Any]] = defaultdict(_new_bucket)
    filter_buckets: Dict[str, Dict[str, Any]] = defaultdict(_new_bucket)
    rr_values = []

    for row in outcomes:
        outcome = _normalize_outcome(row)
        if outcome not in {"WIN", "LOSS"}:
            continue
        rr_achieved = _achieved_rr(row, outcome)
        rr_values.append(rr_achieved)
        setup_type = _setup_type(row)
        symbol = _upper(row.get("symbol"))
        regime = _parse_market_regime(row)
        _update_bucket(setup_buckets[setup_type], outcome, rr_achieved)
        _update_bucket(symbol_buckets[symbol], outcome, rr_achieved)
        _update_bucket(regime_buckets[regime], outcome, rr_achieved)
        for tag in _filter_tags(" ".join([_text(row.get("reason")), _text(row.get("result_reason")), setup_type])):
            _update_bucket(filter_buckets[tag], outcome, rr_achieved)

    setup_stats = {key: _finalize_bucket(value) for key, value in sorted(setup_buckets.items())}
    symbol_stats = {key: _finalize_bucket(value) for key, value in sorted(symbol_buckets.items())}
    regime_stats = {key: _finalize_bucket(value) for key, value in sorted(regime_buckets.items())}
    filter_stats = {key: _finalize_bucket(value) for key, value in sorted(filter_buckets.items())}
    total = len(outcomes)
    wins = sum(1 for row in outcomes if _normalize_outcome(row) == "WIN")
    recommended_weights = _recommended_weights(filter_stats)
    learning_confidence = round(min(1.0, total / 30.0), 4)

    memory = {
        "generated_at_utc": generated_at,
        "closed_outcome_count": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total, 4) if total else 0.0,
        "average_rr_achieved": round(sum(rr_values) / len(rr_values), 4) if rr_values else 0.0,
        "learning_confidence": learning_confidence,
        "setup_type_performance": setup_stats,
        "symbol_accuracy": symbol_stats,
        "market_regime_accuracy": regime_stats,
        "filter_performance": filter_stats,
        "best_performing_filters": _rank_best(filter_stats),
        "worst_performing_filters": _rank_worst(filter_stats),
        "top_performing_setup_type": (_rank_best(setup_stats, 1) or [{"name": "INSUFFICIENT_OUTCOMES"}])[0],
        "weakest_setup_type": (_rank_worst(setup_stats, 1) or [{"name": "INSUFFICIENT_OUTCOMES"}])[0],
        "best_symbols": _rank_best(symbol_stats),
        "weakest_symbols": _rank_worst(symbol_stats),
        "recommended_strategy_weights": recommended_weights,
        "score_weight_changes_are_advisory": True,
        "safety": _safety(),
    }
    weight_log = _append_weight_log(previous_memory, recommended_weights, generated_at, total)
    setups_payload = _read_json(FINAL_VALIDATED_SETUPS_PATH, {"setups": []})
    setups = setups_payload.get("setups") if isinstance(setups_payload.get("setups"), list) else []
    setup_history = {
        "generated_at_utc": generated_at,
        "closed_outcome_count": total,
        "setup_type_performance": setup_stats,
        "current_setup_score_change_proofs": _score_change_proofs(setups, memory, previous_memory),
        "safety": _safety(),
    }
    if write_files:
        _write_json(EVOLUTION_MEMORY_PATH, memory)
        _write_json(SETUP_PERFORMANCE_HISTORY_PATH, setup_history)
        _write_json(MARKET_REGIME_ACCURACY_PATH, {
            "generated_at_utc": generated_at,
            "market_regime_accuracy": regime_stats,
            "safety": _safety(),
        })
        _write_json(SYMBOL_ACCURACY_TABLE_PATH, {
            "generated_at_utc": generated_at,
            "symbol_accuracy": symbol_stats,
            "best_symbols": memory["best_symbols"],
            "weakest_symbols": memory["weakest_symbols"],
            "safety": _safety(),
        })
    memory["strategy_weight_change_log"] = {
        "path": "data/runtime/strategy_weight_change_log.json",
        "changes_today": weight_log.get("changes_today", 0),
        "change_count": weight_log.get("change_count", 0),
    }
    return memory


if __name__ == "__main__":
    result = refresh_learning_evolution_truth(write_files=True)
    print(f"closed_outcome_count: {result.get('closed_outcome_count')}")
    print(f"win_rate: {result.get('win_rate')}")
    print(f"learning_confidence: {result.get('learning_confidence')}")
    print(f"changes_today: {(result.get('strategy_weight_change_log') or {}).get('changes_today')}")
