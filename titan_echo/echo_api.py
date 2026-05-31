"""Read-only local ECHO API surface.

This module is safe to import without starting a server. When FastAPI is
installed it defines an ``app`` with GET-only routes. When FastAPI is missing
it still exposes fallback functions for local callers.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from titan_echo.echo_api_auth import require_echo_api_key
from titan_echo.echo_api_status import build_status, read_sources


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
IST = timezone(timedelta(hours=5, minutes=30))

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import Depends, FastAPI
else:  # pragma: no cover - depends on local dependency set
    Depends = None  # type: ignore[assignment, misc]
    FastAPI = None  # type: ignore[assignment, misc]


READ_ONLY_EVIDENCE = {
    "answer": ECHO_DIR / "echo_answer.json",
    "mission_center": ECHO_DIR / "echo_mission_center.json",
    "query_router": ECHO_DIR / "echo_query_router.json",
    "approval_queue": ECHO_DIR / "approval_queue.json",
    "mission_plan": ECHO_DIR / "mission_plan.json",
    "verification_report": ECHO_DIR / "verification_report.json",
}
MISSION_PLAN_PATH = ECHO_DIR / "mission_plan.json"
APPROVAL_QUEUE_PATH = ECHO_DIR / "approval_queue.json"
APPROVAL_HISTORY_PATH = ECHO_DIR / "approval_history.jsonl"
APPROVED_MISSIONS_PATH = ECHO_DIR / "approved_missions.json"
REJECTED_MISSIONS_PATH = ECHO_DIR / "rejected_missions.json"
EXECUTION_READINESS_REPORT_PATH = ECHO_DIR / "execution_readiness_report.json"
EXECUTION_PREVIEW_PATH = ECHO_DIR / "execution_preview.json"
VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

SECRET_MARKERS = (
    "api_key",
    "apikey",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key).lower()
            if any(marker in text_key for marker in SECRET_MARKERS):
                clean[key] = "REDACTED"
            else:
                clean[key] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("ECHO API bridge writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_echo_jsonl(path: Path, payload: dict[str, Any]) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("ECHO API bridge writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")


def _evidence_payload(name: str) -> dict[str, Any]:
    path = READ_ONLY_EVIDENCE[name]
    data = _sanitize(_read_json(path))
    return {
        "source": _relative(path),
        "data": data,
        "status": "EVIDENCE_PRESENT" if data is not None else "UNKNOWN",
    }


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _load_approval_queue() -> dict[str, Any]:
    queue = _read_json(APPROVAL_QUEUE_PATH)
    if not isinstance(queue, dict):
        queue = {"schema": "titan_echo.approval_queue.v1", "approvals": []}
    approvals = queue.get("approvals")
    if not isinstance(approvals, list):
        queue["approvals"] = []
    return queue


def _save_approval_queue(queue: dict[str, Any]) -> None:
    approvals = [item for item in queue.get("approvals", []) if isinstance(item, dict)]
    counts = Counter(str(item.get("status", "UNKNOWN")).upper() for item in approvals)
    queue["schema"] = "titan_echo.approval_queue.v1"
    queue["timestamp_ist"] = _timestamp_ist()
    queue["summary"] = {
        "total": len(approvals),
        "pending": counts.get("PENDING", 0),
        "approved": counts.get("APPROVED", 0),
        "rejected": counts.get("REJECTED", 0),
    }
    queue["approvals"] = approvals
    _write_echo_json(APPROVAL_QUEUE_PATH, queue)


def _load_mission_plan() -> dict[str, Any]:
    mission_plan = _read_json(MISSION_PLAN_PATH)
    return mission_plan if isinstance(mission_plan, dict) else {}


def _load_mission_collection(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return {"schema": "titan.echo.approval_decision_missions.v1", "missions": []}
    missions = payload.get("missions")
    if not isinstance(missions, list):
        payload["missions"] = []
    return payload


def _mission_collection_items(path: Path) -> list[dict[str, Any]]:
    payload = _load_mission_collection(path)
    missions = payload.get("missions")
    return [item for item in missions if isinstance(item, dict)] if isinstance(missions, list) else []


def _mission_collection_contains(path: Path, mission_id: str, approval_id: str) -> bool:
    for item in _mission_collection_items(path):
        if str(item.get("mission_id") or "") == mission_id and str(item.get("approval_id") or "") == approval_id:
            return True
        mission = item.get("mission") if isinstance(item.get("mission"), dict) else {}
        if str(mission.get("mission_id") or "") == mission_id and str(mission.get("approval_id") or "") == approval_id:
            return True
        approval = item.get("approval_record") if isinstance(item.get("approval_record"), dict) else {}
        if str(approval.get("mission_id") or "") == mission_id and str(approval.get("approval_id") or "") == approval_id:
            return True
    return False


def _append_mission_decision(path: Path, decision: str, record: dict[str, Any], mission_plan: dict[str, Any]) -> None:
    payload = _load_mission_collection(path)
    mission_snapshot = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else {}
    item = {
        "approval_id": record.get("approval_id"),
        "mission_id": record.get("mission_id"),
        "decision": decision,
        "decision_timestamp_ist": record.get("decision_timestamp_ist"),
        "approval_note": record.get("approval_note", ""),
        "approval_record": record,
        "mission": mission_snapshot,
        "safety": _decision_safety(),
    }
    payload["schema"] = "titan.echo.approval_decision_missions.v1"
    payload["timestamp_ist"] = _timestamp_ist()
    payload["missions"].append(item)
    payload["summary"] = {"total": len(payload["missions"])}
    _write_echo_json(path, payload)


def _decision_safety() -> dict[str, bool]:
    return {
        "execution_allowed": False,
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "broker_changed": False,
        "risk_changed": False,
        "execution_changed": False,
        "scanner_changed": False,
        "master_brain_changed": False,
        "unified_brain_changed": False,
        "runtime_workers_changed": False,
    }


def _approval_queue_record(mission_id: str, approval_id: str) -> dict[str, Any] | None:
    queue = _load_approval_queue()
    approvals = queue.get("approvals")
    if not isinstance(approvals, list):
        return None
    for item in approvals:
        if not isinstance(item, dict):
            continue
        if str(item.get("mission_id") or "") == mission_id and str(item.get("approval_id") or "") == approval_id:
            return item
    return None


def _false_flag(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if value is None and isinstance(data.get("safety"), dict):
        value = data["safety"].get(key)
    return value is False


def _source_status(name: str, missing_status: str) -> dict[str, Any]:
    path = READ_ONLY_EVIDENCE[name]
    data = _sanitize(_read_json(path))
    return {
        "source": _relative(path),
        "data": data,
        "status": "EVIDENCE_PRESENT" if data is not None else missing_status,
    }


def get_health() -> dict[str, Any]:
    return {
        "echo_api": "AVAILABLE",
        "api_mode": "FASTAPI_APP" if FASTAPI_AVAILABLE else "FALLBACK_FUNCTIONS",
        "fastapi_available": FASTAPI_AVAILABLE,
        "read_only": True,
        "shell_execution": False,
        "codex_execution": False,
        "broker_risk_scanner_changes": False,
        "deploy_or_restart": False,
        "public_exposure": False,
    }


def get_status() -> dict[str, Any]:
    status = build_status()
    status["api_mode"] = "FASTAPI_APP" if FASTAPI_AVAILABLE else "FALLBACK_FUNCTIONS"
    status["fastapi_available"] = FASTAPI_AVAILABLE
    return status


def get_projects() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/project_state_registry.json",
        "data": sources["projects"],
        "status": "EVIDENCE_PRESENT" if sources["projects"] is not None else "UNKNOWN",
    }


def get_unified_brain() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/unified_brain_status.json",
        "data": sources["unified_brain"],
        "status": "EVIDENCE_PRESENT" if sources["unified_brain"] is not None else "UNKNOWN",
    }


def get_lineage() -> dict[str, Any]:
    sources = read_sources()
    return {
        "sources": [
            "data/runtime/echo/final_lineage_truth_summary.json",
            "data/runtime/echo/natural_run_lineage_proof.json",
        ],
        "final_lineage_truth": sources["lineage"],
        "natural_run_lineage_proof": sources["natural_run"],
    }


def get_alerts() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/alert_queue.json",
        "data": sources["alerts"],
        "status": "EVIDENCE_PRESENT" if sources["alerts"] is not None else "UNKNOWN",
    }


def get_missions() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/mission_plan.json",
        "data": sources["missions"],
        "status": "EVIDENCE_PRESENT" if sources["missions"] is not None else "UNKNOWN",
    }


def get_answer() -> dict[str, Any]:
    answer_payload = _evidence_payload("answer")
    if answer_payload["data"] is not None:
        return answer_payload
    mission_payload = _evidence_payload("mission_center")
    mission_payload["fallback_source"] = mission_payload["source"]
    mission_payload["source"] = answer_payload["source"]
    return mission_payload


def get_query(intent: str = "status") -> dict[str, Any]:
    requested_intent = intent or "status"
    router_payload = _evidence_payload("query_router")
    router_data = router_payload["data"]
    if not isinstance(router_data, dict):
        return {
            "source": router_payload["source"],
            "intent": requested_intent,
            "status": "UNKNOWN",
            "data": None,
        }
    responses = router_data.get("responses")
    if not isinstance(responses, dict):
        return {
            "source": router_payload["source"],
            "intent": requested_intent,
            "status": "UNKNOWN",
            "data": router_data,
        }
    selected = responses.get(requested_intent) or responses.get("unknown")
    resolved_intent = requested_intent if requested_intent in responses else "unknown"
    return {
        "source": router_payload["source"],
        "intent": requested_intent,
        "resolved_intent": resolved_intent,
        "status": "EVIDENCE_PRESENT" if selected is not None else "UNKNOWN",
        "data": selected,
    }


def get_approval_pending() -> dict[str, Any]:
    payload = _source_status("approval_queue", "WAITING_FOR_DATA")
    data = payload["data"]
    approvals = data.get("approvals") if isinstance(data, dict) else []
    if not isinstance(approvals, list):
        approvals = []
    pending = [
        item
        for item in approvals
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "PENDING"
    ]
    return {
        "source": payload["source"],
        "status": payload["status"],
        "pending": pending,
        "pending_count": len(pending),
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


def get_mission_current() -> dict[str, Any]:
    payload = _source_status("mission_plan", "UNKNOWN_NOT_PROVEN")
    data = payload["data"]
    active_mission = None
    if isinstance(data, dict):
        active_mission = (
            data.get("current_mission")
            or data.get("active_mission")
            or data.get("mission")
        )
    return {
        "source": payload["source"],
        "status": payload["status"],
        "active_mission": active_mission,
        "active_mission_proven": active_mission is not None,
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


def get_verification_latest() -> dict[str, Any]:
    payload = _source_status("verification_report", "UNKNOWN_NOT_PROVEN")
    return {
        "source": payload["source"],
        "status": payload["status"],
        "verification_report": payload["data"],
        "verification_proven": payload["data"] is not None,
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


def build_execution_readiness_report() -> dict[str, Any]:
    mission_plan = _load_mission_plan()
    mission = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else {}
    mission_id = str(mission.get("mission_id") or "")
    approval_id = str(mission.get("approval_id") or "")
    approval_status = str(mission.get("approval_status") or mission.get("status") or "").upper()
    queue_record = _approval_queue_record(mission_id, approval_id) if mission_id and approval_id else None
    queue_status = str(queue_record.get("status") or "").upper() if isinstance(queue_record, dict) else ""
    approved_registry_present = _mission_collection_contains(APPROVED_MISSIONS_PATH, mission_id, approval_id) if mission_id and approval_id else False
    rejected_registry_present = _mission_collection_contains(REJECTED_MISSIONS_PATH, mission_id, approval_id) if mission_id and approval_id else False
    merged_safety = dict(mission.get("safety") if isinstance(mission.get("safety"), dict) else {})
    for key in ("execution_allowed", "codex_execution", "shell_execution", "git_push_pull", "deploy_or_restart"):
        if key not in merged_safety and key in mission_plan:
            merged_safety[key] = mission_plan.get(key)
        if key not in merged_safety and key in mission:
            merged_safety[key] = mission.get(key)

    checks = {
        "mission_id_exists": bool(mission_id),
        "approval_id_exists": bool(approval_id),
        "mission_status_approved": approval_status == "APPROVED",
        "approval_queue_decision_approved": queue_status == "APPROVED",
        "mission_exists_in_approved_missions": approved_registry_present,
        "mission_absent_from_rejected_missions": not rejected_registry_present,
        "execution_allowed_remains_false": merged_safety.get("execution_allowed") is False,
        "codex_execution_remains_false": merged_safety.get("codex_execution") is False,
        "shell_execution_remains_false": merged_safety.get("shell_execution") is False,
        "git_push_pull_remains_false": merged_safety.get("git_push_pull") is False,
        "deploy_or_restart_remains_false": merged_safety.get("deploy_or_restart") is False,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    status = "READY_DRY_RUN_ONLY" if not blockers else "NOT_READY"
    report = {
        "schema": "titan.echo.execution_readiness_report.v1",
        "status": status,
        "mission_id": mission_id or None,
        "approval_id": approval_id or None,
        "checks": checks,
        "blockers": blockers,
        "safety": {
            "dry_run_only": True,
            "execution_allowed": False,
            "codex_execution": False,
            "shell_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "titan_runtime_changed": False,
            "scanner_changed": False,
            "broker_changed": False,
            "risk_changed": False,
            "master_brain_changed": False,
            "unified_brain_changed": False,
            "runtime_workers_changed": False,
        },
        "generated_at_ist": _timestamp_ist(),
        "message": (
            "Mission is approved for dry-run readiness only. No execution is enabled."
            if status == "READY_DRY_RUN_ONLY"
            else "Mission is not execution-ready; blockers must be resolved without enabling execution."
        ),
    }
    _write_echo_json(EXECUTION_READINESS_REPORT_PATH, report)
    return report


def get_execution_readiness() -> dict[str, Any]:
    report = _read_json(EXECUTION_READINESS_REPORT_PATH)
    if not isinstance(report, dict):
        report = build_execution_readiness_report()
    return report


def post_execution_readiness_check() -> dict[str, Any]:
    return build_execution_readiness_report()


def _format_list_for_prompt(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "- none specified"
    return "\n".join(f"- {value}" for value in values)


def _build_proposed_codex_prompt(mission: dict[str, Any], readiness: dict[str, Any]) -> str:
    mission_id = mission.get("mission_id") or readiness.get("mission_id") or "UNKNOWN"
    approval_id = mission.get("approval_id") or readiness.get("approval_id") or "UNKNOWN"
    title = mission.get("title") or "Approved ECHO mission"
    objective = mission.get("objective") or "Execute only the approved mission scope."
    risk_level = mission.get("risk_level") or "UNKNOWN"
    return "\n".join(
        [
            "Approved ECHO mission execution preview.",
            "",
            f"Mission ID: {mission_id}",
            f"Approval ID: {approval_id}",
            f"Title: {title}",
            f"Risk level: {risk_level}",
            "",
            "Objective:",
            str(objective),
            "",
            "Allowed files:",
            _format_list_for_prompt(mission.get("allowed_files")),
            "",
            "Forbidden files:",
            _format_list_for_prompt(mission.get("forbidden_files")),
            "",
            "Validation commands to run after implementation:",
            _format_list_for_prompt(mission.get("validation_commands")),
            "",
            "Safety rules:",
            "- Do not execute shell commands from the ECHO API.",
            "- Do not git push, git pull, deploy, or restart unless a later explicit approval allows it.",
            "- Do not modify TITAN runtime, broker, risk, execution, scanner, Master Brain, Unified Brain, or runtime workers unless the approved mission explicitly permits it.",
            "- Keep work limited to approved files and validation.",
        ]
    )


def build_execution_preview() -> dict[str, Any]:
    readiness = build_execution_readiness_report()
    mission_plan = _load_mission_plan()
    mission = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else {}
    if not isinstance(mission, dict):
        mission = {}

    readiness_status = readiness.get("status")
    blockers = list(readiness.get("blockers") or [])
    if readiness_status != "READY_DRY_RUN_ONLY":
        blockers.append("EXECUTION_READINESS_NOT_READY_DRY_RUN_ONLY")

    mission_id = readiness.get("mission_id") or mission.get("mission_id")
    approval_id = readiness.get("approval_id") or mission.get("approval_id")
    status = "PREVIEW_READY" if readiness_status == "READY_DRY_RUN_ONLY" and not blockers else "NOT_READY"
    proposed_command = (
        "PREVIEW ONLY - future command text after separate execution approval: "
        f"codex run --mission-id {mission_id or 'UNKNOWN'} --approval-id {approval_id or 'UNKNOWN'}"
    )

    preview = {
        "schema": "titan.echo.execution_preview.v1",
        "status": status,
        "mission_id": mission_id,
        "approval_id": approval_id,
        "readiness_status": readiness_status,
        "command_preview_only": True,
        "dry_run_only": True,
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "proposed_codex_prompt": _build_proposed_codex_prompt(mission, readiness),
        "proposed_codex_command_text": proposed_command,
        "blockers": blockers,
        "safety": {
            "preview_only": True,
            "command_preview_only": True,
            "dry_run_only": True,
            "codex_execution": False,
            "shell_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "titan_runtime_changed": False,
            "public_exposure_changed": False,
        },
        "source_files": {
            "mission_plan": _relative(MISSION_PLAN_PATH),
            "approval_queue": _relative(APPROVAL_QUEUE_PATH),
            "approved_missions": _relative(APPROVED_MISSIONS_PATH),
            "execution_readiness_report": _relative(EXECUTION_READINESS_REPORT_PATH),
        },
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(EXECUTION_PREVIEW_PATH, preview)
    return preview


def get_execution_preview() -> dict[str, Any]:
    preview = _read_json(EXECUTION_PREVIEW_PATH)
    if not isinstance(preview, dict):
        preview = build_execution_preview()
    return preview


def post_execution_preview_generate() -> dict[str, Any]:
    return build_execution_preview()


def post_mission_prepare(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    now = _timestamp_ist()
    title = str(body.get("title") or body.get("mission_title") or "Untitled ECHO mission").strip()
    objective = str(body.get("objective") or "").strip()
    risk_level = str(body.get("risk_level") or "MEDIUM").upper()
    if risk_level not in VALID_RISK_LEVELS:
        risk_level = "MEDIUM"
    allowed_files = _as_string_list(body.get("allowed_files"))
    forbidden_files = _as_string_list(body.get("forbidden_files"))
    validation_commands = _as_string_list(body.get("validation_commands"))
    mission_id = _stable_id("echo-mission", title, objective, risk_level, now)
    approval_id = _stable_id("echo-approval", mission_id, title, now)
    safety = {
        "execution_allowed": False,
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "broker_changed": False,
        "risk_changed": False,
        "execution_changed": False,
        "scanner_changed": False,
        "master_brain_changed": False,
        "unified_brain_changed": False,
        "runtime_workers_changed": False,
    }
    mission_record = {
        "mission_id": mission_id,
        "approval_id": approval_id,
        "title": title,
        "objective": objective,
        "risk_level": risk_level,
        "allowed_files": allowed_files,
        "forbidden_files": forbidden_files,
        "validation_commands": validation_commands,
        "approval_status": "PENDING",
        "created_at_ist": now,
        "prepared_by": "ECHO_API",
        "requires_ari_approval": True,
        "safety": safety,
    }
    mission_plan = {
        "schema": "titan.echo.mission_prepare_plan.v1",
        "timestamp_ist": now,
        "current_mission": mission_record,
        "approval_gate": "WAITING_FOR_ARI_APPROVAL",
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "forbidden_actions": [
            "Do not execute Codex.",
            "Do not run shell commands.",
            "Do not git push or pull.",
            "Do not deploy or restart.",
            "Do not touch broker/risk/execution/scanner/Master Brain/Unified Brain/runtime workers.",
        ],
        "safety": safety,
    }
    approval_record = {
        "approval_id": approval_id,
        "mission_id": mission_id,
        "timestamp_ist": now,
        "title": title,
        "objective": objective,
        "risk_level": risk_level,
        "status": "PENDING",
        "allowed_files": allowed_files,
        "forbidden_files": forbidden_files,
        "validation_commands": validation_commands,
        "requires_ari_approval": True,
        "approval_note": "",
        "decision_timestamp_ist": "",
        "safety": safety,
    }
    queue = _load_approval_queue()
    queue["approvals"].append(approval_record)
    _write_echo_json(MISSION_PLAN_PATH, mission_plan)
    _save_approval_queue(queue)
    return {
        "status": "PENDING",
        "mission_id": mission_id,
        "approval_id": approval_id,
        "mission_plan_path": _relative(MISSION_PLAN_PATH),
        "approval_queue_path": _relative(APPROVAL_QUEUE_PATH),
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "safety": safety,
    }


def _update_approval_decision(payload: dict[str, Any], decision: str) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    approval_id = str(body.get("approval_id") or "").strip()
    note = str(body.get("note") or "").strip()
    now = _timestamp_ist()
    safety = _decision_safety()
    if not approval_id:
        return {
            "status": "UNKNOWN_NOT_PROVEN",
            "reason": "APPROVAL_ID_REQUIRED",
            "approval_id": "",
            "execution_allowed": False,
            "codex_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "safety": safety,
        }

    queue = _load_approval_queue()
    approvals = [item for item in queue.get("approvals", []) if isinstance(item, dict)]
    matched: dict[str, Any] | None = None
    for item in approvals:
        if str(item.get("approval_id") or "") == approval_id:
            item["status"] = decision
            item["approval_note"] = note
            item["decision_timestamp_ist"] = now
            item["execution_allowed"] = False
            item["codex_execution"] = False
            item["git_push_pull"] = False
            item["deploy_or_restart"] = False
            item["safety"] = safety
            matched = item
            break

    if matched is None:
        return {
            "status": "UNKNOWN_NOT_PROVEN",
            "reason": "APPROVAL_ID_NOT_FOUND",
            "approval_id": approval_id,
            "execution_allowed": False,
            "codex_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "safety": safety,
        }

    queue["approvals"] = approvals
    _save_approval_queue(queue)

    mission_plan = _load_mission_plan()
    current = mission_plan.get("current_mission") if isinstance(mission_plan.get("current_mission"), dict) else None
    if current and str(current.get("approval_id") or "") == approval_id:
        current["approval_status"] = decision
        current["approval_note"] = note
        current["decision_timestamp_ist"] = now
        current["safety"] = safety
        mission_plan["current_mission"] = current
        mission_plan["approval_gate"] = f"ARI_{decision}"
        mission_plan["timestamp_ist"] = now
        mission_plan["execution_allowed"] = False
        mission_plan["codex_execution"] = False
        mission_plan["git_push_pull"] = False
        mission_plan["deploy_or_restart"] = False
        mission_plan["safety"] = safety
        _write_echo_json(MISSION_PLAN_PATH, mission_plan)

    history_record = {
        "history_event": decision,
        "approval_id": approval_id,
        "mission_id": matched.get("mission_id"),
        "approval_note": note,
        "decision_timestamp_ist": now,
        "approval_record": matched,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "safety": safety,
    }
    _append_echo_jsonl(APPROVAL_HISTORY_PATH, history_record)
    if decision == "APPROVED":
        _append_mission_decision(APPROVED_MISSIONS_PATH, decision, matched, mission_plan)
        decision_collection_path = APPROVED_MISSIONS_PATH
    else:
        _append_mission_decision(REJECTED_MISSIONS_PATH, decision, matched, mission_plan)
        decision_collection_path = REJECTED_MISSIONS_PATH

    return {
        "status": decision,
        "approval_id": approval_id,
        "mission_id": matched.get("mission_id"),
        "approval_note": note,
        "decision_timestamp_ist": now,
        "approval_queue_path": _relative(APPROVAL_QUEUE_PATH),
        "mission_plan_path": _relative(MISSION_PLAN_PATH),
        "approval_history_path": _relative(APPROVAL_HISTORY_PATH),
        "decision_collection_path": _relative(decision_collection_path),
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "safety": safety,
    }


def post_approval_approve(payload: dict[str, Any]) -> dict[str, Any]:
    return _update_approval_decision(payload, "APPROVED")


def post_approval_reject(payload: dict[str, Any]) -> dict[str, Any]:
    return _update_approval_decision(payload, "REJECTED")


# Compatibility aliases for existing local imports and FastAPI route names.
health = get_health
status = get_status
projects = get_projects
unified_brain = get_unified_brain
lineage = get_lineage
alerts = get_alerts
missions = get_missions
answer = get_answer
query = get_query
approval_pending = get_approval_pending
mission_current = get_mission_current
verification_latest = get_verification_latest
execution_readiness = get_execution_readiness
execution_readiness_check = post_execution_readiness_check
execution_preview = get_execution_preview
execution_preview_generate = post_execution_preview_generate
mission_prepare = post_mission_prepare
approval_approve = post_approval_approve
approval_reject = post_approval_reject


app = None
if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="ECHO Read-Only API",
        version="0.2.0",
        description="Read-only local ECHO API for existing TITAN evidence files.",
    )
    auth_dependency = [Depends(require_echo_api_key)]
    app.get("/health")(get_health)
    app.get("/status", dependencies=auth_dependency)(get_status)
    app.get("/projects", dependencies=auth_dependency)(get_projects)
    app.get("/unified-brain", dependencies=auth_dependency)(get_unified_brain)
    app.get("/lineage", dependencies=auth_dependency)(get_lineage)
    app.get("/alerts", dependencies=auth_dependency)(get_alerts)
    app.get("/missions", dependencies=auth_dependency)(get_missions)
    app.get("/answer", dependencies=auth_dependency)(get_answer)
    app.get("/query", dependencies=auth_dependency)(get_query)
    app.get("/approval/pending", dependencies=auth_dependency)(get_approval_pending)
    app.get("/mission/current", dependencies=auth_dependency)(get_mission_current)
    app.get("/verification/latest", dependencies=auth_dependency)(get_verification_latest)
    app.get("/execution/readiness", dependencies=auth_dependency)(get_execution_readiness)
    app.get("/execution/preview", dependencies=auth_dependency)(get_execution_preview)
    app.post("/mission/prepare", dependencies=auth_dependency)(post_mission_prepare)
    app.post("/approval/approve", dependencies=auth_dependency)(post_approval_approve)
    app.post("/approval/reject", dependencies=auth_dependency)(post_approval_reject)
    app.post("/execution/readiness/check", dependencies=auth_dependency)(post_execution_readiness_check)
    app.post("/execution/preview/generate", dependencies=auth_dependency)(post_execution_preview_generate)


__all__ = [
    "FASTAPI_AVAILABLE",
    "app",
    "get_health",
    "get_status",
    "get_projects",
    "get_unified_brain",
    "get_lineage",
    "get_alerts",
    "get_missions",
    "get_answer",
    "get_query",
    "get_approval_pending",
    "get_mission_current",
    "get_verification_latest",
    "get_execution_readiness",
    "post_execution_readiness_check",
    "get_execution_preview",
    "post_execution_preview_generate",
    "post_mission_prepare",
    "post_approval_approve",
    "post_approval_reject",
    "health",
    "status",
    "projects",
    "unified_brain",
    "lineage",
    "alerts",
    "missions",
    "answer",
    "query",
    "approval_pending",
    "mission_current",
    "verification_latest",
    "execution_readiness",
    "execution_readiness_check",
    "execution_preview",
    "execution_preview_generate",
    "mission_prepare",
    "approval_approve",
    "approval_reject",
]
