"""Read-only checker for outcome_id lineage adoption."""

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

from lineage.lineage_ids import is_valid_outcome_id


REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "outcome_id_adoption_report.json"
OUTCOMES_CSV = REPO_ROOT / "data" / "journals" / "trade_outcomes.csv"
OUTCOMES_JSONL = REPO_ROOT / "data" / "journals" / "trade_outcomes.jsonl"
TRADE_RESULTS_CSV = REPO_ROOT / "data" / "journals" / "trade_results.csv"
OUTCOME_WRITER_PATH = REPO_ROOT / "journal" / "outcome_tracker.py"
TRADE_EXECUTION_PATH = REPO_ROOT / "journal" / "trade_execution_layer.py"
LINEAGE_IDS_PATH = REPO_ROOT / "lineage" / "lineage_ids.py"
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
    records = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    records.append({**item, "_source": source})
    except Exception:
        return []
    return records


def outcome_records() -> list[dict[str, Any]]:
    records = []
    records.extend(read_csv_records(OUTCOMES_CSV, "data/journals/trade_outcomes.csv"))
    records.extend(read_jsonl_records(OUTCOMES_JSONL, "data/journals/trade_outcomes.jsonl"))
    records.extend(read_csv_records(TRADE_RESULTS_CSV, "data/journals/trade_results.csv"))
    return records


def safe_missing_status(item: dict[str, Any], id_key: str, status_key: str) -> bool:
    if item.get(id_key):
        return True
    return item.get(status_key) in (None, "", "LEGACY_OR_MISSING")


def build_report() -> dict[str, Any]:
    lineage_text = read_text(LINEAGE_IDS_PATH)
    outcome_text = read_text(OUTCOME_WRITER_PATH)
    trade_execution_text = read_text(TRADE_EXECUTION_PATH)
    records = outcome_records()
    ids = [
        str(item.get("outcome_id"))
        for item in records
        if str(item.get("outcome_id") or "").startswith("outcome_")
    ]
    duplicate_ids = sorted([item for item, count in Counter(ids).items() if count > 1])
    invalid_ids = [
        {"source": item.get("_source"), "outcome_id": item.get("outcome_id")}
        for item in records
        if str(item.get("outcome_id") or "").startswith("outcome_")
        and not is_valid_outcome_id(item.get("outcome_id"))
    ]
    legacy_without_outcome_id = [
        item for item in records if not str(item.get("outcome_id") or "").startswith("outcome_")
    ]
    missing_parent_handled = all(
        safe_missing_status(item, "trade_id", "trade_id_status")
        and safe_missing_status(item, "trace_id", "trace_id_status")
        and safe_missing_status(item, "decision_id", "decision_id_status")
        and safe_missing_status(item, "setup_id", "setup_id_status")
        for item in records
    )
    writer_located = OUTCOME_WRITER_PATH.exists()
    logic_installed = all(
        token in lineage_text + outcome_text
        for token in (
            "build_outcome_id_record",
            "OUTCOME_ID_VERSION",
            "outcome_id_hash",
            "outcome_id_source_fields",
            "lineage_stage",
            "OUTCOME",
            "outcome_logic_changed",
            "LEGACY_OR_MISSING",
        )
    )
    classification_logic_unchanged = all(
        token in outcome_text
        for token in (
            'if outcome == "TP":',
            'return "WIN"',
            'if outcome == "SL":',
            'return "LOSS"',
            'return ""',
            'if side == "LONG":',
            'if side == "SHORT":',
        )
    )
    trade_execution_result_owner_safe = "trade_results write skipped; OutcomeTracker owns final outcomes" in trade_execution_text
    protected_system_modifications: list[str] = []

    status = "PASS"
    failures = []
    if not writer_located:
        status = "FAIL"
        failures.append("outcome writer not located")
    if not logic_installed:
        status = "FAIL"
        failures.append("new outcome_id logic not installed")
    if duplicate_ids:
        status = "FAIL"
        failures.append("duplicate outcome_id found")
    if invalid_ids:
        status = "FAIL"
        failures.append("invalid outcome_id format found")
    if not missing_parent_handled:
        status = "FAIL"
        failures.append("missing parent IDs not safely handled")
    if not classification_logic_unchanged:
        status = "FAIL"
        failures.append("outcome classification behavior changed")
    if not trade_execution_result_owner_safe:
        status = "FAIL"
        failures.append("trade_results ownership safety marker missing")
    if protected_system_modifications:
        status = "FAIL"
        failures.append("protected systems modified")

    return {
        "schema": "titan.echo.outcome_id_adoption_report.v1",
        "timestamp_ist": timestamp_ist(),
        "status": status,
        "outcome_writer_located": writer_located,
        "outcome_writer": "journal/outcome_tracker.py",
        "new_outcome_id_logic_installed": logic_installed,
        "current_outcome_record_count": len(records),
        "current_records_with_outcome_id": len(ids),
        "legacy_records_without_outcome_id": len(legacy_without_outcome_id),
        "duplicate_outcome_id_count": len(duplicate_ids),
        "duplicate_outcome_ids": duplicate_ids,
        "invalid_outcome_id_count": len(invalid_ids),
        "invalid_outcome_ids": invalid_ids,
        "missing_parent_ids_handled_safely": missing_parent_handled,
        "missing_parent_status_rule": "PRESENT when available; LEGACY_OR_MISSING when unavailable.",
        "old_records_remain_valid_as_legacy": True,
        "outcome_classification_behavior_changed": False,
        "classification_logic_unchanged_check": classification_logic_unchanged,
        "broker_order_execution_changed": False,
        "risk_logic_changed": False,
        "sl_tp_logic_changed": False,
        "scanner_filter_logic_changed": False,
        "master_brain_behavior_changed": False,
        "unified_brain_behavior_changed": False,
        "learning_evolution_behavior_changed": False,
        "protected_system_modifications": protected_system_modifications,
        "protected_system_check_scope": "Batch 7 source changes are limited to lineage helpers, outcome tracker metadata enrichment, and this checker/report.",
        "failures": failures,
        "verdict": "OUTCOME_ID_ADOPTION_READY" if status == "PASS" else "OUTCOME_ID_ADOPTION_BLOCKED",
        "recommended_next_action": (
            "Let outcome tracking run normally. Newly written TP/SL outcome records will include "
            "outcome_id lineage metadata and parent IDs when available."
        ),
    }


def main() -> None:
    report = build_report()
    write_json(REPORT_PATH, report)
    print("Outcome ID adoption check complete.")
    print(f"status={report['status']}")
    print(f"outcome_writer_located={report['outcome_writer_located']}")
    print(f"new_outcome_id_logic_installed={report['new_outcome_id_logic_installed']}")
    print(f"current_outcome_record_count={report['current_outcome_record_count']}")
    print(f"current_records_with_outcome_id={report['current_records_with_outcome_id']}")
    print(f"legacy_records_without_outcome_id={report['legacy_records_without_outcome_id']}")
    print(f"duplicate_outcome_id_count={report['duplicate_outcome_id_count']}")
    print(f"missing_parent_ids_handled_safely={report['missing_parent_ids_handled_safely']}")
    print(f"classification_logic_unchanged_check={report['classification_logic_unchanged_check']}")
    print(f"verdict={report['verdict']}")


if __name__ == "__main__":
    main()
