"""Validate the TITAN ECHO observation summarizer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARIZER_PATH = REPO_ROOT / "titan_echo" / "echo_observation_summarizer.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "observation_summary.json"

REQUIRED_FIELDS = {
    "timestamp_ist",
    "overall_health",
    "total_observations",
    "critical_count",
    "warnings_count",
    "top_issues",
    "affected_layers",
    "likely_root_areas",
    "recommended_next_actions",
    "mission_suggestions",
    "confidence",
    "evidence",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_summarizer() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(SUMMARIZER_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed_prefixes = (
        "TITAN ECHO observation summarizer:",
        "Overall health:",
        "Total observations:",
        "Top issues:",
        "Recommended actions:",
        "Mission suggestions:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Summarizer printed unexpected output.")
            break
    return errors


def load_summary() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing summary: {relative(OUTPUT_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(OUTPUT_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Summary root must be an object."
    return data, None


def validate_summary(data: dict[str, Any]) -> list[str]:
    errors = []
    missing = REQUIRED_FIELDS - set(data)
    if missing:
        errors.append(f"Summary missing fields: {sorted(missing)}")
    for field in ["top_issues", "recommended_next_actions", "mission_suggestions"]:
        if not isinstance(data.get(field), list):
            errors.append(f"{field} must be a list.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not SUMMARIZER_PATH.is_file():
        errors.append(f"Missing summarizer: {relative(SUMMARIZER_PATH)}")
    else:
        returncode, stdout, stderr = run_summarizer()
        if returncode != 0:
            errors.append(f"Summarizer failed with exit code {returncode}.")
        if stderr:
            errors.append("Summarizer wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    summary, error = load_summary()
    if error:
        errors.append(error)
    elif summary is not None:
        errors.extend(validate_summary(summary))

    if errors:
        print("TITAN ECHO observation summarizer check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO observation summarizer check: PASSED")
    print(f"Overall health: {summary.get('overall_health') if summary else 'UNKNOWN'}")
    print(f"Top issues: {len(summary.get('top_issues', [])) if summary else 0}")
    print(f"Mission suggestions: {len(summary.get('mission_suggestions', [])) if summary else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
