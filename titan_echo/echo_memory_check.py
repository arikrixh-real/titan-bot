"""Validate the TITAN ECHO permanent memory writer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MEMORY_SCRIPT = REPO_ROOT / "titan_echo" / "echo_memory.py"
MEMORY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "echo_memory.jsonl"


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_memory(*args: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(MEMORY_SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    errors = []
    allowed_prefixes = (
        "TITAN ECHO memory add:",
        "TITAN ECHO memory list:",
        "TITAN ECHO memory summarize:",
        "Event type:",
        "Risk level:",
        "Written files:",
        "Total events:",
        "Shown events:",
        "Event types:",
        "Risk levels:",
        "Memory file:",
        "- ",
    )
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Memory CLI printed unexpected output.")
            break
    return errors


def load_jsonl() -> tuple[list[dict[str, Any]], list[str]]:
    errors = []
    events: list[dict[str, Any]] = []
    if not MEMORY_PATH.is_file():
        return events, [f"Missing memory file: {relative(MEMORY_PATH)}"]
    with MEMORY_PATH.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                errors.append(f"Invalid JSONL at line {line_number}")
                continue
            if not isinstance(data, dict):
                errors.append(f"JSONL entry must be object at line {line_number}")
                continue
            if "event_type" not in data:
                errors.append(f"Missing event_type at line {line_number}")
            if "timestamp_ist" not in data:
                errors.append(f"Missing timestamp_ist at line {line_number}")
            events.append(data)
    return events, errors


def main() -> int:
    errors: list[str] = []

    if not MEMORY_SCRIPT.is_file():
        errors.append(f"Missing memory writer: {relative(MEMORY_SCRIPT)}")
    else:
        commands = [
            (
                "add",
                "--event-type",
                "warning",
                "--title",
                "Phase 5 check memory",
                "--summary",
                "Testing ECHO memory writer check",
                "--source",
                "echo_memory_check",
            ),
            ("list", "--limit", "3"),
            ("summarize",),
        ]
        for command in commands:
            returncode, stdout, stderr = run_memory(*command)
            if returncode != 0:
                errors.append(f"Memory CLI failed: {' '.join(command)}")
            if stderr:
                errors.append("Memory CLI wrote to stderr.")
            if stdout:
                errors.extend(validate_stdout(stdout))

    events, jsonl_errors = load_jsonl()
    errors.extend(jsonl_errors)

    if errors:
        print("TITAN ECHO memory check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO memory check: PASSED")
    print(f"Memory events: {len(events)}")
    print(f"Memory file: {relative(MEMORY_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
