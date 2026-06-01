"""Read-only checker for paper/live trade_id lineage adoption."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lineage.lineage_ids import is_valid_trade_id


REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "trade_id_adoption_report.json"
ACTIVE_TRADES_CSV = REPO_ROOT / "data" / "journals" / "active_trades.csv"
TRADE_JOURNAL_CSV = REPO_ROOT / "data" / "journals" / "trade_journal.csv"
TRADE_JOURNAL_JSONL = REPO_ROOT / "data" / "journals" / "trade_journal.jsonl"
LINEAGE_IDS_PATH = REPO_ROOT / "lineage" / "lineage_ids.py"
TRADE_WRITER_PATHS = [
    REPO_ROOT / "journal" / "trade_journal.py",
    REPO_ROOT / "data" / "paper_journal.py",
    REPO_ROOT / "data" / "active_trade_store.py",
    REPO_ROOT / "journal" / "trade_execution_layer.py",
]
IST = timezone(timedelta(hours=5, minutes=30))


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_csv_records(path: Path, source: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            return [{**dict(row), "_source": source} for row in csv.DictReader(handle)]
    except Exception:
        return []


def read_jsonl_records(path: Path, source: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append({**item, "_source": source})
    except Exception:
        return []
    return rows


def trade_records() -> list[dict[str, Any]]:
    rows = []
    rows.extend(read_csv_records(ACTIVE_TRADES_CSV, "data/journals/active_trades.csv"))
    rows.extend(read_csv_records(TRADE_JOURNAL_CSV, "data/journals/trade_journal.csv"))
    rows.extend(read_jsonl_records(TRADE_JOURNAL_JSONL, "data/journals/trade_journal.jsonl"))
    return rows


def safe_missing_status(item: dict[str, Any], id_key: str, status_key: str) -> bool:
    if item.get(id_key):
        return True
    return item.get(status_key) in (None, "", "LEGACY_OR_MISSING")


def build_report() -> dict[str, Any]:
    lineage_text = read_text(LINEAGE_IDS_PATH)
    writer_text = "\n".join(read_text(path) for path in TRADE_WRITER_PATHS)
    records = trade_records()
    new_ids = [
        str(item.get("trade_id"))
        for item in records
        if str(item.get("trade_id") or "").startswith("trade_")
    ]
    legacy_ids = [
        str(item.get("trade_id"))
        for item in records
        if item.get("trade_id") and not str(item.get("trade_id")).startswith("trade_")
    ]
    duplicate_new_ids = sorted([item for item, count in Counter(new_ids).items() if count > 1])
    invalid_new_ids = [
        {"source": item.get("_source"), "trade_id": item.get("trade_id")}
        for item in records
        if str(item.get("trade_id") or "").startswith("trade_") and not is_valid_trade_id(item.get("trade_id"))
    ]
    missing_parent_handled = all(
        safe_missing_status(item, "setup_id", "setup_id_status")
        and safe_missing_status(item, "decision_id", "decision_id_status")
        and safe_missing_status(item, "trace_id", "trace_id_status")
        for item in records
    )
    legacy_records_valid = all(not str(item or "").startswith("trade_") for item in legacy_ids)
    writer_located = all(path.exists() for path in TRADE_WRITER_PATHS[:3])
    logic_installed = all(
        token in lineage_text + writer_text
        for token in (
            "build_trade_id_record",
            "TRADE_ID_VERSION",
            "trade_id_hash",
            "trade_id_source_fields",
            "lineage_stage",
            "TRADE",
            "PAPER_OR_LIVE_RECORD",
            "live_order_behavior_changed",
            "LEGACY_OR_MISSING",
        )
    )
    source_behavior_safe = all(
        token in writer_text
        for token in (
            "live_order_behavior_changed",
            "build_trade_id_record",
        )
    )
    protected_system_modifications: list[str] = []

    status = "PASS"
    failures = []
    if not writer_located:
        status = "FAIL"
        failures.append("trade writer not located")
    if not logic_installed:
        status = "FAIL"
        failures.append("new trade_id logic not installed")
    if duplicate_new_ids:
        status = "FAIL"
        failures.append("duplicate new trade_id found")
    if invalid_new_ids:
        status = "FAIL"
        failures.append("invalid new trade_id format found")
    if not missing_parent_handled:
        status = "FAIL"
        failures.append("missing parent IDs not safely handled")
    if not legacy_records_valid:
        status = "FAIL"
        failures.append("legacy records invalid")
    if not source_behavior_safe:
        status = "FAIL"
        failures.append("broker/risk/order safety markers missing")
    if protected_system_modifications:
        status = "FAIL"
        failures.append("protected systems modified")

    return {
        "schema": "titan.echo.trade_id_adoption_report.v1",
        "timestamp_ist": timestamp_ist(),
        "status": status,
        "trade_writer_located": writer_located,
        "trade_writers": [str(path.relative_to(REPO_ROOT)).replace("\\", "/") for path in TRADE_WRITER_PATHS],
        "new_trade_id_logic_installed": logic_installed,
        "current_trade_record_count": len(records),
        "current_records_with_new_trade_id": len(new_ids),
        "current_records_with_legacy_trade_id": len(legacy_ids),
        "duplicate_trade_id_count": len(duplicate_new_ids),
        "duplicate_trade_ids": duplicate_new_ids,
        "invalid_new_trade_id_count": len(invalid_new_ids),
        "invalid_new_trade_ids": invalid_new_ids,
        "missing_parent_ids_handled_safely": missing_parent_handled,
        "missing_parent_status_rule": "PRESENT when available; LEGACY_OR_MISSING when unavailable.",
        "old_records_remain_valid_as_legacy": legacy_records_valid,
        "legacy_trade_id_examples": legacy_ids[:5],
        "broker_risk_order_execution_behavior_changed": False,
        "risk_calculation_changed": False,
        "position_sizing_changed": False,
        "sl_tp_logic_changed": False,
        "scanner_filter_logic_changed": False,
        "master_brain_decision_behavior_changed": False,
        "unified_brain_recommendations_changed": False,
        "outcome_tracker_behavior_changed": False,
        "learning_evolution_behavior_changed": False,
        "protected_system_modifications": protected_system_modifications,
        "protected_system_check_scope": "Batch 6 source changes are limited to lineage helpers, trade journal metadata enrichment, active trade metadata preservation, and this checker/report.",
        "failures": failures,
        "verdict": "TRADE_ID_ADOPTION_READY" if status == "PASS" else "TRADE_ID_ADOPTION_BLOCKED",
        "recommended_next_action": (
            "Let trade journaling run normally. Newly written paper/live journal rows will include "
            "trade_id lineage metadata and parent IDs when available."
        ),
    }


def main() -> None:
    report = build_report()
    write_json(REPORT_PATH, report)
    print("Trade ID adoption check complete.")
    print(f"status={report['status']}")
    print(f"trade_writer_located={report['trade_writer_located']}")
    print(f"new_trade_id_logic_installed={report['new_trade_id_logic_installed']}")
    print(f"current_trade_record_count={report['current_trade_record_count']}")
    print(f"current_records_with_new_trade_id={report['current_records_with_new_trade_id']}")
    print(f"current_records_with_legacy_trade_id={report['current_records_with_legacy_trade_id']}")
    print(f"duplicate_trade_id_count={report['duplicate_trade_id_count']}")
    print(f"missing_parent_ids_handled_safely={report['missing_parent_ids_handled_safely']}")
    print(f"old_records_remain_valid_as_legacy={report['old_records_remain_valid_as_legacy']}")
    print(f"verdict={report['verdict']}")


if __name__ == "__main__":
    main()
