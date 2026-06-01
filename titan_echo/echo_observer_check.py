"""Validate the TITAN ECHO read-only observer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OBSERVER_PATH = REPO_ROOT / "titan_echo" / "echo_observer.py"
LIVE_STATUS_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "live_status.json"
OBSERVATIONS_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "observations.json"

LIVE_STATUS_FIELDS = {
    "timestamp_ist",
    "observer_version",
    "files_checked",
    "files_found",
    "files_missing",
    "overall_health",
    "warnings_count",
    "critical_count",
}

OBSERVATION_FIELDS = {"severity", "source_file", "summary", "evidence"}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_observer() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(OBSERVER_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed_prefixes = (
        "TITAN ECHO observer:",
        "Files checked:",
        "Files found:",
        "Files missing:",
        "Overall health:",
        "Observations:",
        "Warnings:",
        "Critical:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Observer printed unexpected output.")
            break
    return errors


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing output file: {relative(path)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(path)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, f"JSON root must be object: {relative(path)}"
    return data, None


def validate_live_status(data: dict[str, Any]) -> list[str]:
    errors = []
    missing = LIVE_STATUS_FIELDS - set(data)
    if missing:
        errors.append(f"live_status missing fields: {sorted(missing)}")
    if data.get("overall_health") not in {"HEALTHY", "DEGRADED", "CRITICAL", "UNKNOWN"}:
        errors.append("live_status has invalid overall_health.")
    return errors


def validate_observations(data: dict[str, Any]) -> list[str]:
    errors = []
    observations = data.get("observations")
    if not isinstance(observations, list):
        return ["observations field must be a list."]
    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            errors.append(f"Observation {index} must be an object.")
            continue
        missing = OBSERVATION_FIELDS - set(item)
        if missing:
            errors.append(f"Observation {index} missing fields: {sorted(missing)}")
    return errors


def main() -> int:
    errors: list[str] = []

    if not OBSERVER_PATH.is_file():
        errors.append(f"Missing observer: {relative(OBSERVER_PATH)}")
    else:
        returncode, stdout, stderr = run_observer()
        if returncode != 0:
            errors.append(f"Observer failed with exit code {returncode}.")
        if stderr:
            errors.append("Observer wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    live_status, error = load_json(LIVE_STATUS_PATH)
    if error:
        errors.append(error)
    elif live_status is not None:
        errors.extend(validate_live_status(live_status))

    observations, error = load_json(OBSERVATIONS_PATH)
    if error:
        errors.append(error)
    elif observations is not None:
        errors.extend(validate_observations(observations))

    if errors:
        print("TITAN ECHO observer check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    observation_count = len(observations.get("observations", [])) if observations else 0
    print("TITAN ECHO observer check: PASSED")
    print(f"Overall health: {live_status.get('overall_health') if live_status else 'UNKNOWN'}")
    print(f"Observations: {observation_count}")
    print(f"Warnings: {live_status.get('warnings_count') if live_status else 0}")
    print(f"Critical: {live_status.get('critical_count') if live_status else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
