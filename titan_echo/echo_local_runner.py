"""Approved localhost/VPS execution runner for ECHO missions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from titan_echo import echo_mission_state as state_store
from titan_echo.echo_codex_adapter import run_codex_step
from titan_echo.echo_git_adapter import commit_changes, pull_changes, push_changes
from titan_echo.echo_verify_adapter import run_verify_step


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCHEMA = "titan.echo.local_runner.v1"
RUNNER_STEPS = ("codex", "verify", "commit", "push", "pull", "report")
ALLOWLIST_PREFIXES = ("titan_echo/", "tests/", "data/runtime/echo/")
BLOCKLIST_TERMS = (
    "broker",
    "risk",
    "scanner",
    "setup_engine",
    "trade_journal",
    "outcome_tracker",
    "master_brain",
    "execution",
    "strategies",
)
LOCALHOST_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
VPS_HOSTS = {"vps", "localhost-vps"}


STATUS_TO_STEP = {
    "APPROVED": "codex",
    "CODEX_DONE": "verify",
    "VERIFY_DONE": "commit",
    "COMMIT_READY": "commit",
    "COMMITTED": "push",
    "PUSHED": "pull",
    "PULLED": "report",
}


def run_once(
    *,
    mission_id: str | None = None,
    client_host: str = "127.0.0.1",
    dry_run: bool = True,
    service_mode: bool = False,
) -> dict[str, Any]:
    mission = _load_mission(mission_id)
    if not mission:
        return _blocked("", "NO_APPROVED_MISSION_FOUND")

    mission_id = str(mission.get("mission_id") or "")
    guard = hardening_guard(mission, client_host=client_host)
    if not guard["execution_allowed"]:
        _write_block_evidence(mission, "guard", guard["reason"])
        return _blocked(mission_id, guard["reason"], mission, guard=guard)

    path_policy = validate_mission_paths(mission)
    if not path_policy["allowed"]:
        _block_state(mission, path_policy["reason"])
        _write_block_evidence(mission, "path_policy", path_policy["reason"])
        return _blocked(mission_id, path_policy["reason"], mission, path_policy=path_policy)

    deploy_policy = validate_deploy_restart_policy(mission)
    if not deploy_policy["allowed"]:
        _block_state(mission, deploy_policy["reason"])
        _write_block_evidence(mission, "deploy_restart", deploy_policy["reason"])
        return _blocked(mission_id, deploy_policy["reason"], mission, deploy_policy=deploy_policy)

    step = next_step_for(mission)
    if not step:
        return _blocked(mission_id, "NO_SAFE_NEXT_STEP", mission)

    git_policy = validate_git_step_policy(mission, step, dry_run=dry_run)
    if not git_policy["allowed"]:
        _block_state(mission, git_policy["reason"])
        _write_block_evidence(mission, step, git_policy["reason"])
        return _blocked(mission_id, git_policy["reason"], mission, git_policy=git_policy)

    result = execute_step(mission, step, dry_run=dry_run)
    result["service_mode"] = bool(service_mode)
    result["runner_stopped"] = not service_mode
    return result


def run_service(*, dry_run: bool = True, client_host: str = "127.0.0.1", service_mode: bool = False) -> dict[str, Any]:
    first = run_once(client_host=client_host, dry_run=dry_run, service_mode=service_mode)
    if not service_mode:
        return first

    results = [first]
    while results[-1].get("status") not in {"BLOCKED", "FAILED", "REPORTED"}:
        results.append(run_once(client_host=client_host, dry_run=dry_run, service_mode=True))
    return {
        "schema": RUNNER_SCHEMA,
        "status": results[-1].get("status"),
        "service_mode": True,
        "missions_processed": len(results),
        "results": results,
    }


def hardening_guard(mission: dict[str, Any], *, client_host: str = "127.0.0.1") -> dict[str, Any]:
    status_ok = mission.get("status") == "APPROVED" or str(mission.get("status") or "") in STATUS_TO_STEP
    approved = mission.get("status") == "APPROVED"
    execution_allowed_flag = mission.get("execution_allowed") is True
    approval_exists = bool(mission.get("approval")) or bool(mission.get("approval_id") and mission.get("approved_at"))
    localhost_only = os.environ.get("ECHO_LOCAL_RUNNER_LOCALHOST_ONLY", "true").strip().lower() == "true"
    local_or_vps = is_localhost_or_vps(client_host)
    reason = ""

    if not local_or_vps:
        reason = "NON_LOCALHOST_EXECUTION_BLOCKED"
    elif not localhost_only:
        reason = "LOCALHOST_ONLY_CONFIG_UNSAFE"
    elif not status_ok:
        reason = "APPROVED_STATUS_REQUIRED"
    elif not approved and str(mission.get("status") or "") not in STATUS_TO_STEP:
        reason = "MISSION_NOT_RESUMABLE"
    elif not execution_allowed_flag:
        reason = "EXECUTION_ALLOWED_FLAG_REQUIRED"
    elif not approval_exists:
        reason = "APPROVAL_REQUIRED"

    return {
        "schema": "titan.echo.local_runner_hardening.v1",
        "client_host": client_host,
        "localhost_or_vps": local_or_vps,
        "localhost_only": localhost_only,
        "status_ok": status_ok,
        "execution_allowed_flag": execution_allowed_flag,
        "approval_exists": approval_exists,
        "execution_allowed": not reason,
        "reason": reason,
    }


def is_localhost_or_vps(client_host: str | None) -> bool:
    host = str(client_host or "").strip().lower()
    if host.startswith("::ffff:"):
        host = host.removeprefix("::ffff:")
    if host in LOCALHOST_HOSTS:
        return True
    return host in VPS_HOSTS and os.environ.get("ECHO_LOCAL_RUNNER_VPS", "false").strip().lower() == "true"


def validate_mission_paths(mission: dict[str, Any]) -> dict[str, Any]:
    paths = _mission_paths(mission)
    blocked: list[dict[str, str]] = []
    for raw in paths:
        path = _normal_path(raw)
        if not any(path.startswith(prefix) for prefix in ALLOWLIST_PREFIXES):
            blocked.append({"path": raw, "reason": "PATH_NOT_ALLOWLISTED"})
            continue
        lowered = path.lower()
        if any(term in lowered for term in BLOCKLIST_TERMS):
            blocked.append({"path": raw, "reason": "PATH_BLOCKLISTED"})

    return {
        "allowed": not blocked,
        "paths": paths,
        "blocked": blocked,
        "reason": "BLOCKED_FILE_PATH" if blocked else "",
        "allowlist": list(ALLOWLIST_PREFIXES),
        "blocklist": list(BLOCKLIST_TERMS),
    }


def validate_git_step_policy(mission: dict[str, Any], step: str, *, dry_run: bool = False) -> dict[str, Any]:
    if step not in {"push", "pull"}:
        return {"allowed": True, "reason": ""}
    if mission.get("dry_run") is True and dry_run:
        return {"allowed": True, "reason": "DRY_RUN_SIMULATION"}
    approved = _flag(mission, "git_push_pull_approved") or _flag(mission, f"git_{step}_approved")
    return {"allowed": approved, "reason": "" if approved else "GIT_PUSH_PULL_APPROVAL_REQUIRED"}


def validate_deploy_restart_policy(mission: dict[str, Any]) -> dict[str, Any]:
    requested = (
        _flag(mission, "deploy_requested")
        or _flag(mission, "restart_requested")
        or str(mission.get("action") or "").lower() in {"deploy", "restart", "deploy_restart"}
    )
    approved = _flag(mission, "deploy_restart_approved")
    return {"allowed": (not requested) or approved, "reason": "" if (not requested or approved) else "DEPLOY_RESTART_APPROVAL_REQUIRED"}


def next_step_for(mission: dict[str, Any]) -> str:
    requested = str(mission.get("next_step") or "").strip().lower()
    if _diagnostics_status_only(mission) and str(mission.get("status") or "") == "VERIFY_DONE":
        return "report" if requested in {"", "report", "commit"} else ""
    if requested in RUNNER_STEPS and requested == STATUS_TO_STEP.get(str(mission.get("status") or ""), requested):
        return requested
    return STATUS_TO_STEP.get(str(mission.get("status") or ""), "")


def execute_step(mission: dict[str, Any], step: str, *, dry_run: bool = True) -> dict[str, Any]:
    adapter_result = _adapter_result(mission, step, dry_run=dry_run)
    mission_id = str(mission.get("mission_id") or "")
    success_status = _success_status(step)
    failed = adapter_result.get("status") != success_status or adapter_result.get("return_code") not in (0, None)
    evidence_status = "FAILED" if failed else success_status
    state_status = "FAILED" if failed else success_status

    try:
        if step in {"codex", "verify"}:
            _transition_running(mission, step)
        state_store.append_evidence(
            mission_id,
            step=step,
            status=evidence_status,
            command=str(adapter_result.get("command") or step),
            return_code=adapter_result.get("return_code") if isinstance(adapter_result.get("return_code"), int) else None,
            stdout_tail=str(adapter_result.get("stdout_tail") or ""),
            stderr_tail=str(adapter_result.get("stderr_tail") or ""),
            files_touched=list(adapter_result.get("files_touched") or []),
            error=str(adapter_result.get("error") or ""),
        )
        if failed:
            mission["error"] = str(adapter_result.get("stderr_tail") or adapter_result.get("error") or f"{step} failed")
            mission["status"] = "FAILED"
            state_store.save_mission_state(mission)
            return _failed(mission_id, step, adapter_result, mission)

        _mark_step_done(mission, step, adapter_result)
        reloaded = state_store.load_mission_state(mission_id)
        return {
            "schema": RUNNER_SCHEMA,
            "status": reloaded.get("status") or state_status,
            "mission_id": mission_id,
            "step": step,
            "next_step": reloaded.get("next_step") or "",
            "dry_run": dry_run,
            "execution_performed": bool(adapter_result.get("execution_performed")),
            "evidence_written": True,
        }
    except Exception as exc:
        state_store.append_evidence(
            mission_id,
            step=step,
            status="FAILED",
            command=step,
            return_code=1,
            error=str(exc),
        )
        mission["status"] = "FAILED"
        mission["error"] = str(exc)
        state_store.save_mission_state(mission)
        return _failed(mission_id, step, {"error": str(exc)}, mission)


def _adapter_result(mission: dict[str, Any], step: str, *, dry_run: bool) -> dict[str, Any]:
    if step == "codex":
        return run_codex_step(mission, repo_root=REPO_ROOT, dry_run=dry_run)
    if step == "verify":
        return run_verify_step(mission, repo_root=REPO_ROOT, dry_run=dry_run)
    if step == "commit":
        return commit_changes(mission, repo_root=REPO_ROOT, dry_run=dry_run)
    if step == "push":
        return push_changes(mission, repo_root=REPO_ROOT, dry_run=dry_run)
    if step == "pull":
        return pull_changes(mission, repo_root=REPO_ROOT, dry_run=dry_run)
    if step == "report":
        return {
            "status": "REPORTED",
            "command": "report",
            "return_code": 0,
            "stdout_tail": "mission report finalized",
            "stderr_tail": "",
            "files_touched": [],
            "execution_performed": False,
        }
    return {"status": "FAILED", "command": step, "return_code": 1, "error": "UNKNOWN_STEP"}


def _transition_running(mission: dict[str, Any], step: str) -> None:
    running = {"codex": "CODEX_RUNNING", "verify": "VERIFY_RUNNING"}.get(step)
    if running:
        state_store.transition_state(mission, running, step=step, action=f"{step} running")


def _mark_step_done(mission: dict[str, Any], step: str, adapter_result: dict[str, Any]) -> None:
    mission_id = str(mission.get("mission_id") or "")
    files = list(adapter_result.get("files_touched") or [])
    mission["files_touched"] = sorted(set(list(mission.get("files_touched") or []) + files))
    mission["next_step"] = _next_after(step)
    if step == "report" and _diagnostics_status_only(mission):
        previous_status = str(mission.get("status") or "")
        mission["next_step"] = ""
        mission["status"] = "REPORTED"
        mission["last_step"] = step
        mission["error"] = ""
        mission.setdefault("history", []).append(
            {
                "timestamp": state_store.utc_now(),
                "from": previous_status,
                "to": "REPORTED",
                "step": step,
                "action": str(adapter_result.get("command") or step),
                "error": "",
            }
        )
        state_store.save_mission_state(mission)
        return
    state_store.transition_state(mission, _success_status(step), step=step, action=str(adapter_result.get("command") or step))
    if step == "verify":
        reloaded = state_store.load_mission_state(mission_id)
        if _diagnostics_status_only(reloaded):
            reloaded["next_step"] = "report"
            state_store.save_mission_state(reloaded)
            return
        reloaded["next_step"] = "commit"
        state_store.transition_state(reloaded, "COMMIT_READY", step=step, action="commit ready")
        return
    reloaded = state_store.load_mission_state(mission_id)
    reloaded["next_step"] = _next_after(step)
    state_store.save_mission_state(reloaded)


def _success_status(step: str) -> str:
    return {
        "codex": "CODEX_DONE",
        "verify": "VERIFY_DONE",
        "commit": "COMMITTED",
        "push": "PUSHED",
        "pull": "PULLED",
        "report": "REPORTED",
    }[step]


def _next_after(step: str) -> str:
    index = RUNNER_STEPS.index(step)
    return RUNNER_STEPS[index + 1] if index + 1 < len(RUNNER_STEPS) else ""


def _load_mission(mission_id: str | None) -> dict[str, Any]:
    if mission_id:
        return state_store.load_mission_state(mission_id)
    missions_dir = state_store.MISSIONS_DIR
    if not missions_dir.exists():
        return {}
    for path in sorted(missions_dir.glob("*.json")):
        try:
            mission = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if isinstance(mission, dict) and mission.get("status") in STATUS_TO_STEP:
            return mission
    return {}


def _mission_paths(mission: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("files", "target_files", "changed_files", "files_touched"):
        value = mission.get(key)
        if isinstance(value, list):
            paths.extend(str(item) for item in value if str(item).strip())
    return list(dict.fromkeys(paths))


def _normal_path(raw: str) -> str:
    return str(raw).replace("\\", "/").strip().lstrip("./").lower()


def _flag(mission: dict[str, Any], name: str) -> bool:
    if mission.get(name) is True:
        return True
    flags = mission.get("approval_flags")
    return isinstance(flags, dict) and flags.get(name) is True


def _diagnostics_status_only(mission: dict[str, Any]) -> bool:
    return str(mission.get("execution_scope") or "").strip() == "diagnostics_status_only"


def _block_state(mission: dict[str, Any], reason: str) -> None:
    mission["status"] = "BLOCKED"
    mission["error"] = reason
    mission["next_step"] = next_step_for(mission)
    state_store.save_mission_state(mission)


def _write_block_evidence(mission: dict[str, Any], step: str, reason: str) -> None:
    mission_id = str(mission.get("mission_id") or "")
    if not state_store.valid_mission_id(mission_id):
        return
    state_store.append_evidence(mission_id, step=step, status="BLOCKED", command=step, return_code=None, error=reason)


def _blocked(mission_id: str, reason: str, mission: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    payload = {
        "schema": RUNNER_SCHEMA,
        "status": "BLOCKED",
        "mission_id": mission_id,
        "reason": reason,
        "execution_performed": False,
    }
    if mission:
        payload["mission_status"] = mission.get("status")
        payload["next_step"] = mission.get("next_step")
    payload.update(extra)
    return payload


def _failed(mission_id: str, step: str, adapter_result: dict[str, Any], mission: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": RUNNER_SCHEMA,
        "status": "FAILED",
        "mission_id": mission_id,
        "step": step,
        "mission_status": mission.get("status"),
        "error": adapter_result.get("error") or adapter_result.get("stderr_tail") or "",
        "execution_performed": bool(adapter_result.get("execution_performed")),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one approved local ECHO mission step")
    parser.add_argument("--mission-id", default="")
    parser.add_argument("--client-host", default="127.0.0.1")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--service-mode", action="store_true", default=False)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dry_run = True if args.dry_run or not args.execute else False
    payload = run_service(
        dry_run=dry_run,
        client_host=args.client_host,
        service_mode=bool(args.service_mode),
    ) if args.service_mode else run_once(
        mission_id=args.mission_id or None,
        client_host=args.client_host,
        dry_run=dry_run,
        service_mode=False,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") not in {"FAILED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ALLOWLIST_PREFIXES",
    "BLOCKLIST_TERMS",
    "RUNNER_STEPS",
    "execute_step",
    "hardening_guard",
    "is_localhost_or_vps",
    "next_step_for",
    "run_once",
    "run_service",
    "validate_deploy_restart_policy",
    "validate_git_step_policy",
    "validate_mission_paths",
]
