"""Checker for ECHO localhost service readiness instructions."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
READINESS_SOURCE = REPO_ROOT / "titan_echo" / "echo_localhost_service_readiness.py"
CHECK_SOURCE = REPO_ROOT / "titan_echo" / "echo_localhost_service_readiness_check.py"
READINESS_PATH = ECHO_DIR / "echo_localhost_service_readiness.json"
SUMMARY_PATH = ECHO_DIR / "echo_localhost_service_summary.json"

SOURCE_FILES = (READINESS_SOURCE, CHECK_SOURCE)
EXPECTED_WRITES = {
    "data/runtime/echo/echo_localhost_service_readiness.json",
    "data/runtime/echo/echo_localhost_service_summary.json",
}
EXPECTED_ALLOWED_ENDPOINTS = {
    "/health",
    "/answer",
    "/query?intent=status",
    "/query?intent=what_next",
}
PLACEHOLDER_KEY = "temporary-test-key"
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
SAFE_SECRET_VALUES = {
    "changeme",
    "dummy",
    "example",
    "none",
    "null",
    "placeholder",
    "redacted",
    PLACEHOLDER_KEY,
}
DANGEROUS_IMPORT_ROOTS = {"os", "requests", "shlex", "socket", "subprocess", "urllib"}
DANGEROUS_CALL_ROOTS = {
    "os.system",
    "os.popen",
    "requests",
    "shlex",
    "socket",
    "subprocess",
    "urllib",
}
SERVER_CALL_NAMES = {"bind", "listen", "serve", "start_server", "run"}
POST_LIKE_NAMES = {"delete", "patch", "post", "put"}
UNSAFE_ENDPOINT_TOKENS = ("command", "shell", "deploy", "restart", "broker", "risk", "order", "codex")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def source_scan(paths: tuple[Path, ...]) -> dict[str, list[str]]:
    findings = {
        "dangerous_imports": [],
        "dangerous_calls": [],
        "server_start_calls": [],
        "post_or_mutation_calls": [],
        "syntax_errors": [],
    }
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings["syntax_errors"].append(f"{relative(path)}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in DANGEROUS_IMPORT_ROOTS:
                        findings["dangerous_imports"].append(f"{relative(path)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                if root in DANGEROUS_IMPORT_ROOTS:
                    findings["dangerous_imports"].append(f"{relative(path)}: from {module} import ...")
            elif isinstance(node, ast.Call):
                call_name = dotted_name(node.func)
                if not call_name:
                    continue
                if any(call_name == root or call_name.startswith(root + ".") for root in DANGEROUS_CALL_ROOTS):
                    findings["dangerous_calls"].append(f"{relative(path)}: {call_name}")
                leaf = call_name.rsplit(".", 1)[-1].lower()
                if leaf in SERVER_CALL_NAMES and call_name not in {"print"}:
                    findings["server_start_calls"].append(f"{relative(path)}: {call_name}")
                if leaf in POST_LIKE_NAMES:
                    findings["post_or_mutation_calls"].append(f"{relative(path)}: {call_name}")
    return {key: sorted(set(value)) for key, value in findings.items()}


def secret_like_findings(paths: tuple[Path, ...], payloads: tuple[Any, ...]) -> list[str]:
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in paths if path.exists()
    )
    payload_text = json.dumps(payloads, sort_keys=True)
    findings: list[str] = []
    for text in (source_text, payload_text):
        for match in SECRET_ASSIGNMENT_RE.finditer(text):
            value = match.group(2)
            if value.lower() not in SAFE_SECRET_VALUES:
                findings.append(match.group(1))
        for match in SECRET_VALUE_RE.finditer(text):
            findings.append(match.group(1)[:8] + "...")
    return sorted(set(findings))


def writes_only_to_echo(readiness: dict[str, Any]) -> bool:
    writes = readiness.get("safety", {}).get("writes_only")
    if not isinstance(writes, list):
        return False
    return set(writes) == EXPECTED_WRITES and all(str(item).startswith("data/runtime/echo/") for item in writes)


def has_unsafe_endpoints(readiness: dict[str, Any]) -> bool:
    endpoints = readiness.get("allowed_test_endpoints", [])
    return any(any(token in str(endpoint).lower() for token in UNSAFE_ENDPOINT_TOKENS) for endpoint in endpoints)


def deploy_restart_push_instruction_problem(readiness: dict[str, Any]) -> bool:
    command_text = json.dumps(readiness.get("safe_run_commands_text_only", {})).lower()
    return any(token in command_text for token in ("deploy", "restart", "git push"))


def build_check() -> dict[str, Any]:
    failures: list[str] = []
    if not READINESS_PATH.exists():
        failures.append(f"missing {relative(READINESS_PATH)}")
    if not SUMMARY_PATH.exists():
        failures.append(f"missing {relative(SUMMARY_PATH)}")
    readiness = read_json(READINESS_PATH) if READINESS_PATH.exists() else {}
    summary = read_json(SUMMARY_PATH) if SUMMARY_PATH.exists() else {}
    scan = source_scan(SOURCE_FILES)
    secrets = secret_like_findings(SOURCE_FILES, (readiness, summary))

    if readiness.get("schema") != "titan.echo.localhost_service_readiness.v1":
        failures.append("invalid readiness schema")
    if summary.get("schema") != "titan.echo.localhost_service_summary.v1":
        failures.append("invalid summary schema")
    if readiness.get("readiness_only") is not True:
        failures.append("readiness_only is not true")
    if readiness.get("allowed_bind_host") != "127.0.0.1":
        failures.append("allowed bind host is not 127.0.0.1")
    forbidden = set(readiness.get("forbidden_bind_hosts", []))
    if not {"0.0.0.0", "public IP"} <= forbidden:
        failures.append("forbidden bind hosts missing")
    if readiness.get("recommended_port") != 8765:
        failures.append("recommended port is not 8765")
    if readiness.get("auth_required") is not True:
        failures.append("auth_required is not true")
    if readiness.get("auth_header") != "X-ECHO-API-KEY":
        failures.append("auth header mismatch")
    if readiness.get("api_key_source") != "environment variable ECHO_API_KEY":
        failures.append("api key source mismatch")
    if readiness.get("reload_allowed") is not False:
        failures.append("reload_allowed is not false")
    if readiness.get("workers_allowed") != 1:
        failures.append("workers_allowed is not 1")
    if readiness.get("public_exposure_allowed") is not False:
        failures.append("public exposure is allowed")
    if set(readiness.get("allowed_test_endpoints", [])) != EXPECTED_ALLOWED_ENDPOINTS:
        failures.append("allowed test endpoint set mismatch")
    commands = readiness.get("safe_run_commands_text_only", {})
    if commands.get("executed") is not False:
        failures.append("safe command text is marked executed")
    if "--host 127.0.0.1" not in commands.get("windows_powershell", ""):
        failures.append("Windows command missing 127.0.0.1 host")
    if "--host 127.0.0.1" not in commands.get("linux_vps_bash", ""):
        failures.append("Linux command missing 127.0.0.1 host")
    if "0.0.0.0" in json.dumps(commands):
        failures.append("safe run commands include 0.0.0.0")
    if commands.get("stop_instruction") != "CTRL+C":
        failures.append("stop instruction mismatch")
    if readiness.get("real_key_written") is not False:
        failures.append("real key written flag is not false")
    safety = readiness.get("safety", {})
    for key in (
        "uvicorn_executed",
        "server_started",
        "socket_started",
        "public_port_exposed",
        "bind_0_0_0_0",
        "deploy",
        "push",
        "restart",
        "command_endpoints",
        "post_execution_endpoints",
        "scanner_master_unified_broker_risk_changes",
        "real_secret_written",
    ):
        if safety.get(key) is not False:
            failures.append(f"safety flag {key} is not false")
    if has_unsafe_endpoints(readiness):
        failures.append("unsafe allowed test endpoint found")
    if deploy_restart_push_instruction_problem(readiness):
        failures.append("deploy/restart/push instruction found in run commands")
    if not writes_only_to_echo(readiness):
        failures.append("writes are not limited to requested data/runtime/echo outputs")
    for key, values in scan.items():
        if values:
            failures.append(f"{key} found")
    if secrets:
        failures.append("secret-like value found")
    if readiness.get("safety_result") != "PASS" or summary.get("safety_result") != "PASS":
        failures.append("safety_result is not PASS")

    return {
        "schema": "titan.echo.localhost_service_readiness_check.v1",
        "checked_files": [relative(path) for path in SOURCE_FILES],
        "checked_artifacts": [relative(READINESS_PATH), relative(SUMMARY_PATH)],
        "allowed_bind_host": readiness.get("allowed_bind_host"),
        "recommended_port": readiness.get("recommended_port"),
        "auth_required": readiness.get("auth_required"),
        "public_exposure_allowed": readiness.get("public_exposure_allowed"),
        "reload_allowed": readiness.get("reload_allowed"),
        "safe_run_command_text_present": summary.get("safe_run_command_text_present"),
        "source_scan": scan,
        "secret_like_findings": secrets,
        "writes_only_to_data_runtime_echo": writes_only_to_echo(readiness),
        "safety_result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "next_recommended_step": readiness.get("next_recommended_step"),
    }


def main() -> None:
    check = build_check()
    print("ECHO localhost service readiness check complete.")
    print(f"allowed_bind_host={check['allowed_bind_host']}")
    print(f"recommended_port={check['recommended_port']}")
    print(f"auth_required={check['auth_required']}")
    print(f"public_exposure_allowed={check['public_exposure_allowed']}")
    print(f"reload_allowed={check['reload_allowed']}")
    print(f"safe_run_command_text_present={check['safe_run_command_text_present']}")
    print(f"safety_result={check['safety_result']}")
    print(f"next_recommended_step={check['next_recommended_step']}")
    if check["failures"]:
        print("failures=" + "; ".join(check["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
