"""Safety checker for the ECHO Project State Registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_SCRIPT = REPO_ROOT / "titan_echo" / "echo_project_state_registry.py"
CHECK_SCRIPT = REPO_ROOT / "titan_echo" / "echo_project_state_registry_check.py"
REGISTRY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "project_state_registry.json"
SUMMARY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "project_state_registry_summary.json"
PROJECT_NAMES = {
    "ECHO",
    "Unified Brain",
    "Outcome Tracking Truth Upgrade",
    "Natural-Run Lineage Proof",
    "ECHO API",
    "Scanner",
    "Master Brain",
    "Learning",
    "Evolution",
    "Runtime Workers",
    "Alerts",
    "Mission Planner",
}
DANGEROUS_TOKENS = ("subprocess", "os.system", "shlex", "pexpect")
SECRET_TOKENS = ("SECRET=", "PASSWORD=", "TOKEN=", "API_KEY=", "PRIVATE_KEY=")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def build_check() -> dict[str, Any]:
    registry = read_json(REGISTRY_PATH)
    summary = read_json(SUMMARY_PATH)
    source_text = read_text(REGISTRY_SCRIPT)
    dangerous_found = [token for token in DANGEROUS_TOKENS if token in source_text]
    secrets_found = [token for token in SECRET_TOKENS if token in source_text]
    projects = registry.get("projects", [])
    project_names = {item.get("name") for item in projects if isinstance(item, dict)}
    missing_projects = sorted(PROJECT_NAMES - project_names)
    failures: list[str] = []
    if not REGISTRY_SCRIPT.exists() or not CHECK_SCRIPT.exists():
        failures.append("registry scripts missing")
    if not registry:
        failures.append("project_state_registry.json missing or unreadable")
    if not summary:
        failures.append("project_state_registry_summary.json missing or unreadable")
    if missing_projects:
        failures.append("required project/subsystem missing")
    if dangerous_found:
        failures.append("dangerous command execution token found")
    if secrets_found:
        failures.append("secret-like literal found")
    safety = registry.get("safety", {})
    if safety.get("reads_env") is not False:
        failures.append(".env read safety not proven false")
    if safety.get("writes_outside_echo_runtime") is not False:
        failures.append("write boundary safety not proven false")
    if safety.get("shell_execution") is not False:
        failures.append("shell execution safety not proven false")
    return {
        "schema": "titan.echo.project_state_registry_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "files_exist": REGISTRY_SCRIPT.exists() and CHECK_SCRIPT.exists() and REGISTRY_PATH.exists() and SUMMARY_PATH.exists(),
        "required_projects_present": not missing_projects,
        "missing_projects": missing_projects,
        "dangerous_command_tokens_found": dangerous_found,
        "secrets_printed_or_embedded": bool(secrets_found),
        "writes_only_echo_runtime": safety.get("writes_outside_echo_runtime") is False,
        "reads_env": safety.get("reads_env"),
        "failures": failures,
    }


def main() -> None:
    report = build_check()
    print("ECHO project state registry check complete.")
    print(f"status={report['status']}")
    print(f"files_exist={report['files_exist']}")
    print(f"required_projects_present={report['required_projects_present']}")
    print(f"dangerous_command_tokens_found={report['dangerous_command_tokens_found']}")
    print(f"secrets_printed_or_embedded={report['secrets_printed_or_embedded']}")
    print(f"writes_only_echo_runtime={report['writes_only_echo_runtime']}")
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
