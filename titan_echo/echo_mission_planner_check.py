"""Validate the TITAN ECHO mission planner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PLANNER_PATH = REPO_ROOT / "titan_echo" / "echo_mission_planner.py"
MISSION_PLAN_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "mission_plan.json"
MISSION_PROMPT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "mission_prompt.txt"
MISSION_HISTORY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "mission_history.jsonl"


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
        "TITAN ECHO mission planner plan:",
        "TITAN ECHO mission planner summary:",
        "TITAN ECHO mission planner from-approval:",
        "Mission ID:",
        "Current mission ID:",
        "Approval status:",
        "Execution allowed:",
        "History count:",
        "Executed:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Mission planner printed unexpected output.")
            break
    if "Executed: True" in stdout:
        errors.append("Mission planner reported execution.")
    return errors


def load_plan() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with MISSION_PLAN_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing mission plan: {relative(MISSION_PLAN_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(MISSION_PLAN_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Mission plan root must be an object."
    return data, None


def validate_history() -> list[str]:
    if not MISSION_HISTORY_PATH.is_file():
        return [f"Missing mission history: {relative(MISSION_HISTORY_PATH)}"]
    errors = []
    with MISSION_HISTORY_PATH.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                errors.append(f"Invalid mission history JSONL at line {line_number}")
                continue
            if not isinstance(data, dict):
                errors.append(f"Mission history line {line_number} must be object.")
    return errors


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors = []
    if "execution_allowed" not in plan:
        errors.append("mission plan missing execution_allowed.")
    elif plan["execution_allowed"] is not False:
        errors.append("execution_allowed must be false.")
    for field in ["forbidden_actions", "required_verification"]:
        if field not in plan:
            errors.append(f"mission plan missing {field}.")
        elif not isinstance(plan[field], list):
            errors.append(f"{field} must be a list.")
    if not MISSION_PROMPT_PATH.is_file():
        errors.append(f"Missing mission prompt: {relative(MISSION_PROMPT_PATH)}")
    else:
        prompt = MISSION_PROMPT_PATH.read_text(encoding="utf-8", errors="replace")
        required_phrases = ["Do not execute automatically.", "Do not deploy.", "Do not push.", "Do not restart."]
        for phrase in required_phrases:
            if phrase not in prompt:
                errors.append(f"mission prompt missing phrase: {phrase}")
    return errors


def main() -> int:
    errors: list[str] = []

    if not PLANNER_PATH.is_file():
        errors.append(f"Missing mission planner: {relative(PLANNER_PATH)}")
    else:
        for command in [
            ("plan", "--title", "Phase 15 check mission plan", "--risk-level", "LOW"),
            ("summary",),
        ]:
            returncode, stdout, stderr = run_planner(*command)
            if returncode != 0:
                errors.append(f"Mission planner command failed: {' '.join(command)}")
            if stderr:
                errors.append("Mission planner wrote to stderr.")
            if stdout:
                errors.extend(validate_stdout(stdout))

    plan, error = load_plan()
    if error:
        errors.append(error)
    elif plan is not None:
        errors.extend(validate_plan(plan))

    errors.extend(validate_history())

    if errors:
        print("TITAN ECHO mission planner check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO mission planner check: PASSED")
    print(f"Mission ID: {plan.get('mission_id') if plan else 'none'}")
    print(f"Execution allowed: {plan.get('execution_allowed') if plan else False}")
    print("Executed: False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
