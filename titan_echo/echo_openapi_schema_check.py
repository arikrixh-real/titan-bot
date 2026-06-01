"""Checker for authenticated ECHO OpenAPI schema export."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
EXPORT_SOURCE = REPO_ROOT / "titan_echo" / "echo_openapi_schema_export.py"
CHECK_SOURCE = REPO_ROOT / "titan_echo" / "echo_openapi_schema_check.py"
OPENAPI_PATH = ECHO_DIR / "echo_openapi_schema.json"
ACTION_PREVIEW_PATH = ECHO_DIR / "echo_chatgpt_action_schema_preview.json"
SUMMARY_PATH = ECHO_DIR / "echo_openapi_schema_summary.json"

SOURCE_FILES = (EXPORT_SOURCE, CHECK_SOURCE)
EXPECTED_WRITES = {
    "data/runtime/echo/echo_openapi_schema.json",
    "data/runtime/echo/echo_chatgpt_action_schema_preview.json",
    "data/runtime/echo/echo_openapi_schema_summary.json",
}
EXPECTED_ENDPOINTS = {
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
PROTECTED_ENDPOINTS = EXPECTED_ENDPOINTS - {"/health"}
PUBLIC_ENDPOINTS = {"/health"}
SAFE_ACTION_ENDPOINTS = {"/health", "/status", "/answer", "/query"}
SECURITY_SCHEME_NAME = "EchoApiKey"
HEADER_NAME = "X-ECHO-API-KEY"
ENV_VAR_NAME = "ECHO_API_KEY"
UNSAFE_TOKENS = ("command", "shell", "deploy", "restart", "broker", "risk", "order", "codex")
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


def endpoint_methods(schema: dict[str, Any]) -> dict[str, list[str]]:
    methods: dict[str, list[str]] = {}
    for path, item in schema.get("paths", {}).items():
        if isinstance(item, dict):
            methods[path] = sorted(
                method.upper()
                for method in item
                if method.lower() in {"get", "post", "put", "patch", "delete"}
            )
    return methods


def unsafe_endpoint_count(schema: dict[str, Any]) -> int:
    count = 0
    for path, methods in endpoint_methods(schema).items():
        if any(method != "GET" for method in methods):
            count += 1
        if any(token in path.lower() for token in UNSAFE_TOKENS):
            count += 1
    return count


def writes_only_to_echo(summary: dict[str, Any]) -> bool:
    writes = summary.get("safety", {}).get("writes_only")
    if not isinstance(writes, list):
        return False
    return set(writes) == EXPECTED_WRITES and all(str(item).startswith("data/runtime/echo/") for item in writes)


def build_check() -> dict[str, Any]:
    failures: list[str] = []
    for path in (OPENAPI_PATH, ACTION_PREVIEW_PATH, SUMMARY_PATH):
        if not path.exists():
            failures.append(f"missing {relative(path)}")
    openapi_schema = read_json(OPENAPI_PATH) if OPENAPI_PATH.exists() else {}
    action_preview = read_json(ACTION_PREVIEW_PATH) if ACTION_PREVIEW_PATH.exists() else {}
    summary = read_json(SUMMARY_PATH) if SUMMARY_PATH.exists() else {}
    scan = source_scan(SOURCE_FILES)
    secrets = secret_like_findings(SOURCE_FILES, (openapi_schema, action_preview, summary))
    methods = endpoint_methods(openapi_schema)
    paths = set(methods)

    security_scheme = (
        openapi_schema.get("components", {})
        .get("securitySchemes", {})
        .get(SECURITY_SCHEME_NAME, {})
    )
    if paths != EXPECTED_ENDPOINTS:
        failures.append("OpenAPI endpoint set mismatch")
    for path, route_methods in methods.items():
        if route_methods != ["GET"]:
            failures.append(f"{path} is not GET-only")
    if security_scheme.get("type") != "apiKey" or security_scheme.get("in") != "header":
        failures.append("API key security scheme missing or invalid")
    if security_scheme.get("name") != HEADER_NAME:
        failures.append("API key header name mismatch")
    if ENV_VAR_NAME not in json.dumps(openapi_schema):
        failures.append("environment variable source is not documented")
    for path in PROTECTED_ENDPOINTS:
        security = openapi_schema.get("paths", {}).get(path, {}).get("get", {}).get("security")
        if security != [{SECURITY_SCHEME_NAME: []}]:
            failures.append(f"{path} missing security requirement")
    health_security = openapi_schema.get("paths", {}).get("/health", {}).get("get", {}).get("security")
    if health_security:
        failures.append("/health should not require auth")
    query_params = openapi_schema.get("paths", {}).get("/query", {}).get("get", {}).get("parameters", [])
    if not any(isinstance(param, dict) and param.get("name") == "intent" and param.get("in") == "query" for param in query_params):
        failures.append("/query intent query parameter missing")
    if unsafe_endpoint_count(openapi_schema) != 0:
        failures.append("unsafe endpoint found")
    action_paths = set(action_preview.get("openapi_subset", {}).get("paths", {}))
    if action_paths != SAFE_ACTION_ENDPOINTS:
        failures.append("ChatGPT Action preview endpoint set mismatch")
    if action_preview.get("safe_get_endpoints_only") is not True:
        failures.append("Action preview is not marked GET-only")
    if action_preview.get("no_write_execute_endpoints") is not True:
        failures.append("Action preview allows write/execute endpoints")
    if action_preview.get("auth", {}).get("header_name") != HEADER_NAME:
        failures.append("Action preview auth header mismatch")
    if action_preview.get("auth", {}).get("real_key_included") is not False:
        failures.append("Action preview includes real key")
    if action_preview.get("public_exposure_allowed_now") is not False:
        failures.append("Action preview allows public exposure now")
    if summary.get("unsafe_endpoint_count") != 0:
        failures.append("summary unsafe endpoint count is not zero")
    expected_false_safety = (
        "server_started",
        "uvicorn_run",
        "public_port_exposed",
        "deploy",
        "push",
        "restart",
        "real_api_key_read_or_written",
        "env_file_reading",
        "command_endpoints",
        "post_execution_endpoints",
        "scanner_master_unified_broker_risk_changes",
    )
    for key in expected_false_safety:
        if summary.get("safety", {}).get(key) is not False:
            failures.append(f"safety flag {key} is not false")
    if summary.get("safety", {}).get("schema_documentation_only") is not True:
        failures.append("schema_documentation_only is not true")
    if not writes_only_to_echo(summary):
        failures.append("writes are not limited to requested data/runtime/echo outputs")
    for key, values in scan.items():
        if values:
            failures.append(f"{key} found")
    if secrets:
        failures.append("secret-like value found")
    if summary.get("safety_result") != "PASS":
        failures.append("summary safety_result is not PASS")

    return {
        "schema": "titan.echo.openapi_schema_check.v1",
        "checked_files": [relative(path) for path in SOURCE_FILES],
        "checked_artifacts": [relative(OPENAPI_PATH), relative(ACTION_PREVIEW_PATH), relative(SUMMARY_PATH)],
        "endpoint_count": len(methods),
        "protected_endpoint_count": len(PROTECTED_ENDPOINTS),
        "public_endpoint_count": len(PUBLIC_ENDPOINTS),
        "unsafe_endpoint_count": unsafe_endpoint_count(openapi_schema),
        "auth_scheme": f"{SECURITY_SCHEME_NAME}:{HEADER_NAME}",
        "chatgpt_action_preview_status": action_preview.get("status"),
        "source_scan": scan,
        "secret_like_findings": secrets,
        "writes_only_to_data_runtime_echo": writes_only_to_echo(summary),
        "safety_result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "next_recommended_step": summary.get("next_recommended_step"),
    }


def main() -> None:
    check = build_check()
    print("ECHO OpenAPI schema check complete.")
    print(f"endpoint_count={check['endpoint_count']}")
    print(f"protected_endpoint_count={check['protected_endpoint_count']}")
    print(f"public_endpoint_count={check['public_endpoint_count']}")
    print(f"unsafe_endpoint_count={check['unsafe_endpoint_count']}")
    print(f"auth_scheme={check['auth_scheme']}")
    print(f"chatgpt_action_preview_status={check['chatgpt_action_preview_status']}")
    print(f"safety_result={check['safety_result']}")
    print(f"next_recommended_step={check['next_recommended_step']}")
    if check["failures"]:
        print("failures=" + "; ".join(check["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
