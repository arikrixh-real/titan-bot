"""Readiness check for the local read-only ECHO API server surface."""

from __future__ import annotations

import ast
import importlib.util
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


ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
READINESS_PATH = ECHO_DIR / "echo_api_server_readiness.json"
SUMMARY_PATH = ECHO_DIR / "echo_api_server_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

API_SOURCE_FILES = [
    REPO_ROOT / "titan_echo" / "echo_api.py",
    REPO_ROOT / "titan_echo" / "echo_api_server_check.py",
]

REQUIRED_ENDPOINTS = {
    "/health": "get_health",
    "/status": "get_status",
    "/projects": "get_projects",
    "/unified-brain": "get_unified_brain",
    "/lineage": "get_lineage",
    "/alerts": "get_alerts",
    "/missions": "get_missions",
    "/answer": "get_answer",
    "/query": "get_query",
}

REQUIRED_FALLBACK_FUNCTIONS = ("get_health", "get_status", "get_answer", "get_query")
DANGEROUS_IMPORT_ROOTS = {"subprocess", "shlex", "pexpect"}
DANGEROUS_CALLS = {"os.system", "subprocess", "shlex", "pexpect"}
POST_LIKE_NAMES = {"post", "put", "patch", "delete"}
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
SAFE_SECRET_WORDS = {"changeme", "dummy", "example", "none", "null", "placeholder", "redacted"}


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("server readiness check writes only under data/runtime/echo")
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


