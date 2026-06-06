"""Strict ECHO mission lifecycle runner."""

from __future__ import annotations

from typing import Any

from titan_echo.echo_mission_state import (
    MissionStateError,
    append_evidence,
    create_mission_state,
    fail_closed,
    load_mission_state,
    read_evidence,
    save_mission_state,
    transition_state,
    valid_mission_id,
)


APPROVAL_CONFIRM = "I_APPROVE_ECHO_MISSION"

STEP_RULES: dict[str, dict[str, Any]] = {
    "codex": {
        "from": "APPROVED",
        "running": "CODEX_RUNNING",
        "done": "CODEX_DONE",
        "next": "verify",
        "command": "codex",
    },
    "verify": {
        "from": "CODEX_DONE",
        "running": "VERIFY_RUNNING",
        "done": "VERIFY_DONE",
        "after_done": "COMMIT_READY",
        "next": "commit",
        "command": "verify",
    },
    "commit": {
        "from": "COMMIT_READY",
        "done": "COMMITTED",
        "next": "push",
        "command": "git commit",
    },
    "push": {
        "from": "COMMITTED",
        "done": "PUSHED",
        "next": "pull",
        "command": "git push",
    },
    "pull": {
        "from": "PUSHED",
        "done": "PULLED",
        "next": "report",
        "command": "git pull",
    },
    "report": {
        "from": "PULLED",
        "done": "REPORTED",
        "next": "",
        "command": "report",
    },
}


def _blocked(mission_id: str | None, reason: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "schema": "titan.echo.mission_runner.v1",
        "status": "BLOCKED",
        "mission_id": mission_id or "",
        "reason": reason,
        "execution_performed": False,
    }
    if state:
        payload["mission_status"] = state.get("status")
        payload["next_step"] = state.get("next_step")
    return payload


