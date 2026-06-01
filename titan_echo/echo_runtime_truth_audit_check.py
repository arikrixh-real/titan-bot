"""Validate the TITAN ECHO runtime truth auditor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = REPO_ROOT / "titan_echo" / "echo_runtime_truth_audit.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "runtime_truth_audit.json"

REQUIRED_FIELDS = {
    "timestamp_ist",
    "overall_health_from_echo",
    "files_inspected",
    "missing_files",
    "malformed_files",
    "stale_or_unknown_files",
    "critical_sources",
    "warning_sources",
    "affected_layers",
    "likely_writer_owners",
    "root_area_candidates",
    "evidence",
    "safe_next_actions",
    "forbidden_actions",
    "confidence",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_auditor() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(AUDITOR_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed_prefixes = (
        "TITAN ECHO runtime truth audit:",
        "Overall health from ECHO:",
        "Files inspected:",
        "Missing files:",
        "Critical sources:",
        "Warning sources:",
        "Root areas:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Auditor printed unexpected output.")
            break
    return errors


def load_audit() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing audit: {relative(OUTPUT_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(OUTPUT_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Audit root must be an object."
    return data, None


def validate_audit(data: dict[str, Any]) -> list[str]:
    errors = []
    missing = REQUIRED_FIELDS - set(data)
    if missing:
        errors.append(f"Audit missing fields: {sorted(missing)}")
    for field in [
        "missing_files",
        "critical_sources",
        "likely_writer_owners",
        "safe_next_actions",
        "forbidden_actions",
    ]:
        if not isinstance(data.get(field), list):
            errors.append(f"{field} must be a list.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not AUDITOR_PATH.is_file():
        errors.append(f"Missing auditor: {relative(AUDITOR_PATH)}")
    else:
        returncode, stdout, stderr = run_auditor()
        if returncode != 0:
            errors.append(f"Auditor failed with exit code {returncode}.")
        if stderr:
            errors.append("Auditor wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    audit, error = load_audit()
    if error:
        errors.append(error)
    elif audit is not None:
        errors.extend(validate_audit(audit))

    if errors:
        print("TITAN ECHO runtime truth audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO runtime truth audit check: PASSED")
    print(f"Overall health from ECHO: {audit.get('overall_health_from_echo') if audit else 'UNKNOWN'}")
    print(f"Missing files: {len(audit.get('missing_files', [])) if audit else 0}")
    print(f"Critical sources: {len(audit.get('critical_sources', [])) if audit else 0}")
    print(f"Root areas: {len(audit.get('root_area_candidates', [])) if audit else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
