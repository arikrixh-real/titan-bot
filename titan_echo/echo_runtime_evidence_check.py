"""Checker for the ECHO runtime evidence layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "titan_echo" / "echo_runtime_evidence.py"
CHECK_PATH = REPO_ROOT / "titan_echo" / "echo_runtime_evidence_check.py"
REPORT_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "runtime_evidence_report.json"
SUMMARY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "runtime_evidence_summary.json"
DANGEROUS_TOKENS = ("subprocess", "os.system", "shlex", "pexpect")
SECRET_TOKENS = ("SECRET=", "PASSWORD=", "TOKEN=", "API_KEY=", "PRIVATE_KEY=")
ALLOWED_STATUSES = {"RUNNING", "STOPPED", "STALE", "HEALTHY", "DEGRADED", "FAIL", "UNKNOWN", "NOT_PROVEN"}


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
    invalid_statuses = [
        name
        for name, item in subsystems.items()
        if not isinstance(item, dict) or item.get("status") not in ALLOWED_STATUSES
    ]
    unsupported_healthy = [
        name
        for name, item in subsystems.items()
        if isinstance(item, dict)
        and item.get("status") in ("RUNNING", "HEALTHY")
        and (not item.get("latest_timestamp") or item.get("freshness_seconds") is None)
    ]
    safety = report.get("safety", {}) if isinstance(report.get("safety"), dict) else {}
    failures: list[str] = []
    if not SCRIPT_PATH.exists() or not CHECK_PATH.exists():
        failures.append("runtime evidence scripts missing")
    if not report:
        failures.append("runtime evidence report missing or invalid")
    if not summary:
        failures.append("runtime evidence summary missing or invalid")
    if dangerous_found:
        failures.append("dangerous command execution token found")
    if secrets_found:
        failures.append("secret-like literal found")
    if invalid_statuses:
        failures.append("invalid subsystem status found")
    if unsupported_healthy:
        failures.append("running/healthy status without timestamp/freshness evidence")
    if safety.get("shell_execution") is not False:
        failures.append("shell execution safety not false")
    if safety.get("reads_env") is not False:
        failures.append(".env read safety not false")
    if safety.get("writes_outside_echo_runtime") is not False:
        failures.append("write boundary safety not false")
    return {
        "schema": "titan.echo.runtime_evidence_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "files_exist": SCRIPT_PATH.exists() and CHECK_PATH.exists() and REPORT_PATH.exists() and SUMMARY_PATH.exists(),
        "json_valid": bool(report) and bool(summary),
        "dangerous_command_tokens_found": dangerous_found,
        "secrets_printed_or_embedded": bool(secrets_found),
        "statuses_are_evidence_based": not invalid_statuses and not unsupported_healthy,
        "writes_only_echo_runtime": safety.get("writes_outside_echo_runtime") is False,
        "failures": failures,
    }


def main() -> None:
    result = build_check()
    print("ECHO runtime evidence check complete.")
    print(f"status={result['status']}")
    print(f"files_exist={result['files_exist']}")
    print(f"json_valid={result['json_valid']}")
    print(f"dangerous_command_tokens_found={result['dangerous_command_tokens_found']}")
    print(f"secrets_printed_or_embedded={result['secrets_printed_or_embedded']}")
    print(f"statuses_are_evidence_based={result['statuses_are_evidence_based']}")
    print(f"writes_only_echo_runtime={result['writes_only_echo_runtime']}")
    if result["failures"]:
        print("failures=" + "; ".join(result["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
