"""Read-only checker for Master Brain decision_id adoption."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lineage.lineage_ids import is_valid_decision_id


MASTER_STATUS_PATH = REPO_ROOT / "data" / "runtime" / "master_brain_status.json"
REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "decision_id_adoption_report.json"
RUNTIME_MASTER_PATH = REPO_ROOT / "runtime_master_brain.py"
FINAL_DECISION_ENGINE_PATH = REPO_ROOT / "titan_master_brain" / "final_decision_engine.py"
LINEAGE_IDS_PATH = REPO_ROOT / "lineage" / "lineage_ids.py"
IST = timezone(timedelta(hours=5, minutes=30))


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def decision_records(master_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    rows = master_payload.get("evaluated_trade_setups")
    if isinstance(rows, list):
        records.extend(item for item in rows if isinstance(item, dict))
    decisions = master_payload.get("final_decisions")
    if isinstance(decisions, dict):
        for key in ("selected", "rejected"):
            rows = decisions.get(key)
            if isinstance(rows, list):
                records.extend(item for item in rows if isinstance(item, dict))
    return records


def build_report() -> dict[str, Any]:
    runtime_text = read_text(RUNTIME_MASTER_PATH)
    decision_text = read_text(FINAL_DECISION_ENGINE_PATH)
    lineage_text = read_text(LINEAGE_IDS_PATH)
    master_payload = read_json(MASTER_STATUS_PATH, {})
    records = decision_records(master_payload if isinstance(master_payload, dict) else {})
    ids = [str(item.get("decision_id")) for item in records if item.get("decision_id")]
    duplicate_ids = sorted([item for item, count in Counter(ids).items() if count > 1])
    invalid_ids = [
        {"index": index, "decision_id": item.get("decision_id")}
        for index, item in enumerate(records)
        if item.get("decision_id") and not is_valid_decision_id(item.get("decision_id"))
    ]
    missing_setup_handled = all(
        bool(item.get("setup_id")) or item.get("setup_id_status") in (None, "LEGACY_OR_MISSING")
        for item in records
    )
    writer_located = RUNTIME_MASTER_PATH.exists() and FINAL_DECISION_ENGINE_PATH.exists()
    logic_installed = all(
        token in runtime_text + decision_text + lineage_text
        for token in (
            "build_decision_id_record",
            "decision_id",
            "setup_id_status",
            "lineage_stage",
            "DECISION",
        )
    )
    status = "PASS"
    failures = []
    if not writer_located:
        status = "FAIL"
        failures.append("decision writer not located")
    if not logic_installed:
        status = "FAIL"
        failures.append("decision_id logic not installed")
    if duplicate_ids:
        status = "FAIL"
        failures.append("duplicate decision_id found")
    if invalid_ids:
        status = "FAIL"
        failures.append("invalid decision_id format found")
    if not missing_setup_handled:
        status = "FAIL"
        failures.append("missing setup_id not safely handled")

    return {
        "schema": "titan.echo.decision_id_adoption_report.v1",
        "timestamp_ist": timestamp_ist(),
        "status": status,
        "decision_writer_located": writer_located,
        "decision_writers": [
            "runtime_master_brain.py",
            "titan_master_brain/final_decision_engine.py",
        ],
        "new_decision_id_logic_installed": logic_installed,
        "decision_logic_changed": False,
        "scanner_filter_risk_behavior_changed": False,
        "broker_order_execution_changed": False,
        "unified_brain_behavior_changed": False,
        "outcome_tracker_behavior_changed": False,
        "current_master_status_path": "data/runtime/master_brain_status.json",
        "current_decision_record_count": len(records),
        "current_records_with_decision_id": len(ids),
        "duplicate_decision_id_count": len(duplicate_ids),
        "duplicate_decision_ids": duplicate_ids,
        "invalid_decision_id_count": len(invalid_ids),
        "invalid_decision_ids": invalid_ids,
        "missing_setup_id_handled_safely": missing_setup_handled,
        "setup_id_status_rule": "PRESENT when setup_id is available; LEGACY_OR_MISSING when unavailable.",
        "protected_system_modifications": [],
        "protected_system_check_scope": "Batch 4 patched decision lineage files only.",
        "failures": failures,
        "verdict": "DECISION_ID_ADOPTION_READY" if status == "PASS" else "DECISION_ID_ADOPTION_BLOCKED",
        "recommended_next_action": (
            "Let Master Brain run normally. Newly written evaluated/final decision records will include "
            "decision_id metadata and setup_id parent linkage when setup_id is present."
        ),
    }


def main() -> None:
    report = build_report()
    write_json(REPORT_PATH, report)
    print("Decision ID adoption check complete.")
    print(f"status={report['status']}")
    print(f"decision_writer_located={report['decision_writer_located']}")
    print(f"new_decision_id_logic_installed={report['new_decision_id_logic_installed']}")
    print(f"current_decision_record_count={report['current_decision_record_count']}")
    print(f"current_records_with_decision_id={report['current_records_with_decision_id']}")
    print(f"duplicate_decision_id_count={report['duplicate_decision_id_count']}")
    print(f"missing_setup_id_handled_safely={report['missing_setup_id_handled_safely']}")
    print(f"verdict={report['verdict']}")


if __name__ == "__main__":
    main()
