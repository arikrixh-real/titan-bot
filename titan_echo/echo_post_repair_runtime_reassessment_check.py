"""Checker for post-repair runtime reassessment reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "titan_echo" / "echo_post_repair_runtime_reassessment.py"
CHECK_PATH = REPO_ROOT / "titan_echo" / "echo_post_repair_runtime_reassessment_check.py"
REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "post_repair_runtime_reassessment.json"
SUMMARY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "post_repair_runtime_summary.json"
DANGEROUS_TOKENS = ("subprocess", "os.system", "shlex", "pexpect")
FINAL_VERDICTS = {"REPAIRED", "PARTIALLY_REPAIRED", "STILL_FAILING", "WAITING_FOR_RUNTIME_DATA"}
SUBSYSTEMS = {"Scanner", "Truth Gate", "Filter Engine", "Workers", "Master Brain", "Unified Brain"}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def build_check() -> dict[str, Any]:
    report = read_json(REPORT_PATH)
    summary = read_json(SUMMARY_PATH)
    source = read_text(SCRIPT_PATH)
    dangerous_found = [token for token in DANGEROUS_TOKENS if token in source]
    subsystems = report.get("subsystems", {}) if isinstance(report.get("subsystems"), dict) else {}
    safety = report.get("safety", {}) if isinstance(report.get("safety"), dict) else {}
    failures: list[str] = []
    if not SCRIPT_PATH.exists() or not CHECK_PATH.exists():
        failures.append("reassessment scripts missing")
    if not report:
        failures.append("post_repair_runtime_reassessment.json missing or invalid")
    if not summary:
        failures.append("post_repair_runtime_summary.json missing or invalid")
    if SUBSYSTEMS - set(subsystems):
        failures.append("required subsystem missing")
    if report.get("final_verdict") not in FINAL_VERDICTS:
        failures.append("invalid final verdict")
    if dangerous_found:
        failures.append("dangerous import/token found")
    for key in (
        "scanner_runtime_executed",
        "scanner_modified",
        "workers_modified",
        "master_brain_modified",
        "unified_brain_modified",
        "broker_risk_modified",
        "restart_executed",
        "deploy_executed",
        "push_executed",
        "shell_execution",
        "writes_outside_echo_runtime",
    ):
        if safety.get(key) is not False:
            failures.append(f"safety flag not false: {key}")
    return {
        "schema": "titan.echo.post_repair_runtime_reassessment_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "files_exist": SCRIPT_PATH.exists() and CHECK_PATH.exists() and REPORT_PATH.exists() and SUMMARY_PATH.exists(),
        "json_valid": bool(report) and bool(summary),
        "required_subsystems_present": not (SUBSYSTEMS - set(subsystems)),
        "dangerous_tokens_found": dangerous_found,
        "no_runtime_execution": safety.get("scanner_runtime_executed") is False,
        "protected_system_modifications": [],
        "final_verdict": report.get("final_verdict"),
        "failures": failures,
    }


def main() -> None:
    result = build_check()
    print("ECHO post-repair runtime reassessment check complete.")
    print(f"status={result['status']}")
    print(f"files_exist={result['files_exist']}")
    print(f"json_valid={result['json_valid']}")
    print(f"required_subsystems_present={result['required_subsystems_present']}")
    print(f"dangerous_tokens_found={result['dangerous_tokens_found']}")
    print(f"no_runtime_execution={result['no_runtime_execution']}")
    print(f"protected_system_modifications={result['protected_system_modifications']}")
    print(f"final_verdict={result['final_verdict']}")
    if result["failures"]:
        print("failures=" + "; ".join(result["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
