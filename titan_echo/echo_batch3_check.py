"""Batch 3 checker for Custom GPT and secure relay integration foundation.

This checker is import-only and read-only. It does not start services, open
ports, call OpenAI, invoke git, deploy, restart, or execute TITAN runtime logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from titan_echo.echo_api import (
    app,
    get_chatgpt_action_catalog,
    get_chatgpt_conversation_status,
    get_chatgpt_custom_gpt_status,
    get_chatgpt_permissions,
    get_chatgpt_relay_readiness,
    get_chatgpt_session_status,
    get_chatgpt_voice_readiness,
)
from titan_echo.echo_api_auth import PROTECTED_ENDPOINTS
from titan_echo.echo_batch2_common import REPO_ROOT, echo_path


EXPECTED_SAFETY = {
    "codex_execution": False,
    "shell_execution": False,
    "git_push_pull": False,
    "deploy_or_restart": False,
    "titan_runtime_changed": False,
    "actual_execution_permitted": False,
    "broker_changed": False,
    "risk_changed": False,
    "scanner_changed": False,
    "master_brain_changed": False,
    "runtime_workers_changed": False,
    "trade_execution_permitted": False,
    "public_exposure_allowed": False,
    "external_api_calls_enabled": False,
    "chatgpt_connection_enabled": False,
    "voice_enabled": False,
}

EXPECTED_FILES = {
    "custom_gpt_contract": (echo_path("custom_gpt_contract.json"), "CUSTOM_GPT_CONTRACT_READY_DISABLED"),
    "action_registry": (echo_path("action_registry.json"), "ACTION_REGISTRY_READY_DISABLED"),
    "permission_matrix": (echo_path("permission_matrix.json"), "PERMISSION_MATRIX_READY_DISABLED"),
    "session_state": (echo_path("session_state.json"), "SESSION_STATE_LOCAL_ONLY"),
    "conversation_bridge": (echo_path("conversation_bridge.json"), "CONVERSATION_BRIDGE_READY_DISABLED"),
    "relay_readiness": (echo_path("relay_readiness.json"), {"RELAY_READY_LOCAL_ONLY", "PARTIAL_EVIDENCE", "UNKNOWN_NOT_PROVEN"}),
    "voice_readiness": (echo_path("voice_readiness.json"), "VOICE_NOT_ENABLED_FUTURE_ONLY"),
    "custom_gpt_openapi_skeleton": (
        echo_path("custom_gpt_openapi_skeleton.json"),
        "CUSTOM_GPT_OPENAPI_SKELETON_READY_DISABLED",
    ),
}

EXPECTED_ROUTES = {
    "/chatgpt/custom-gpt/status": get_chatgpt_custom_gpt_status,
    "/chatgpt/action/catalog": get_chatgpt_action_catalog,
    "/chatgpt/session/status": get_chatgpt_session_status,
    "/chatgpt/permissions": get_chatgpt_permissions,
    "/chatgpt/conversation/status": get_chatgpt_conversation_status,
    "/chatgpt/voice/readiness": get_chatgpt_voice_readiness,
    "/chatgpt/relay/readiness": get_chatgpt_relay_readiness,
}

FORBIDDEN_OPENAPI_PATH_PARTS = (
    "/approval/",
    "/broker",
    "/codex/runner",
    "/deploy",
    "/execution/",
    "/risk",
    "/rollback",
)


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore")), None
    except json.JSONDecodeError as exc:
        return None, f"malformed_json_line_{exc.lineno}"
    except OSError as exc:
        return None, f"read_error_{type(exc).__name__}"


def _status_allowed(status: Any, allowed: str | set[str]) -> bool:
    return status in allowed if isinstance(allowed, set) else status == allowed


def _safety_ok(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("safety") == EXPECTED_SAFETY


def _disabled_flags_ok(payload: dict[str, Any]) -> bool:
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    return all(safety.get(key) is False for key in EXPECTED_SAFETY)


def _route_map() -> dict[str, Any]:
    if app is None:
        return {}
    return {route.path: route for route in app.routes}


def _route_dependencies(route: Any) -> tuple[bool, list[str]]:
    dependency_attr = getattr(route, "dependencies", None)
    if dependency_attr is None:
        return False, []
    names = []
    for dependency in dependency_attr or []:
        call = getattr(dependency, "dependency", None)
        names.append(getattr(call, "__name__", str(call)))
    return True, names


def _response_ok(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    if set(response) != {"source", "status", "data", "safety"}:
        return False
    if response.get("safety") != EXPECTED_SAFETY:
        return False
    data = response.get("data")
    return data is None or _safety_ok(data)


def _openapi_skeleton_ok(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    skeleton = payload.get("openapi_skeleton")
    if not isinstance(skeleton, dict):
        return False
    paths = skeleton.get("paths")
    if not isinstance(paths, dict):
        return False
    for path in paths:
        if any(part in path for part in FORBIDDEN_OPENAPI_PATH_PARTS):
            return False
    return True


def run_check() -> dict[str, Any]:
    failures: list[str] = []
    file_results: dict[str, dict[str, Any]] = {}

    for name, (path, allowed_status) in EXPECTED_FILES.items():
        payload, error = _read_json(path)
        status = payload.get("status") if isinstance(payload, dict) else None
        ok = (
            isinstance(payload, dict)
            and error is None
            and _status_allowed(status, allowed_status)
            and _safety_ok(payload)
            and _disabled_flags_ok(payload)
        )
        if name == "custom_gpt_openapi_skeleton":
            ok = ok and _openapi_skeleton_ok(payload)
        file_results[name] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "exists": error is None,
            "status": status,
            "safety_ok": isinstance(payload, dict) and _safety_ok(payload),
        }
        if not ok:
            failures.append(f"{name} artifact invalid")

    missing_protected = sorted(route for route in EXPECTED_ROUTES if route not in PROTECTED_ENDPOINTS)
    failures.extend(f"{route} missing from PROTECTED_ENDPOINTS" for route in missing_protected)

    routes = _route_map()
    route_results: dict[str, dict[str, Any]] = {}
    for path in EXPECTED_ROUTES:
        route = routes.get(path)
        if route is None:
            failures.append(f"{path} missing from FastAPI app")
            continue
        methods = getattr(route, "methods", set()) or set()
        dependency_inspectable, dependencies = _route_dependencies(route)
        route_results[path] = {
            "methods": sorted(methods),
            "dependency_inspectable": dependency_inspectable,
            "dependencies": dependencies,
            "protected": "require_echo_api_key" in dependencies if dependency_inspectable else None,
        }
        if "GET" not in methods:
            failures.append(f"{path} missing GET method")
        if dependency_inspectable and "require_echo_api_key" not in dependencies:
            failures.append(f"{path} missing require_echo_api_key dependency")

    response_results: dict[str, dict[str, Any]] = {}
    for path, func in EXPECTED_ROUTES.items():
        response = func()
        ok = _response_ok(response)
        response_results[path] = {
            "status": response.get("status") if isinstance(response, dict) else None,
            "schema_ok": isinstance(response, dict) and set(response) == {"source", "status", "data", "safety"},
            "safety_ok": ok,
        }
        if not ok:
            failures.append(f"{path} response schema or safety invalid")

    report = {
        "schema": "titan.echo.batch3_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "files": file_results,
        "routes": route_results,
        "responses": response_results,
        "failures": failures,
        "safety": EXPECTED_SAFETY,
    }
    return report


def main() -> int:
    report = run_check()
    print(f"ECHO batch3 check: {report['status']}")
    print(f"Files checked: {len(report['files'])}")
    print(f"Routes checked: {len(EXPECTED_ROUTES)}")
    if report["failures"]:
        for failure in report["failures"]:
            print(f"FAIL: {failure}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
