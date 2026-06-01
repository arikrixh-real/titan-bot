"""Validate the TITAN ECHO duplicate writer auditor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = REPO_ROOT / "titan_echo" / "echo_duplicate_writer_audit.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "duplicate_writer_audit.json"

TARGET_NAMES = {
    "brain_state.json",
    "runtime_status.json",
    "filter_engine_diagnostics.json",
    "truth_gate_status.json",
    "worker_health.json",
    "scanner_status.json",
    "outcome_tracker_diagnostics.json",
    "trade_contract_diagnostics.json",
}

REQUIRED_FIELDS = {
    "truth_file",
    "classification",
    "likely_writer",
    "competing_writers",
    "readers",
    "confidence",
    "duplicate_writer_risk",
    "ownership_recommendation",
    "evidence",
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
        "TITAN ECHO duplicate writer audit:",
        "Files audited:",
        "Confirmed single writers:",
        "Likely single writers:",
        "Multiple writer risks:",
        "No writer found:",
        "Reader-only references:",
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
    truth_files = data.get("truth_files")
    if not isinstance(truth_files, list):
        return ["truth_files must be a list."]
    names = {Path(str(item.get("truth_file", ""))).name for item in truth_files if isinstance(item, dict)}
    missing = TARGET_NAMES - names
    if missing:
        errors.append(f"Missing truth file audit entries: {sorted(missing)}")
    for index, item in enumerate(truth_files):
        if not isinstance(item, dict):
            errors.append(f"truth_files[{index}] must be an object.")
            continue
        missing_fields = REQUIRED_FIELDS - set(item)
        if missing_fields:
            errors.append(f"truth_files[{index}] missing fields: {sorted(missing_fields)}")
    if "recommended_next_steps" not in data:
        errors.append("Missing recommended_next_steps.")
    elif not isinstance(data["recommended_next_steps"], list):
        errors.append("recommended_next_steps must be a list.")
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
        print("TITAN ECHO duplicate writer audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO duplicate writer audit check: PASSED")
    print(f"Files audited: {audit.get('files_audited') if audit else 0}")
    print(f"Multiple writer risks: {audit.get('multiple_writer_risk_count') if audit else 0}")
    print(f"Reader-only references: {audit.get('reader_only_count') if audit else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
