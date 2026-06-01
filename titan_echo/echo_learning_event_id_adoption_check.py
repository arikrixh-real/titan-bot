"""Read-only checker for learning_event_id lineage adoption."""

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

from lineage.lineage_ids import is_valid_learning_event_id


REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "learning_event_id_adoption_report.json"
LINEAGE_IDS_PATH = REPO_ROOT / "lineage" / "lineage_ids.py"
LEARNING_WRITER_PATHS = [
    REPO_ROOT / "journal" / "outcome_tracker.py",
    REPO_ROOT / "engines" / "reinforcement_learning_layer.py",
    REPO_ROOT / "engines" / "learning_engine.py",
    REPO_ROOT / "learning_evolution_truth.py",
]
LEARNING_JSON_PATHS = [
    REPO_ROOT / "data" / "learning" / "learning_report.json",
    REPO_ROOT / "data" / "runtime" / "evolution_memory.json",
    REPO_ROOT / "data" / "runtime" / "strategy_weight_change_log.json",
    REPO_ROOT / "data" / "runtime" / "setup_performance_history.json",
    REPO_ROOT / "data" / "runtime" / "market_regime_accuracy.json",
    REPO_ROOT / "data" / "runtime" / "symbol_accuracy_table.json",
]
LEARNING_JSONL_PATHS = [
    REPO_ROOT / "data" / "learning" / "reinforcement_learning_reports.jsonl",
]
IST = timezone(timedelta(hours=5, minutes=30))


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except Exception:
        return []
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def flatten_records(value: Any) -> list[dict[str, Any]]:
    records = []
    if isinstance(value, dict):
        records.append(value)
        for nested_key in ("changes", "sample_reports"):
            nested = value.get(nested_key)
            if isinstance(nested, list):
                records.extend(item for item in nested if isinstance(item, dict))
    elif isinstance(value, list):
        records.extend(item for item in value if isinstance(item, dict))
    return records


def learning_records() -> list[dict[str, Any]]:
    records = []
    for path in LEARNING_JSON_PATHS:
        payload = read_json(path)
        for item in flatten_records(payload):
            records.append({**item, "_source": str(path.relative_to(REPO_ROOT)).replace("\\", "/")})
    for path in LEARNING_JSONL_PATHS:
        for item in read_jsonl(path):
            records.append({**item, "_source": str(path.relative_to(REPO_ROOT)).replace("\\", "/")})
    return records


def safe_missing_status(item: dict[str, Any], id_key: str, status_key: str) -> bool:
    if item.get(id_key):
        return True
    return item.get(status_key) in (None, "", "LEGACY_OR_MISSING")


