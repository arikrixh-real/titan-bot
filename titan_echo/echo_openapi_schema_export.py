"""Export authenticated ECHO OpenAPI schema and ChatGPT Action preview.

This is documentation-only. It does not start a server, bind a port, deploy,
push, read real API keys, or mutate TITAN runtime behavior.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo import echo_api
from titan_echo.echo_api_auth import ENV_VAR_NAME, HEADER_NAME, PROTECTED_ENDPOINTS, PUBLIC_ENDPOINTS


ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
OPENAPI_PATH = ECHO_DIR / "echo_openapi_schema.json"
ACTION_PREVIEW_PATH = ECHO_DIR / "echo_chatgpt_action_schema_preview.json"
SUMMARY_PATH = ECHO_DIR / "echo_openapi_schema_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

EXPECTED_ENDPOINTS = (
    "/health",
    "/status",
    "/projects",
    "/unified-brain",
    "/lineage",
    "/alerts",
    "/missions",
    "/answer",
    "/query",
)
BLOCKED_ENDPOINTS = (
    "POST /command",
    "shell",
    "deploy",
    "restart",
    "broker",
    "risk",
    "order execution",
    "Codex executor",
)
SAFE_ACTION_ENDPOINTS = (
    "/health",
    "/status",
    "/answer",
    "/query",
)
SECURITY_SCHEME_NAME = "EchoApiKey"


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
        raise ValueError("OpenAPI export writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def base_openapi_schema() -> dict[str, Any]:
    app = getattr(echo_api, "app", None)
    if app is None:
        raise RuntimeError("echo_api.app is not available")
    schema = app.openapi()
    schema.setdefault("info", {})["description"] = (
        "Read-only ECHO API. Real API keys must come from the ECHO_API_KEY "
        "environment variable on the server side; no key value is documented here."
    )
    return schema


def route_methods(schema: dict[str, Any]) -> dict[str, list[str]]:
    methods: dict[str, list[str]] = {}
    for path, item in schema.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        route_methods_found = [
            method.upper()
            for method in item
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        ]
        methods[path] = sorted(route_methods_found)
    return methods


def protect_openapi_schema(schema: dict[str, Any]) -> dict[str, Any]:
    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes[SECURITY_SCHEME_NAME] = {
        "type": "apiKey",
        "in": "header",
        "name": HEADER_NAME,
        "description": (
            "API key header for protected ECHO GET endpoints. The real key must be "
            f"provided from the {ENV_VAR_NAME} environment variable and must not be committed."
        ),
    }
    for path, item in schema.get("paths", {}).items():
        if not isinstance(item, dict) or "get" not in item:
            continue
        if path in PROTECTED_ENDPOINTS:
            item["get"]["security"] = [{SECURITY_SCHEME_NAME: []}]
        elif path in PUBLIC_ENDPOINTS:
            item["get"].pop("security", None)
    return schema


def make_action_preview(openapi_schema: dict[str, Any]) -> dict[str, Any]:
    safe_paths: dict[str, Any] = {}
    for path in SAFE_ACTION_ENDPOINTS:
        path_item = openapi_schema.get("paths", {}).get(path)
        if isinstance(path_item, dict) and "get" in path_item:
            safe_paths[path] = {"get": path_item["get"]}
    return {
        "schema": "titan.echo.chatgpt_action_schema_preview.v1",
        "timestamp_ist": timestamp_ist(),
        "status": "PREVIEW_ONLY_NOT_DEPLOYABLE",
        "warning": "localhost/private VPS only until HTTPS + auth + approval gate are ready",
        "auth": {
            "type": "apiKey",
            "header_name": HEADER_NAME,
            "environment_variable_name": ENV_VAR_NAME,
            "real_key_included": False,
            "env_file_reading": False,
        },
        "openapi_subset": {
            "openapi": openapi_schema.get("openapi"),
            "info": openapi_schema.get("info"),
            "paths": safe_paths,
            "components": {
                "securitySchemes": openapi_schema.get("components", {}).get("securitySchemes", {})
            },
        },
        "safe_get_endpoints_only": True,
        "no_write_execute_endpoints": True,
        "blocked_endpoints": list(BLOCKED_ENDPOINTS),
        "public_exposure_allowed_now": False,
    }


def unsafe_endpoint_count(schema: dict[str, Any]) -> int:
    count = 0
    for path, methods in route_methods(schema).items():
        if any(method != "GET" for method in methods):
            count += 1
        lowered = path.lower()
        if any(token in lowered for token in ("command", "shell", "deploy", "restart", "broker", "risk", "order", "codex")):
            count += 1
    return count


def build_summary(schema: dict[str, Any], action_preview: dict[str, Any]) -> dict[str, Any]:
    methods = route_methods(schema)
    endpoint_count = len(methods)
    protected_count = sum(
        1
        for path in PROTECTED_ENDPOINTS
        if schema.get("paths", {}).get(path, {}).get("get", {}).get("security") == [{SECURITY_SCHEME_NAME: []}]
    )
    public_count = sum(
        1
        for path in PUBLIC_ENDPOINTS
        if path in schema.get("paths", {}) and "security" not in schema["paths"][path].get("get", {})
    )
    unsafe_count = unsafe_endpoint_count(schema)
    return {
        "schema": "titan.echo.openapi_schema_summary.v1",
        "timestamp_ist": timestamp_ist(),
        "endpoint_count": endpoint_count,
        "protected_endpoint_count": protected_count,
        "public_endpoint_count": public_count,
        "unsafe_endpoint_count": unsafe_count,
        "auth_scheme": {
            "name": SECURITY_SCHEME_NAME,
            "type": "apiKey",
            "header_name": HEADER_NAME,
            "environment_variable_name": ENV_VAR_NAME,
            "real_key_included": False,
        },
        "chatgpt_action_preview_status": action_preview["status"],
        "blocked_endpoints": list(BLOCKED_ENDPOINTS),
        "safety": {
            "schema_documentation_only": True,
            "server_started": False,
            "uvicorn_run": False,
            "public_port_exposed": False,
            "deploy": False,
            "push": False,
            "restart": False,
            "real_api_key_read_or_written": False,
            "env_file_reading": False,
            "command_endpoints": False,
            "post_execution_endpoints": False,
            "scanner_master_unified_broker_risk_changes": False,
            "writes_only": [
                relative(OPENAPI_PATH),
                relative(ACTION_PREVIEW_PATH),
                relative(SUMMARY_PATH),
            ],
        },
        "safety_result": "PASS" if unsafe_count == 0 else "FAIL",
        "next_recommended_step": "Review the authenticated OpenAPI schema locally, then run a localhost-only service readiness check before any HTTPS or connector exposure.",
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    openapi_schema = protect_openapi_schema(base_openapi_schema())
    openapi_schema["x-echo-auth-notes"] = {
        "protected_endpoints": list(PROTECTED_ENDPOINTS),
        "public_endpoints": list(PUBLIC_ENDPOINTS),
        "key_source": f"{ENV_VAR_NAME} environment variable",
        "real_key_included": False,
        "env_file_reading": False,
        "blocked_endpoints": list(BLOCKED_ENDPOINTS),
    }
    action_preview = make_action_preview(openapi_schema)
    summary = build_summary(openapi_schema, action_preview)
    write_echo_json(OPENAPI_PATH, openapi_schema)
    write_echo_json(ACTION_PREVIEW_PATH, action_preview)
    write_echo_json(SUMMARY_PATH, summary)
    return openapi_schema, action_preview, summary


def main() -> None:
    _, _, summary = generate_reports()
    print("ECHO OpenAPI schema export complete.")
    print(f"endpoint_count={summary['endpoint_count']}")
    print(f"protected_endpoint_count={summary['protected_endpoint_count']}")
    print(f"public_endpoint_count={summary['public_endpoint_count']}")
    print(f"unsafe_endpoint_count={summary['unsafe_endpoint_count']}")
    print(f"auth_scheme={summary['auth_scheme']['name']}:{summary['auth_scheme']['header_name']}")
    print(f"chatgpt_action_preview_status={summary['chatgpt_action_preview_status']}")
    print(f"safety_result={summary['safety_result']}")
    print(f"next_recommended_step={summary['next_recommended_step']}")
    if summary["safety_result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
