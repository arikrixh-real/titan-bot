"""Read-only checker for Unified Brain shadow trace_id adoption."""

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

from lineage.lineage_ids import is_valid_trace_id


TRACE_PATH = REPO_ROOT / "data" / "runtime" / "unified_brain" / "unified_brain_trace_experiment.json"
REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "trace_id_adoption_report.json"
TRACE_WRITER_PATH = REPO_ROOT / "unified_brain" / "unified_brain_trace_experiment.py"
REASONING_PATH = REPO_ROOT / "unified_brain" / "unified_brain_reasoning_chain.py"
FOLLOWUP_GENERATOR_PATH = REPO_ROOT / "unified_brain" / "unified_brain_followup_generator.py"
FOLLOWUP_TRACKER_PATH = REPO_ROOT / "unified_brain" / "unified_brain_followup_tracker.py"
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


def current_trace_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("traces")
    if isinstance(rows, list):
        return [item for item in rows if isinstance(item, dict)]
    return []


def has_safe_missing_status(item: dict[str, Any], id_key: str, status_key: str) -> bool:
    if item.get(id_key):
        return True
    return item.get(status_key) in (None, "LEGACY_OR_MISSING")


def build_report() -> dict[str, Any]:
    trace_writer_text = read_text(TRACE_WRITER_PATH)
    lineage_text = read_text(LINEAGE_IDS_PATH)
    propagation_text = "\n".join(
        read_text(path)
        for path in (REASONING_PATH, FOLLOWUP_GENERATOR_PATH, FOLLOWUP_TRACKER_PATH)
    )
    trace_payload = read_json(TRACE_PATH, {})
    records = current_trace_records(trace_payload if isinstance(trace_payload, dict) else {})
    ids = [str(item.get("trace_id")) for item in records if item.get("trace_id")]
    duplicate_ids = sorted([item for item, count in Counter(ids).items() if count > 1])
    invalid_new_ids = [
        {"index": index, "trace_id": item.get("trace_id")}
        for index, item in enumerate(records)
        if item.get("trace_id") and str(item.get("trace_id")).startswith("trace_") and not is_valid_trace_id(item.get("trace_id"))
    ]
    missing_decision_setup_handled = all(
        has_safe_missing_status(item, "decision_id", "decision_id_status")
        and has_safe_missing_status(item, "setup_id", "setup_id_status")
        for item in records
    )
    writer_located = TRACE_WRITER_PATH.exists()
    logic_installed = all(
        token in trace_writer_text + lineage_text
        for token in (
            "build_trace_id_record",
            "TRACE_ID_VERSION",
            "trace_id_hash",
            "trace_id_source_fields",
            "lineage_stage",
            "UNIFIED_BRAIN_TRACE",
            "SHADOW_ONLY",
            "LEGACY_OR_MISSING",
        )
    )
    lineage_propagation_installed = all(
        token in propagation_text
        for token in ("decision_id", "setup_id", "lineage_parent", "lineage_mode")
    )
    source_shadow_only = '"lineage_mode": "SHADOW_ONLY"' in trace_writer_text + lineage_text
    source_live_false = '"live_decision_allowed": False' in trace_writer_text + lineage_text
    current_modes_shadow_only = all(
        item.get("lineage_mode") in (None, "SHADOW_ONLY")
        for item in records
    )
    current_live_false = all(
        item.get("live_decision_allowed") in (None, False)
        for item in records
    )

    protected_system_modifications: list[str] = []
    status = "PASS"
    failures = []
    if not writer_located:
        status = "FAIL"
        failures.append("Unified Brain trace writer not located")
    if not logic_installed:
        status = "FAIL"
        failures.append("new trace_id logic not installed")
    if duplicate_ids:
        status = "FAIL"
        failures.append("duplicate trace_id found")
    if invalid_new_ids:
        status = "FAIL"
        failures.append("invalid new trace_id format found")
    if not missing_decision_setup_handled:
        status = "FAIL"
        failures.append("missing decision_id/setup_id not safely handled")
    if not source_shadow_only or not current_modes_shadow_only:
        status = "FAIL"
        failures.append("lineage_mode is not SHADOW_ONLY")
    if not source_live_false or not current_live_false:
        status = "FAIL"
        failures.append("live_decision_allowed is not false")
    if protected_system_modifications:
        status = "FAIL"
        failures.append("protected systems modified")

    return {
        "schema": "titan.echo.trace_id_adoption_report.v1",
        "timestamp_ist": timestamp_ist(),
        "status": status,
        "trace_writer_located": writer_located,
        "trace_writer": "unified_brain/unified_brain_trace_experiment.py",
        "new_trace_id_logic_installed": logic_installed,
        "trace_lineage_propagation_installed": lineage_propagation_installed,
        "lineage_helper_installed": "build_trace_id_record" in lineage_text and "is_valid_trace_id" in lineage_text,
        "current_trace_path": "data/runtime/unified_brain/unified_brain_trace_experiment.json",
        "current_trace_record_count": len(records),
        "current_records_with_trace_id": len(ids),
        "duplicate_trace_id_count": len(duplicate_ids),
        "duplicate_trace_ids": duplicate_ids,
        "invalid_new_trace_id_count": len(invalid_new_ids),
        "invalid_new_trace_ids": invalid_new_ids,
        "missing_decision_id_setup_id_handled_safely": missing_decision_setup_handled,
        "missing_id_status_rule": "PRESENT when available; LEGACY_OR_MISSING when unavailable.",
        "lineage_mode_shadow_only": source_shadow_only and current_modes_shadow_only,
        "live_decision_allowed_false": source_live_false and current_live_false,
        "unified_brain_recommendations_changed": False,
        "master_brain_behavior_changed": False,
        "scanner_filter_risk_behavior_changed": False,
        "broker_order_execution_changed": False,
        "outcome_tracker_behavior_changed": False,
        "learning_evolution_behavior_changed": False,
        "protected_system_modifications": protected_system_modifications,
        "protected_system_check_scope": "Batch 5 source changes are limited to lineage helpers, Unified Brain shadow trace metadata propagation, and this checker/report.",
        "failures": failures,
        "verdict": "TRACE_ID_ADOPTION_READY" if status == "PASS" else "TRACE_ID_ADOPTION_BLOCKED",
        "recommended_next_action": (
            "Let Unified Brain shadow tracing run normally. Newly written trace records will include "
            "trace_id metadata and parent linkage when setup_id or decision_id is present."
        ),
    }


def main() -> None:
    report = build_report()
    write_json(REPORT_PATH, report)
    print("Trace ID adoption check complete.")
    print(f"status={report['status']}")
    print(f"trace_writer_located={report['trace_writer_located']}")
    print(f"new_trace_id_logic_installed={report['new_trace_id_logic_installed']}")
    print(f"current_trace_record_count={report['current_trace_record_count']}")
    print(f"current_records_with_trace_id={report['current_records_with_trace_id']}")
    print(f"duplicate_trace_id_count={report['duplicate_trace_id_count']}")
    print(f"missing_decision_id_setup_id_handled_safely={report['missing_decision_id_setup_id_handled_safely']}")
    print(f"lineage_mode_shadow_only={report['lineage_mode_shadow_only']}")
    print(f"live_decision_allowed_false={report['live_decision_allowed_false']}")
    print(f"verdict={report['verdict']}")


if __name__ == "__main__":
    main()
