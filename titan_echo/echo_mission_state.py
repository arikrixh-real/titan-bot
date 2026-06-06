"""Durable ECHO mission state and evidence storage."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
MISSIONS_DIR = ECHO_DIR / "missions"
EVIDENCE_DIR = ECHO_DIR / "evidence"

MISSION_STATUSES = (
    "CREATED",
    "APPROVAL_REQUIRED",
    "APPROVED",
    "CODEX_RUNNING",
    "CODEX_DONE",
    "VERIFY_RUNNING",
    "VERIFY_DONE",
    "COMMIT_READY",
    "COMMITTED",
    "PUSHED",
    "PULLED",
    "REPORTED",
    "FAILED",
    "BLOCKED",
)

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "CREATED": ("APPROVAL_REQUIRED",),
    "APPROVAL_REQUIRED": ("APPROVED", "BLOCKED"),
    "APPROVED": ("CODEX_RUNNING", "BLOCKED"),
    "CODEX_RUNNING": ("CODEX_DONE", "FAILED"),
    "CODEX_DONE": ("VERIFY_RUNNING", "BLOCKED"),
    "VERIFY_RUNNING": ("VERIFY_DONE", "FAILED"),
    "VERIFY_DONE": ("COMMIT_READY", "FAILED"),
    "COMMIT_READY": ("COMMITTED", "BLOCKED", "FAILED"),
    "COMMITTED": ("PUSHED", "BLOCKED", "FAILED"),
    "PUSHED": ("PULLED", "BLOCKED", "FAILED"),
    "PULLED": ("REPORTED", "BLOCKED", "FAILED"),
    "REPORTED": (),
    "FAILED": (),
    "BLOCKED": ("APPROVAL_REQUIRED", "APPROVED", "CODEX_DONE", "VERIFY_DONE", "COMMIT_READY", "COMMITTED", "PUSHED", "PULLED", "FAILED"),
}

MISSION_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
INTAKE_SCOPE_ALLOWLIST = ("echo_only", "diagnostics_status_only", "harmless_dry_run")
INTAKE_REQUIRED_FIELDS = ("approved_by", "approval_id", "title", "instructions", "execution_scope", "dry_run")
INTAKE_COMMAND_FIELDS = (
    "command",
    "shell_command",
    "subprocess",
    "codex_command",
    "verify_command",
    "git_command",
    "runner_command",
)
INTAKE_UNSAFE_TERMS = (
    "trading",
    "trade",
    "broker",
    "risk",
    "scanner",
    "setup_engine",
    "setup engine",
    "trade_journal",
    "trade journal",
    "outcome_tracker",
    "outcome tracker",
    "master_brain",
    "master brain",
    "execution mutation",
    "execution_mutation",
    "live order",
    "place order",
)


class MissionStateError(ValueError):
    """Raised when a mission state operation fails closed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def valid_mission_id(mission_id: str | None) -> bool:
    return bool(mission_id and MISSION_ID_RE.fullmatch(mission_id))


def _ensure_echo_path(path: Path) -> Path:
    resolved_root = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_root not in (resolved_path, *resolved_path.parents):
        raise MissionStateError("echo mission writes only under data/runtime/echo")
    return path


def mission_path(mission_id: str) -> Path:
    if not valid_mission_id(mission_id):
        raise MissionStateError("invalid mission_id")
    return _ensure_echo_path(MISSIONS_DIR / f"{mission_id}.json")


def evidence_path(mission_id: str) -> Path:
    if not valid_mission_id(mission_id):
        raise MissionStateError("invalid mission_id")
    return _ensure_echo_path(EVIDENCE_DIR / f"{mission_id}.jsonl")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_echo_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def new_mission_id() -> str:
    return f"echo-{uuid.uuid4().hex[:16]}"


