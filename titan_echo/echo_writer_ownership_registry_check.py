"""Validate the TITAN ECHO writer ownership registry."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_SCRIPT = REPO_ROOT / "titan_echo" / "echo_writer_ownership_registry.py"
OUTPUT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "writer_ownership_registry.json"

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

ENTRY_REQUIRED_FIELDS = {
    "truth_file",
    "exists_now",
    "owner_status",
    "confirmed_writer",
    "possible_writers",
    "readers",
    "affected_layer",
    "confidence",
    "duplicate_writer_risk",
    "ownership_rule",
    "required_verification",
    "safe_next_action",
    "forbidden_actions",
    "evidence",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_registry() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(REGISTRY_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed_prefixes = (
        "TITAN ECHO writer ownership registry:",
        "Files registered:",
        "Confirmed owners:",
        "Possible owners:",
        "Unresolved owners:",
        "Reader only:",
        "No reference:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Registry script printed unexpected output.")
            break
    return errors


def load_registry() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing registry: {relative(OUTPUT_PATH)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(OUTPUT_PATH)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, "Registry root must be an object."
    return data, None


def validate_registry(data: dict[str, Any]) -> list[str]:
    errors = []
    entries = data.get("truth_files")
    if not isinstance(entries, list):
        return ["truth_files must be a list."]
    represented = {
        str(item.get("truth_file"))
        for item in entries
        if isinstance(item, dict)
    }
    missing = TARGET_TRUTH_FILES - represented
    if missing:
        errors.append(f"Missing target truth files: {sorted(missing)}")
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            errors.append(f"truth_files[{index}] must be an object.")
            continue
        missing_fields = ENTRY_REQUIRED_FIELDS - set(item)
        if missing_fields:
            errors.append(f"truth_files[{index}] missing fields: {sorted(missing_fields)}")
        for required in ["owner_status", "ownership_rule", "required_verification"]:
            if required not in item:
                errors.append(f"truth_files[{index}] missing {required}.")
    if "recommended_next_missions" not in data:
        errors.append("Missing recommended_next_missions.")
    elif not isinstance(data["recommended_next_missions"], list):
        errors.append("recommended_next_missions must be a list.")
    return errors


def main() -> int:
    errors: list[str] = []

    if not REGISTRY_SCRIPT.is_file():
        errors.append(f"Missing registry script: {relative(REGISTRY_SCRIPT)}")
    else:
        returncode, stdout, stderr = run_registry()
        if returncode != 0:
            errors.append(f"Registry script failed with exit code {returncode}.")
        if stderr:
            errors.append("Registry script wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    registry, error = load_registry()
    if error:
        errors.append(error)
    elif registry is not None:
        errors.extend(validate_registry(registry))

    if errors:
        print("TITAN ECHO writer ownership registry check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("TITAN ECHO writer ownership registry check: PASSED")
    print(f"Files registered: {registry.get('files_registered') if registry else 0}")
    print(f"Confirmed owners: {registry.get('confirmed_owner_count') if registry else 0}")
    print(f"Unresolved owners: {registry.get('unresolved_owner_count') if registry else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