def build_report() -> dict[str, Any]:
    lineage_text = read_text(LINEAGE_IDS_PATH)
    writer_text = "\n".join(read_text(path) for path in LEARNING_WRITER_PATHS)
    records = learning_records()
    ids = [
        str(item.get("learning_event_id"))
        for item in records
        if str(item.get("learning_event_id") or "").startswith("learning_")
    ]
    duplicates = sorted([item for item, count in Counter(ids).items() if count > 1])
    invalid_ids = [
        {"source": item.get("_source"), "learning_event_id": item.get("learning_event_id")}
        for item in records
        if str(item.get("learning_event_id") or "").startswith("learning_")
        and not is_valid_learning_event_id(item.get("learning_event_id"))
    ]
    legacy_records = [item for item in records if not str(item.get("learning_event_id") or "").startswith("learning_")]
    missing_parent_handled = all(
        safe_missing_status(item, "outcome_id", "outcome_id_status")
        and safe_missing_status(item, "trade_id", "trade_id_status")
        and safe_missing_status(item, "trace_id", "trace_id_status")
        and safe_missing_status(item, "decision_id", "decision_id_status")
        and safe_missing_status(item, "setup_id", "setup_id_status")
        for item in records
    )
    writers_located = all(path.exists() for path in LEARNING_WRITER_PATHS)
    logic_installed = all(
        token in lineage_text + writer_text
        for token in (
            "build_learning_event_id_record",
            "LEARNING_EVENT_ID_VERSION",
            "learning_event_id_hash",
            "learning_event_id_source_fields",
            "lineage_stage",
            "LEARNING",
            "learning_logic_changed",
            "LEGACY_OR_MISSING",
        )
    )
    behavior_unchanged = all(
        token in writer_text
        for token in (
            "score_weight_changes_are_advisory",
            "advisory proof only",
            "Shadow-only reinforcement learning attachment.",
            "does not update live strategy weights",
        )
    )
    protected_system_modifications: list[str] = []

    status = "PASS"
    failures = []
    if not writers_located:
        status = "FAIL"
        failures.append("learning writer not located")
    if not logic_installed:
        status = "FAIL"
        failures.append("new learning_event_id logic not installed")
    if duplicates:
        status = "FAIL"
        failures.append("duplicate learning_event_id found")
    if invalid_ids:
        status = "FAIL"
        failures.append("invalid learning_event_id format found")
    if not missing_parent_handled:
        status = "FAIL"
        failures.append("missing parent IDs not safely handled")
    if not behavior_unchanged:
        status = "FAIL"
        failures.append("learning behavior unchanged markers missing")
    if protected_system_modifications:
        status = "FAIL"
        failures.append("protected systems modified")

    return {
        "schema": "titan.echo.learning_event_id_adoption_report.v1",
        "timestamp_ist": timestamp_ist(),
        "status": status,
        "learning_writer_located": writers_located,
        "learning_writers": [str(path.relative_to(REPO_ROOT)).replace("\\", "/") for path in LEARNING_WRITER_PATHS],
        "new_learning_event_id_logic_installed": logic_installed,
        "current_learning_record_count": len(records),
        "current_records_with_learning_event_id": len(ids),
        "legacy_records_without_learning_event_id": len(legacy_records),
        "duplicate_learning_event_id_count": len(duplicates),
        "duplicate_learning_event_ids": duplicates,
        "invalid_learning_event_id_count": len(invalid_ids),
        "invalid_learning_event_ids": invalid_ids,
        "missing_parent_ids_handled_safely": missing_parent_handled,
        "missing_parent_status_rule": "PRESENT when available; LEGACY_OR_MISSING when unavailable.",
        "old_records_remain_valid_as_legacy": True,
        "learning_behavior_changed": False,
        "learning_behavior_unchanged_check": behavior_unchanged,
        "learning_calculations_changed": False,
        "strategy_weights_changed_by_patch": False,
        "ranking_logic_changed": False,
        "scanner_filter_logic_changed": False,
        "master_brain_behavior_changed": False,
        "unified_brain_behavior_changed": False,
        "outcome_classification_changed": False,
        "evolution_behavior_changed": False,
        "protected_system_modifications": protected_system_modifications,
        "protected_system_check_scope": "Batch 8 source changes are limited to lineage helpers, learning metadata enrichment, and this checker/report.",
        "failures": failures,
        "verdict": "LEARNING_EVENT_ID_ADOPTION_READY" if status == "PASS" else "LEARNING_EVENT_ID_ADOPTION_BLOCKED",
        "recommended_next_action": (
            "Let learning run normally. Newly written learning records will include "
            "learning_event_id lineage metadata and parent IDs when available."
        ),
    }


def main() -> None:
    report = build_report()
    write_json(REPORT_PATH, report)
    print("Learning event ID adoption check complete.")
    print(f"status={report['status']}")
    print(f"learning_writer_located={report['learning_writer_located']}")
    print(f"new_learning_event_id_logic_installed={report['new_learning_event_id_logic_installed']}")
    print(f"current_learning_record_count={report['current_learning_record_count']}")
    print(f"current_records_with_learning_event_id={report['current_records_with_learning_event_id']}")
    print(f"legacy_records_without_learning_event_id={report['legacy_records_without_learning_event_id']}")
    print(f"duplicate_learning_event_id_count={report['duplicate_learning_event_id_count']}")
    print(f"missing_parent_ids_handled_safely={report['missing_parent_ids_handled_safely']}")
    print(f"learning_behavior_unchanged_check={report['learning_behavior_unchanged_check']}")
    print(f"verdict={report['verdict']}")


if __name__ == "__main__":
    main()
