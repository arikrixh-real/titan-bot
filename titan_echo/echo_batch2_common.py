"""Shared helpers for ECHO Batch 2 read-only artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_RUNTIME = RUNTIME_DIR / "echo"

SAFETY = {
    "codex_execution": False,
    "shell_execution": False,
    "git_push_pull": False,
    "deploy_or_restart": False,
    "titan_runtime_changed": False,
    "actual_execution_permitted": False,
    "broker_changed": False,
    "risk_changed": False,
    "scanner_changed": False,
    "master_brain_changed": False,
    "runtime_workers_changed": False,
    "trade_execution_permitted": False,
    "telegram_sending_enabled": False,
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def runtime_path(relative_name: str) -> Path:
    return RUNTIME_DIR / relative_name


def echo_path(name: str) -> Path:
    return ECHO_RUNTIME / name


def read_json(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore")), None
    except json.JSONDecodeError as exc:
        return None, f"malformed_json_line_{exc.lineno}"
    except OSError as exc:
        return None, f"read_error_{type(exc).__name__}"


def write_echo_json(path: Path, payload: dict[str, Any]) -> None:
    resolved_echo = ECHO_RUNTIME.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("ECHO Batch 2 writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safety() -> dict[str, bool]:
    return dict(SAFETY)


def source_record(path: Path) -> dict[str, Any]:
    data, error = read_json(path)
    return {
        "path": relative(path),
        "exists": error is None,
        "error": error,
        "data": data if error is None else None,
    }


def status_from_counts(ready: str, total: int, present: int, errors: int = 0) -> str:
    if present == total and errors == 0:
        return ready
    if present > 0:
        return "PARTIAL_EVIDENCE"
    return "UNKNOWN_NOT_PROVEN"
