"""Safety checker for the ECHO read-only API skeleton."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo.echo_api_status import CONTRACT_PATH, STATUS_PATH, generate_reports


API_FILES = [
    REPO_ROOT / "titan_echo" / "echo_api.py",
    REPO_ROOT / "titan_echo" / "echo_api_status.py",
    REPO_ROOT / "titan_echo" / "echo_api_check.py",
    REPO_ROOT / "titan_echo" / "echo_mission_center.py",
    REPO_ROOT / "titan_echo" / "echo_mission_center_check.py",
    REPO_ROOT / "titan_echo" / "echo_query_router.py",
    REPO_ROOT / "titan_echo" / "echo_query_router_check.py",
]
API_IMPLEMENTATION_FILES = API_FILES[:2]
DANGEROUS_IMPORT_ROOTS = {"subprocess", "shlex", "pexpect", "socket", "socketserver", "requests"}
DANGEROUS_IMPORT_MODULES = {"http.server"}
DANGEROUS_CALL_ROOTS = {"subprocess", "pexpect", "socket", "socketserver", "requests"}
DANGEROUS_CALL_NAMES = {"Popen"}
DANGEROUS_CALL_ATTRS = {("os", "system")}
SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    \b(api[_-]?key|token|secret|password|private[_-]?key)\b
    \s*[:=]\s*
    ['\"]([^'\"\s]{16,})['\"]
    """
)
SECRET_VALUE_RE = re.compile(
    r"""(?x)
    \b(
        sk-[A-Za-z0-9_-]{20,}
        |ghp_[A-Za-z0-9_]{20,}
        |github_pat_[A-Za-z0-9_]{20,}
        |xox[baprs]-[A-Za-z0-9-]{20,}
        |AKIA[0-9A-Z]{16}
    )\b
    """
)
SAFE_SECRET_WORDS = {"placeholder", "example", "redacted", "changeme", "dummy", "none", "null"}
REQUIRED_ENDPOINTS = {
    "/health",
    "/status",
    "/projects",
    "/unified-brain",
    "/lineage",
    "/alerts",
    "/missions",
    "/answer",
    "/query",
}


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


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def dangerous_source_findings(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        try:
            tree = ast.parse(read_text(path), filename=str(path))
        except SyntaxError as exc:
            findings.append(f"{path.name}: syntax error while scanning source: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in DANGEROUS_IMPORT_ROOTS or alias.name in DANGEROUS_IMPORT_MODULES:
                        findings.append(f"{path.name}: dangerous import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                if root in DANGEROUS_IMPORT_ROOTS or module in DANGEROUS_IMPORT_MODULES:
                    findings.append(f"{path.name}: dangerous import from {module}")
            elif isinstance(node, ast.Call):
                call_name = dotted_name(node.func)
                if not call_name:
                    continue
                parts = call_name.split(".")
                if len(parts) >= 2 and (parts[0], parts[1]) in DANGEROUS_CALL_ATTRS:
                    findings.append(f"{path.name}: dangerous call {call_name}")
                elif parts[0] in DANGEROUS_CALL_ROOTS:
                    findings.append(f"{path.name}: dangerous call {call_name}")
                elif parts[-1] in DANGEROUS_CALL_NAMES:
                    findings.append(f"{path.name}: dangerous call {call_name}")
    return sorted(set(findings))


def secret_like_findings(text: str) -> list[str]:
    findings: list[str] = []
    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        value = match.group(2)
        if value.lower() not in SAFE_SECRET_WORDS:
            findings.append(match.group(1))
    for match in SECRET_VALUE_RE.finditer(text):
        findings.append(match.group(1)[:8] + "...")
    return sorted(set(findings))


def build_check() -> dict[str, Any]:
    status, contract = generate_reports()
    combined = "\n".join(read_text(path) for path in API_FILES)
    dangerous_found = dangerous_source_findings(API_FILES)
    secrets_found = secret_like_findings(combined)
    endpoint_paths = {
        endpoint.get("path")
        for endpoint in contract.get("endpoints", [])
        if isinstance(endpoint, dict)
    }
    endpoints_read_only = all(
        endpoint.get("read_only") is True
        for endpoint in contract.get("endpoints", [])
        if isinstance(endpoint, dict)
    )
    status_file = read_json(STATUS_PATH)
    contract_file = read_json(CONTRACT_PATH)
    failures: list[str] = []
    if not all(path.exists() for path in API_FILES):
        failures.append("API skeleton files missing")
    if not status_file:
        failures.append("API status generation failed")
    if not contract_file:
        failures.append("API contract generation failed")
    if REQUIRED_ENDPOINTS - endpoint_paths:
        failures.append("required endpoint missing")
    if not endpoints_read_only:
        failures.append("one or more endpoints are not read-only")
    if dangerous_found:
        failures.append("dangerous shell/network executable source found")
    if secrets_found:
        failures.append("secret-like value found")
    if status.get("safety", {}).get("shell_execution") is not False:
        failures.append("status does not prove shell execution disabled")
    if status.get("safety", {}).get("writes_outside_echo_runtime") is not False:
        failures.append("status does not prove write boundary")

    return {
        "schema": "titan.echo.api_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "files_exist": all(path.exists() for path in API_FILES),
        "api_status_generation_works": bool(status_file),
        "contract_generated": bool(contract_file),
        "dangerous_command_tokens_found": dangerous_found,
        "secrets_printed_or_embedded": bool(secrets_found),
        "all_required_endpoints_present": not (REQUIRED_ENDPOINTS - endpoint_paths),
        "answer_contract_exists": "/answer" in endpoint_paths,
        "all_endpoints_read_only": endpoints_read_only,
        "endpoint_paths": sorted(endpoint_paths),
        "safety": status.get("safety", {}),
        "failures": failures,
    }


def main() -> None:
    report = build_check()
    print("ECHO API safety check complete.")
    print(f"status={report['status']}")
    print(f"files_exist={report['files_exist']}")
    print(f"api_status_generation_works={report['api_status_generation_works']}")
    print(f"contract_generated={report['contract_generated']}")
    print(f"dangerous_command_tokens_found={report['dangerous_command_tokens_found']}")
    print(f"secrets_printed_or_embedded={report['secrets_printed_or_embedded']}")
    print(f"all_required_endpoints_present={report['all_required_endpoints_present']}")
    print(f"answer_contract_exists={report['answer_contract_exists']}")
    print(f"all_endpoints_read_only={report['all_endpoints_read_only']}")
    print("endpoints=" + ", ".join(report["endpoint_paths"]))
    if report["failures"]:
        print("failures=" + "; ".join(report["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
