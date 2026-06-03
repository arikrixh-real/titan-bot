"""Disabled approval-gated Codex runner skeleton for ECHO.

This module records future Codex work requests only. It never invokes Codex,
shells, subprocesses, git, deployment tools, or TITAN runtime code.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
IST = timezone(timedelta(hours=5, minutes=30))

RUNNER_ENABLED_ENV = "ECHO_CODEX_RUNNER_ENABLED"
CODEX_RUNNER_STATUS_PATH = ECHO_DIR / "codex_runner_status.json"
CODEX_RUNNER_REQUEST_PATH = ECHO_DIR / "codex_runner_request.json"
CODEX_RUNNER_POLICY_PATH = ECHO_DIR / "codex_runner_policy.json"

MISSION_PLAN_PATH = ECHO_DIR / "mission_plan.json"
APPROVAL_QUEUE_PATH = ECHO_DIR / "approval_queue.json"
EXECUTION_AUTHORIZATION_PATH = ECHO_DIR / "execution_authorization.json"
EXECUTION_LOCK_PATH = ECHO_DIR / "execution_lock.json"
EXECUTION_EVIDENCE_PATH = ECHO_DIR / "execution_evidence.json"
EXECUTION_LEDGER_PATH = ECHO_DIR / "execution_ledger.json"
EXECUTION_GATE_PATH = ECHO_DIR / "execution_gate.json"


def _timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def _runner_enabled() -> bool:
    return os.environ.get(RUNNER_ENABLED_ENV, "false").strip().lower() == "true"


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("Codex runner writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def runner_safety() -> dict[str, bool]:
    return {
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "actual_execution_permitted": False,
        "execution_performed": False,
    }


def build_codex_runner_policy() -> dict[str, Any]:
    payload = {
        "schema": "titan.echo.codex_runner_policy.v1",
        "status": "CODEX_RUNNER_DISABLED",
        "runner_enabled": _runner_enabled(),
        "allowed_future_action": "CODEX_PROMPT_EXECUTION_AFTER_SEPARATE_APPROVAL",
        "current_action": "RECORD_ONLY",
        "codex_execution": False,
        "shell_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "actual_execution_permitted": False,
        "safety": runner_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(CODEX_RUNNER_POLICY_PATH, payload)
    return payload


def get_codex_runner_policy() -> dict[str, Any]:
    return build_codex_runner_policy()


def build_codex_runner_status() -> dict[str, Any]:
    if not CODEX_RUNNER_REQUEST_PATH.exists():
        _write_echo_json(
            CODEX_RUNNER_REQUEST_PATH,
            {
                "schema": "titan.echo.codex_runner_request.v1",
                "status": "CODEX_REQUEST_NONE_RECORDED",
                "execution_performed": False,
                "safety": runner_safety(),
                "generated_at_ist": _timestamp_ist(),
            },
        )
    payload = {
        "schema": "titan.echo.codex_runner_status.v1",
        "status": "CODEX_RUNNER_DISABLED",
        "runner_enabled": _runner_enabled(),
        "env_var": RUNNER_ENABLED_ENV,
        "policy_path": _relative(CODEX_RUNNER_POLICY_PATH),
        "request_path": _relative(CODEX_RUNNER_REQUEST_PATH),
        "execution_performed": False,
        "safety": runner_safety(),
        "generated_at_ist": _timestamp_ist(),
    }
    _write_echo_json(CODEX_RUNNER_STATUS_PATH, payload)
    return payload


def get_codex_runner_status() -> dict[str, Any]:
    return build_codex_runner_status()


def _mission_exists(mission_id: str) -> bool:
    mission_plan = _read_json(MISSION_PLAN_PATH)
    if not isinstance(mission_plan, dict):
        return False

    if str(mission_plan.get("mission_id") or "") == mission_id:
        return True

    current = mission_plan.get("current_mission")
    if isinstance(current, dict) and str(current.get("mission_id") or "") == mission_id:
        return True

    for key in ("mission", "active_mission"):
        item = mission_plan.get(key)
        if isinstance(item, dict) and str(item.get("mission_id") or "") == mission_id:
            return True

    return False


def _approval_exists(approval_id: str) -> bool:
    queue = _read_json(APPROVAL_QUEUE_PATH)
    approvals = queue.get("approvals") if isinstance(queue, dict) else None
    if not isinstance(approvals, list):
        return False

    for item in approvals:
        if not isinstance(item, dict):
            continue

        if str(item.get("approval_id") or "") == approval_id:
            return True

        if str(item.get("mission_id") or "") == approval_id:
            return True

    return False


def _dict_present(path: Path) -> bool:
    return isinstance(_read_json(path), dict)


def _gate_blocked() -> bool:
    gate = _read_json(EXECUTION_GATE_PATH)
    return isinstance(gate, dict) and gate.get("status") == "EXECUTION_BLOCKED_POLICY_LOCKED"


def _request_checks(mission_id: str, approval_id: str) -> dict[str, bool]:
    return {
        "mission_exists": bool(mission_id) and _mission_exists(mission_id),
        "approval_exists": bool(approval_id) and _approval_exists(approval_id),
        "authorization_exists": _dict_present(EXECUTION_AUTHORIZATION_PATH),
        "lock_exists": _dict_present(EXECUTION_LOCK_PATH),
        "evidence_exists": _dict_present(EXECUTION_EVIDENCE_PATH),
        "ledger_exists": _dict_present(EXECUTION_LEDGER_PATH),
        "execution_gate_exists": _dict_present(EXECUTION_GATE_PATH),
        "execution_gate_status_blocked": _gate_blocked(),
        "runner_enabled_false": _runner_enabled() is False,
    }


def post_codex_runner_request(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    mission_id = str(body.get("mission_id") or "").strip()
    approval_id = str(body.get("approval_id") or "").strip()
    prompt = str(body.get("prompt") or "")
    now = _timestamp_ist()
    checks = _request_checks(mission_id, approval_id)
    blockers = [name for name, passed in checks.items() if not passed]
    policy = build_codex_runner_policy()
    status = "CODEX_REQUEST_RECORDED_DISABLED" if not blockers else "CODEX_REQUEST_NOT_RECORDED"
    request = {
        "schema": "titan.echo.codex_runner_request.v1",
        "status": status,
        "request_id": _stable_id("codex-request", mission_id, approval_id, prompt, now),
        "mission_id": mission_id,
        "approval_id": approval_id,
        "prompt": prompt,
        "checks": checks,
        "blockers": blockers,
        "policy": policy,
        "execution_performed": False,
        "safety": runner_safety(),
        "generated_at_ist": now,
    }
    if not blockers:
        _write_echo_json(CODEX_RUNNER_REQUEST_PATH, request)
    build_codex_runner_status()
    return request


__all__ = [
    "CODEX_RUNNER_POLICY_PATH",
    "CODEX_RUNNER_REQUEST_PATH",
    "CODEX_RUNNER_STATUS_PATH",
    "RUNNER_ENABLED_ENV",
    "build_codex_runner_policy",
    "build_codex_runner_status",
    "get_codex_runner_policy",
    "get_codex_runner_status",
    "post_codex_runner_request",
    "runner_safety",
]
