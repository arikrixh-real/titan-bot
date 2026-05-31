"""Evidence-only writers for Master Brain and Unified Brain runtime status.

This module creates compatibility evidence files consumed by ECHO runtime
evidence checks. It reads existing status artifacts and writes metadata only;
it does not call brain decision/reasoning code.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"
IST = timezone(timedelta(hours=5, minutes=30))

BRAIN_STATE_PATH = RUNTIME_DIR / "brain_state.json"
UNIFIED_BRAIN_STATUS_PATH = RUNTIME_DIR / "unified_brain_status.json"
REPAIR_REPORT_PATH = ECHO_DIR / "brain_status_evidence_repair_report.json"

MASTER_EVIDENCE_PATHS = [
    RUNTIME_DIR / "master_brain_status.json",
    RUNTIME_DIR / "titan_runtime_status.json",
    ECHO_DIR / "project_state_registry.json",
    ECHO_DIR / "runtime_evidence_summary.json",
]
UNIFIED_EVIDENCE_PATHS = [
    RUNTIME_DIR / "unified_brain" / "unified_brain_final_status.json",
    RUNTIME_DIR / "unified_brain" / "unified_brain_final_summary.json",
    RUNTIME_DIR / "titan_runtime_status.json",
    ECHO_DIR / "project_state_registry.json",
    ECHO_DIR / "runtime_evidence_summary.json",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}"}


def file_evidence(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    missing: list[str] = []
    for path in paths:
        item: dict[str, Any] = {
            "path": relative(path),
            "exists": path.exists(),
        }
        if path.exists():
            try:
                item["mtime_ist"] = datetime.fromtimestamp(path.stat().st_mtime, IST).isoformat()
            except OSError:
                item["mtime_ist"] = None
        else:
            missing.append(relative(path))
        evidence.append(item)
    return evidence, missing


def status_from_master_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "status": "MISSING",
            "source_path": relative(RUNTIME_DIR / "master_brain_status.json"),
        }
    return {
        "status": payload.get("status") or payload.get("master_brain_runtime_health") or "PRESENT",
        "runtime_mode": payload.get("runtime_mode"),
        "mode": payload.get("mode"),
        "timestamp_ist": payload.get("timestamp_ist"),
        "master_brain_runtime_health": payload.get("master_brain_runtime_health"),
        "master_brain_freshness_confidence": payload.get("master_brain_freshness_confidence"),
        "observe_only": payload.get("observe_only"),
        "live_execution_enabled": payload.get("live_execution_enabled"),
        "telegram_enabled": payload.get("telegram_enabled"),
        "journal_writes_enabled": payload.get("journal_writes_enabled"),
        "source_path": relative(RUNTIME_DIR / "master_brain_status.json"),
    }


def status_from_unified_payload(status_payload: Any, summary_payload: Any) -> dict[str, Any]:
    source = status_payload if isinstance(status_payload, dict) else {}
    summary = summary_payload if isinstance(summary_payload, dict) else {}
    merged = {**summary, **source}
    return {
        "status": merged.get("final_verdict") or merged.get("status") or "MISSING",
        "mode": merged.get("mode"),
        "timestamp_ist": merged.get("timestamp_ist"),
        "promotion_state": merged.get("promotion_state"),
        "architecture_state": merged.get("architecture_state"),
        "validation_state": merged.get("validation_state"),
        "live_decision_allowed": bool(merged.get("live_decision_allowed", False)),
        "remaining_blockers": merged.get("remaining_blockers") or [],
        "source_paths": [
            relative(RUNTIME_DIR / "unified_brain" / "unified_brain_final_status.json"),
            relative(RUNTIME_DIR / "unified_brain" / "unified_brain_final_summary.json"),
        ],
    }


def build_brain_state(now: str | None = None) -> dict[str, Any]:
    generated_at = now or timestamp_ist()
    master_payload = read_json(RUNTIME_DIR / "master_brain_status.json")
    evidence, missing = file_evidence(MASTER_EVIDENCE_PATHS)
    return {
        "schema": "titan.echo.brain_state_evidence.v1",
        "timestamp_ist": generated_at,
        "status_source": "titan_echo.echo_brain_status_evidence_writer",
        "master_brain_status": status_from_master_payload(master_payload),
        "evidence_files_read": evidence,
        "missing_evidence": missing,
        "brain_behavior_changed": False,
    }


def build_unified_brain_status(now: str | None = None) -> dict[str, Any]:
    generated_at = now or timestamp_ist()
    final_status = read_json(RUNTIME_DIR / "unified_brain" / "unified_brain_final_status.json")
    final_summary = read_json(RUNTIME_DIR / "unified_brain" / "unified_brain_final_summary.json")
    unified_status = status_from_unified_payload(final_status, final_summary)
    evidence, missing = file_evidence(UNIFIED_EVIDENCE_PATHS)
    return {
        "schema": "titan.echo.unified_brain_status_evidence.v1",
        "timestamp_ist": generated_at,
        "status_source": "titan_echo.echo_brain_status_evidence_writer",
        "unified_brain_status": unified_status["status"],
        "promotion_state": unified_status["promotion_state"],
        "architecture_state": unified_status["architecture_state"],
        "validation_state": unified_status["validation_state"],
        "live_decision_allowed": False,
        "evidence_status": unified_status,
        "evidence_files_read": evidence,
        "missing_evidence": missing,
        "unified_brain_behavior_changed": False,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def generate_brain_status_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    now = timestamp_ist()
    brain_state = build_brain_state(now)
    unified_status = build_unified_brain_status(now)
    report = {
        "schema": "titan.echo.brain_status_evidence_repair_report.v1",
        "timestamp_ist": now,
        "status": "PASS",
        "outputs_written": [
            relative(BRAIN_STATE_PATH),
            relative(UNIFIED_BRAIN_STATUS_PATH),
            relative(REPAIR_REPORT_PATH),
        ],
        "source_inputs": [relative(path) for path in MASTER_EVIDENCE_PATHS + UNIFIED_EVIDENCE_PATHS],
        "master_brain_behavior_changed": False,
        "unified_brain_behavior_changed": False,
        "runtime_behavior_changed": False,
        "safety": {
            "metadata_status_evidence_only": True,
            "master_brain_decision_logic_changed": False,
            "unified_brain_reasoning_logic_changed": False,
            "scanner_filter_risk_broker_changed": False,
            "daemon_restart_start_stop": False,
            "duplicate_runner_logic_added": False,
            "runtime_scheduling_changed": False,
            "live_decision_allowed": False,
        },
        "remaining_missing_evidence": sorted(
            set(brain_state["missing_evidence"] + unified_status["missing_evidence"])
        ),
    }
    write_json(BRAIN_STATE_PATH, brain_state)
    write_json(UNIFIED_BRAIN_STATUS_PATH, unified_status)
    write_json(REPAIR_REPORT_PATH, report)
    return brain_state, unified_status, report


def main() -> None:
    brain_state, unified_status, report = generate_brain_status_evidence()
    print("ECHO brain status evidence generated.")
    print(f"master_brain_status={brain_state['master_brain_status'].get('status')}")
    print(f"unified_brain_status={unified_status.get('unified_brain_status')}")
    print(f"live_decision_allowed={unified_status.get('live_decision_allowed')}")
    print("remaining_missing_evidence=" + ", ".join(report["remaining_missing_evidence"]))


if __name__ == "__main__":
    main()
