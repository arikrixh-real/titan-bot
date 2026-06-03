"""Record-only Git/VPS bridge for TITAN ECHO.

This module does not run git, shell, deploy, restart, or pull.
It only records approval-gated requests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
POLICY_PATH = ECHO_DIR / "git_vps_bridge_policy.json"
REQUEST_PATH = ECHO_DIR / "git_vps_bridge_request.json"


def _now() -> str:
    return datetime.now().isoformat()


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return prefix + "-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_policy() -> dict[str, Any]:
    policy = _read_json(POLICY_PATH)
    if not policy:
        policy = {
            "schema": "titan.echo.git_vps_bridge_policy.v1",
            "status": "DISABLED_POLICY_READY",
            "git_push_enabled": False,
            "vps_pull_enabled": False,
            "deploy_or_restart_enabled": False,
            "approval_required": True,
        }
    return policy


def record_request(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    mission_id = str(payload.get("mission_id") or "")
    approval_id = str(payload.get("approval_id") or "")
    action = str(payload.get("action") or "").strip().lower()
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    note = str(payload.get("note") or "")

    allowed_actions = {"git_push", "vps_pull", "verify_only"}
    blockers = []

    if action not in allowed_actions:
        blockers.append("ACTION_NOT_ALLOWED")
    if not mission_id:
        blockers.append("MISSION_ID_MISSING")
    if not approval_id:
        blockers.append("APPROVAL_ID_MISSING")

    policy = get_policy()

    request = {
        "schema": "titan.echo.git_vps_bridge_request.v1",
        "status": "RECORDED_DISABLED" if not blockers else "NOT_RECORDED",
        "request_id": _stable_id("git-vps-request", mission_id, approval_id, action, note),
        "mission_id": mission_id,
        "approval_id": approval_id,
        "action": action,
        "files": files,
        "note": note,
        "blockers": blockers,
        "policy_status": policy.get("status"),
        "git_push_enabled": False,
        "vps_pull_enabled": False,
        "deploy_or_restart_enabled": False,
        "execution_performed": False,
        "safety": {
            "git_push_pull": False,
            "deploy_or_restart": False,
            "shell_execution": False,
            "titan_runtime_changed": False,
            "broker_changed": False,
            "risk_changed": False,
        },
        "generated_at_ist": _now(),
    }

    ECHO_DIR.mkdir(parents=True, exist_ok=True)
    if not blockers:
        REQUEST_PATH.write_text(json.dumps(request, indent=2), encoding="utf-8")

    return request



def verify_request() -> dict[str, Any]:
    """
    Safe verification only.
    No git push.
    No git pull.
    No deploy.
    No shell writes.
    """

    import subprocess

    try:
        git = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )

        return {
            "schema": "titan.echo.git_vps_bridge_verify.v1",
            "status": "VERIFY_OK",
            "execution_performed": True,
            "git_status": git.stdout.splitlines()[:30],
            "safety": {
                "git_push_pull": False,
                "deploy_or_restart": False,
                "shell_execution": True,
                "runtime_changed": False,
            },
        }

    except Exception as e:
        return {
            "schema": "titan.echo.git_vps_bridge_verify.v1",
            "status": "VERIFY_FAILED",
            "error": str(e),
            "execution_performed": False,
        }

if __name__ == "__main__":
    print(json.dumps({"policy": get_policy()}, indent=2))
