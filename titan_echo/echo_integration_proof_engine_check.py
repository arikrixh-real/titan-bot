"""Validate the TITAN ECHO integration proof engine."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = REPO_ROOT / "titan_echo" / "echo_integration_proof_engine.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "integration_proof_report.json"

SUBSYSTEMS = {
    "ECHO",
    "Unified Brain",
    "Consciousness Core",
    "Master Brain",
    "Runtime/Daemon",
    "Scanner",
    "Filters",
    "Risk",
    "Execution",
    "Outcome Tracker",
    "Learning",
    "Evolution",
    "Memory",
    "News",
    "Dashboard",
    "Supabase",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_engine() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(ENGINE_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed = (
        "TITAN ECHO integration proof engine:",
        "Integration score:",
        "Subsystems evaluated:",
        "Strongest integrations:",
        "Weakest integrations:",
        "Top gaps:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed):
            errors.append("Integration proof engine printed unexpected output.")
            break
    return errors


def load_report() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing report: {relative(OUTPUT_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(OUTPUT_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Report root must be object."
    return data, None


def validate_report(report: dict[str, Any]) -> list[str]:
    errors = []
    if "integration_score" not in report:
        errors.append("Missing integration_score.")
    subsystems = report.get("subsystems")
    if not isinstance(subsystems, list):
        errors.append("subsystems must be a list.")
    else:
        represented = {str(item.get("subsystem")) for item in subsystems if isinstance(item, dict)}
        missing = SUBSYSTEMS - represented
        if missing:
            errors.append(f"Missing subsystems: {sorted(missing)}")
    for field in ["strongest_integrations", "weakest_integrations", "top_10_integration_gaps", "recommended_next_missions"]:
        if field not in report:
            errors.append(f"Missing {field}.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not ENGINE_PATH.is_file():
        errors.append(f"Missing integration proof engine: {relative(ENGINE_PATH)}")
    else:
        returncode, stdout, stderr = run_engine()
        if returncode != 0:
            errors.append(f"Integration proof engine failed with exit code {returncode}.")
        if stderr:
            errors.append("Integration proof engine wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    report, error = load_report()
    if error:
        errors.append(error)
    elif report is not None:
        errors.extend(validate_report(report))

    if errors:
        print("TITAN ECHO integration proof engine check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO integration proof engine check: PASSED")
    print(f"Integration score: {report.get('integration_score') if report else 0}")
    print(f"Subsystems: {len(report.get('subsystems', [])) if report else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