def create_mission_state(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    requested_id = str(body.get("mission_id") or "").strip()
    mission_id = requested_id or new_mission_id()
    if not valid_mission_id(mission_id):
        return fail_closed(mission_id, "INVALID_MISSION_ID")

    approval_id = f"approval-{uuid.uuid4().hex[:16]}"
    now = utc_now()
    state = {
        "schema": "titan.echo.mission_state.v2",
        "mission_id": mission_id,
        "status": "CREATED",
        "created_at": now,
        "updated_at": now,
        "objective": str(body.get("objective") or body.get("mission") or body.get("title") or "").strip(),
        "approval_id": approval_id,
        "approved_at": "",
        "last_step": "create",
        "next_step": "approve",
        "history": [{"timestamp": now, "from": "", "to": "CREATED", "step": "create"}],
        "files_touched": [],
        "error": "",
    }
    save_mission_state(state)
    transition_state(state, "APPROVAL_REQUIRED", step="create", action="approval required")
    return state


def create_approved_intake_mission(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    validation = validate_intake_payload(body)
    if not validation["allowed"]:
        return fail_closed(str(body.get("mission_id") or ""), validation["reason"])

    requested_id = str(body.get("mission_id") or "").strip()
    mission_id = requested_id or new_mission_id()
    if not valid_mission_id(mission_id):
        return fail_closed(mission_id, "INVALID_MISSION_ID")

    now = utc_now()
    approval_id = str(body.get("approval_id") or "").strip()
    title = str(body.get("title") or "").strip()
    instructions = str(body.get("instructions") or "").strip()
    execution_scope = str(body.get("execution_scope") or "").strip()
    approved_by = str(body.get("approved_by") or "").strip()
    dry_run = bool(body.get("dry_run"))

    state = {
        "schema": "titan.echo.mission_state.v2",
        "mission_id": mission_id,
        "status": "APPROVED",
        "created_at": now,
        "updated_at": now,
        "title": title,
        "objective": title,
        "instructions": instructions,
        "execution_scope": execution_scope,
        "dry_run": dry_run,
        "execution_allowed": True,
        "approval_id": approval_id,
        "approved_at": now,
        "approval": {
            "approved_by": approved_by,
            "approval_id": approval_id,
            "approved_at": now,
            "source": "relay_mission_intake_approved",
        },
        "last_step": "intake",
        "next_step": "codex",
        "files": ["titan_echo/"],
        "files_touched": [],
        "history": [{"timestamp": now, "from": "", "to": "APPROVED", "step": "intake", "action": "approved intake"}],
        "error": "",
        "safety": {
            "echo_only": True,
            "direct_codex_call": False,
            "direct_git_command": False,
            "arbitrary_subprocess_command": False,
            "runner_trigger_command": "sudo systemctl start titan-echo-runner",
            "scope_allowlist": list(INTAKE_SCOPE_ALLOWLIST),
        },
    }
    save_mission_state(state)
    append_evidence(
        mission_id,
        step="intake",
        status="APPROVED",
        command="mission intake approved",
        return_code=0,
        stdout_tail=f"approved_by={approved_by}; execution_scope={execution_scope}; dry_run={dry_run}",
        files_touched=[f"data/runtime/echo/missions/{mission_id}.json"],
    )
    return state


def validate_intake_payload(payload: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in INTAKE_REQUIRED_FIELDS if field not in payload or payload.get(field) in ("", None)]
    if missing:
        return {"allowed": False, "reason": "MISSING_APPROVAL_FIELDS", "missing": missing}
    if not isinstance(payload.get("dry_run"), bool):
        return {"allowed": False, "reason": "DRY_RUN_BOOL_REQUIRED"}

    command_fields = [field for field in INTAKE_COMMAND_FIELDS if field in payload]
    if command_fields:
        return {"allowed": False, "reason": "ARBITRARY_COMMAND_NOT_ALLOWED", "fields": command_fields}

    scope = str(payload.get("execution_scope") or "").strip()
    if scope not in INTAKE_SCOPE_ALLOWLIST:
        return {"allowed": False, "reason": "UNSAFE_SCOPE", "allowed_scopes": list(INTAKE_SCOPE_ALLOWLIST)}

    scope_text = " ".join(
        str(payload.get(key) or "")
        for key in ("execution_scope", "title", "instructions")
    ).lower()
    hits = [term for term in INTAKE_UNSAFE_TERMS if term in scope_text]
    if hits:
        return {"allowed": False, "reason": "TRADING_OR_PROTECTED_SCOPE_BLOCKED", "hits": hits}

    return {"allowed": True, "reason": "SCOPE_ALLOWED", "allowed_scopes": list(INTAKE_SCOPE_ALLOWLIST)}


def load_mission_state(mission_id: str | None) -> dict[str, Any]:
    if not valid_mission_id(str(mission_id or "")):
        return {}
    return _read_json(mission_path(str(mission_id)))


def save_mission_state(state: dict[str, Any]) -> dict[str, Any]:
    mission_id = str(state.get("mission_id") or "")
    if not valid_mission_id(mission_id):
        raise MissionStateError("invalid mission_id")
    state["updated_at"] = utc_now()
    _write_json(mission_path(mission_id), state)
    return state


def transition_state(
    state: dict[str, Any],
    target_status: str,
    *,
    step: str,
    action: str,
    error: str = "",
) -> dict[str, Any]:
    current = str(state.get("status") or "")
    if target_status not in MISSION_STATUSES:
        raise MissionStateError(f"unknown target status: {target_status}")
    if target_status not in TRANSITIONS.get(current, ()):
        raise MissionStateError(f"invalid transition {current}->{target_status}")
    now = utc_now()
    state["status"] = target_status
    state["last_step"] = step
    state["error"] = error
    state["updated_at"] = now
    state.setdefault("history", []).append(
        {"timestamp": now, "from": current, "to": target_status, "step": step, "action": action, "error": error}
    )
    return save_mission_state(state)


def fail_closed(mission_id: str | None, reason: str) -> dict[str, Any]:
    return {
        "schema": "titan.echo.mission_state.v2",
        "status": "FAILED",
        "mission_id": mission_id or "",
        "error": reason,
        "execution_performed": False,
    }


def append_evidence(
    mission_id: str,
    *,
    step: str,
    status: str,
    command: str,
    return_code: int | None = None,
    stdout_tail: str = "",
    stderr_tail: str = "",
    files_touched: list[str] | None = None,
    error: str = "",
) -> dict[str, Any]:
    record = {
        "timestamp": utc_now(),
        "mission_id": mission_id,
        "step": step,
        "status": status,
        "command": command,
        "action": command,
        "return_code": return_code,
        "stdout_tail": stdout_tail[-4000:],
        "stderr_tail": stderr_tail[-4000:],
        "files_touched": list(files_touched or [])[:200],
        "error": error,
    }
    path = evidence_path(mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read_evidence(mission_id: str) -> list[dict[str, Any]]:
    if not valid_mission_id(mission_id):
        return []
    path = evidence_path(mission_id)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


__all__ = [
    "ECHO_DIR",
    "EVIDENCE_DIR",
    "MISSION_STATUSES",
    "MISSIONS_DIR",
    "MissionStateError",
    "append_evidence",
    "create_approved_intake_mission",
    "create_mission_state",
    "evidence_path",
    "fail_closed",
    "load_mission_state",
    "mission_path",
    "read_evidence",
    "save_mission_state",
    "transition_state",
    "validate_intake_payload",
    "valid_mission_id",
]
