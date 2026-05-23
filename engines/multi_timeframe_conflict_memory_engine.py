"""
TITAN Experience Maturity Batch 2 - Multi-Timeframe Conflict Memory Engine.

Builds advisory-only memory for historical outcomes around multi-timeframe
alignment/conflict. It does not import or change the live multi-timeframe
engine, strict filter, scanner, ranking, execution, dashboard, broker/API,
Telegram, or Supabase state.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "multi_timeframe_conflict_memory.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "multi_timeframe_conflict_memory_report.txt"

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


def _side(row: Dict[str, Any]) -> str:
    side = _safe_text(row.get("side") or row.get("direction") or row.get("trade_side")).upper()
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side


def _trend(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _safe_text(row.get(key)).upper()
        if value:
            return value
    return "UNKNOWN"


def _normalise_outcome(row: Dict[str, Any]) -> Optional[str]:
    text = _safe_text(row.get("outcome") or row.get("result") or row.get("status") or row.get("trade_result")).upper()
    if text in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if text in {"LOSS", "LOST", "SL", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}:
        return "LOSS"
    return None


def infer_conflict_type(row: Dict[str, Any]) -> str:
    side = _side(row)
    short = _trend(row, "short_trend", "short_timeframe_trend")
    medium = _trend(row, "medium_trend", "medium_timeframe_trend")
    long = _trend(row, "long_trend", "long_timeframe_trend", "higher_timeframe_trend")
    warning = " ".join(
        _safe_text(row.get(key)).lower()
        for key in ("multi_timeframe_warning", "warning", "reason", "setup_reason", "block_reason")
    )

    if "higher timeframe conflict" in warning or "timeframe conflict" in warning:
        if side == "SHORT":
            return "HIGHER_TIMEFRAME_AGAINST_SHORT"
        return "HIGHER_TIMEFRAME_AGAINST_LONG"
    if side == "LONG" and (medium == "BEARISH" or long == "BEARISH"):
        return "HIGHER_TIMEFRAME_AGAINST_LONG"
    if side == "SHORT" and (medium == "BULLISH" or long == "BULLISH"):
        return "HIGHER_TIMEFRAME_AGAINST_SHORT"
    if side == "LONG" and short == medium == long == "BULLISH":
        return "ALIGNED"
    if side == "SHORT" and short == medium == long == "BEARISH":
        return "ALIGNED"
    if "mixed" in warning or len({short, medium, long} - {"UNKNOWN"}) > 1:
        return "MIXED_TIMEFRAME"
    return "UNKNOWN_OR_NEUTRAL"


def _new_bucket(name: str) -> Dict[str, Any]:
    return {
        "conflict_type": name,
        "samples": 0,
        "wins": 0,
        "losses": 0,
        "loss_rate": 0.0,
        "avg_score": 0.0,
        "examples": [],
    }


def _update_bucket(bucket: Dict[str, Any], row: Dict[str, Any], outcome: Optional[str]) -> None:
    samples = int(bucket.get("samples") or 0) + 1
    old_samples = samples - 1
    score = _safe_float(row.get("score") or row.get("final_score"), 0.0)
    bucket["samples"] = samples
    if outcome == "WIN":
        bucket["wins"] = int(bucket.get("wins") or 0) + 1
    elif outcome == "LOSS":
        bucket["losses"] = int(bucket.get("losses") or 0) + 1
    attempts = int(bucket.get("wins") or 0) + int(bucket.get("losses") or 0)
    bucket["loss_rate"] = round((int(bucket.get("losses") or 0) / attempts), 4) if attempts else 0.0
    bucket["avg_score"] = round(((_safe_float(bucket.get("avg_score")) * old_samples) + score) / samples, 4)
    examples = bucket.setdefault("examples", [])
    if len(examples) < MAX_EXAMPLES:
        examples.append({"symbol": _symbol(row), "side": _side(row), "outcome": outcome or "UNKNOWN", "score": score})


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
        "strict_filter_changes": False,
        "multi_timeframe_engine_changes": False,
        "live_order_allowed": False,
    }


def build_multi_timeframe_conflict_memory(records: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    rows = [item for item in list(records or [])[-MAX_RECORDS:] if isinstance(item, dict)]
    conflict_buckets: Dict[str, Dict[str, Any]] = {}
    symbol_conflict_buckets: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        conflict = infer_conflict_type(row)
        outcome = _normalise_outcome(row)
        _update_bucket(conflict_buckets.setdefault(conflict, _new_bucket(conflict)), row, outcome)

        key = f"{_symbol(row)}|{conflict}"
        symbol_bucket = symbol_conflict_buckets.setdefault(key, _new_bucket(conflict))
        symbol_bucket["symbol"] = _symbol(row)
        _update_bucket(symbol_bucket, row, outcome)

    ranked_symbols = sorted(
        symbol_conflict_buckets.items(),
        key=lambda item: (int(item[1].get("samples") or 0), _safe_float(item[1].get("loss_rate")), item[0]),
        reverse=True,
    )

    return {
        "version": STATE_VERSION,
        "generated_at": _now_text(),
        "source_type": "MULTI_TIMEFRAME_CONFLICT_MEMORY",
        "advisory_only": True,
        "replay_research_only": True,
        "affects_live_execution_directly": False,
        "record_count": len(rows),
        "conflict_buckets": dict(sorted(conflict_buckets.items())),
        "symbol_conflict_buckets": {key: value for key, value in ranked_symbols[:MAX_BUCKETS]},
        "memory_notes": [
            "Uses existing records only.",
            "Does not change titan_brain.multi_timeframe_engine or titan_brain.strict_filter.",
            "Does not mutate ranking, execution, scanner, alerts, dashboard, broker/API, or Supabase state.",
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


def render_multi_timeframe_conflict_memory_report(memory: Dict[str, Any]) -> str:
    lines = [
        "TITAN Multi-Timeframe Conflict Memory Report",
        "============================================",
        "",
        "Safety",
        "- Advisory/research-only memory.",
        "- No multi-timeframe engine, strict filter, ranking, final-decision, scanner, Telegram, broker/API, dashboard, or Supabase mutation.",
        "",
        f"Updated: {memory.get('generated_at')}",
        f"Records: {memory.get('record_count', 0)}",
        "",
        "Conflict Buckets:",
    ]
    buckets = memory.get("conflict_buckets") if isinstance(memory.get("conflict_buckets"), dict) else {}
    for name, bucket in buckets.items():
        if isinstance(bucket, dict):
            lines.append(f"- {name}: samples={bucket.get('samples', 0)}, losses={bucket.get('losses', 0)}, loss_rate={bucket.get('loss_rate', 0.0)}")
    if not buckets:
        lines.append("- None observed")
    return "\n".join(lines) + "\n"


def refresh_multi_timeframe_conflict_memory(records: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    source_records = list(records) if records is not None else load_default_records()
    memory = build_multi_timeframe_conflict_memory(source_records)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_multi_timeframe_conflict_memory_report(memory), encoding="utf-8")
    return memory


if __name__ == "__main__":
    result = refresh_multi_timeframe_conflict_memory()
    print("TITAN multi-timeframe conflict memory refreshed")
    print("Records:", result.get("record_count"))
