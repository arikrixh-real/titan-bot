"""Git adapter for the approved local ECHO runner."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def commit_changes(mission: dict[str, Any], *, repo_root: Path, dry_run: bool = True) -> dict[str, Any]:
    message = str(mission.get("commit_message") or f"ECHO mission {mission.get('mission_id', '')}").strip()
    if dry_run:
        return _dry("COMMITTED", "git commit dry-run", "commit step accepted by local runner dry-run")
    result = subprocess.run(["git", "commit", "-am", message], cwd=str(repo_root), capture_output=True, text=True, timeout=120)
    return _result("COMMITTED", "COMMIT_FAILED", "git commit -am", result)


def push_changes(mission: dict[str, Any], *, repo_root: Path, dry_run: bool = True) -> dict[str, Any]:
    if dry_run:
        return _dry("PUSHED", "git push dry-run", "push step accepted by local runner dry-run")
    result = subprocess.run(["git", "push"], cwd=str(repo_root), capture_output=True, text=True, timeout=180)
    return _result("PUSHED", "PUSH_FAILED", "git push", result)


def pull_changes(mission: dict[str, Any], *, repo_root: Path, dry_run: bool = True) -> dict[str, Any]:
    if dry_run:
        return _dry("PULLED", "git pull dry-run", "pull step accepted by local runner dry-run")
    result = subprocess.run(["git", "pull", "--ff-only"], cwd=str(repo_root), capture_output=True, text=True, timeout=180)
    return _result("PULLED", "PULL_FAILED", "git pull --ff-only", result)


def _dry(status: str, command: str, stdout: str) -> dict[str, Any]:
    return {
        "status": status,
        "command": command,
        "return_code": 0,
        "stdout_tail": stdout,
        "stderr_tail": "",
        "files_touched": [],
        "execution_performed": False,
    }


def _result(done_status: str, failed_status: str, command: str, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "status": done_status if result.returncode == 0 else failed_status,
        "command": command,
        "return_code": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "files_touched": [],
        "execution_performed": True,
    }


__all__ = ["commit_changes", "pull_changes", "push_changes"]
