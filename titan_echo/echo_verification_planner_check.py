"""Validate the TITAN ECHO verification planner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PLANNER_PATH = REPO_ROOT / "titan_echo" / "echo_verification_planner.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "verification_plan.json"


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_planner(*args: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(PLANNER_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed_prefixes = (
        "TITAN ECHO verification planner plan:",
        "TITAN ECHO verification planner summary:",
        "Mission ID:",
        "Required checks:",
        "Optional checks:",
        "Blocked conditions:",
        "Verification status:",
        "Execution allowed:",
        "Checks executed:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Verification planner printed unexpected output.")
            break
    if "Checks executed: True" in stdout:
        errors.append("Verification planner reported check execution.")
    return errors


def load_plan() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing verification plan: {relative(OUTPUT_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(OUTPUT_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Verification plan root must be object."
    return data, None


def validate_plan(data: dict[str, Any]) -> list[str]:
    errors = []
    if "required_checks" not in data:
        errors.append("Missing required_checks.")
    if "forbidden_changes" not in data:
        errors.append("Missing forbidden_changes.")
    if data.get("execution_allowed") is not False:
        errors.append("execution_allowed must be false.")
    if data.get("verification_status") != "PLANNED_ONLY":
        errors.append("verification_status must be PLANNED_ONLY.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not PLANNER_PATH.is_file():
        errors.append(f"Missing verification planner: {relative(PLANNER_PATH)}")
    else:
        for command in [("plan",), ("summary",)]:
            returncode, stdout, stderr = run_planner(*command)
            if returncode != 0:
                errors.append(f"Verification planner command failed: {' '.join(command)}")
            if stderr:
                errors.append("Verification planner wrote to stderr.")
            if stdout:
                errors.extend(validate_stdout(stdout))

    plan, error = load_plan()
    if error:
        errors.append(error)
    elif plan is not None:
        errors.extend(validate_plan(plan))

    if errors:
        print("TITAN ECHO verification planner check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO verification planner check: PASSED")
    print(f"Required checks: {len(plan.get('required_checks', [])) if plan else 0}")
    print(f"Execution allowed: {plan.get('execution_allowed') if plan else False}")
    print("Checks executed: False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
