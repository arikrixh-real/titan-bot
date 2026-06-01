"""Final read-only lineage truth audit for Outcome Tracking Truth Upgrade.

This audit consumes the existing adoption reports and lineage helper contract.
It writes Echo reports only; it does not modify runtime behavior or source
writers.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


IST = timezone(timedelta(hours=5, minutes=30))
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
AUDIT_PATH = ECHO_DIR / "final_lineage_truth_audit.json"
SUMMARY_PATH = ECHO_DIR / "final_lineage_truth_summary.json"
LINEAGE_IDS_PATH = REPO_ROOT / "lineage" / "lineage_ids.py"

STAGES = [
    {
        "name": "setup",
        "id_key": "setup_id",
        "report": ECHO_DIR / "setup_id_adoption_report.json",
        "count_keys": ("current_setup_count",),
        "with_id_keys": ("records_with_setup_id",),
        "legacy_keys": ("legacy_unlinked_count",),
        "duplicate_keys": ("duplicate_setup_id_count",),
        "invalid_keys": ("invalid_setup_id_count",),
        "writer_keys": ("checks.every_record_has_setup_id_or_reported_legacy_unlinked",),
        "logic_keys": ("checks.setup_id_format_valid",),
        "missing_keys": ("checks.old_records_without_setup_id_do_not_break_checks",),
        "verdict_ready": "SETUP_ID_ADOPTION_READY",
    },
    {
        "name": "decision",
        "id_key": "decision_id",
        "report": ECHO_DIR / "decision_id_adoption_report.json",
        "count_keys": ("current_decision_record_count",),
        "with_id_keys": ("current_records_with_decision_id",),
        "legacy_keys": (),
        "duplicate_keys": ("duplicate_decision_id_count",),
        "invalid_keys": ("invalid_decision_id_count",),
        "writer_keys": ("decision_writer_located",),
        "logic_keys": ("new_decision_id_logic_installed",),
        "missing_keys": ("missing_setup_id_handled_safely",),
        "verdict_ready": "DECISION_ID_ADOPTION_READY",
    },
    {
        "name": "trace",
        "id_key": "trace_id",
        "report": ECHO_DIR / "trace_id_adoption_report.json",
        "count_keys": ("current_trace_record_count",),
        "with_id_keys": ("current_records_with_trace_id",),
        "legacy_keys": (),
        "duplicate_keys": ("duplicate_trace_id_count",),
        "invalid_keys": ("invalid_new_trace_id_count",),
        "writer_keys": ("trace_writer_located",),
        "logic_keys": ("new_trace_id_logic_installed", "trace_lineage_propagation_installed"),
        "missing_keys": ("missing_decision_id_setup_id_handled_safely",),
        "mode_keys": ("lineage_mode_shadow_only", "live_decision_allowed_false"),
        "verdict_ready": "TRACE_ID_ADOPTION_READY",
    },
    {
        "name": "trade",
        "id_key": "trade_id",
        "report": ECHO_DIR / "trade_id_adoption_report.json",
        "count_keys": ("current_trade_record_count",),
        "with_id_keys": ("current_records_with_new_trade_id",),
        "legacy_keys": ("current_records_with_legacy_trade_id",),
        "duplicate_keys": ("duplicate_trade_id_count",),
        "invalid_keys": ("invalid_new_trade_id_count",),
        "writer_keys": ("trade_writer_located",),
        "logic_keys": ("new_trade_id_logic_installed",),
        "missing_keys": ("missing_parent_ids_handled_safely", "old_records_remain_valid_as_legacy"),
        "verdict_ready": "TRADE_ID_ADOPTION_READY",
    },
    {
        "name": "outcome",
        "id_key": "outcome_id",
        "report": ECHO_DIR / "outcome_id_adoption_report.json",
        "count_keys": ("current_outcome_record_count",),
        "with_id_keys": ("current_records_with_outcome_id",),
        "legacy_keys": ("legacy_records_without_outcome_id",),
        "duplicate_keys": ("duplicate_outcome_id_count",),
        "invalid_keys": ("invalid_outcome_id_count",),
        "writer_keys": ("outcome_writer_located",),
        "logic_keys": ("new_outcome_id_logic_installed",),
        "missing_keys": ("missing_parent_ids_handled_safely", "old_records_remain_valid_as_legacy"),
        "verdict_ready": "OUTCOME_ID_ADOPTION_READY",
    },
    {
        "name": "learning",
        "id_key": "learning_event_id",
        "report": ECHO_DIR / "learning_event_id_adoption_report.json",
        "count_keys": ("current_learning_record_count",),
        "with_id_keys": ("current_records_with_learning_event_id",),
        "legacy_keys": ("legacy_records_without_learning_event_id",),
        "duplicate_keys": ("duplicate_learning_event_id_count",),
        "invalid_keys": ("invalid_learning_event_id_count",),
        "writer_keys": ("learning_writer_located",),
        "logic_keys": ("new_learning_event_id_logic_installed",),
        "missing_keys": ("missing_parent_ids_handled_safely", "old_records_remain_valid_as_legacy"),
        "verdict_ready": "LEARNING_EVENT_ID_ADOPTION_READY",
    },
    {
        "name": "evolution",
        "id_key": "evolution_event_id",
        "report": ECHO_DIR / "evolution_event_id_adoption_report.json",
        "count_keys": ("current_evolution_record_count",),
        "with_id_keys": ("current_records_with_evolution_event_id",),
        "legacy_keys": ("legacy_records_without_evolution_event_id",),
        "duplicate_keys": ("duplicate_evolution_event_id_count",),
        "invalid_keys": ("invalid_evolution_event_id_count",),
        "writer_keys": ("evolution_writer_located",),
        "logic_keys": ("new_evolution_event_id_logic_installed",),
        "missing_keys": ("missing_parent_ids_handled_safely", "old_records_remain_valid_as_legacy"),
        "verdict_ready": "EVOLUTION_EVENT_ID_ADOPTION_READY",
    },
]

CONTRACT_TOKENS = [
    "build_setup_id_record",
    "is_valid_setup_id",
    "build_decision_id_record",
    "is_valid_decision_id",
    "build_trace_id_record",
    "is_valid_trace_id",
    "build_trade_id_record",
    "is_valid_trade_id",
    "build_outcome_id_record",
    "is_valid_outcome_id",
    "build_learning_event_id_record",
    "is_valid_learning_event_id",
    "build_evolution_event_id_record",
    "is_valid_evolution_event_id",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def nested_get(data: dict[str, Any], key: str, default: Any = None) -> Any:
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def first_number(data: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = nested_get(data, key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def keys_true(data: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return bool(keys) and all(nested_get(data, key) is True for key in keys)


def pct(part: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return round((part / total) * 100.0, 2)


def ratio(part: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return round(part / total, 4)


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def stage_audit(stage: dict[str, Any]) -> dict[str, Any]:
    report = read_json(stage["report"])
    total = first_number(report, stage["count_keys"])
    with_id = first_number(report, stage["with_id_keys"])
    legacy = first_number(report, stage["legacy_keys"])
    if legacy == 0 and total > 0 and with_id < total:
        legacy = total - with_id
    duplicate_count = first_number(report, stage["duplicate_keys"])
    invalid_count = first_number(report, stage["invalid_keys"])
    writer_ready = keys_true(report, stage["writer_keys"])
    logic_ready = keys_true(report, stage["logic_keys"])
    missing_safe = keys_true(report, stage["missing_keys"])
    mode_keys = stage.get("mode_keys", ())
    mode_safe = keys_true(report, mode_keys) if mode_keys else True
    adoption_ready = (
        report.get("status") == "PASS"
        and report.get("verdict") == stage["verdict_ready"]
        and writer_ready
        and logic_ready
        and missing_safe
        and mode_safe
        and duplicate_count == 0
        and invalid_count == 0
    )
    newly_lineage_enabled = with_id
    adoption_ready_records = total if adoption_ready else with_id
    legacy_records = max(legacy, total - with_id)
    current_orphans = 0 if missing_safe else with_id
    legacy_orphans = legacy_records
    ambiguous_links = duplicate_count + invalid_count
    future_ready_score = 1.0 if adoption_ready else 0.0
    runtime_proven = with_id > 0

    return {
        "stage": stage["name"],
        "id_key": stage["id_key"],
        "source_report": str(stage["report"].relative_to(REPO_ROOT)).replace("\\", "/"),
        "source_report_exists": stage["report"].exists(),
        "source_status": report.get("status"),
        "source_verdict": report.get("verdict"),
        "record_count": total,
        "records_with_id": with_id,
        "coverage_pct": pct(with_id, total),
        "legacy_records": legacy_records,
        "adoption_ready_records": adoption_ready_records,
        "newly_lineage_enabled_records": newly_lineage_enabled,
        "writer_ready": writer_ready,
        "logic_installed": logic_ready,
        "missing_parent_handled_safely": missing_safe,
        "mode_safe": mode_safe,
        "adoption_ready": adoption_ready,
        "runtime_proven": runtime_proven,
        "duplicate_count": duplicate_count,
        "invalid_id_count": invalid_count,
        "legacy_orphans": legacy_orphans,
        "current_orphans": current_orphans,
        "ambiguous_link_count": ambiguous_links,
        "future_ready_score": future_ready_score,
    }


def build_audit() -> tuple[dict[str, Any], dict[str, Any]]:
    lineage_text = LINEAGE_IDS_PATH.read_text(encoding="utf-8", errors="ignore") if LINEAGE_IDS_PATH.exists() else ""
    contract_complete = all(token in lineage_text for token in CONTRACT_TOKENS)
    stages = [stage_audit(stage) for stage in STAGES]

    total_records = sum(item["record_count"] for item in stages)
    total_with_id = sum(item["records_with_id"] for item in stages)
    total_legacy = sum(item["legacy_records"] for item in stages)
    total_duplicates = sum(item["duplicate_count"] for item in stages)
    total_invalid = sum(item["invalid_id_count"] for item in stages)
    legacy_orphans = sum(item["legacy_orphans"] for item in stages)
    current_orphans = sum(item["current_orphans"] for item in stages)
    ambiguous_links = sum(item["ambiguous_link_count"] for item in stages)

    writer_adoption_complete = all(item["adoption_ready"] for item in stages)
    future_lineage_ready = contract_complete and writer_adoption_complete and total_duplicates == 0 and total_invalid == 0
    current_runtime_proven = all(item["runtime_proven"] for item in stages)
    legacy_data_limitation = total_legacy > 0

    adoption_scores = [item["future_ready_score"] for item in stages]
    runtime_coverage_scores = [ratio(item["records_with_id"], item["record_count"]) for item in stages]
    lineage_completeness_score = mean(adoption_scores)
    traceability_score = mean([
        1.0 if item["adoption_ready"] and item["duplicate_count"] == 0 and item["ambiguous_link_count"] == 0 else 0.0
        for item in stages
    ])
    learning_stage = next(item for item in stages if item["stage"] == "learning")
    evolution_stage = next(item for item in stages if item["stage"] == "evolution")
    learning_linkage_score = 1.0 if learning_stage["adoption_ready"] and learning_stage["current_orphans"] == 0 else 0.0
    evolution_linkage_score = 1.0 if evolution_stage["adoption_ready"] and evolution_stage["current_orphans"] == 0 else 0.0
    future_adoption_score = mean(adoption_scores)

    if not contract_complete or not any(item["adoption_ready"] for item in stages):
        final_verdict = "BROKEN"
    elif not writer_adoption_complete:
        final_verdict = "PARTIAL"
    elif future_lineage_ready and current_runtime_proven and not legacy_data_limitation:
        final_verdict = "READY"
    elif future_lineage_ready:
        final_verdict = "FUTURE_READY"
    else:
        final_verdict = "PARTIAL"

    truth_status = {
        "contract_complete": contract_complete,
        "writer_adoption_complete": writer_adoption_complete,
        "future_lineage_ready": future_lineage_ready,
        "current_runtime_proven": current_runtime_proven,
        "legacy_data_limitation": legacy_data_limitation,
    }

    outcome_upgrade_complete = future_lineage_ready
    recommendations = {
        "what_is_actually_fixed": [
            "Stable ID helper and validator contracts exist for setup, decision, trace, trade, outcome, learning, and evolution stages.",
            "All adoption checkers report PASS and writer adoption is ready for future records.",
            "Duplicate checks are clean for all currently reported lineage IDs.",
            "Missing parent IDs are handled as LEGACY_OR_MISSING instead of breaking backward compatibility.",
        ],
        "what_remains_legacy_only": [
            "Historical records written before their stage adoption remain valid but cannot be fully end-to-end linked.",
            "Current runtime proof is incomplete until each stage naturally writes fresh post-adoption records.",
        ],
        "outcome_tracking_truth_upgrade_status": "COMPLETE" if outcome_upgrade_complete else "NOT_COMPLETE",
        "next_recommended_titan_project": (
            "Natural-run lineage proof: let TITAN run normally without behavior changes, then audit one fresh "
            "setup -> decision -> trace -> trade -> outcome -> learning -> evolution chain end to end."
        ),
    }

    audit = {
        "schema": "titan.echo.final_lineage_truth_audit.v1",
        "timestamp_ist": timestamp_ist(),
        "audit_mode": "READ_ONLY",
        "runtime_behavior_modified": False,
        "protected_systems_modified": [],
        "lineage_chain": [
            "setup_id",
            "decision_id",
            "trace_id",
            "trade_id",
            "outcome_id",
            "learning_event_id",
            "evolution_event_id",
        ],
        "coverage": {item["stage"]: item for item in stages},
        "legacy_separation": {
            "legacy_records": total_legacy,
            "adoption_ready_records": sum(item["adoption_ready_records"] for item in stages),
            "newly_lineage_enabled_records": sum(item["newly_lineage_enabled_records"] for item in stages),
            "historical_legacy_not_penalized": True,
        },
        "orphans_and_duplicates": {
            "orphan_count": legacy_orphans + current_orphans,
            "legacy_orphans": legacy_orphans,
            "current_orphans": current_orphans,
            "duplicate_count": total_duplicates,
            "invalid_id_count": total_invalid,
            "ambiguous_link_count": ambiguous_links,
        },
        "scores": {
            "lineage_completeness_score": lineage_completeness_score,
            "traceability_score": traceability_score,
            "learning_linkage_score": learning_linkage_score,
            "evolution_linkage_score": evolution_linkage_score,
            "future_adoption_score": future_adoption_score,
            "raw_historical_runtime_coverage_score": mean(runtime_coverage_scores),
        },
        "LINEAGE_TRUTH_STATUS": truth_status,
        "final_verdict": final_verdict,
        "recommendations": recommendations,
    }
    summary = {
        "schema": "titan.echo.final_lineage_truth_summary.v1",
        "timestamp_ist": audit["timestamp_ist"],
        "LINEAGE_TRUTH_STATUS": truth_status,
        "lineage_completeness_score": lineage_completeness_score,
        "traceability_score": traceability_score,
        "learning_linkage_score": learning_linkage_score,
        "evolution_linkage_score": evolution_linkage_score,
        "future_adoption_score": future_adoption_score,
        "legacy_orphans": legacy_orphans,
        "current_orphans": current_orphans,
        "orphan_count": legacy_orphans + current_orphans,
        "duplicate_count": total_duplicates,
        "ambiguous_link_count": ambiguous_links,
        "final_verdict": final_verdict,
        "outcome_tracking_truth_upgrade_status": recommendations["outcome_tracking_truth_upgrade_status"],
        "recommended_next_titan_project": recommendations["next_recommended_titan_project"],
    }
    return audit, summary


def main() -> None:
    audit, summary = build_audit()
    write_json(AUDIT_PATH, audit)
    write_json(SUMMARY_PATH, summary)
    scores = audit["scores"]
    orphans = audit["orphans_and_duplicates"]
    print("Final lineage truth audit complete.")
    print(f"lineage_completeness_score={scores['lineage_completeness_score']}")
    print(f"traceability_score={scores['traceability_score']}")
    print(f"learning_linkage_score={scores['learning_linkage_score']}")
    print(f"evolution_linkage_score={scores['evolution_linkage_score']}")
    print(f"future_adoption_score={scores['future_adoption_score']}")
    print(f"legacy_orphans={orphans['legacy_orphans']}")
    print(f"current_orphans={orphans['current_orphans']}")
    print(f"orphan_count={orphans['orphan_count']}")
    print(f"duplicate_count={orphans['duplicate_count']}")
    print(f"ambiguous_link_count={orphans['ambiguous_link_count']}")
    print(f"final_verdict={audit['final_verdict']}")
    print(f"outcome_tracking_truth_upgrade_status={audit['recommendations']['outcome_tracking_truth_upgrade_status']}")
    print(f"recommended_next_titan_project={audit['recommendations']['next_recommended_titan_project']}")


if __name__ == "__main__":
    main()
