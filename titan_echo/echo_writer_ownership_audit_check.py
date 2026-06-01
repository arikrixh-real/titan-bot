"""Validate the TITAN ECHO writer ownership auditor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = REPO_ROOT / "titan_echo" / "echo_writer_ownership_audit.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "writer_ownership_audit.json"

TARGET_TRUTH_FILES = {
    "data/runtime/brain_state.json",
    "data/runtime/runtime_status.json",
    "data/runtime/filter_engine_diagnostics.json",
    "data/runtime/truth_gate_status.json",
    "data/runtime/worker_health.json",
    "data/runtime/scanner_status.json",
    "data/runtime/outcome_tracker_diagnostics.json",
    "data/runtime/trade_contract_diagnostics.json",
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
        "TITAN ECHO writer ownership audit:",
        "Truth files audited:",
        "Clear ownership:",
        "Unclear ownership:",
        "No writer found:",
        "Multiple possible writers:",
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

    represented = {
        str(item.get("truth_file"))
        for item in truth_files
        if isinstance(item, dict)
    }
    missing_targets = TARGET_TRUTH_FILES - represented
    if missing_targets:
        errors.append(f"Missing target truth files: {sorted(missing_targets)}")

    for index, item in enumerate(truth_files):
        if not isinstance(item, dict):
            errors.append(f"truth_files[{index}] must be an object.")
            continue
        for field in ["likely_writers", "likely_readers", "ownership_status"]:
            if field not in item:
                errors.append(f"truth_files[{index}] missing {field}.")

    if "recommended_next_missions" not in data:
        errors.append("Missing recommended_next_missions.")
    elif not isinstance(data["recommended_next_missions"], list):
        errors.append("recommended_next_missions must be a list.")

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
        print("TITAN ECHO writer ownership audit check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO writer ownership audit check: PASSED")
    print(f"Truth files audited: {audit.get('total_truth_files_audited') if audit else 0}")
    print(f"Clear ownership: {audit.get('clear_ownership_count') if audit else 0}")
    print(f"No writer found: {audit.get('no_writer_found_count') if audit else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
