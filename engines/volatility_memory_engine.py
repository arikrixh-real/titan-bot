"""
TITAN Experience Maturity - Volatility Memory Engine.

Builds advisory-only memory for volatility expansion/compression behavior from
already-produced records. This module does not classify market regime, does not
scan markets, and does not mutate ranking, broker, Telegram, or Supabase state.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "volatility_expansion_compression_memory.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "volatility_memory_report.txt"

DEFAULT_RECORD_PATHS = [
    PROJECT_ROOT / "data" / "experience_vault" / "imported_trade_logs" / "historical_experience_import.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.jsonl",
    PROJECT_ROOT / "data" / "journals" / "trade_outcomes.csv",
    PROJECT_ROOT / "journal" / "trade_journal.csv",
]

STATE_VERSION = "1.0"
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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalise_outcome(row: Dict[str, Any]) -> Optional[str]:
    text = _safe_text(row.get("outcome") or row.get("result") or row.get("status") or row.get("trade_result")).upper()
    if text in {"WIN", "WON", "TP", "TARGET", "TARGET_HIT", "PROFIT", "SUCCESS"}:
        return "WIN"
    if text in {"LOSS", "LOST", "SL", "STOPLOSS", "STOP_LOSS", "SL_HIT", "FAILED"}:
        return "LOSS"
    return None


def _symbol(row: Dict[str, Any]) -> str:
    return _safe_text(row.get("symbol") or row.get("stock") or row.get("ticker") or "UNKNOWN").replace(".NS", "").upper()


def _record_text(row: Dict[str, Any]) -> str:
    fields = [
        row.get("setup_type"),
        row.get("reason"),
        row.get("setup_reason"),
        row.get("confirmations"),
        row.get("lesson_learned"),
        row.get("outcome_reason"),
        row.get("market_regime"),
        row.get("regime"),
        row.get("volatility_state"),
        row.get("volatility_regime"),
    ]
    return " ".join(_safe_text(item).lower() for item in fields if item is not None)


def infer_volatility_phase(row: Dict[str, Any]) -> str:
    """
    Infers a memory phase from existing record fields only.
    This is not regime classification and does not inspect live market data.
    """

    text = _record_text(row)
    explicit = _safe_text(
        row.get("volatility_phase")
        or row.get("volatility_state")
        or row.get("volatility_regime")
        or row.get("phase")
    ).upper()
    if explicit in {"COMPRESSION", "EXPANSION", "NORMAL", "VOLATILITY_COMPRESSION", "VOLATILITY_EXPANSION"}:
        return explicit.replace("VOLATILITY_", "")

    compression_score = _safe_float(row.get("compression_score"), -1.0)
    range_spike = _safe_float(row.get("range_spike"), 0.0)
    atr_spike = _safe_float(row.get("atr_spike"), 0.0)
    volatility_score = _safe_float(row.get("volatility_score") or row.get("vix"), 0.0)

    if "compression" in text or "squeeze" in text or "tight range" in text or compression_score >= 5.0:
        return "COMPRESSION"
    if (
        "expansion" in text
        or "volatility spike" in text
        or "range expansion" in text
        or range_spike >= 1.35
        or atr_spike >= 1.35
        or volatility_score >= 70.0
    ):
        return "EXPANSION"
    return "NORMAL"


def _new_bucket(phase: str) -> Dict[str, Any]:
    return {
        "phase": phase,
        "samples": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "avg_score": 0.0,
        "avg_compression_score": 0.0,
        "examples": [],
    }


def _update_bucket(bucket: Dict[str, Any], row: Dict[str, Any], outcome: Optional[str]) -> None:
    samples = int(bucket.get("samples") or 0) + 1
    old_samples = samples - 1
    score = _safe_float(row.get("score") or row.get("final_score"), 0.0)
    compression = _safe_float(row.get("compression_score"), 0.0)

    bucket["samples"] = samples
    if outcome == "WIN":
        bucket["wins"] = int(bucket.get("wins") or 0) + 1
    elif outcome == "LOSS":
        bucket["losses"] = int(bucket.get("losses") or 0) + 1
    attempts = int(bucket.get("wins") or 0) + int(bucket.get("losses") or 0)
    bucket["win_rate"] = round((int(bucket.get("wins") or 0) / attempts), 4) if attempts else 0.0
    bucket["avg_score"] = round(((_safe_float(bucket.get("avg_score")) * old_samples) + score) / samples, 4)
    bucket["avg_compression_score"] = round(((_safe_float(bucket.get("avg_compression_score")) * old_samples) + compression) / samples, 4)

    examples = bucket.setdefault("examples", [])
    if len(examples) < MAX_EXAMPLES:
        examples.append(
            {
                "symbol": _symbol(row),
                "outcome": outcome or "UNKNOWN",
                "score": score,
                "compression_score": compression,
                "source_type": _safe_text(row.get("source_type") or "EXPERIENCE_RECORD"),
            }
        )


def build_volatility_memory(records: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    rows = [item for item in list(records or [])[-MAX_RECORDS:] if isinstance(item, dict)]
    buckets: Dict[str, Dict[str, Any]] = {}
    symbol_phase: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        phase = infer_volatility_phase(row)
        outcome = _normalise_outcome(row)
        bucket = buckets.setdefault(phase, _new_bucket(phase))
        _update_bucket(bucket, row, outcome)

        symbol = _symbol(row)
        symbol_bucket = symbol_phase.setdefault(f"{symbol}|{phase}", _new_bucket(phase))
        symbol_bucket["symbol"] = symbol
        _update_bucket(symbol_bucket, row, outcome)

    ranked_symbol_phase = sorted(
        symbol_phase.items(),
        key=lambda item: (int(item[1].get("samples") or 0), _safe_float(item[1].get("win_rate")), item[0]),
        reverse=True,
    )

    return {
        "version": STATE_VERSION,
        "generated_at": _now_text(),
        "source_type": "VOLATILITY_EXPANSION_COMPRESSION_MEMORY",
        "advisory_only": True,
        "affects_live_execution_directly": False,
        "record_count": len(rows),
        "phase_buckets": dict(sorted(buckets.items())),
        "symbol_phase_buckets": {key: value for key, value in ranked_symbol_phase[:MAX_BUCKETS]},
        "memory_notes": [
            "Uses existing experience/journal fields only.",
            "Does not scan live candles or classify market regime.",
            "Compression here means market-price compression, not runtime memory compression.",
        ],
        "safety": {
            "broker_api_changes": False,
            "telegram_changes": False,
            "supabase_changes": False,
            "scanner_changes": False,
            "ranking_changes": False,
            "final_decision_changes": False,
            "live_order_allowed": False,
        },
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


def render_volatility_memory_report(memory: Dict[str, Any]) -> str:
    phase_buckets = memory.get("phase_buckets") if isinstance(memory.get("phase_buckets"), dict) else {}
    lines = [
        "TITAN Volatility Expansion/Compression Memory Report",
        "====================================================",
        "",
        "Safety",
        "- Advisory/research-only memory.",
        "- No scanner, ranking, final-decision, Telegram, broker/API, Supabase, or live-price mutation.",
        "",
        f"Updated: {memory.get('generated_at')}",
        f"Source Type: {memory.get('source_type')}",
        f"Advisory Only: {memory.get('advisory_only')}",
        f"Records: {memory.get('record_count', 0)}",
        "",
        "Phase Buckets:",
    ]
    for phase, bucket in phase_buckets.items():
        if isinstance(bucket, dict):
            lines.append(
                f"- {phase}: samples={bucket.get('samples', 0)}, wins={bucket.get('wins', 0)}, "
                f"losses={bucket.get('losses', 0)}, win_rate={bucket.get('win_rate', 0.0)}, "
                f"avg_compression={bucket.get('avg_compression_score', 0.0)}"
            )
    if not phase_buckets:
        lines.append("- None observed")
    return "\n".join(lines) + "\n"


def refresh_volatility_memory(records: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    source_records = list(records) if records is not None else load_default_records()
    memory = build_volatility_memory(source_records)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_volatility_memory_report(memory), encoding="utf-8")
    return memory


if __name__ == "__main__":
    result = refresh_volatility_memory()
    print("TITAN volatility memory refreshed")
    print("Records:", result.get("record_count"))
    print("Memory:", MEMORY_PATH)
