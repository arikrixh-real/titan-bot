"""Local TestClient smoke test for ECHO FastAPI API-key auth."""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from titan_echo import echo_api
from titan_echo.echo_api_auth import ENV_VAR_NAME, HEADER_NAME


ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
REPORT_PATH = ECHO_DIR / "echo_fastapi_auth_smoke_test.json"
IST = timezone(timedelta(hours=5, minutes=30))
TEST_KEY = "local-test-key"
WRONG_KEY = "wrong-test-key"


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
        raise ValueError("auth smoke test writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@contextmanager
def temporary_auth_key(value: str | None) -> Iterator[None]:
    had_previous = ENV_VAR_NAME in os.environ
    previous = os.environ.get(ENV_VAR_NAME)
    if value is None:
        os.environ.pop(ENV_VAR_NAME, None)
    else:
        os.environ[ENV_VAR_NAME] = value
    try:
        yield
    finally:
        if had_previous and previous is not None:
            os.environ[ENV_VAR_NAME] = previous
        else:
            os.environ.pop(ENV_VAR_NAME, None)


def make_client() -> TestClient:
    return TestClient(echo_api.app, base_url="http://127.0.0.1")


def run_case(
    client: TestClient,
    name: str,
    path: str,
    expected_statuses: set[int],
    env_key: str | None,
    header_key: str | None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    with temporary_auth_key(env_key):
        headers = {HEADER_NAME: header_key} if header_key is not None else {}
        response = client.get(path, params=params or {}, headers=headers)
    passed = response.status_code in expected_statuses
    body: Any
    try:
        body = response.json()
    except Exception:
        body = None
    return {
        "name": name,
        "method": "GET",
        "path": path,
        "params": params or {},
        "expected_statuses": sorted(expected_statuses),
        "status_code": response.status_code,
        "passed": passed,
        "response_shape": "dict" if isinstance(body, dict) else type(body).__name__,
        "response": body if passed and response.status_code == 200 else {"detail": body.get("detail") if isinstance(body, dict) else None},
    }


def build_report() -> dict[str, Any]:
    client = make_client()
    tests = [
        run_case(client, "/health without key", "/health", {200}, None, None),
        run_case(client, "/answer without key", "/answer", {401, 403}, None, None),
        run_case(client, "/query without key", "/query", {401, 403}, None, None, {"intent": "what_next"}),
        run_case(client, "/answer with test key", "/answer", {200}, TEST_KEY, TEST_KEY),
        run_case(client, "/query with test key", "/query", {200}, TEST_KEY, TEST_KEY, {"intent": "what_next"}),
        run_case(client, "wrong key", "/answer", {401, 403}, TEST_KEY, WRONG_KEY),
    ]
    passed = [test["name"] for test in tests if test["passed"]]
    failed = [test["name"] for test in tests if not test["passed"]]
    answer_with_key = next(test for test in tests if test["name"] == "/answer with test key")
    query_with_key = next(test for test in tests if test["name"] == "/query with test key")
    without_key = [test for test in tests if "without key" in test["name"] and test["path"] != "/health"]
    wrong_key = next(test for test in tests if test["name"] == "wrong key")
    safety_failures: list[str] = []
    if failed:
        safety_failures.append("one or more auth smoke tests failed")
    if any(test["status_code"] not in {401, 403} for test in without_key):
        safety_failures.append("auth without key did not fail closed")
    if wrong_key["status_code"] not in {401, 403}:
        safety_failures.append("wrong key did not fail closed")
    if answer_with_key["status_code"] != 200 or query_with_key["status_code"] != 200:
        safety_failures.append("test key did not authorize protected GET requests")
    return {
        "schema": "titan.echo.fastapi_auth_smoke_test.v1",
        "timestamp_ist": timestamp_ist(),
        "transport": "fastapi_testclient_in_process",
        "base_url": "http://127.0.0.1",
        "server_started": False,
        "uvicorn_used": False,
        "public_exposure": False,
        "test_key": "IN_MEMORY_ONLY_NOT_RECORDED",
        "tests": tests,
        "tests_passed": len(passed),
        "tests_failed": len(failed),
        "passed_test_names": passed,
        "failed_test_names": failed,
        "protected_endpoints": [
            "/status",
            "/projects",
            "/unified-brain",
            "/lineage",
            "/alerts",
            "/missions",
            "/answer",
            "/query",
        ],
        "public_endpoints": ["/health"],
        "auth_without_key_result": "FAIL_CLOSED" if not safety_failures[:1] else "FAIL",
        "auth_with_test_key_result": "PASS" if answer_with_key["status_code"] == 200 and query_with_key["status_code"] == 200 else "FAIL",
        "wrong_key_result": "FAIL_CLOSED" if wrong_key["status_code"] in {401, 403} else "FAIL",
        "sample_answer_response": answer_with_key["response"],
        "sample_query_what_next_response": query_with_key["response"],
        "safety": {
            "localhost_only": True,
            "bind_only": "127.0.0.1",
            "no_real_secret_written": True,
            "no_key_printed": True,
            "no_env_file_reading": True,
            "no_command_endpoints": True,
            "no_post_execution": True,
            "no_shell_execution": True,
            "no_uvicorn": True,
            "no_server_start": True,
            "no_public_bind": True,
            "no_deploy_push_restart": True,
            "scanner_master_unified_broker_risk_changes": False,
            "writes_only": [relative(REPORT_PATH)],
        },
        "safety_failures": safety_failures,
        "safety_result": "PASS" if not safety_failures else "FAIL",
        "next_recommended_step": "Document authenticated OpenAPI schema locally; do not expose a server until auth and localhost service checks are complete.",
    }


def generate_report() -> dict[str, Any]:
    report = build_report()
    write_echo_json(REPORT_PATH, report)
    return report


def main() -> None:
    report = generate_report()
    print("ECHO FastAPI auth smoke test complete.")
    print("protected_endpoints=" + ", ".join(report["protected_endpoints"]))
    print("public_endpoints=" + ", ".join(report["public_endpoints"]))
    print(f"auth_without_key_result={report['auth_without_key_result']}")
    print(f"auth_with_test_key_result={report['auth_with_test_key_result']}")
    print(f"wrong_key_result={report['wrong_key_result']}")
    print(f"safety_result={report['safety_result']}")
    print(f"next_recommended_step={report['next_recommended_step']}")
    if report["safety_failures"]:
        print("safety_failures=" + "; ".join(report["safety_failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