def create_mission(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return create_mission_state(payload or {})


def approve_mission(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    mission_id = str(body.get("mission_id") or "").strip()
    if not valid_mission_id(mission_id):
        return fail_closed(mission_id, "INVALID_MISSION_ID")
    state = load_mission_state(mission_id)
    if not state:
        return fail_closed(mission_id, "MISSION_NOT_FOUND")
    if state.get("status") != "APPROVAL_REQUIRED":
        return _blocked(mission_id, "MISSION_NOT_WAITING_FOR_APPROVAL", state)
    if str(body.get("approval_id") or "").strip() != state.get("approval_id"):
        return _blocked(mission_id, "APPROVAL_ID_MISMATCH", state)
    if str(body.get("confirm") or "").strip() != APPROVAL_CONFIRM:
        return _blocked(mission_id, "INVALID_APPROVAL_CONFIRM", state)

    state["approved_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    state["next_step"] = "codex"
    try:
        state = transition_state(state, "APPROVED", step="approve", action="operator approval")
    except MissionStateError as exc:
        return fail_closed(mission_id, str(exc))
    append_evidence(
        mission_id,
        step="approve",
        status="APPROVED",
        command="operator approval",
        files_touched=[],
    )
    return state


def mission_status(mission_id: str | None) -> dict[str, Any]:
    if not valid_mission_id(str(mission_id or "")):
        return fail_closed(mission_id, "INVALID_MISSION_ID")
    state = load_mission_state(str(mission_id))
    if not state:
        return fail_closed(mission_id, "MISSION_NOT_FOUND")
    state = dict(state)
    state["evidence_count"] = len(read_evidence(str(mission_id)))
    return state


def _expected_next_step(status: str) -> str:
    for step, rule in STEP_RULES.items():
        if rule["from"] == status:
            return step
    return ""


def run_next(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    mission_id = str(body.get("mission_id") or "").strip()
    if not valid_mission_id(mission_id):
        return fail_closed(mission_id, "INVALID_MISSION_ID")
    state = load_mission_state(mission_id)
    if not state:
        return fail_closed(mission_id, "MISSION_NOT_FOUND")

    current_status = str(state.get("status") or "")
    if current_status in ("CREATED", "APPROVAL_REQUIRED"):
        return _blocked(mission_id, "APPROVAL_REQUIRED", state)
    if current_status in ("REPORTED", "FAILED"):
        return _blocked(mission_id, "MISSION_TERMINAL", state)

    expected_step = _expected_next_step(current_status)
    requested_step = str(body.get("step") or expected_step).strip().lower()
    if not expected_step:
        return _blocked(mission_id, "NO_VALID_NEXT_STEP", state)
    if requested_step != expected_step:
        return _blocked(mission_id, f"{requested_step.upper()}_CANNOT_RUN_FROM_{current_status}", state)

    return run_step(state, requested_step, body)


def run_step(state: dict[str, Any], step: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    mission_id = str(state.get("mission_id") or "")
    rule = STEP_RULES.get(step)
    if not rule:
        return _blocked(mission_id, "UNKNOWN_STEP", state)
    if state.get("status") != rule["from"]:
        return _blocked(mission_id, f"{step.upper()}_CANNOT_RUN_FROM_{state.get('status')}", state)
    if step == "report" and not read_evidence(mission_id):
        return _blocked(mission_id, "REPORT_REQUIRES_EVIDENCE", state)

    files_touched = body.get("files_touched") if isinstance(body.get("files_touched"), list) else []
    command = str(body.get("command") or rule["command"])
    stdout_tail = str(body.get("stdout_tail") or "")
    stderr_tail = str(body.get("stderr_tail") or "")
    return_code = body.get("return_code") if isinstance(body.get("return_code"), int) else 0

    try:
        if rule.get("running"):
            state["next_step"] = step
            state = transition_state(state, str(rule["running"]), step=step, action=command)
            append_evidence(
                mission_id,
                step=step,
                status=str(rule["running"]),
                command=command,
                return_code=None,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
                files_touched=files_touched,
            )

        state["next_step"] = str(rule.get("next") or "")
        state = transition_state(state, str(rule["done"]), step=step, action=command)
        evidence = append_evidence(
            mission_id,
            step=step,
            status=str(rule["done"]),
            command=command,
            return_code=return_code,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            files_touched=files_touched,
        )
        state["files_touched"] = sorted(set(list(state.get("files_touched") or []) + list(files_touched)))
        state["latest_evidence"] = evidence
        state = transition_state(state, str(rule["after_done"]), step=step, action="commit ready") if rule.get("after_done") else state
        state["next_step"] = str(rule.get("next") or "")
        state = save_mission_state(state)
        return state
    except MissionStateError as exc:
        append_evidence(
            mission_id,
            step=step,
            status="FAILED",
            command=command,
            return_code=1,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            files_touched=files_touched,
            error=str(exc),
        )
        return fail_closed(mission_id, str(exc))


def mission_report(mission_id: str | None) -> dict[str, Any]:
    if not valid_mission_id(str(mission_id or "")):
        return fail_closed(mission_id, "INVALID_MISSION_ID")
    state = load_mission_state(str(mission_id))
    if not state:
        return fail_closed(mission_id, "MISSION_NOT_FOUND")
    evidence = read_evidence(str(mission_id))
    if not evidence:
        return _blocked(str(mission_id), "REPORT_REQUIRES_EVIDENCE", state)
    return {
        "schema": "titan.echo.mission_report.v1",
        "status": "MISSION_REPORT_PRESENT" if state.get("status") != "REPORTED" else "REPORTED",
        "mission_id": mission_id,
        "mission_status": state.get("status"),
        "evidence_count": len(evidence),
        "latest_evidence": evidence[-1],
        "files_touched": state.get("files_touched") or [],
        "error": state.get("error") or "",
    }


__all__ = [
    "APPROVAL_CONFIRM",
    "STEP_RULES",
    "approve_mission",
    "create_mission",
    "mission_report",
    "mission_status",
    "run_next",
    "run_step",
]
