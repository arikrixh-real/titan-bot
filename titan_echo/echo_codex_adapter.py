"""Local ECHO Codex step adapter.

The adapter is deliberately small: dry-run is the default integration path and
real command execution only happens when a mission supplies an explicit command
and the local runner has already passed its approval gates.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def run_codex_step(mission: dict[str, Any], *, repo_root: Path, dry_run: bool = True) -> dict[str, Any]:
    command = mission.get("codex_command")
    if dry_run or not command:
        return {
            "status": "CODEX_DONE",
            "command": "codex dry-run",
            "return_code": 0,
            "stdout_tail": "codex step accepted by local runner dry-run",
            "stderr_tail": "",
            "files_touched": _mission_files(mission),
            "execution_performed": False,
        }

    if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
        return {
            "status": "CODEX_FAILED",
            "command": "codex",
            "return_code": 2,
            "stdout_tail": "",
            "stderr_tail": "codex_command must be a list of strings",
            "files_touched": [],
            "execution_performed": False,
        }

    result = subprocess.run(command, cwd=str(repo_root), capture_output=True, text=True, timeout=300)
    return {
        "status": "CODEX_DONE" if result.returncode == 0 else "CODEX_FAILED",
        "command": " ".join(command),
        "return_code": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "files_touched": _mission_files(mission),
        "execution_performed": True,
    }


def _mission_files(mission: dict[str, Any]) -> list[str]:
    for key in ("files_touched", "files", "target_files", "changed_files"):
        value = mission.get(key)
        if isinstance(value, list):
            return [str(item).replace("\\", "/") for item in value if str(item).strip()]
    return []


__all__ = ["run_codex_step"]
