"""
TITAN Experience Maturity Batch 2 - Transition Instability Memory Engine.

Builds advisory-only memory for unstable, unconfirmed, or whipsaw regime
transitions from already-produced records. It does not modify regime engines,
ranking, scanners, alerts, execution, dashboard, broker/API, or Supabase state.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "transition_instability_memory.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "transition_instability_memory_report.txt"

DEFAULT_RECORD_PATHS = [
    PROJECT_ROOT / "data" / "memory" / "historical_regime_transition_memory.json",
    PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.csv",
]

STATE_VERSION = "2.0"
MAX_RECORDS = 300
MAX_BUCKETS = 50
MAX_EVENTS = 100
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


def _normalise_outcome(row: Dict[str, Any]) -> Optional[str]:
    text = _safe_text(row.get("outcome") or row.get("result") or row.get("status") or row.get("trade_result")).upper()
    if text in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if text in {"LOSS", "LOST", "SL", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}:
        return "LOSS"
    return None


def _from_regime(row: Dict[str, Any]) -> str:
    return _safe_text(row.get("from_regime") or row.get("previous_primary") or row.get("previous_regime") or "UNKNOWN").upper()


def _to_regime(row: Dict[str, Any]) -> str:
    return _safe_text(row.get("to_regime") or row.get("primary") or row.get("current_regime") or row.get("market_regime") or "UNKNOWN").upper()


def infer_instability_type(row: Dict[str, Any]) -> str:
    text = " ".join(
        _safe_text(row.get(key)).lower()
        for key in ("reason", "setup_reason", "lesson_learned", "failure_cause", "transition_quality", "regime_note")
    )
    confirmed_value = row.get("transition_confirmed")
    confirmed = bool(confirmed_value)
    strength = _safe_float(row.get("transition_strength"), 0.0)
    if row.get("whipsaw") or "whipsaw" in text or "false transition" in text:
        return "WHIPSAW"
    if confirmed_value is False or (row.get("transition_detected") and not confirmed):
        return "UNCONFIRMED"
    if strength and strength < 0.35:
        return "WEAK_TRANSITION"
    if "chop" in text or "unstable" in text:
        return "CHOPPY_TRANSITION"
    return "STABLE_OR_UNKNOWN"


def _new_bucket(name: str) -> Dict[str, Any]:
    return {
        "instability_type": name,
        "samples": 0,
        "wins": 0,
        "losses": 0,
        "loss_rate": 0.0,
        "avg_transition_strength": 0.0,
        "examples": [],
    }


def _update_bucket(bucket: Dict[str, Any], row: Dict[str, Any], outcome: Optional[str]) -> None:
    samples = int(bucket.get("samples") or 0) + 1
    old_samples = samples - 1
    strength = _safe_float(row.get("transition_strength"), 0.0)
    bucket["samples"] = samples
    if outcome == "WIN":
        bucket["wins"] = int(bucket.get("wins") or 0) + 1
    elif outcome == "LOSS":
        bucket["losses"] = int(bucket.get("losses") or 0) + 1
    attempts = int(bucket.get("wins") or 0) + int(bucket.get("losses") or 0)
    bucket["loss_rate"] = round((int(bucket.get("losses") or 0) / attempts), 4) if attempts else 0.0
    bucket["avg_transition_strength"] = round(((_safe_float(bucket.get("avg_transition_strength")) * old_samples) + strength) / samples, 4)
    examples = bucket.setdefault("examples", [])
    if len(examples) < MAX_EXAMPLES:
        examples.append({"from": _from_regime(row), "to": _to_regime(row), "outcome": outcome or "UNKNOWN", "strength": strength})


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
        "regime_engine_changes": False,
        "live_order_allowed": False,
    }


def build_transition_instability_memory(records: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    rows = [item for item in list(records or [])[-MAX_RECORDS:] if isinstance(item, dict)]
    buckets: Dict[str, Dict[str, Any]] = {}
    transition_buckets: Dict[str, Dict[str, Any]] = {}
    events: List[Dict[str, Any]] = []

    for row in rows:
        instability = infer_instability_type(row)
        outcome = _normalise_outcome(row)
        _update_bucket(buckets.setdefault(instability, _new_bucket(instability)), row, outcome)

        key = f"{_from_regime(row)}->{_to_regime(row)}|{instability}"
        transition_bucket = transition_buckets.setdefault(key, _new_bucket(instability))
        transition_bucket["transition_key"] = key
        _update_bucket(transition_bucket, row, outcome)

        if instability != "STABLE_OR_UNKNOWN":
            events.append(
                {
                    "from_regime": _from_regime(row),
                    "to_regime": _to_regime(row),
                    "instability_type": instability,
                    "transition_strength": _safe_float(row.get("transition_strength"), 0.0),
                    "outcome": outcome or "UNKNOWN",
                }
            )

    ranked = sorted(
        transition_buckets.items(),
        key=lambda item: (int(item[1].get("samples") or 0), _safe_float(item[1].get("loss_rate")), item[0]),
        reverse=True,
    )

    return {
        "version": STATE_VERSION,
        "generated_at": _now_text(),
        "source_type": "TRANSITION_INSTABILITY_MEMORY",
        "advisory_only": True,
        "replay_research_only": True,
        "affects_live_execution_directly": False,
        "record_count": len(rows),
        "instability_buckets": dict(sorted(buckets.items())),
        "transition_instability_buckets": {key: value for key, value in ranked[:MAX_BUCKETS]},
        "recent_transition_events": events[-MAX_EVENTS:],
        "memory_notes": [
            "Complements historical regime transition memory without modifying it.",
            "Tracks unstable transition outcomes from existing records only.",
            "Does not mutate ranking, execution, scanner, alerts, dashboard, broker/API, or Supabase state.",
        ],
        "safety": _safety(),
        "rank_adjustment": 0.0,
        "recommended_live_weight": 0.0,
    }


def _flatten_transition_memory(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in payload.get("recent_transitions") or []:
        if isinstance(item, dict):
            rows.append(item)
    for key, bucket in (payload.get("transition_buckets") or {}).items():
        if isinstance(bucket, dict):
            row = dict(bucket)
            if "->" in str(key):
                left, right = str(key).split("->", 1)
                row.setdefault("from_regime", left)
                row.setdefault("to_regime", right)
            rows.append(row)
    return rows[-MAX_RECORDS:]


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
            elif path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    rows.extend(_flatten_transition_memory(payload))
        except Exception:
            continue
        if len(rows) >= MAX_RECORDS:
            break
    return rows[-MAX_RECORDS:]


def render_transition_instability_memory_report(memory: Dict[str, Any]) -> str:
    lines = [
        "TITAN Transition Instability Memory Report",
        "==========================================",
        "",
        "Safety",
        "- Advisory/research-only memory.",
        "- No regime engine, ranking, final-decision, scanner, Telegram, broker/API, dashboard, or Supabase mutation.",
        "",
        f"Updated: {memory.get('generated_at')}",
        f"Records: {memory.get('record_count', 0)}",
        "",
        "Instability Buckets:",
    ]
    buckets = memory.get("instability_buckets") if isinstance(memory.get("instability_buckets"), dict) else {}
    for name, bucket in buckets.items():
        if isinstance(bucket, dict):
            lines.append(f"- {name}: samples={bucket.get('samples', 0)}, losses={bucket.get('losses', 0)}, loss_rate={bucket.get('loss_rate', 0.0)}")
    if not buckets:
        lines.append("- None observed")
    return "\n".join(lines) + "\n"


def refresh_transition_instability_memory(records: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    source_records = list(records) if records is not None else load_default_records()
    memory = build_transition_instability_memory(source_records)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_transition_instability_memory_report(memory), encoding="utf-8")
    return memory


if __name__ == "__main__":
    result = refresh_transition_instability_memory()
    print("TITAN transition instability memory refreshed")
    print("Records:", result.get("record_count"))
