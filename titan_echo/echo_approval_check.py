"""Validate the TITAN ECHO approval system."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
APPROVAL_SCRIPT = REPO_ROOT / "titan_echo" / "echo_approval.py"
APPROVAL_QUEUE_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "approval_queue.json"
APPROVAL_HISTORY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "approval_history.jsonl"

REQUIRED_RECORD_FIELDS = {
    "mission_id",
    "status",
    "risk_level",
    "forbidden_actions",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_approval(*args: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(APPROVAL_SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed_prefixes = (
        "TITAN ECHO approval create:",
        "TITAN ECHO approval list:",
        "TITAN ECHO approval approve:",
        "TITAN ECHO approval reject:",
        "TITAN ECHO approval summary:",
        "Mission ID:",
        "Status:",
        "Risk level:",
        "Approvals:",
        "Total approvals:",
        "Status counts:",
        "Risk counts:",
        "Executed:",
        "- ",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Approval CLI printed unexpected output.")
            break
    if "Executed: True" in stdout:
        errors.append("Approval CLI reported execution.")
    return errors


def extract_mission_id(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("Mission ID:"):
            return line.split(":", 1)[1].strip()
    return ""


def load_queue() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with APPROVAL_QUEUE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing approval queue: {relative(APPROVAL_QUEUE_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(APPROVAL_QUEUE_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Approval queue root must be an object."
    return data, None


def validate_history() -> list[str]:
    if not APPROVAL_HISTORY_PATH.is_file():
        return [f"Missing approval history: {relative(APPROVAL_HISTORY_PATH)}"]
    errors = []
    with APPROVAL_HISTORY_PATH.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                errors.append(f"Invalid approval history JSONL at line {line_number}")
                continue
            if not isinstance(data, dict):
                errors.append(f"Approval history line {line_number} must be object.")
    return errors


def validate_queue(data: dict[str, Any]) -> list[str]:
    errors = []
    approvals = data.get("approvals")
    if not isinstance(approvals, list):
        return ["approvals must be a list."]
    for index, item in enumerate(approvals):
        if not isinstance(item, dict):
            errors.append(f"approvals[{index}] must be object.")
            continue
        missing = REQUIRED_RECORD_FIELDS - set(item)
        if missing:
            errors.append(f"approvals[{index}] missing fields: {sorted(missing)}")
    return errors


def main() -> int:
    errors: list[str] = []
    mission_ids: list[str] = []

    if not APPROVAL_SCRIPT.is_file():
        errors.append(f"Missing approval script: {relative(APPROVAL_SCRIPT)}")
    else:
        commands = [
            (
                "create",
                "--title",
                "Phase 14 check approve",
                "--risk-level",
                "LOW",
                "--summary",
                "Testing approval approve path",
                "--source",
                "echo_approval_check",
            ),
            (
                "create",
                "--title",
                "Phase 14 check reject",
                "--risk-level",
                "LOW",
                "--summary",
                "Testing approval reject path",
                "--source",
                "echo_approval_check",
            ),
        ]
        for command in commands:
            returncode, stdout, stderr = run_approval(*command)
            if returncode != 0:
                errors.append(f"Approval create failed: {' '.join(command)}")
            if stderr:
                errors.append("Approval CLI wrote to stderr.")
            if stdout:
                errors.extend(validate_stdout(stdout))
                mission_id = extract_mission_id(stdout)
                if mission_id:
                    mission_ids.append(mission_id)

        for command in [("list",), ("summary",)]:
            returncode, stdout, stderr = run_approval(*command)
            if returncode != 0:
                errors.append(f"Approval command failed: {' '.join(command)}")
            if stderr:
                errors.append("Approval CLI wrote to stderr.")
            if stdout:
                errors.extend(validate_stdout(stdout))

        if mission_ids:
            for command in [("approve", "--mission-id", mission_ids[0]), ("reject", "--mission-id", mission_ids[-1])]:
                returncode, stdout, stderr = run_approval(*command)
                if returncode != 0:
                    errors.append(f"Approval decision failed: {' '.join(command)}")
                if stderr:
                    errors.append("Approval CLI wrote to stderr.")
                if stdout:
                    errors.extend(validate_stdout(stdout))
        else:
            errors.append("No mission ID captured from create command.")

    queue, error = load_queue()
    if error:
        errors.append(error)
    elif queue is not None:
        errors.extend(validate_queue(queue))

    errors.extend(validate_history())

    if errors:
        print("TITAN ECHO approval check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    approvals = queue.get("approvals", []) if queue else []
    print("TITAN ECHO approval check: PASSED")
    print(f"Approvals: {len(approvals)}")
    print("Executed: False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
