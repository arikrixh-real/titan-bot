"""Validate the TITAN ECHO read-only context builder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "titan_echo" / "echo_context_builder.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "echo_context_report.json"

REQUIRED_FIELDS = [
    "issue_keyword",
    "timestamp",
    "matched_files",
    "matched_layers",
    "related_modules",
    "probable_affected_systems",
    "criticality_summary",
    "forbidden_files",
    "allowed_safe_scope",
    "required_tests",
    "safety_notes",
    "mission_prompt_guidance",
    "confidence",
    "evidence",
]


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_builder(*args: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(BUILDER_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    errors = []
    allowed_prefixes = (
        "TITAN ECHO context builder:",
        "Issue keyword:",
        "Matched files:",
        "Matched layers:",
        "Confidence:",
        "Output:",
    )
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Context builder printed unexpected output.")
            break
    return errors


def load_report() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing context report: {relative(OUTPUT_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(OUTPUT_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Context report root must be an object."
    return data, None


def validate_report(report: dict[str, Any]) -> list[str]:
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in report:
            errors.append(f"Missing required field: {field}")
    if not isinstance(report.get("matched_files"), list):
        errors.append("matched_files must be a list.")
    if not isinstance(report.get("safety_notes"), list):
        errors.append("safety_notes must be a list.")
    if not isinstance(report.get("mission_prompt_guidance"), list):
        errors.append("mission_prompt_guidance must be a list.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not BUILDER_PATH.is_file():
        errors.append(f"Missing context builder: {relative(BUILDER_PATH)}")
    else:
        for args in [(), ("outcome_tracker",)]:
            returncode, stdout, stderr = run_builder(*args)
            if returncode != 0:
                label = "no keyword" if not args else "outcome_tracker"
                errors.append(f"Context builder failed for {label} with exit code {returncode}.")
            if stderr:
                errors.append("Context builder wrote to stderr.")
            if stdout:
                errors.extend(validate_stdout(stdout))

    report, load_error = load_report()
    if load_error:
        errors.append(load_error)
    elif report is not None:
        errors.extend(validate_report(report))

    if errors:
        print("TITAN ECHO context builder check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO context builder check: PASSED")
    print(f"Report: {relative(OUTPUT_PATH)}")
    print(f"Issue keyword: {report.get('issue_keyword') if report else 'unknown'}")
    print(f"Matched files: {len(report.get('matched_files', [])) if report else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
