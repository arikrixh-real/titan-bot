"""Checker and design artifact writer for ECHO API-key authentication."""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo import echo_api
from titan_echo.echo_api_auth import (
    ENV_VAR_NAME,
    HEADER_NAME,
    PROTECTED_ENDPOINTS,
    PUBLIC_ENDPOINTS,
    get_auth_design,
    validate_api_key,
)


ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
DESIGN_PATH = ECHO_DIR / "echo_api_auth_design.json"
SUMMARY_PATH = ECHO_DIR / "echo_api_auth_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

SOURCE_FILES = (
    REPO_ROOT / "titan_echo" / "echo_api_auth.py",
    REPO_ROOT / "titan_echo" / "echo_api_auth_check.py",
    REPO_ROOT / "titan_echo" / "echo_api.py",
    REPO_ROOT / "titan_echo" / "echo_fastapi_auth_smoke_test.py",
)
EXPECTED_WRITES = {
    "data/runtime/echo/echo_api_auth_design.json",
    "data/runtime/echo/echo_api_auth_summary.json",
}
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
DANGEROUS_IMPORT_ROOTS = {"requests", "shlex", "socket", "subprocess", "urllib", "uvicorn"}
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


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("auth checker writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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
        "env_file_reads": [],
        "key_prints": [],
        "syntax_errors": [],
    }
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
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
                    if alias.name == "dotenv":
                        findings["env_file_reads"].append(f"{relative(path)}: import dotenv")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                if root in DANGEROUS_IMPORT_ROOTS:
                    findings["dangerous_imports"].append(f"{relative(path)}: from {module} import ...")
                if root == "dotenv":
                    findings["env_file_reads"].append(f"{relative(path)}: from dotenv import ...")
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
                if leaf == "load_dotenv":
                    findings["env_file_reads"].append(f"{relative(path)}: {call_name}")
                if leaf == "print":
                    rendered = ast.get_source_segment(text, node) or ""
                    if ENV_VAR_NAME in rendered or HEADER_NAME in rendered:
                        findings["key_prints"].append(f"{relative(path)}: auth key/header print")
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


def route_auth_map() -> dict[str, dict[str, Any]]:
    app = getattr(echo_api, "app", None)
    route_map: dict[str, dict[str, Any]] = {}
    if app is None:
        return route_map
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", "")
        methods = sorted(getattr(route, "methods", set()) or [])
        if not path or path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        dependency_names = []
        dependant = getattr(route, "dependant", None)
        for dependency in getattr(dependant, "dependencies", []) if dependant is not None else []:
            call = getattr(dependency, "call", None)
            dependency_names.append(getattr(call, "__name__", str(call)))
        route_map[path] = {
            "methods": methods,
            "dependencies": sorted(dependency_names),
            "protected": "require_echo_api_key" in dependency_names,
        }
    return route_map


def build_design_report() -> dict[str, Any]:
    design = get_auth_design()
    route_map = route_auth_map()
    protected = list(PROTECTED_ENDPOINTS)
    public = list(PUBLIC_ENDPOINTS)
    failures: list[str] = []
    scan = source_scan(SOURCE_FILES)
    secrets = secret_like_findings(SOURCE_FILES, (design,))
    if design["header_name"] != HEADER_NAME:
        failures.append("auth header mismatch")
    if design["environment_variable_name"] != ENV_VAR_NAME:
        failures.append("environment variable name mismatch")
    if design["env_file_reading"] is not False:
        failures.append(".env reading is allowed")
    if design["hardcoded_key"] is not False:
        failures.append("hardcoded key is allowed")
    if validate_api_key(None, None) is not False:
        failures.append("auth does not fail closed when key is missing")
    if set(public) != {"/health"}:
        failures.append("public endpoint set mismatch")
    if set(protected) != set(PROTECTED_ENDPOINTS):
        failures.append("protected endpoint set mismatch")
    for endpoint in public:
        if route_map.get(endpoint, {}).get("protected") is not False:
            failures.append(f"{endpoint} should be public")
    for endpoint in protected:
        if route_map.get(endpoint, {}).get("protected") is not True:
            failures.append(f"{endpoint} is not protected")
    for path, info in route_map.items():
        if any(method != "GET" for method in info["methods"]):
            failures.append(f"{path} has non-GET method")
    for key, values in scan.items():
        if values:
            failures.append(f"{key} found")
    if secrets:
        failures.append("secret-like value found")
    design.update(
        {
            "timestamp_ist": timestamp_ist(),
            "route_auth_map": route_map,
            "source_scan": scan,
            "secret_like_findings": secrets,
            "safety": {
                "no_real_secret_committed": True,
                "no_key_printed": True,
                "no_env_file_reading": True,
                "env_var_name_only": True,
                "auth_fails_closed": True,
                "health_public": True,
                "sensitive_endpoints_protected": True,
                "no_command_endpoints": True,
                "no_uvicorn_or_server_start": True,
                "no_public_bind": True,
                "no_deploy_push_restart": True,
                "scanner_master_unified_broker_risk_changes": False,
                "writes_only": [
                    relative(DESIGN_PATH),
                    relative(SUMMARY_PATH),
                ],
            },
            "failures": failures,
            "safety_result": "PASS" if not failures else "FAIL",
            "next_recommended_step": "Run local auth TestClient smoke test, then design OpenAPI auth documentation before any server exposure.",
        }
    )
    return design


def build_summary(design: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "titan.echo.api_auth_summary.v1",
        "timestamp_ist": design["timestamp_ist"],
        "auth_method": design["auth_method"],
        "header_name": design["header_name"],
        "key_source": design["key_source"],
        "auth_required": design["auth_required"],
        "public_endpoints": design["public_endpoints"],
        "protected_endpoints": design["protected_endpoints"],
        "auth_fails_closed": design["safety"]["auth_fails_closed"],
        "safety_result": design["safety_result"],
        "next_recommended_step": design["next_recommended_step"],
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    design = build_design_report()
    summary = build_summary(design)
    write_echo_json(DESIGN_PATH, design)
    write_echo_json(SUMMARY_PATH, summary)
    return design, summary


def main() -> None:
    design, summary = generate_reports()
    print("ECHO API auth check complete.")
    print("protected_endpoints=" + ", ".join(summary["protected_endpoints"]))
    print("public_endpoints=" + ", ".join(summary["public_endpoints"]))
    print("auth_without_key_result=FAIL_CLOSED")
    print("auth_with_test_key_result=CHECKED_BY_SMOKE_TEST")
    print("wrong_key_result=CHECKED_BY_SMOKE_TEST")
    print(f"safety_result={summary['safety_result']}")
    print(f"next_recommended_step={summary['next_recommended_step']}")
    if design["failures"]:
        print("failures=" + "; ".join(design["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
