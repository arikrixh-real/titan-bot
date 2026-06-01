"""Local in-process FastAPI GET smoke test for ECHO.

This test uses FastAPI TestClient only. It does not run uvicorn, bind a
network socket, expose a public port, deploy, push, restart TITAN, or mutate
scanner/Master Brain/Unified Brain/broker/risk behavior.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo import echo_api


ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
REPORT_PATH = ECHO_DIR / "echo_fastapi_local_smoke_test.json"
SUMMARY_PATH = ECHO_DIR / "echo_fastapi_local_smoke_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

GET_CASES = (
    {"name": "GET /health", "path": "/health", "params": {}},
    {"name": "GET /status", "path": "/status", "params": {}},
    {"name": "GET /answer", "path": "/answer", "params": {}},
    {"name": "GET /query?intent=status", "path": "/query", "params": {"intent": "status"}},
    {"name": "GET /query?intent=unified_brain", "path": "/query", "params": {"intent": "unified_brain"}},
    {"name": "GET /query?intent=what_next", "path": "/query", "params": {"intent": "what_next"}},
    {"name": "GET /query?intent=unknown_test", "path": "/query", "params": {"intent": "unknown_test"}},
)
SECRET_MARKERS = (
    "api_key",
    "apikey",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


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
        raise ValueError("FastAPI local smoke test writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key).lower()
            if any(marker in text_key for marker in SECRET_MARKERS):
                clean[key] = "REDACTED"
            else:
                clean[key] = sanitize(item)
        return clean
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def contains_exposed_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            text_key = str(key).lower()
            if any(marker in text_key for marker in SECRET_MARKERS) and item != "REDACTED":
                return True
            if contains_exposed_secret(item):
                return True
    elif isinstance(value, list):
        return any(contains_exposed_secret(item) for item in value)
    return False


def route_methods() -> dict[str, list[str]]:
    methods_by_path: dict[str, set[str]] = {}
    app = getattr(echo_api, "app", None)
    if app is None:
        return {}
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if not path or path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        methods_by_path.setdefault(path, set()).update(str(method) for method in methods)
    return {path: sorted(methods) for path, methods in sorted(methods_by_path.items())}


def make_client() -> Any:
    if importlib.util.find_spec("fastapi") is None:
        raise RuntimeError("fastapi is not installed")
    if getattr(echo_api, "app", None) is None:
        raise RuntimeError("echo_api.app is not available")
    from fastapi.testclient import TestClient

    return TestClient(echo_api.app, base_url="http://127.0.0.1")


def run_case(client: Any, case: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    payload: Any = None
    status_code: int | None = None
    try:
        response = client.get(case["path"], params=case["params"])
        status_code = response.status_code
        payload = response.json()
    except Exception as exc:  # pragma: no cover - captured in report
        errors.append(f"GET request raised {exc.__class__.__name__}: {exc}")
    if status_code != 200:
        errors.append(f"expected HTTP 200, got {status_code}")
    returns_dict = isinstance(payload, dict)
    if not returns_dict:
        errors.append("response body is not a JSON object/dict")
    safe_payload = sanitize(payload) if returns_dict else payload
    if returns_dict and contains_exposed_secret(safe_payload):
        errors.append("secret-like response key was not redacted")
    if case["name"] == "GET /query?intent=unknown_test":
        if safe_payload.get("resolved_intent") != "unknown":
            errors.append("unknown_test did not resolve to unknown")
    return {
        "name": case["name"],
        "method": "GET",
        "path": case["path"],
        "params": case["params"],
        "status_code": status_code,
        "returns_dict": returns_dict,
        "exposes_secrets": returns_dict and contains_exposed_secret(safe_payload),
        "passed": not errors,
        "errors": errors,
        "response": safe_payload,
    }


def build_report() -> dict[str, Any]:
    app_exists = getattr(echo_api, "app", None) is not None
    fastapi_available = bool(getattr(echo_api, "FASTAPI_AVAILABLE", False))
    tests: list[dict[str, Any]] = []
    setup_errors: list[str] = []
    client = None
    try:
        client = make_client()
    except Exception as exc:
        setup_errors.append(f"TestClient unavailable: {exc}")
    if client is not None:
        tests = [run_case(client, case) for case in GET_CASES]
    else:
        tests = [
            {
                "name": case["name"],
                "method": "GET",
                "path": case["path"],
                "params": case["params"],
                "status_code": None,
                "returns_dict": False,
                "exposes_secrets": False,
                "passed": False,
                "errors": setup_errors,
                "response": None,
            }
            for case in GET_CASES
        ]

    methods = route_methods()
    non_get_routes = [
        {"path": path, "methods": route_method_list}
        for path, route_method_list in methods.items()
        if any(method != "GET" for method in route_method_list)
    ]
    passed = [test["name"] for test in tests if test["passed"]]
    failed = [test["name"] for test in tests if not test["passed"]]
    answer_sample = next((test["response"] for test in tests if test["name"] == "GET /answer"), None)
    what_next_sample = next((test["response"] for test in tests if test["name"] == "GET /query?intent=what_next"), None)
    safety_failures: list[str] = []
    if not fastapi_available:
        safety_failures.append("FastAPI is not available")
    if not app_exists:
        safety_failures.append("echo_api.app is not available")
    if non_get_routes:
        safety_failures.append("non-GET FastAPI route found")
    if failed:
        safety_failures.append("one or more GET smoke tests failed")
    return {
        "schema": "titan.echo.fastapi_local_smoke_test.v1",
        "timestamp_ist": timestamp_ist(),
        "local_only": True,
        "transport": "fastapi_testclient_in_process",
        "base_url": "http://127.0.0.1",
        "bind_host": "127.0.0.1",
        "server_started": False,
        "uvicorn_used": False,
        "fastapi_available": fastapi_available,
        "app_exists": app_exists,
        "route_methods": methods,
        "non_get_routes": non_get_routes,
        "tests": tests,
        "tests_passed": len(passed),
        "tests_failed": len(failed),
        "passed_test_names": passed,
        "failed_test_names": failed,
        "setup_errors": setup_errors,
        "sample_answer_response": answer_sample,
        "sample_query_what_next_response": what_next_sample,
        "safety": {
            "localhost_only": True,
            "bind_only": "127.0.0.1",
            "public_exposure": False,
            "post_endpoints": False,
            "command_endpoints": False,
            "command_execution": False,
            "shell_execution": False,
            "uvicorn_used": False,
            "server_started": False,
            "deploy": False,
            "push": False,
            "restart": False,
            "scanner_master_unified_broker_risk_changes": False,
            "secrets_exposed": False,
            "writes_only": [
                relative(REPORT_PATH),
                relative(SUMMARY_PATH),
            ],
        },
        "safety_failures": safety_failures,
        "safety_result": "PASS" if not safety_failures else "FAIL",
    }


def build_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "titan.echo.fastapi_local_smoke_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "fastapi_available": report["fastapi_available"],
        "app_exists": report["app_exists"],
        "transport": report["transport"],
        "base_url": report["base_url"],
        "tests_passed": report["tests_passed"],
        "tests_failed": report["tests_failed"],
        "sample_answer_response": report["sample_answer_response"],
        "sample_query_what_next_response": report["sample_query_what_next_response"],
        "safety_result": report["safety_result"],
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    report = build_report()
    summary = build_summary(report)
    write_echo_json(REPORT_PATH, report)
    write_echo_json(SUMMARY_PATH, summary)
    return report, summary


def main() -> None:
    report, _ = generate_reports()
    print("ECHO FastAPI local smoke test complete.")
    print(f"tests_passed={report['tests_passed']}")
    print(f"tests_failed={report['tests_failed']}")
    print(f"sample_answer_response={json.dumps(report['sample_answer_response'], sort_keys=True)}")
    print(f"sample_query_what_next_response={json.dumps(report['sample_query_what_next_response'], sort_keys=True)}")
    print(f"safety_result={report['safety_result']}")
    if report["safety_result"] != "PASS":
        if report["safety_failures"]:
            print("safety_failures=" + "; ".join(report["safety_failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
