"""Validate the TITAN ECHO writer function inspector."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
INSPECTOR_PATH = REPO_ROOT / "titan_echo" / "echo_writer_function_inspector.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "writer_function_inspection.json"

TARGET_FILES = {
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
    "confirmed_writer_functions",
    "possible_writer_functions",
    "appender_functions",
    "reader_references",
    "unknown_references",
    "confidence",
    "writer_status",
    "evidence",
    "safe_next_action",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_inspector() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(INSPECTOR_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed_prefixes = (
        "TITAN ECHO writer function inspector:",
        "Files inspected:",
        "Confirmed writers:",
        "Possible writers:",
        "Appender only:",
        "Reader only:",
        "No reference:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Inspector printed unexpected output.")
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
        return None, "Report root must be an object."
    return data, None


def validate_report(data: dict[str, Any]) -> list[str]:
    errors = []
    truth_files = data.get("truth_files")
    if not isinstance(truth_files, list):
        return ["truth_files must be a list."]
    represented = {
        str(item.get("truth_file"))
        for item in truth_files
        if isinstance(item, dict)
    }
    missing = TARGET_FILES - represented
    if missing:
        errors.append(f"Missing truth files: {sorted(missing)}")
    for index, item in enumerate(truth_files):
        if not isinstance(item, dict):
            errors.append(f"truth_files[{index}] must be an object.")
            continue
        missing_fields = REQUIRED_FIELDS - set(item)
        if missing_fields:
            errors.append(f"truth_files[{index}] missing fields: {sorted(missing_fields)}")
    if "recommended_next_steps" not in data:
        errors.append("Missing recommended_next_steps.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not INSPECTOR_PATH.is_file():
        errors.append(f"Missing inspector: {relative(INSPECTOR_PATH)}")
    else:
        returncode, stdout, stderr = run_inspector()
        if returncode != 0:
            errors.append(f"Inspector failed with exit code {returncode}.")
        if stderr:
            errors.append("Inspector wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    report, error = load_report()
    if error:
        errors.append(error)
    elif report is not None:
        errors.extend(validate_report(report))

    if errors:
        print("TITAN ECHO writer function inspector check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO writer function inspector check: PASSED")
    print(f"Confirmed writers: {report.get('confirmed_writer_count') if report else 0}")
    print(f"Possible writers: {report.get('possible_writer_count') if report else 0}")
    print(f"Unresolved files: {len(report.get('unresolved_truth_files', [])) if report else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
