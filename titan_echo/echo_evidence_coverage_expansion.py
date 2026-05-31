"""Regenerate ECHO coverage evidence for known missing proof surfaces.

This is an ECHO evidence-only orchestrator. It calls existing read-only
builders and writes status/report JSON artifacts only; it does not start
services, execute commands, or mutate TITAN runtime subsystems.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from echo_alert_engine import build_alerts, write_queue
from echo_answer_engine import generate_answer
from echo_api_status import generate_reports as generate_api_status
from echo_brain_status_evidence_writer import generate_brain_status_evidence
from echo_final_readiness_audit import AUDIT_PATH, SUMMARY_PATH as FINAL_READINESS_SUMMARY_PATH
from echo_final_readiness_audit import build_reports as build_final_readiness
from echo_project_state_registry import generate_reports as generate_project_registry
from echo_runtime_evidence import generate_reports as generate_runtime_evidence
from echo_runtime_repair_priority_planner import main as generate_runtime_repair_priority


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
IST = timezone(timedelta(hours=5, minutes=30))

TARGET_EVIDENCE_FILES = [
    RUNTIME_DIR / "unified_brain_status.json",
    RUNTIME_DIR / "brain_state.json",
    ECHO_DIR / "alert_queue.json",
    ECHO_DIR / "project_state_registry.json",
    ECHO_DIR / "runtime_repair_priority_summary.json",
    ECHO_DIR / "final_readiness_summary.json",
]

SUMMARY_PATH = ECHO_DIR / "echo_evidence_coverage_expansion_summary.json"


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def write_echo_json(path: Path, payload: dict[str, Any]) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("coverage expansion summary writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def unknown_count_snapshot() -> dict[str, Any]:
    project_summary = read_json(ECHO_DIR / "project_state_registry_summary.json") or {}
    runtime_summary = read_json(ECHO_DIR / "runtime_evidence_summary.json") or {}
    answer = read_json(ECHO_DIR / "echo_answer.json") or {}
    api_status = read_json(ECHO_DIR / "echo_api_status.json") or {}

    project_unknowns = project_summary.get("still_unknown_systems")
    if not isinstance(project_unknowns, list):
        project_unknowns = []
    runtime_unknowns = runtime_summary.get("still_unknown_systems")
    if not isinstance(runtime_unknowns, list):
        runtime_unknowns = []
    answer_unknowns = answer.get("unknown_status")
    if not isinstance(answer_unknowns, list):
        answer_unknowns = []

    api_unknown_fields = [
        key
        for key in (
            "echo_status",
            "titan_status",
            "unified_brain_status",
            "outcome_tracking_status",
            "lineage_status",
            "natural_run_status",
            "current_focus",
            "next_recommended_action",
        )
        if str(api_status.get(key, "UNKNOWN")).upper() in {"UNKNOWN", "UNKNOWN_NOT_PROVEN", "MISSING"}
    ]

    combined = sorted(
        set(
            [str(item) for item in project_unknowns]
            + [str(item) for item in runtime_unknowns]
            + [str(item.get("name", item)) for item in answer_unknowns]
            + api_unknown_fields
        )
    )
    return {
        "project_registry_unknown_count": len(project_unknowns),
        "runtime_unknown_count": int(runtime_summary.get("unknown_count") or len(runtime_unknowns)),
        "answer_unknown_count": len(answer_unknowns),
        "api_unknown_field_count": len(api_unknown_fields),
        "combined_unknown_count": len(combined),
        "combined_unknowns": combined,
    }


def target_file_statuses() -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for path in TARGET_EVIDENCE_FILES:
        item: dict[str, Any] = {
            "path": rel(path),
            "exists": path.exists(),
            "status_if_missing": "UNKNOWN_NOT_PROVEN",
        }
        if path.exists():
            item["size_bytes"] = path.stat().st_size
            item["modified_at_ist"] = datetime.fromtimestamp(path.stat().st_mtime, IST).isoformat()
        statuses.append(item)
    return statuses


def generate_final_readiness_files() -> None:
    audit, summary = build_final_readiness()
    safety = {
        "read_only_evidence_summary": True,
        "broker_changed": False,
        "risk_changed": False,
        "scanner_changed": False,
        "runtime_behavior_changed": False,
        "master_brain_behavior_changed": False,
        "unified_brain_behavior_changed": False,
        "deploy_or_restart": False,
        "push": False,
    }
    audit["safety"] = safety
    summary["safety"] = safety
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    FINAL_READINESS_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_coverage() -> dict[str, Any]:
    before = unknown_count_snapshot()

    generate_brain_status_evidence()
    alerts = build_alerts()
    write_queue(alerts)
    generate_project_registry()
    generate_runtime_repair_priority()
    generate_final_readiness_files()
    generate_runtime_evidence()
    generate_answer()
    generate_api_status()

    after = unknown_count_snapshot()
    severity_counts = Counter(str(alert.get("severity", "UNKNOWN")) for alert in alerts)
    summary = {
        "schema": "titan.echo.evidence_coverage_expansion_summary.v1",
        "timestamp_ist": timestamp_ist(),
        "mode": "READ_ONLY_EVIDENCE_COVERAGE",
        "target_evidence_files": target_file_statuses(),
        "generated_evidence_files": [rel(path) for path in TARGET_EVIDENCE_FILES if path.exists()],
        "before_unknowns": before,
        "after_unknowns": after,
        "unknown_count_delta": before["combined_unknown_count"] - after["combined_unknown_count"],
        "alerts_generated": len(alerts),
        "alert_severity_counts": dict(severity_counts),
        "safety": {
            "read_only_inspection_only": True,
            "commands_executed_by_script": False,
            "server_started": False,
            "deploy_or_restart": False,
            "push": False,
            "broker_changed": False,
            "risk_changed": False,
            "scanner_changed": False,
            "execution_changed": False,
            "runtime_behavior_changed": False,
            "master_brain_behavior_changed": False,
            "unified_brain_behavior_changed": False,
            "command_endpoints_added": False,
        },
        "risk_level": "LOW",
        "next_recommended_mission": "Run targeted ECHO status/query validation and inspect any remaining UNKNOWN_NOT_PROVEN evidence surfaces.",
    }
    write_echo_json(SUMMARY_PATH, summary)
    return summary


def main() -> None:
    summary = generate_coverage()
    print("ECHO evidence coverage expansion generated.")
    print(f"before_unknown_count={summary['before_unknowns']['combined_unknown_count']}")
    print(f"after_unknown_count={summary['after_unknowns']['combined_unknown_count']}")
    print(f"unknown_count_delta={summary['unknown_count_delta']}")
    print("generated_evidence_files=" + ", ".join(summary["generated_evidence_files"]))
    print(f"risk_level={summary['risk_level']}")


if __name__ == "__main__":
    main()
