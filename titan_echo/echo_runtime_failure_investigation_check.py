"""Checker for read-only runtime failure investigation reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "titan_echo" / "echo_runtime_failure_investigation.py"
CHECK_PATH = REPO_ROOT / "titan_echo" / "echo_runtime_failure_investigation_check.py"
REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "runtime_failure_investigation.json"
SUMMARY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "runtime_failure_summary.json"
TARGETS = {"Scanner", "Workers", "Master Brain", "Unified Brain", "Truth Gate", "Selector", "Filter Engine"}
DANGEROUS_TOKENS = ("subprocess", "os.system", "shlex", "pexpect")
SECRET_TOKENS = ("SECRET=", "PASSWORD=", "TOKEN=", "API_KEY=", "PRIVATE_KEY=")
FINAL_VERDICTS = {"HEALTHY", "DEGRADED", "FAILING", "NOT_PROVEN"}


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
    secrets_found = [token for token in SECRET_TOKENS if token in source]
    subsystems = report.get("subsystems", {}) if isinstance(report.get("subsystems"), dict) else {}
    missing_targets = sorted(TARGETS - set(subsystems))
    safety = report.get("safety", {}) if isinstance(report.get("safety"), dict) else {}
    failures: list[str] = []
    if not SCRIPT_PATH.exists() or not CHECK_PATH.exists():
        failures.append("investigation scripts missing")
    if not report:
        failures.append("runtime_failure_investigation.json missing or invalid")
    if not summary:
        failures.append("runtime_failure_summary.json missing or invalid")
    if missing_targets:
        failures.append("required subsystem investigation missing")
    if not report.get("FIX_PRIORITY_ORDER"):
        failures.append("FIX_PRIORITY_ORDER missing")
    if report.get("final_verdict") not in FINAL_VERDICTS:
        failures.append("invalid final verdict")
    if dangerous_found:
        failures.append("dangerous command execution token found")
    if secrets_found:
        failures.append("secret-like literal found")
    for key in ("repair_actions_executed", "restart_executed", "deploy_executed", "push_executed", "shell_execution", "reads_env", "writes_outside_echo_runtime"):
        if safety.get(key) is not False:
            failures.append(f"safety flag not false: {key}")
    return {
        "schema": "titan.echo.runtime_failure_investigation_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "files_exist": SCRIPT_PATH.exists() and CHECK_PATH.exists() and REPORT_PATH.exists() and SUMMARY_PATH.exists(),
        "json_valid": bool(report) and bool(summary),
        "required_subsystems_present": not missing_targets,
        "fix_priority_order_present": bool(report.get("FIX_PRIORITY_ORDER")),
        "dangerous_command_tokens_found": dangerous_found,
        "secrets_printed_or_embedded": bool(secrets_found),
        "read_only_safety_confirmed": not any(
            safety.get(key) is not False
            for key in ("repair_actions_executed", "restart_executed", "deploy_executed", "push_executed", "shell_execution", "reads_env", "writes_outside_echo_runtime")
        ),
        "final_verdict": report.get("final_verdict"),
        "failures": failures,
    }


def main() -> None:
    result = build_check()
    print("ECHO runtime failure investigation check complete.")
    print(f"status={result['status']}")
    print(f"files_exist={result['files_exist']}")
    print(f"json_valid={result['json_valid']}")
    print(f"required_subsystems_present={result['required_subsystems_present']}")
    print(f"fix_priority_order_present={result['fix_priority_order_present']}")
    print(f"dangerous_command_tokens_found={result['dangerous_command_tokens_found']}")
    print(f"secrets_printed_or_embedded={result['secrets_printed_or_embedded']}")
    print(f"read_only_safety_confirmed={result['read_only_safety_confirmed']}")
    print(f"final_verdict={result['final_verdict']}")
    if result["failures"]:
        print("failures=" + "; ".join(result["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
