"""
TITAN Experience Maturity Batch 2 - No-Trade Refinement Memory Engine.

Builds advisory-only memory for historical no-trade decisions versus outcomes.
It is not a no-trade gate and does not modify Phase 35, final decisions, alert
filtering, ranking, scanners, execution, dashboard, broker/API, Telegram, or
Supabase state.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "no_trade_refinement_memory.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "no_trade_refinement_memory_report.txt"

DEFAULT_RECORD_PATHS = [
    PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.csv",
    PROJECT_ROOT / "journal" / "trade_journal.csv",
]

STATE_VERSION = "2.0"
MAX_RECORDS = 300
MAX_BUCKETS = 50
MAX_EXAMPLES = 5
MAX_FILE_BYTES = 1_000_000


def _now_text() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_text(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value).strip()
    except Exception:
        return default


def _symbol(row: Dict[str, Any]) -> str:
    return _safe_text(row.get("symbol") or row.get("stock") or row.get("ticker") or "UNKNOWN").replace(".NS", "").upper()


def _permission(row: Dict[str, Any]) -> str:
    return _safe_text(row.get("trade_permission") or row.get("no_trade_permission") or row.get("permission") or "UNKNOWN").upper()


def _warning(row: Dict[str, Any]) -> str:
    return _safe_text(row.get("no_trade_warning") or row.get("warning") or "NONE").upper()


def _normalise_outcome(row: Dict[str, Any]) -> Optional[str]:
    text = _safe_text(row.get("outcome") or row.get("result") or row.get("status") or row.get("trade_result")).upper()
    if text in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if text in {"LOSS", "LOST", "SL", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}:
        return "LOSS"
    pnl = _safe_float(row.get("pnl") or row.get("pnl_pct") or row.get("profit"), 0.0)
    if pnl > 0.0:
        return "WIN"
    if pnl < 0.0:
        return "LOSS"
    return None


def infer_refinement_bucket(row: Dict[str, Any]) -> str:
    permission = _permission(row)
    warning = _warning(row)
    outcome = _normalise_outcome(row)
    text = " ".join(_safe_text(row.get(key)).lower() for key in ("reason", "setup_reason", "lesson_learned", "failure_cause"))

    blocked = permission == "BLOCK" or warning == "SKIP"
    waited = permission == "WAIT" or warning == "WAIT"
    allowed = permission == "ALLOW" or warning in {"NONE", ""}

    if allowed and outcome == "LOSS":
        return "ALLOW_THEN_LOSS"
    if blocked and outcome == "WIN":
        return "BLOCK_THEN_WIN"
    if waited and outcome == "WIN":
        return "WAIT_THEN_WIN"
    if blocked and outcome == "LOSS":
        return "BLOCK_THEN_LOSS"
    if waited and outcome == "LOSS":
        return "WAIT_THEN_LOSS"
    if "chop" in text or "low edge" in text or "weak breadth" in text:
        return "CONTEXT_WARNING"
    return "UNKNOWN_OR_NEUTRAL"


def _new_bucket(name: str) -> Dict[str, Any]:
    return {
        "refinement_type": name,
        "samples": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "avg_no_trade_score": 0.0,
        "examples": [],
    }


def _update_bucket(bucket: Dict[str, Any], row: Dict[str, Any], outcome: Optional[str]) -> None:
    samples = int(bucket.get("samples") or 0) + 1
    old_samples = samples - 1
    score = _safe_float(row.get("no_trade_score"), 0.0)
    bucket["samples"] = samples
    if outcome == "WIN":
        bucket["wins"] = int(bucket.get("wins") or 0) + 1
    elif outcome == "LOSS":
        bucket["losses"] = int(bucket.get("losses") or 0) + 1
    attempts = int(bucket.get("wins") or 0) + int(bucket.get("losses") or 0)
    bucket["win_rate"] = round((int(bucket.get("wins") or 0) / attempts), 4) if attempts else 0.0
    bucket["avg_no_trade_score"] = round(((_safe_float(bucket.get("avg_no_trade_score")) * old_samples) + score) / samples, 4)
    examples = bucket.setdefault("examples", [])
    if len(examples) < MAX_EXAMPLES:
        examples.append({"symbol": _symbol(row), "permission": _permission(row), "warning": _warning(row), "outcome": outcome or "UNKNOWN"})


def _safety() -> Dict[str, bool]:
    return {
        "broker_api_changes": False,
        "telegram_changes": False,
        "supabase_changes": False,
        "dashboard_changes": False,
        "scanner_changes": False,
        "ranking_changes": False,
        "final_decision_changes": False,
        "execution_changes": False,
        "alert_filter_changes": False,
        "no_trade_engine_changes": False,
        "live_order_allowed": False,
    }


def build_no_trade_refinement_memory(records: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    rows = [item for item in list(records or [])[-MAX_RECORDS:] if isinstance(item, dict)]
    refinement_buckets: Dict[str, Dict[str, Any]] = {}
    symbol_refinement_buckets: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        bucket_name = infer_refinement_bucket(row)
        outcome = _normalise_outcome(row)
        _update_bucket(refinement_buckets.setdefault(bucket_name, _new_bucket(bucket_name)), row, outcome)

        key = f"{_symbol(row)}|{bucket_name}"
        symbol_bucket = symbol_refinement_buckets.setdefault(key, _new_bucket(bucket_name))
        symbol_bucket["symbol"] = _symbol(row)
        _update_bucket(symbol_bucket, row, outcome)

    ranked_symbols = sorted(
        symbol_refinement_buckets.items(),
        key=lambda item: (int(item[1].get("samples") or 0), _safe_float(item[1].get("win_rate")), item[0]),
        reverse=True,
    )

    return {
        "version": STATE_VERSION,
        "generated_at": _now_text(),
        "source_type": "NO_TRADE_REFINEMENT_MEMORY",
        "advisory_only": True,
        "replay_research_only": True,
        "affects_live_execution_directly": False,
        "record_count": len(rows),
        "refinement_buckets": dict(sorted(refinement_buckets.items())),
        "symbol_refinement_buckets": {key: value for key, value in ranked_symbols[:MAX_BUCKETS]},
        "memory_notes": [
            "Research-only memory for no-trade decision aftermath.",
            "Does not create a no-trade gate or modify Phase 35.",
            "Does not mutate ranking, final decisions, alert filtering, execution, scanner, dashboard, broker/API, or Supabase state.",
        ],
        "safety": _safety(),
        "rank_adjustment": 0.0,
        "recommended_live_weight": 0.0,
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-MAX_RECORDS:]:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            continue
    return rows


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)][-MAX_RECORDS:]


def load_default_records(paths: Iterable[Path] | None = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths or DEFAULT_RECORD_PATHS:
        try:
            if not path.exists() or path.stat().st_size > MAX_FILE_BYTES:
                continue
            if path.suffix.lower() == ".jsonl":
                rows.extend(_read_jsonl(path))
            elif path.suffix.lower() == ".csv":
                rows.extend(_read_csv(path))
        except Exception:
            continue
        if len(rows) >= MAX_RECORDS:
            break
    return rows[-MAX_RECORDS:]


def render_no_trade_refinement_memory_report(memory: Dict[str, Any]) -> str:
    lines = [
        "TITAN No-Trade Refinement Memory Report",
        "=======================================",
        "",
        "Safety",
        "- Advisory/research-only memory.",
        "- No no-trade engine, final-decision, alert-filter, ranking, scanner, Telegram, broker/API, dashboard, or Supabase mutation.",
        "",
        f"Updated: {memory.get('generated_at')}",
        f"Records: {memory.get('record_count', 0)}",
        "",
        "Refinement Buckets:",
    ]
    buckets = memory.get("refinement_buckets") if isinstance(memory.get("refinement_buckets"), dict) else {}
    for name, bucket in buckets.items():
        if isinstance(bucket, dict):
            lines.append(f"- {name}: samples={bucket.get('samples', 0)}, wins={bucket.get('wins', 0)}, losses={bucket.get('losses', 0)}, win_rate={bucket.get('win_rate', 0.0)}")
    if not buckets:
        lines.append("- None observed")
    return "\n".join(lines) + "\n"


def refresh_no_trade_refinement_memory(records: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    source_records = list(records) if records is not None else load_default_records()
    memory = build_no_trade_refinement_memory(source_records)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_no_trade_refinement_memory_report(memory), encoding="utf-8")
    return memory


if __name__ == "__main__":
    result = refresh_no_trade_refinement_memory()
    print("TITAN no-trade refinement memory refreshed")
    print("Records:", result.get("record_count"))
