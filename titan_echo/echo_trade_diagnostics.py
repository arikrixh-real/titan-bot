"""Read-only trade diagnostic evidence builders for ECHO."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
JOURNAL_DIR = REPO_ROOT / "data" / "journals"
IST = timezone(timedelta(hours=5, minutes=30))

FILTER_DIAGNOSTICS_PATH = RUNTIME_DIR / "filter_engine_diagnostics.json"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
TRADE_CONTRACT_DIAGNOSTICS_PATH = RUNTIME_DIR / "trade_contract_diagnostics.json"
TRADE_JOURNAL_DIAGNOSTICS_PATH = RUNTIME_DIR / "trade_journal_diagnostics.json"
OUTCOME_TRACKER_DIAGNOSTICS_PATH = RUNTIME_DIR / "outcome_tracker_diagnostics.json"
TRADE_JOURNAL_CSV = JOURNAL_DIR / "trade_journal.csv"
ACTIVE_TRADES_CSV = JOURNAL_DIR / "active_trades.csv"
TRADE_OUTCOMES_CSV = JOURNAL_DIR / "trade_outcomes.csv"


def _timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _write_runtime_json(path: Path, payload: dict[str, Any]) -> None:
    resolved_runtime = RUNTIME_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_runtime not in (resolved_path, *resolved_path.parents):
        raise ValueError("trade diagnostics write only under data/runtime")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _side(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text == "LONG":
        return "BUY"
    if text == "SHORT":
        return "SELL"
    return text


def _trade_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("symbol") or "").upper(),
            _side(row.get("side")),
            str(row.get("entry") or row.get("entry_price") or ""),
            str(row.get("sl") or row.get("stop_loss") or ""),
            str(row.get("target") or row.get("tp") or ""),
        ]
    )


def _final_setup_symbols(filter_payload: dict[str, Any]) -> list[dict[str, Any]]:
    final: list[dict[str, Any]] = []
    for item in filter_payload.get("symbols") or []:
        if not isinstance(item, dict):
            continue
        engines = ("trend_engine", "momentum_engine", "structure_engine", "entry_engine")
        if all(isinstance(item.get(engine), dict) and item[engine].get("status") == "PASS" for engine in engines):
            final.append(item)
    return final


def build_trade_contract_diagnostics() -> dict[str, Any]:
    filter_payload = _read_json(FILTER_DIAGNOSTICS_PATH)
    scanner_payload = _read_json(SCANNER_STATUS_PATH)
    setups: list[dict[str, Any]] = []
    for item in _final_setup_symbols(filter_payload):
        entry_values = (item.get("entry_engine") or {}).get("values") or {}
        trend_values = (item.get("trend_engine") or {}).get("values") or {}
        score_values = (item.get("final_score_engine") or {}).get("values") or {}
        setups.append(
            {
                "symbol": str(item.get("symbol") or "").upper(),
                "side": _side(trend_values.get("side")),
                "entry": _safe_float(entry_values.get("entry_price")),
                "rr": _safe_float(entry_values.get("RR") or entry_values.get("rr")),
                "final_score": _safe_float(score_values.get("final_score") or item.get("final_score")),
                "source": "filter_engine_diagnostics",
                "validation": {
                    "status": "EVIDENCE_PRESENT",
                    "reason": "Read-only setup contract evidence from filter diagnostics; no trade levels recalculated.",
                },
            }
        )
    payload = {
        "schema": "titan.echo.trade_contract_diagnostics.v1",
        "status": "EVIDENCE_PRESENT" if filter_payload else "UNKNOWN_NOT_PROVEN",
        "reason": "FILTER_DIAGNOSTICS_PARSED" if filter_payload else "MISSING_OR_UNREADABLE_FILTER_DIAGNOSTICS",
        "timestamp_ist": _timestamp_ist(),
        "scanner_cycle_id": filter_payload.get("scanner_cycle_id") or scanner_payload.get("scanner_cycle_id"),
        "final_setup_count": len(setups),
        "setups_sample": setups[:20],
        "source_files": {
            "filter_engine_diagnostics": {"path": _relative(FILTER_DIAGNOSTICS_PATH), "exists": FILTER_DIAGNOSTICS_PATH.exists()},
            "scanner_status": {"path": _relative(SCANNER_STATUS_PATH), "exists": SCANNER_STATUS_PATH.exists()},
        },
        "safety": _safety(),
    }
    _write_runtime_json(TRADE_CONTRACT_DIAGNOSTICS_PATH, payload)
    return payload


def build_trade_journal_diagnostics(contract_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    contract_payload = contract_payload or _read_json(TRADE_CONTRACT_DIAGNOSTICS_PATH)
    journal_rows = _read_csv(TRADE_JOURNAL_CSV)
    active_rows = _read_csv(ACTIVE_TRADES_CSV)
    setup_keys = {
        "|".join([str(item.get("symbol") or "").upper(), _side(item.get("side")), str(item.get("entry") or ""), "", ""])
        for item in contract_payload.get("setups_sample") or []
        if isinstance(item, dict)
    }
    journal_keys = {_trade_key(row) for row in journal_rows}
    active_keys = [_trade_key(row) for row in active_rows]
    duplicates = [key for key, count in Counter(active_keys).items() if key and count > 1]
    scanner = _read_json(SCANNER_STATUS_PATH)
    journal_writes_enabled = bool(scanner.get("journal_writes"))
    payload = {
        "schema": "titan.echo.trade_journal_diagnostics.v1",
        "status": "EVIDENCE_PRESENT",
        "reason": "JOURNAL_AND_ACTIVE_TRADE_CSV_PARSED",
        "timestamp_ist": _timestamp_ist(),
        "final_setup_count": contract_payload.get("final_setup_count", 0),
        "journal_rows": len(journal_rows),
        "active_trade_rows": len(active_rows),
        "journal_writes_enabled_in_runtime_scanner": journal_writes_enabled,
        "journal_write_status": "ENABLED" if journal_writes_enabled else "DISABLED_READONLY_SCANNER",
        "sample_setup_key_count": len(setup_keys),
        "journal_key_count": len(journal_keys),
        "duplicate_active_trade_keys": duplicates[:20],
        "duplicates_prevented": not duplicates,
        "status_fields": sorted({str(row.get("status") or "").upper() for row in active_rows if row.get("status")}),
        "source_files": {
            "trade_journal": {"path": _relative(TRADE_JOURNAL_CSV), "exists": TRADE_JOURNAL_CSV.exists()},
            "active_trades": {"path": _relative(ACTIVE_TRADES_CSV), "exists": ACTIVE_TRADES_CSV.exists()},
            "scanner_status": {"path": _relative(SCANNER_STATUS_PATH), "exists": SCANNER_STATUS_PATH.exists()},
        },
        "safety": _safety(),
    }
    _write_runtime_json(TRADE_JOURNAL_DIAGNOSTICS_PATH, payload)
    return payload


def build_outcome_tracker_diagnostics() -> dict[str, Any]:
    active_rows = _read_csv(ACTIVE_TRADES_CSV)
    outcome_rows = _read_csv(TRADE_OUTCOMES_CSV)
    open_rows = [row for row in active_rows if str(row.get("status") or "").upper() == "OPEN"]
    closed_rows = [row for row in active_rows if str(row.get("status") or "").upper() == "CLOSED"]
    payload = {
        "schema": "titan.echo.outcome_tracker_diagnostics.v1",
        "status": "EVIDENCE_PRESENT",
        "reason": "ACTIVE_TRADES_AND_OUTCOMES_PARSED_NO_LIVE_PRICE_CHECK",
        "timestamp_ist": _timestamp_ist(),
        "active_trade_rows": len(active_rows),
        "open_trade_count": len(open_rows),
        "closed_active_trade_count": len(closed_rows),
        "trade_outcome_rows": len(outcome_rows),
        "tp_hit_count": sum(1 for row in outcome_rows if str(row.get("outcome") or "").upper() == "TP"),
        "sl_hit_count": sum(1 for row in outcome_rows if str(row.get("outcome") or "").upper() == "SL"),
        "tp_sl_check_status": "NO_OPEN_TRADES" if not open_rows else "OPEN_TRADES_PRESENT_READ_ONLY",
        "monitored_count": len(open_rows),
        "source_files": {
            "active_trades": {"path": _relative(ACTIVE_TRADES_CSV), "exists": ACTIVE_TRADES_CSV.exists()},
            "trade_outcomes": {"path": _relative(TRADE_OUTCOMES_CSV), "exists": TRADE_OUTCOMES_CSV.exists()},
        },
        "safety": _safety(),
    }
    _write_runtime_json(OUTCOME_TRACKER_DIAGNOSTICS_PATH, payload)
    return payload


def build_all_trade_diagnostics() -> dict[str, dict[str, Any]]:
    contract = build_trade_contract_diagnostics()
    journal = build_trade_journal_diagnostics(contract)
    outcome = build_outcome_tracker_diagnostics()
    return {
        "trade_contract_diagnostics": contract,
        "trade_journal_diagnostics": journal,
        "outcome_tracker_diagnostics": outcome,
    }


def ensure_trade_diagnostics() -> dict[str, dict[str, Any]]:
    required = [
        TRADE_CONTRACT_DIAGNOSTICS_PATH,
        TRADE_JOURNAL_DIAGNOSTICS_PATH,
        OUTCOME_TRACKER_DIAGNOSTICS_PATH,
    ]
    if all(path.exists() for path in required):
        return {
            "trade_contract_diagnostics": _read_json(TRADE_CONTRACT_DIAGNOSTICS_PATH),
            "trade_journal_diagnostics": _read_json(TRADE_JOURNAL_DIAGNOSTICS_PATH),
            "outcome_tracker_diagnostics": _read_json(OUTCOME_TRACKER_DIAGNOSTICS_PATH),
        }
    return build_all_trade_diagnostics()


def _safety() -> dict[str, bool]:
    return {
        "read_only_diagnostics": True,
        "broker_execution": False,
        "trade_placement": False,
        "risk_change": False,
        "live_price_fetch": False,
        "scanner_execution": False,
        "deploy_or_restart": False,
    }


if __name__ == "__main__":
    result = build_all_trade_diagnostics()
    print("ECHO trade diagnostics generated.")
    for name, payload in result.items():
        print(f"{name}={payload.get('status')} reason={payload.get('reason')}")
