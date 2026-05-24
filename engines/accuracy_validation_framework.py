"""
TITAN Phase 40 - Accuracy Validation Framework.

Advisory-only validation over existing live, paper, replay, and journal
artifacts. It persists rolling state and writes reports for visibility only.
It never changes ranking, scanner output, alerts, execution, broker state,
Telegram, Supabase, dashboards, or live orders.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "accuracy_validation_state.json"
RUNTIME_STATUS_PATH = PROJECT_ROOT / "data" / "runtime" / "accuracy_validation_status.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "accuracy_validation_report.txt"

MAX_ROWS_PER_SOURCE = 2000
MAX_PROCESSED_IDS = 10000
STATE_VERSION = "40.0"

ARTIFACT_SOURCES = [
    ("live_outcomes_jsonl", PROJECT_ROOT / "data" / "journals" / "trade_outcomes.jsonl", "jsonl", "live_or_paper"),
    ("journal_outcomes_jsonl", PROJECT_ROOT / "data" / "journals" / "trade_journal.jsonl", "jsonl", "live_or_paper"),
    ("journal_outcomes_csv", PROJECT_ROOT / "data" / "journals" / "trade_outcomes.csv", "csv", "live_or_paper"),
    ("root_trade_journal_csv", PROJECT_ROOT / "data" / "trade_journal.csv", "csv", "live_or_paper"),
    ("legacy_trade_journal_csv", PROJECT_ROOT / "journal" / "trade_journal.csv", "csv", "live_or_paper"),
    (
        "historical_replay_jsonl",
        PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
        "jsonl",
        "replay",
    ),
]

WIN_OUTCOMES = {"TP", "WIN", "WON", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS", "CLOSED_PROFIT"}
LOSS_OUTCOMES = {"SL", "LOSS", "LOST", "STOPLOSS", "STOP_LOSS", "STOP_LOSS_HIT", "SL_HIT", "FAILED", "CLOSED_LOSS"}
NEGATIVE_DECISIONS = {"NO_TRADE", "REJECT", "REJECTED", "SKIP", "SKIPPED", "BLOCK", "BLOCKED", "AVOID"}


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


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)][-MAX_ROWS_PER_SOURCE:]
    except Exception:
        return []


def _read_jsonl_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text)
                except Exception:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        return rows[-MAX_ROWS_PER_SOURCE:]
    except Exception:
        return []


def _normalize_outcome(value: Any) -> str:
    text = _safe_text(value, "UNKNOWN").upper().replace(" ", "_")
    if text in WIN_OUTCOMES:
        return "WIN"
    if text in LOSS_OUTCOMES:
        return "LOSS"
    if text in {"OPEN", "ACTIVE", "LIVE", "RUNNING", "PENDING"}:
        return "OPEN"
    if text in {"FLAT", "BREAKEVEN", "NO_FOLLOWUP"}:
        return "NEUTRAL"
    return text or "UNKNOWN"


def _outcome(row: Dict[str, Any]) -> str:
    for key in ("outcome", "result", "status", "trade_result", "exit_reason"):
        if _safe_text(row.get(key)):
            return _normalize_outcome(row.get(key))
    return "UNKNOWN"


def _symbol(row: Dict[str, Any]) -> str:
    return _safe_text(row.get("symbol") or row.get("stock") or row.get("ticker"), "UNKNOWN").replace(".NS", "").upper()


def _strategy(row: Dict[str, Any]) -> str:
    return _safe_text(
        row.get("strategy")
        or row.get("strategy_family")
        or row.get("setup_type")
        or row.get("pattern")
        or row.get("setup_name"),
        "UNKNOWN",
    ).upper()


def _regime(row: Dict[str, Any]) -> str:
    return _safe_text(
        row.get("regime")
        or row.get("market_regime")
        or row.get("regime_label")
        or row.get("market_context_label")
        or row.get("market_type"),
        "UNKNOWN",
    ).upper()


def _sector(row: Dict[str, Any]) -> str:
    return _safe_text(row.get("sector") or row.get("industry") or row.get("sector_name") or row.get("sector_rotation_label"), "UNKNOWN").upper()


def _prediction(row: Dict[str, Any]) -> str:
    for key in ("prediction", "predicted_outcome", "expected_outcome", "decision", "trade_permission", "action"):
        value = _safe_text(row.get(key))
        if not value:
            continue
        text = value.upper().replace(" ", "_")
        if text in WIN_OUTCOMES or text in {"TRADE", "BUY", "SELL", "LONG", "SHORT", "SELECTED", "APPROVED"}:
            return "POSITIVE"
        if text in LOSS_OUTCOMES or text in NEGATIVE_DECISIONS:
            return "NEGATIVE"
    for key in ("selected", "alert_sent", "paper_trade", "trade_taken"):
        if str(row.get(key)).strip().lower() in {"true", "1", "yes"}:
            return "POSITIVE"
    score = None
    for key in ("final_score", "score", "rank_score", "final_portfolio_rank", "confidence_score"):
        if row.get(key) not in (None, ""):
            score = _safe_float(row.get(key))
            break
    if score is not None and score >= 65.0:
        return "POSITIVE"
    return "POSITIVE"


def _record_id(source_name: str, row: Dict[str, Any], index: int) -> str:
    explicit = _safe_text(row.get("trade_id") or row.get("id") or row.get("signal_id") or row.get("setup_id"))
    if explicit:
        return f"{source_name}:{explicit}"
    parts = [
        _safe_text(row.get("timestamp") or row.get("created_at") or row.get("entry_time") or row.get("date")),
        _symbol(row),
        _safe_text(row.get("side") or row.get("direction")),
        _safe_text(row.get("entry") or row.get("entry_price") or row.get("price")),
        _outcome(row),
        str(index),
    ]
    return f"{source_name}:{'|'.join(parts)}"


def _empty_bucket() -> Dict[str, Any]:
    return {"samples": 0, "wins": 0, "losses": 0, "unknown": 0, "false_positive": 0, "false_negative": 0, "accuracy": 0.0}


def _update_bucket(bucket: Dict[str, Any], outcome: str, prediction: str) -> None:
    bucket["samples"] = int(bucket.get("samples", 0)) + 1
    if outcome == "WIN":
        bucket["wins"] = int(bucket.get("wins", 0)) + 1
    elif outcome == "LOSS":
        bucket["losses"] = int(bucket.get("losses", 0)) + 1
    else:
        bucket["unknown"] = int(bucket.get("unknown", 0)) + 1
    if prediction == "POSITIVE" and outcome == "LOSS":
        bucket["false_positive"] = int(bucket.get("false_positive", 0)) + 1
    if prediction == "NEGATIVE" and outcome == "WIN":
        bucket["false_negative"] = int(bucket.get("false_negative", 0)) + 1


def _finalize_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    samples = int(bucket.get("samples", 0))
    wins = int(bucket.get("wins", 0))
    losses = int(bucket.get("losses", 0))
    closed = wins + losses
    false_positive = int(bucket.get("false_positive", 0))
    false_negative = int(bucket.get("false_negative", 0))
    bucket["closed_samples"] = closed
    bucket["win_rate"] = round(wins / closed, 4) if closed else 0.0
    bucket["false_positive_rate"] = round(false_positive / closed, 4) if closed else 0.0
    bucket["false_negative_rate"] = round(false_negative / closed, 4) if closed else 0.0
    bucket["accuracy"] = round((closed - false_positive - false_negative) / closed, 4) if closed else 0.0
    bucket["sample_confidence"] = round(min(1.0, closed / 50.0), 4)
    bucket["data_available"] = samples > 0
    return bucket


def _collect_rows() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    sources: Dict[str, Any] = {}
    for source_name, path, kind, mode in ARTIFACT_SOURCES:
        raw_rows = _read_jsonl_rows(path) if kind == "jsonl" else _read_csv_rows(path)
        sources[source_name] = {
            "path": _relative(path),
            "available": path.exists(),
            "rows_loaded": len(raw_rows),
            "mode": mode,
        }
        for index, row in enumerate(raw_rows):
            item = dict(row)
            item["_phase40_source"] = source_name
            item["_phase40_mode"] = mode
            item["_phase40_record_id"] = _record_id(source_name, row, index)
            rows.append(item)
    return rows, sources


def _group_stats(rows: Iterable[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = defaultdict(_empty_bucket)
    for row in rows:
        outcome = _outcome(row)
        if outcome not in {"WIN", "LOSS", "NEUTRAL", "OPEN"}:
            continue
        _update_bucket(groups[key_fn(row)], outcome, _prediction(row))
    return {key: _finalize_bucket(value) for key, value in sorted(groups.items())}


def _top_weak_areas(groups: Dict[str, Dict[str, Any]], area: str, limit: int = 12) -> List[Dict[str, Any]]:
    items = []
    for name, bucket in groups.items():
        closed = int(bucket.get("closed_samples", 0))
        if not closed:
            continue
        weakness = (1.0 - _safe_float(bucket.get("accuracy"))) * min(1.0, closed / 30.0)
        items.append({
            "area": area,
            "name": name,
            "closed_samples": closed,
            "accuracy": bucket.get("accuracy"),
            "false_positive_rate": bucket.get("false_positive_rate"),
            "false_negative_rate": bucket.get("false_negative_rate"),
            "weakness_score": round(weakness, 4),
        })
    items.sort(key=lambda item: (item["weakness_score"], item["closed_samples"]), reverse=True)
    return items[:limit]


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
    }


def build_accuracy_validation_state(previous: Dict[str, Any] | None = None) -> Dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    rows, sources = _collect_rows()
    closed_rows = [row for row in rows if _outcome(row) in {"WIN", "LOSS"}]
    processed_ids = {_safe_text(item) for item in previous.get("processed_record_ids", []) if _safe_text(item)}
    current_ids = {_safe_text(row.get("_phase40_record_id")) for row in rows if _safe_text(row.get("_phase40_record_id"))}
    new_ids = current_ids.difference(processed_ids)
    combined_ids = list((processed_ids | current_ids))[-MAX_PROCESSED_IDS:]

    overall = _finalize_bucket(_empty_bucket())
    by_mode: Dict[str, Dict[str, Any]] = defaultdict(_empty_bucket)
    for row in rows:
        outcome = _outcome(row)
        if outcome not in {"WIN", "LOSS", "NEUTRAL", "OPEN"}:
            continue
        prediction = _prediction(row)
        _update_bucket(overall, outcome, prediction)
        _update_bucket(by_mode[row.get("_phase40_mode") or "unknown"], outcome, prediction)
    overall = _finalize_bucket(overall)
    by_mode = {key: _finalize_bucket(value) for key, value in sorted(by_mode.items())}

    strategy_accuracy = _group_stats(rows, _strategy)
    regime_accuracy = _group_stats(rows, _regime)
    sector_accuracy = _group_stats(rows, _sector)
    symbol_accuracy = _group_stats(rows, _symbol)
    weak_areas = (
        _top_weak_areas(strategy_accuracy, "strategy")
        + _top_weak_areas(regime_accuracy, "regime")
        + _top_weak_areas(sector_accuracy, "sector")
    )
    weak_areas.sort(key=lambda item: (item["weakness_score"], item["closed_samples"]), reverse=True)

    run_count = int(_safe_float(previous.get("run_count"), 0.0)) + 1
    now = _now_utc()
    state = {
        "version": STATE_VERSION,
        "phase": "PHASE_40_ACCURACY_VALIDATION_FRAMEWORK",
        "status": "OK" if closed_rows else "WAITING_FOR_OUTCOMES",
        "generated_at": now,
        "first_seen_at": previous.get("first_seen_at") or now,
        "previous_generated_at": previous.get("generated_at"),
        "run_count": run_count,
        "continued_from_previous_state": bool(previous),
        "previous_run_count": previous.get("run_count", 0),
        "records_seen_this_run": len(rows),
        "closed_records_this_run": len(closed_rows),
        "new_record_ids_this_run": len(new_ids),
        "unique_record_ids_total": len(combined_ids),
        "processed_record_ids": combined_ids,
        "sources": sources,
        "overall_accuracy": overall,
        "mode_accuracy": by_mode,
        "strategy_accuracy": strategy_accuracy,
        "regime_accuracy": regime_accuracy,
        "sector_accuracy": sector_accuracy,
        "symbol_accuracy": dict(list(symbol_accuracy.items())[:200]),
        "weak_areas": weak_areas[:24],
        "report_path": _relative(REPORT_PATH),
        "state_path": _relative(MEMORY_PATH),
        "runtime_status_path": _relative(RUNTIME_STATUS_PATH),
        "safety_flags": _safety_flags(),
        **_safety_flags(),
    }
    return state


def render_accuracy_validation_report(state: Dict[str, Any]) -> str:
    overall = state.get("overall_accuracy") if isinstance(state.get("overall_accuracy"), dict) else {}
    lines = [
        "TITAN PHASE 40 ACCURACY VALIDATION REPORT",
        "=" * 60,
        f"Updated: {state.get('generated_at')}",
        f"Status: {state.get('status')}",
        f"Run count: {state.get('run_count')} | Continued: {state.get('continued_from_previous_state')}",
        f"Records seen: {state.get('records_seen_this_run')} | Closed: {state.get('closed_records_this_run')} | New IDs: {state.get('new_record_ids_this_run')}",
        "",
        "Safety",
        "- advisory_only=true research_only=true shadow_mode=true",
        "- affects_live_ranking=false affects_execution=false broker_mutation=false telegram_mutation=false supabase_mutation=false",
        "",
        "Overall",
        f"- Accuracy: {overall.get('accuracy')} | Win rate: {overall.get('win_rate')} | False positive rate: {overall.get('false_positive_rate')} | False negative rate: {overall.get('false_negative_rate')}",
        "",
        "Weak Areas",
    ]
    for item in state.get("weak_areas", [])[:12]:
        lines.append(
            f"- {item.get('area')} {item.get('name')}: accuracy={item.get('accuracy')}, "
            f"fp={item.get('false_positive_rate')}, fn={item.get('false_negative_rate')}, samples={item.get('closed_samples')}"
        )
    if not state.get("weak_areas"):
        lines.append("- None with closed samples yet")
    return "\n".join(lines) + "\n"


def refresh_accuracy_validation(write_files: bool = True) -> Dict[str, Any]:
    previous = _read_json(MEMORY_PATH)
    state = build_accuracy_validation_state(previous)
    runtime_status = {
        "phase": state["phase"],
        "status": state["status"],
        "generated_at": state["generated_at"],
        "run_count": state["run_count"],
        "continued_from_previous_state": state["continued_from_previous_state"],
        "records_seen_this_run": state["records_seen_this_run"],
        "closed_records_this_run": state["closed_records_this_run"],
        "new_record_ids_this_run": state["new_record_ids_this_run"],
        "overall_accuracy": state["overall_accuracy"],
        "weak_areas": state["weak_areas"][:8],
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
        REPORT_PATH.write_text(render_accuracy_validation_report(state), encoding="utf-8")
    return state


if __name__ == "__main__":
    result = refresh_accuracy_validation(write_files=True)
    print("TITAN Phase 40 Accuracy Validation refreshed")
    print("Status:", result.get("status"))
    print("Run count:", result.get("run_count"))
