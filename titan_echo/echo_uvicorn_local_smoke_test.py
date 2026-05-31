"""Localhost-only uvicorn smoke test for authenticated ECHO API.

This script is intentionally narrow: it starts uvicorn on 127.0.0.1:8765 with
a temporary process environment key, performs GET checks, then stops the server
and confirms the port is closed.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
REPORT_PATH = ECHO_DIR / "echo_uvicorn_local_smoke_test.json"
IST = timezone(timedelta(hours=5, minutes=30))

HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"
HEADER_NAME = "X-ECHO-API-KEY"
ENV_VAR_NAME = "ECHO_API_KEY"
TEMP_KEY = "temporary-test-key"
WRONG_KEY = "wrong-temporary-test-key"


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
        raise ValueError("uvicorn local smoke test writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((HOST, PORT)) == 0


def wait_for_server(timeout_seconds: float = 10.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if port_open():
            return True
        time.sleep(0.1)
    return False


def request_get(path: str, params: dict[str, str] | None = None, key: str | None = None) -> dict[str, Any]:
    query = f"?{urlencode(params)}" if params else ""
    headers = {HEADER_NAME: key} if key is not None else {}
    request = Request(f"{BASE_URL}{path}{query}", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8", errors="ignore")
            parsed = json.loads(body) if body else None
            return {"status_code": response.status, "body": parsed}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        return {"status_code": exc.code, "body": parsed}
    except URLError as exc:
        return {"status_code": None, "body": None, "error": str(exc.reason)}


def run_case(
    name: str,
    path: str,
    expected_statuses: set[int],
    params: dict[str, str] | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    result = request_get(path, params=params, key=key)
    status_code = result.get("status_code")
    passed = status_code in expected_statuses
    body = result.get("body")
    if passed and status_code == 200:
        recorded_body = body
    elif isinstance(body, dict):
        recorded_body = {"detail": body.get("detail")}
    else:
        recorded_body = body
    return {
        "name": name,
        "method": "GET",
        "path": path,
        "params": params or {},
        "expected_statuses": sorted(expected_statuses),
        "status_code": status_code,
        "passed": passed,
        "response": recorded_body,
        "error": result.get("error"),
    }


def start_uvicorn() -> subprocess.Popen[str]:
    env = os.environ.copy()
    env[ENV_VAR_NAME] = TEMP_KEY
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "titan_echo.echo_api:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--workers",
        "1",
    ]
    return subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def stop_uvicorn(process: subprocess.Popen[str]) -> dict[str, Any]:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    time.sleep(0.5)
    stdout = ""
    stderr = ""
    try:
        if process.stdout is not None:
            stdout = process.stdout.read()
        if process.stderr is not None:
            stderr = process.stderr.read()
    except Exception:
        stdout = ""
        stderr = ""
    return {
        "returncode": process.returncode,
        "server_stopped": process.poll() is not None,
        "port_closed_after_stop": not port_open(),
        "stdout_tail": stdout[-1000:],
        "stderr_tail": stderr[-1000:],
    }


def build_report() -> dict[str, Any]:
    preexisting_server = port_open()
    process: subprocess.Popen[str] | None = None
    startup_ready = False
    tests: list[dict[str, Any]] = []
    stop_result: dict[str, Any] = {
        "server_stopped": False,
        "port_closed_after_stop": not preexisting_server,
    }
    safety_failures: list[str] = []
    if preexisting_server:
        safety_failures.append("port 8765 was already open before test")
    try:
        if not preexisting_server:
            process = start_uvicorn()
            startup_ready = wait_for_server()
            if not startup_ready:
                safety_failures.append("uvicorn did not become ready on 127.0.0.1:8765")
            else:
                tests = [
                    run_case("GET /health without key", "/health", {200}),
                    run_case("GET /answer without key", "/answer", {401, 403}),
                    run_case("GET /answer with key", "/answer", {200}, key=TEMP_KEY),
                    run_case(
                        "GET /query?intent=status with key",
                        "/query",
                        {200},
                        params={"intent": "status"},
                        key=TEMP_KEY,
                    ),
                    run_case(
                        "GET /query?intent=what_next with key",
                        "/query",
                        {200},
                        params={"intent": "what_next"},
                        key=TEMP_KEY,
                    ),
                    run_case("wrong key", "/answer", {401, 403}, key=WRONG_KEY),
                ]
    finally:
        if process is not None:
            stop_result = stop_uvicorn(process)

    passed = [test["name"] for test in tests if test.get("passed")]
    failed = [test["name"] for test in tests if not test.get("passed")]
    if failed:
        safety_failures.append("one or more local server GET tests failed")
    if tests and not all(test["method"] == "GET" for test in tests):
        safety_failures.append("non-GET test found")
    if stop_result.get("server_stopped") is not True:
        safety_failures.append("server process was not stopped")
    if stop_result.get("port_closed_after_stop") is not True:
        safety_failures.append("port 8765 remained open after stop")
    auth_without_key = next((test for test in tests if test["name"] == "GET /answer without key"), {})
    auth_with_key = next((test for test in tests if test["name"] == "GET /answer with key"), {})
    wrong_key = next((test for test in tests if test["name"] == "wrong key"), {})
    auth_result = (
        "PASS"
        if auth_without_key.get("status_code") in {401, 403}
        and auth_with_key.get("status_code") == 200
        and wrong_key.get("status_code") in {401, 403}
        else "FAIL"
    )
    if auth_result != "PASS":
        safety_failures.append("auth behavior did not pass")
    local_server_smoke_result = "PASS" if startup_ready and not failed and not safety_failures else "FAIL"
    return {
        "schema": "titan.echo.uvicorn_local_smoke_test.v1",
        "timestamp_ist": timestamp_ist(),
        "localhost_only": True,
        "bind_host": HOST,
        "port": PORT,
        "base_url": BASE_URL,
        "uvicorn_started": process is not None,
        "uvicorn_command_recorded": "python -m uvicorn titan_echo.echo_api:app --host 127.0.0.1 --port 8765 --workers 1",
        "preexisting_server_on_port": preexisting_server,
        "startup_ready": startup_ready,
        "tests": tests,
        "tests_passed": len(passed),
        "tests_failed": len(failed),
        "passed_test_names": passed,
        "failed_test_names": failed,
        "auth_result": auth_result,
        "server_stop": stop_result,
        "server_stopped_confirmation": stop_result.get("server_stopped") is True
        and stop_result.get("port_closed_after_stop") is True,
        "real_key_written": False,
        "temporary_key_source": "process environment only",
        "safety": {
            "bind_127_0_0_1_only": True,
            "bind_0_0_0_0": False,
            "public_exposure": False,
            "deploy": False,
            "push": False,
            "restart": False,
            "command_endpoints": False,
            "post_command_endpoints": False,
            "scanner_master_unified_broker_risk_changes": False,
            "real_secret_written": False,
            "server_stopped_after_test": stop_result.get("server_stopped") is True,
            "port_closed_after_stop": stop_result.get("port_closed_after_stop") is True,
            "writes_only": [relative(REPORT_PATH)],
        },
        "safety_failures": safety_failures,
        "local_server_smoke_result": local_server_smoke_result,
        "safety_result": "PASS" if not safety_failures else "FAIL",
        "next_recommended_step": "Prepare VPS localhost-only deployment plan; do not expose public HTTPS or connect ChatGPT Action yet.",
    }


def generate_report() -> dict[str, Any]:
    report = build_report()
    write_echo_json(REPORT_PATH, report)
    return report


def main() -> None:
    report = generate_report()
    print("ECHO uvicorn localhost smoke test complete.")
    print(f"local_server_smoke_result={report['local_server_smoke_result']}")
    print(f"auth_result={report['auth_result']}")
    print(f"server_stopped_confirmation={report['server_stopped_confirmation']}")
    print(f"safety_result={report['safety_result']}")
    print(f"next_recommended_step={report['next_recommended_step']}")
    if report["safety_failures"]:
        print("safety_failures=" + "; ".join(report["safety_failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
