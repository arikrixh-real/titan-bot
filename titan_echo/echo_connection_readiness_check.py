"""Checker for the ECHO connection readiness design package."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
PLAN_SOURCE = REPO_ROOT / "titan_echo" / "echo_connection_readiness_plan.py"
CHECK_SOURCE = REPO_ROOT / "titan_echo" / "echo_connection_readiness_check.py"
PLAN_PATH = ECHO_DIR / "echo_connection_readiness_plan.json"
SUMMARY_PATH = ECHO_DIR / "echo_connection_readiness_summary.json"

SOURCE_FILES = (PLAN_SOURCE, CHECK_SOURCE)
EXPECTED_WRITES = {
    "data/runtime/echo/echo_connection_readiness_plan.json",
    "data/runtime/echo/echo_connection_readiness_summary.json",
}
ALLOWED_ENDPOINTS = {
    ("GET", "/health"),
    ("GET", "/status"),
    ("GET", "/answer"),
    ("GET", "/query"),
}
REQUIRED_BLOCKED = {"POST /command", "shell", "broker", "deploy", "restart"}
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
SAFE_SECRET_VALUES = {"changeme", "dummy", "example", "none", "null", "placeholder", "redacted"}
DANGEROUS_IMPORT_ROOTS = {"os", "requests", "shlex", "socket", "subprocess", "urllib", "uvicorn"}
DANGEROUS_CALL_ROOTS = {
    "os.system",
    "os.popen",
    "requests",
    "shlex",
    "socket",
    "subprocess",
    "urllib",
    "uvicorn",
}
SERVER_CALL_NAMES = {"bind", "listen", "serve", "start_server"}
POST_LIKE_NAMES = {"delete", "patch", "post", "put"}


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
                if leaf in SERVER_CALL_NAMES:
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


def writes_only_to_echo(plan: dict[str, Any]) -> bool:
    writes = plan.get("safety", {}).get("writes_only")
    if not isinstance(writes, list):
        return False
    return set(writes) == EXPECTED_WRITES and all(str(item).startswith("data/runtime/echo/") for item in writes)


def connector_endpoints_are_safe(plan: dict[str, Any]) -> bool:
    preview = plan.get("chatgpt_connector_requirements_preview", {})
    allowed = preview.get("allowed_endpoints")
    if not isinstance(allowed, list):
        return False
    normalized = {
        (str(item.get("method", "")).upper(), str(item.get("path", "")))
        for item in allowed
        if isinstance(item, dict)
    }
    blocked = set(preview.get("blocked_endpoints", []))
    return normalized == ALLOWED_ENDPOINTS and REQUIRED_BLOCKED <= blocked


def build_check() -> dict[str, Any]:
    failures: list[str] = []
    if not PLAN_PATH.exists():
        failures.append(f"missing {relative(PLAN_PATH)}")
    if not SUMMARY_PATH.exists():
        failures.append(f"missing {relative(SUMMARY_PATH)}")
    plan = read_json(PLAN_PATH) if PLAN_PATH.exists() else {}
    summary = read_json(SUMMARY_PATH) if SUMMARY_PATH.exists() else {}
    scan = source_scan(SOURCE_FILES)
    secrets = secret_like_findings(SOURCE_FILES, (plan, summary))

    fastapi = plan.get("fastapi_readiness", {})
    local_server = plan.get("local_server_readiness", {})
    auth = plan.get("auth_design", {})
    safety = plan.get("safety", {})

    if plan.get("schema") != "titan.echo.connection_readiness_plan.v1":
        failures.append("invalid plan schema")
    if summary.get("schema") != "titan.echo.connection_readiness_summary.v1":
        failures.append("invalid summary schema")
    if plan.get("review_only") is not True:
        failures.append("plan is not marked review-only")
    if fastapi.get("install_performed") is not False:
        failures.append("plan indicates install was performed")
    if local_server.get("server_started") is not False:
        failures.append("plan indicates server was started")
    if local_server.get("uvicorn_start_performed") is not False:
        failures.append("plan indicates uvicorn was started")
    if local_server.get("public_exposure_allowed") is not False:
        failures.append("public exposure is allowed")
    if local_server.get("server_start_allowed_now") is not False:
        failures.append("server start is allowed now")
    if local_server.get("local_only_bind_recommendation") != "127.0.0.1":
        failures.append("local bind recommendation is not 127.0.0.1")
    if auth.get("recommended_auth_method") != "API key header":
        failures.append("auth method mismatch")
    if auth.get("header_name") != "X-ECHO-API-KEY":
        failures.append("auth header mismatch")
    if auth.get("env_file_reading_allowed_current_batch") is not False:
        failures.append(".env reading is allowed in current batch")
    if auth.get("hardcoded_key_allowed") is not False:
        failures.append("hardcoded key is allowed")
    if not connector_endpoints_are_safe(plan):
        failures.append("unsafe connector endpoint proposal")
    expected_true_safety = (
        "read_only_design",
        "no_install_performed",
        "no_server_started",
        "no_uvicorn_run",
        "no_public_port",
        "no_deploy",
        "no_push",
        "no_restart",
        "no_command_execution_endpoints",
        "no_secrets_in_files",
        "no_env_file_reading",
    )
    for flag in expected_true_safety:
        if safety.get(flag) is not True:
            failures.append(f"safety flag {flag} is not true")
    if safety.get("scanner_master_unified_broker_risk_changes") is not False:
        failures.append("scanner/Master/Unified/broker/risk changes flag is not false")
    if not writes_only_to_echo(plan):
        failures.append("writes are not limited to requested data/runtime/echo outputs")
    for key, values in scan.items():
        if values:
            failures.append(f"{key} found")
    if secrets:
        failures.append("secret-like value found")
    if plan.get("safety_result") != "PASS" or summary.get("safety_result") != "PASS":
        failures.append("safety_result is not PASS")

    return {
        "schema": "titan.echo.connection_readiness_check.v1",
        "checked_files": [relative(path) for path in SOURCE_FILES],
        "checked_artifacts": [relative(PLAN_PATH), relative(SUMMARY_PATH)],
        "fastapi_installed": summary.get("fastapi_installed"),
        "uvicorn_installed": summary.get("uvicorn_installed"),
        "recommended_next_step": summary.get("recommended_next_step"),
        "auth_method": summary.get("auth_method"),
        "public_exposure_allowed": summary.get("public_exposure_allowed"),
        "source_scan": scan,
        "secret_like_findings": secrets,
        "writes_only_to_data_runtime_echo": writes_only_to_echo(plan),
        "safety_result": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def main() -> None:
    check = build_check()
    print("ECHO connection readiness check complete.")
    print(f"fastapi_installed={check['fastapi_installed']}")
    print(f"uvicorn_installed={check['uvicorn_installed']}")
    print(f"recommended_next_step={check['recommended_next_step']}")
    print(f"auth_method={check['auth_method']}")
    print(f"public_exposure_allowed={check['public_exposure_allowed']}")
    print(f"safety_result={check['safety_result']}")
    if check["failures"]:
        print("failures=" + "; ".join(check["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