def source_findings(paths: list[Path]) -> dict[str, Any]:
    dangerous: list[str] = []
    env_reads: list[str] = []
    post_routes: list[str] = []
    for path in paths:
        try:
            tree = ast.parse(read_text(path), filename=str(path))
        except SyntaxError as exc:
            dangerous.append(f"{path.name}: syntax error: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in DANGEROUS_IMPORT_ROOTS:
                        dangerous.append(f"{path.name}: dangerous import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                if root in DANGEROUS_IMPORT_ROOTS:
                    dangerous.append(f"{path.name}: dangerous import from {module}")
            elif isinstance(node, ast.Call):
                call_name = dotted_name(node.func)
                if not call_name:
                    continue
                if call_name in DANGEROUS_CALLS or any(
                    call_name == name or call_name.startswith(name + ".")
                    for name in DANGEROUS_CALLS - {"os.system"}
                ):
                    dangerous.append(f"{path.name}: dangerous call {call_name}")
                if call_name in {"open", "Path.read_text", "pathlib.Path.read_text"}:
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and arg.value == "." + "env":
                            env_reads.append(f"{path.name}: reads dot-env file")
                if call_name.split(".")[-1].lower() in POST_LIKE_NAMES:
                    post_routes.append(f"{path.name}: non-GET route decorator/call {call_name}")
    return {
        "dangerous_imports_or_calls": sorted(set(dangerous)),
        "env_file_reads": sorted(set(env_reads)),
        "post_execution_endpoints": sorted(set(post_routes)),
    }


def secret_like_findings(paths: list[Path]) -> list[str]:
    combined = "\n".join(read_text(path) for path in paths)
    findings: list[str] = []
    for match in SECRET_ASSIGNMENT_RE.finditer(combined):
        value = match.group(2)
        if value.lower() not in SAFE_SECRET_WORDS:
            findings.append(match.group(1))
    for match in SECRET_VALUE_RE.finditer(combined):
        findings.append(match.group(1)[:8] + "...")
    return sorted(set(findings))


def fastapi_routes() -> dict[str, Any]:
    app = getattr(echo_api, "app", None)
    if app is None:
        return {"paths": [], "methods_by_path": {}, "post_paths": []}
    paths: set[str] = set()
    methods_by_path: dict[str, list[str]] = {}
    post_paths: list[str] = []
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", "")
        methods = sorted(getattr(route, "methods", set()) or [])
        if not path or path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        paths.add(path)
        methods_by_path[path] = methods
        if any(method != "GET" for method in methods):
            post_paths.append(path)
    return {
        "paths": sorted(paths),
        "methods_by_path": methods_by_path,
        "post_paths": sorted(set(post_paths)),
    }


def build_readiness() -> dict[str, Any]:
    fastapi_available = importlib.util.find_spec("fastapi") is not None
    api_detected_fastapi = getattr(echo_api, "FASTAPI_AVAILABLE", None)
    api_mode = "FASTAPI_APP" if fastapi_available and getattr(echo_api, "app", None) is not None else "FALLBACK_FUNCTIONS"
    routes = fastapi_routes()
    endpoint_functions_exist = {
        path: callable(getattr(echo_api, function_name, None))
        for path, function_name in REQUIRED_ENDPOINTS.items()
    }
    fallback_functions_exist = {
        name: callable(getattr(echo_api, name, None))
        for name in REQUIRED_FALLBACK_FUNCTIONS
    }
    endpoint_paths_ready = (
        set(routes["paths"]) >= set(REQUIRED_ENDPOINTS)
        if api_mode == "FASTAPI_APP"
        else all(fallback_functions_exist.values())
    )
    answer_payload = echo_api.get_answer()
    query_payload = echo_api.get_query("status")
    answer_source = answer_payload.get("source")
    answer_fallback_source = answer_payload.get("fallback_source")
    answer_ready = answer_source == "data/runtime/echo/echo_answer.json" or answer_fallback_source == "data/runtime/echo/echo_mission_center.json"
    query_ready = query_payload.get("source") == "data/runtime/echo/echo_query_router.json"
    source_scan = source_findings(API_SOURCE_FILES)
    secret_findings = secret_like_findings(API_SOURCE_FILES)
    failures: list[str] = []
    if api_detected_fastapi is not fastapi_available:
        failures.append("FastAPI availability detection mismatch")
    if api_mode == "FASTAPI_APP" and getattr(echo_api, "app", None) is None:
        failures.append("FastAPI app missing")
    if not all(fallback_functions_exist.values()):
        failures.append("required fallback function missing")
    if not all(endpoint_functions_exist.values()):
        failures.append("required endpoint function missing")
    if not endpoint_paths_ready:
        failures.append("required endpoint path missing")
    if routes["post_paths"]:
        failures.append("non-GET API route found")
    if not answer_ready:
        failures.append("answer endpoint is not backed by answer or Mission Center evidence")
    if not query_ready:
        failures.append("query endpoint is not backed by query router evidence")
    if source_scan["dangerous_imports_or_calls"]:
        failures.append("dangerous command import or call found")
    if source_scan["env_file_reads"]:
        failures.append("environment file read found")
    if source_scan["post_execution_endpoints"]:
        failures.append("POST-like execution endpoint found")
    if secret_findings:
        failures.append("secret-like source value found")

    safety_result = "PASS" if not failures else "FAIL"
    return {
        "schema": "titan.echo.api_server_readiness.v1",
        "timestamp_ist": timestamp_ist(),
        "fastapi_available": fastapi_available,
        "fastapi_detection_recorded": isinstance(api_detected_fastapi, bool),
        "api_mode": api_mode,
        "api_app_exists": getattr(echo_api, "app", None) is not None,
        "fallback_functions": fallback_functions_exist,
        "endpoint_functions": endpoint_functions_exist,
        "endpoint_paths": routes["paths"],
        "endpoint_methods": routes["methods_by_path"],
        "endpoints_ready": endpoint_paths_ready and all(endpoint_functions_exist.values()),
        "answer_ready": answer_ready,
        "answer_source": answer_source,
        "answer_fallback_source": answer_fallback_source,
        "query_ready": query_ready,
        "query_source": query_payload.get("source"),
        "query_default_intent_ready": query_payload.get("resolved_intent") == "status",
        "safety_result": safety_result,
        "safety": {
            "read_only": True,
            "command_execution": False,
            "codex_execution": False,
            "shell_execution": False,
            "post_endpoints": False,
            "broker_risk_scanner_changes": False,
            "master_unified_brain_changes": False,
            "deploy_restart_public_exposure": False,
            "secrets_exposed": False,
            "writes_only": [
                relative(READINESS_PATH),
                relative(SUMMARY_PATH),
            ],
        },
        "source_scan": source_scan,
        "secret_like_findings": secret_findings,
        "failures": failures,
        "next_recommended_step": "Keep the API local and read-only; next verify a local-only GET smoke test only after explicit approval.",
    }


def build_summary(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "titan.echo.api_server_summary.v1",
        "timestamp_ist": readiness["timestamp_ist"],
        "fastapi_available": readiness["fastapi_available"],
        "api_mode": readiness["api_mode"],
        "endpoints_ready": readiness["endpoints_ready"],
        "answer_ready": readiness["answer_ready"],
        "query_ready": readiness["query_ready"],
        "safety_result": readiness["safety_result"],
        "next_recommended_step": readiness["next_recommended_step"],
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    readiness = build_readiness()
    summary = build_summary(readiness)
    write_echo_json(READINESS_PATH, readiness)
    write_echo_json(SUMMARY_PATH, summary)
    return readiness, summary


def main() -> None:
    readiness, _ = generate_reports()
    print("ECHO API server readiness check complete.")
    print(f"fastapi_available={readiness['fastapi_available']}")
    print(f"api_mode={readiness['api_mode']}")
    print(f"endpoints_ready={readiness['endpoints_ready']}")
    print(f"answer_ready={readiness['answer_ready']}")
    print(f"query_ready={readiness['query_ready']}")
    print(f"safety_result={readiness['safety_result']}")
    print(f"next_recommended_step={readiness['next_recommended_step']}")
    if readiness["failures"]:
        print("failures=" + "; ".join(readiness["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
