"""Persistent ECHO mission brain and rollback state.

The mission brain is an approval-gated state machine. It persists mission
state, journals every transition, and records evidence, but it does not run
Codex, git push/pull, deploy, broker, scanner, risk, or runtime workers.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from titan_echo.echo_relay_config import relay_safety


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
MISSIONS_DIR = ECHO_DIR / "missions"
ROLLBACK_DIR = ECHO_DIR / "rollback"
IST = timezone(timedelta(hours=5, minutes=30))

PHASES = [
    "MISSION_CREATED",
    "PLAN_READY",
    "APPROVAL_WAITING",
    "CODEX_READY",
    "CODEX_RUNNING",
    "TEST_RUNNING",
    "COMMIT_READY",
    "PUSH_READY",
    "VPS_PULL_READY",
    "VERIFY_RUNNING",
    "REPORT_READY",
    "COMPLETE",
    "FAILED",
    "ROLLED_BACK",
]

STEP_ORDER = ["codex", "test", "commit", "push", "vps_pull", "verify", "report"]
STEP_PHASE = {
    "codex": "CODEX_RUNNING",
    "test": "TEST_RUNNING",
    "commit": "COMMIT_READY",
    "push": "PUSH_READY",
    "vps_pull": "VPS_PULL_READY",
    "verify": "VERIFY_RUNNING",
    "report": "REPORT_READY",
}


def _now() -> str:
    return datetime.now(IST).isoformat()


def _safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    resolved_root = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_root not in (resolved_path, *resolved_path.parents):
        raise ValueError("ECHO mission brain writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    resolved_root = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_root not in (resolved_path, *resolved_path.parents):
        raise ValueError("ECHO mission brain writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _mission_dir(mission_id: str) -> Path:
    return MISSIONS_DIR / mission_id


def _state_path(mission_id: str) -> Path:
    return _mission_dir(mission_id) / "state.json"


def _journal_path(mission_id: str) -> Path:
    return _mission_dir(mission_id) / "journal.jsonl"


def _evidence_path(mission_id: str, step: str) -> Path:
    return _mission_dir(mission_id) / "evidence" / f"{step}.json"


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _git_output(args: list[str], timeout: int = 10) -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return "", f"{type(exc).__name__}:{exc}"
    if result.returncode != 0:
        return "", (result.stderr or result.stdout).strip()
    return result.stdout.strip(), ""


def _pre_mission_commit() -> str:
    stdout, _ = _git_output(["rev-parse", "HEAD"])
    return stdout


def _changed_files() -> list[str]:
    stdout, _ = _git_output(["status", "--short"])
    files: list[str] = []
    for line in stdout.splitlines():
        item = line[3:].strip() if len(line) > 3 else line.strip()
        if item:
            files.append(item.replace("\\", "/"))
    return files[:200]


def _compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    if not evidence:
        return {"present": False}
    return {
        "present": True,
        "step": evidence.get("step"),
        "status": evidence.get("status"),
        "evidence_path": evidence.get("evidence_path"),
        "execution_performed": bool(evidence.get("execution_performed")),
        "blocked_reason": evidence.get("blocked_reason"),
    }


def _pending_approval(state: dict[str, Any]) -> dict[str, Any]:
    approvals = state.get("approvals") if isinstance(state.get("approvals"), dict) else {}
    step = str(state.get("current_step") or "")
    item = approvals.get(step) if isinstance(approvals, dict) else None
    return item if isinstance(item, dict) else {}


def _approvals_remaining(state: dict[str, Any]) -> list[str]:
    approvals = state.get("approvals") if isinstance(state.get("approvals"), dict) else {}
    remaining = []
    if isinstance(approvals, dict):
        for step in STEP_ORDER:
            item = approvals.get(step)
            if isinstance(item, dict) and item.get("status") == "PENDING":
                remaining.append(str(item.get("approval_id") or step))
    return remaining


def _safety() -> dict[str, bool]:
    safety = relay_safety()
    safety.update(
        {
            "mission_persisted": True,
            "get_executes": False,
            "broker_execution": False,
            "automatic_reset_revert": False,
            "uncontrolled_self_modification": False,
        }
    )
    return safety


def _progress(state: dict[str, Any]) -> int:
    completed = state.get("completed_steps")
    count = len(completed) if isinstance(completed, list) else 0
    if state.get("phase") == "COMPLETE":
        return 100
    return min(99, int((count / len(STEP_ORDER)) * 100))


def compact_contract(state: dict[str, Any], status: str | None = None) -> dict[str, Any]:
    latest = state.get("latest_evidence") if isinstance(state.get("latest_evidence"), dict) else {}
    return {
        "status": status or state.get("status") or "MISSION_STATE_PRESENT",
        "mission_id": state.get("mission_id"),
        "phase": state.get("phase"),
        "progress_percent": _progress(state),
        "current_step": state.get("current_step"),
        "blocked_reason": state.get("blocked_reason") or "",
        "approvals_remaining": _approvals_remaining(state),
        "latest_evidence": _compact_evidence(latest),
        "next_step": state.get("next_step") or "",
        "safety": _safety(),
    }


def _save_state(state: dict[str, Any], event: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    state["updated_at_ist"] = _now()
    _safe_write_json(_state_path(str(state["mission_id"])), state)
    _append_jsonl(
        _journal_path(str(state["mission_id"])),
        {
            "timestamp_ist": state["updated_at_ist"],
            "event": event,
            "mission_id": state["mission_id"],
            "phase": state.get("phase"),
            "current_step": state.get("current_step"),
            "detail": detail or {},
        },
    )
    _safe_write_json(MISSIONS_DIR / "current_mission.json", state)
    return state


def load_mission(mission_id: str | None = None) -> dict[str, Any]:
    if mission_id:
        return _read_json(_state_path(mission_id))
    return _read_json(MISSIONS_DIR / "current_mission.json")


def _new_approval(mission_id: str, step: str) -> dict[str, Any]:
    now = _now()
    return {
        "approval_id": _stable_id("approval", mission_id, step, now),
        "step": step,
        "status": "PENDING",
        "created_at_ist": now,
        "approved_at_ist": "",
        "requires_explicit_operator_approval": True,
    }


def _set_waiting_for_step(state: dict[str, Any], step: str, reason: str) -> None:
    approvals = state.setdefault("approvals", {})
    if not isinstance(approvals, dict):
        approvals = {}
        state["approvals"] = approvals
    if not isinstance(approvals.get(step), dict) or approvals[step].get("status") != "PENDING":
        approvals[step] = _new_approval(str(state["mission_id"]), step)
    state["phase"] = "APPROVAL_WAITING"
    state["current_step"] = step
    state["blocked_reason"] = reason
    state["next_step"] = f"Approve step '{step}' with POST /relay/mission/approve-step."


def create_mission(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    title = str(body.get("title") or body.get("mission") or "ECHO mission").strip()
    objective = str(body.get("objective") or body.get("summary") or title).strip()
    created = _now()
    mission_id = str(body.get("mission_id") or "").strip() or _stable_id("echo-mission", title, objective, created)
    state = {
        "schema": "titan.echo.mission_state.v1",
        "mission_id": mission_id,
        "created_at_ist": created,
        "updated_at_ist": created,
        "title": title,
        "objective": objective,
        "phase": "MISSION_CREATED",
        "status": "MISSION_CREATED",
        "current_step": "plan",
        "last_completed_step": "",
        "completed_steps": [],
        "blocked_reason": "",
        "blockers": [],
        "approvals": {},
        "latest_evidence": {},
        "pre_mission_commit": _pre_mission_commit(),
        "changed_files": _changed_files(),
        "test_evidence": {},
        "pushed_commit_hash": "",
        "rollback_requested": False,
        "next_step": "Mission plan is ready; approve codex step to continue.",
        "phases": PHASES,
        "step_order": STEP_ORDER,
        "continuity": {
            "state_path": str(_state_path(mission_id).relative_to(REPO_ROOT)).replace("\\", "/"),
            "journal_path": str(_journal_path(mission_id).relative_to(REPO_ROOT)).replace("\\", "/"),
            "evidence_dir": str((_mission_dir(mission_id) / "evidence").relative_to(REPO_ROOT)).replace("\\", "/"),
            "survives_api_restart": True,
            "survives_relay_restart": True,
            "survives_vps_disconnect": True,
            "survives_pc_off_then_resume": True,
        },
    }
    _save_state(state, "MISSION_CREATED")
    state["phase"] = "PLAN_READY"
    state["status"] = "PLAN_READY"
    _save_state(state, "PLAN_READY", {"plan": STEP_ORDER})
    _set_waiting_for_step(state, "codex", "APPROVAL_REQUIRED_CODEX")
    state["status"] = "APPROVAL_WAITING"
    _save_state(state, "APPROVAL_WAITING", {"approval": _pending_approval(state)})
    return compact_contract(state)


def mission_status(mission_id: str | None = None) -> dict[str, Any]:
    state = load_mission(mission_id)
    if not state:
        return {
            "status": "MISSION_NOT_FOUND",
            "mission_id": mission_id,
            "phase": "FAILED",
            "progress_percent": 0,
            "current_step": "",
            "blocked_reason": "MISSION_STATE_NOT_FOUND",
            "approvals_remaining": [],
            "latest_evidence": {"present": False},
            "next_step": "Create a mission with POST /relay/mission/create.",
            "safety": _safety(),
        }
    return compact_contract(state, "MISSION_STATE_PRESENT")


def approve_step(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    mission_id = str(body.get("mission_id") or "").strip()
    step = str(body.get("step") or "").strip().lower()
    approval_id = str(body.get("approval_id") or "").strip()
    if not mission_id:
        return mission_status(None) | {"status": "APPROVAL_BLOCKED", "blocked_reason": "mission_id required"}
    state = load_mission(mission_id)
    if not state:
        return mission_status(mission_id)
    step = step or str(state.get("current_step") or "")
    approval = _pending_approval(state)
    if step != state.get("current_step"):
        return compact_contract(state, "APPROVAL_BLOCKED") | {"blocked_reason": "STEP_NOT_CURRENT"}
    if approval_id and approval_id != approval.get("approval_id"):
        return compact_contract(state, "APPROVAL_BLOCKED") | {"blocked_reason": "APPROVAL_ID_MISMATCH"}
    approvals = state.setdefault("approvals", {})
    approvals[step] = {**approval, "status": "APPROVED", "approved_at_ist": _now(), "note": str(body.get("note") or "")}
    state["blocked_reason"] = ""
    state["next_step"] = f"Resume mission to run approved step '{step}'."
    state["status"] = "APPROVAL_RECORDED"
    _save_state(state, "APPROVAL_RECORDED", {"step": step, "approval_id": approvals[step].get("approval_id")})
    return compact_contract(state, "APPROVAL_RECORDED")


def _record_step_evidence(state: dict[str, Any], step: str, status: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    mission_id = str(state["mission_id"])
    evidence_path = _evidence_path(mission_id, step)
    evidence = {
        "schema": "titan.echo.mission_step_evidence.v1",
        "mission_id": mission_id,
        "step": step,
        "status": status,
        "phase": STEP_PHASE.get(step, state.get("phase")),
        "execution_performed": False,
        "generated_at_ist": _now(),
        "evidence_path": str(evidence_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "safety": _safety(),
    }
    evidence.update(extra or {})
    _safe_write_json(evidence_path, evidence)
    state["latest_evidence"] = evidence
    if step == "test":
        state["test_evidence"] = evidence
    if step == "push":
        state["pushed_commit_hash"] = _pre_mission_commit()
    state["changed_files"] = _changed_files()
    return evidence


def _complete_step(state: dict[str, Any], step: str, evidence: dict[str, Any]) -> None:
    completed = state.setdefault("completed_steps", [])
    if step not in completed:
        completed.append(step)
    state["last_completed_step"] = step
    next_index = STEP_ORDER.index(step) + 1
    if next_index >= len(STEP_ORDER):
        state["phase"] = "COMPLETE"
        state["status"] = "COMPLETE"
        state["current_step"] = "complete"
        state["blocked_reason"] = ""
        state["next_step"] = "Mission complete. Compact report is ready."
        return
    _set_waiting_for_step(state, STEP_ORDER[next_index], f"APPROVAL_REQUIRED_{STEP_ORDER[next_index].upper()}")
    state["status"] = "APPROVAL_WAITING"


def resume_mission(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    mission_id = str(body.get("mission_id") or "").strip()
    state = load_mission(mission_id or None)
    if not state:
        return mission_status(mission_id or None)
    step = str(state.get("current_step") or "")
    if step not in STEP_ORDER:
        return compact_contract(state, "MISSION_NOOP")
    approval = _pending_approval(state)
    if approval.get("status") != "APPROVED":
        state["phase"] = "APPROVAL_WAITING"
        state["status"] = "BLOCKED_APPROVAL_REQUIRED"
        state["blocked_reason"] = f"APPROVAL_REQUIRED_{step.upper()}"
        state["next_step"] = f"Approve step '{step}' before resume."
        _save_state(state, "RESUME_BLOCKED_APPROVAL_REQUIRED", {"step": step, "approval": approval})
        return compact_contract(state, "BLOCKED_APPROVAL_REQUIRED")

    state["phase"] = STEP_PHASE[step]
    state["status"] = f"{step.upper()}_RECORDED"
    evidence_extra = {
        "approval_id": approval.get("approval_id"),
        "changed_files": _changed_files(),
        "pre_mission_commit": state.get("pre_mission_commit"),
    }
    if step == "report":
        evidence_extra["report"] = {
            "mission_id": state.get("mission_id"),
            "completed_steps": state.get("completed_steps", []),
            "test_evidence_present": bool(state.get("test_evidence")),
            "pushed_commit_hash": state.get("pushed_commit_hash") or "",
            "rollback_available": True,
        }
    evidence = _record_step_evidence(state, step, f"{step.upper()}_EVIDENCE_RECORDED", evidence_extra)
    _complete_step(state, step, evidence)
    _save_state(state, f"{step.upper()}_COMPLETED", {"evidence": evidence})
    return compact_contract(state, state.get("status"))


def rollback_status(mission_id: str | None = None) -> dict[str, Any]:
    state = load_mission(mission_id)
    request_state = _read_json(ROLLBACK_DIR / "rollback_request.json")
    return {
        "status": "ROLLBACK_STATUS_PRESENT",
        "mission_id": state.get("mission_id") or mission_id,
        "phase": state.get("phase") or "ROLLBACK_STATUS",
        "progress_percent": _progress(state) if state else 0,
        "current_step": "rollback",
        "blocked_reason": request_state.get("blocked_reason") or "ROLLBACK_REQUIRES_EXPLICIT_APPROVAL",
        "approvals_remaining": [request_state.get("approval_id")] if request_state.get("status") == "ROLLBACK_APPROVAL_WAITING" else [],
        "latest_evidence": {
            "present": bool(request_state),
            "status": request_state.get("status"),
            "pre_mission_commit": state.get("pre_mission_commit") or "",
            "changed_files_count": len(state.get("changed_files") or []),
            "pushed_commit_hash": state.get("pushed_commit_hash") or "",
        },
        "next_step": "Use POST /relay/rollback/request, then POST /relay/rollback/run-approved after explicit approval.",
        "safety": _safety(),
    }


def rollback_request(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    mission_id = str(body.get("mission_id") or "").strip()
    state = load_mission(mission_id or None)
    approval_id = _stable_id("rollback-approval", mission_id or state.get("mission_id"), _now())
    request_state = {
        "schema": "titan.echo.rollback_request.v1",
        "status": "ROLLBACK_APPROVAL_WAITING",
        "mission_id": state.get("mission_id") or mission_id,
        "approval_id": approval_id,
        "pre_mission_commit": state.get("pre_mission_commit") or "",
        "changed_files": state.get("changed_files") or [],
        "test_evidence": state.get("test_evidence") or {},
        "pushed_commit_hash": state.get("pushed_commit_hash") or "",
        "blocked_reason": "ROLLBACK_REQUIRES_EXPLICIT_APPROVAL",
        "execution_performed": False,
        "automatic_reset_revert": False,
        "generated_at_ist": _now(),
        "safety": _safety(),
    }
    _safe_write_json(ROLLBACK_DIR / "rollback_request.json", request_state)
    if state:
        state["rollback_requested"] = True
        _save_state(state, "ROLLBACK_REQUESTED", {"approval_id": approval_id})
    return rollback_status(str(request_state.get("mission_id") or ""))


def rollback_run_approved(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    request_state = _read_json(ROLLBACK_DIR / "rollback_request.json")
    approval_id = str(body.get("approval_id") or "").strip()
    confirm = str(body.get("confirm") or "").strip()
    if not request_state:
        return rollback_status(str(body.get("mission_id") or "")) | {"status": "ROLLBACK_BLOCKED", "blocked_reason": "ROLLBACK_REQUEST_NOT_FOUND"}
    if approval_id != request_state.get("approval_id"):
        return rollback_status(str(request_state.get("mission_id") or "")) | {"status": "ROLLBACK_BLOCKED", "blocked_reason": "APPROVAL_ID_MISMATCH"}
    if confirm != "I_APPROVE_ROLLBACK":
        return rollback_status(str(request_state.get("mission_id") or "")) | {"status": "ROLLBACK_BLOCKED", "blocked_reason": "confirm must be I_APPROVE_ROLLBACK"}
    request_state["status"] = "ROLLBACK_APPROVED_MANUAL_ACTION_REQUIRED"
    request_state["blocked_reason"] = "NO_AUTOMATIC_RESET_REVERT_OPERATOR_MUST_RUN_MANUAL_RECOVERY"
    request_state["approved_at_ist"] = _now()
    request_state["execution_performed"] = False
    _safe_write_json(ROLLBACK_DIR / "rollback_request.json", request_state)
    state = load_mission(str(request_state.get("mission_id") or ""))
    if state:
        _save_state(state, "ROLLBACK_APPROVED_RECORD_ONLY", {"approval_id": approval_id})
    return rollback_status(str(request_state.get("mission_id") or "")) | {"status": "ROLLBACK_APPROVED_MANUAL_ACTION_REQUIRED"}


__all__ = [
    "PHASES",
    "STEP_ORDER",
    "approve_step",
    "compact_contract",
    "create_mission",
    "load_mission",
    "mission_status",
    "resume_mission",
    "rollback_request",
    "rollback_run_approved",
    "rollback_status",
]
