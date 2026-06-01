"""Localhost-only ECHO service readiness plan.

This script writes safe run instructions as text only. It does not execute
uvicorn, bind sockets, expose ports, deploy, push, restart TITAN, or write
secrets.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
READINESS_PATH = ECHO_DIR / "echo_localhost_service_readiness.json"
SUMMARY_PATH = ECHO_DIR / "echo_localhost_service_summary.json"
OPENAPI_SUMMARY_PATH = ECHO_DIR / "echo_openapi_schema_summary.json"
AUTH_SUMMARY_PATH = ECHO_DIR / "echo_api_auth_summary.json"
AUTH_SMOKE_PATH = ECHO_DIR / "echo_fastapi_auth_smoke_test.json"
IST = timezone(timedelta(hours=5, minutes=30))

ALLOWED_BIND_HOST = "127.0.0.1"
FORBIDDEN_BIND_HOSTS = ["0.0.0.0", "public IP"]
RECOMMENDED_PORT = 8765
AUTH_HEADER = "X-ECHO-API-KEY"
API_KEY_SOURCE = "environment variable ECHO_API_KEY"
ALLOWED_TEST_ENDPOINTS = [
    "/health",
    "/answer",
    "/query?intent=status",
    "/query?intent=what_next",
]
WINDOWS_RUN_TEXT = (
    '$env:ECHO_API_KEY="temporary-test-key"\n'
    "python -m uvicorn titan_echo.echo_api:app --host 127.0.0.1 --port 8765"
)
LINUX_RUN_TEXT = (
    'export ECHO_API_KEY="temporary-test-key"\n'
    "python -m uvicorn titan_echo.echo_api:app --host 127.0.0.1 --port 8765"
)


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("localhost service readiness writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_readiness() -> dict[str, Any]:
    openapi_summary = read_json(OPENAPI_SUMMARY_PATH)
    auth_summary = read_json(AUTH_SUMMARY_PATH)
    auth_smoke = read_json(AUTH_SMOKE_PATH)
    prerequisites = {
        "fastapi_app_ready": True,
        "auth_ready": isinstance(auth_summary, dict) and auth_summary.get("safety_result") == "PASS",
        "openapi_schema_ready": isinstance(openapi_summary, dict) and openapi_summary.get("safety_result") == "PASS",
        "auth_smoke_passed": isinstance(auth_smoke, dict) and auth_smoke.get("safety_result") == "PASS",
        "unsafe_endpoints": openapi_summary.get("unsafe_endpoint_count") if isinstance(openapi_summary, dict) else None,
    }
    failures: list[str] = []
    if prerequisites["auth_ready"] is not True:
        failures.append("auth summary is not ready")
    if prerequisites["openapi_schema_ready"] is not True:
        failures.append("OpenAPI summary is not ready")
    if prerequisites["auth_smoke_passed"] is not True:
        failures.append("auth smoke test is not passing")
    if prerequisites["unsafe_endpoints"] != 0:
        failures.append("unsafe endpoint count is not zero")
    return {
        "schema": "titan.echo.localhost_service_readiness.v1",
        "timestamp_ist": timestamp_ist(),
        "readiness_only": True,
        "allowed_bind_host": ALLOWED_BIND_HOST,
        "forbidden_bind_hosts": FORBIDDEN_BIND_HOSTS,
        "recommended_port": RECOMMENDED_PORT,
        "auth_required": True,
        "auth_header": AUTH_HEADER,
        "api_key_source": API_KEY_SOURCE,
        "real_key_written": False,
        "placeholder_key_text_allowed": "temporary-test-key",
        "reload_allowed": False,
        "workers_allowed": 1,
        "public_exposure_allowed": False,
        "allowed_test_endpoints": ALLOWED_TEST_ENDPOINTS,
        "safe_run_commands_text_only": {
            "windows_powershell": WINDOWS_RUN_TEXT,
            "linux_vps_bash": LINUX_RUN_TEXT,
            "stop_instruction": "CTRL+C",
            "executed": False,
        },
        "forbidden_actions": [
            "Do not run uvicorn until the next explicit smoke-test batch.",
            "Do not bind 0.0.0.0.",
            "Do not expose a public port.",
            "Do not deploy.",
            "Do not push.",
            "Do not restart TITAN.",
            "Do not add command endpoints.",
            "Do not add POST execution endpoints.",
            "Do not modify scanner/Master Brain/Unified Brain/broker/risk.",
            "Do not write real secrets.",
        ],
        "prerequisites": prerequisites,
        "safety": {
            "uvicorn_executed": False,
            "server_started": False,
            "socket_started": False,
            "public_port_exposed": False,
            "bind_0_0_0_0": False,
            "deploy": False,
            "push": False,
            "restart": False,
            "command_endpoints": False,
            "post_execution_endpoints": False,
            "scanner_master_unified_broker_risk_changes": False,
            "real_secret_written": False,
            "writes_only": [
                relative(READINESS_PATH),
                relative(SUMMARY_PATH),
            ],
        },
        "failures": failures,
        "safety_result": "PASS" if not failures else "FAIL",
        "next_recommended_step": "Next batch may run a localhost-only uvicorn smoke test on 127.0.0.1:8765 with a temporary session ECHO_API_KEY, if explicitly approved.",
    }


def build_summary(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "titan.echo.localhost_service_summary.v1",
        "timestamp_ist": readiness["timestamp_ist"],
        "allowed_bind_host": readiness["allowed_bind_host"],
        "recommended_port": readiness["recommended_port"],
        "auth_required": readiness["auth_required"],
        "auth_header": readiness["auth_header"],
        "public_exposure_allowed": readiness["public_exposure_allowed"],
        "reload_allowed": readiness["reload_allowed"],
        "workers_allowed": readiness["workers_allowed"],
        "safe_run_command_text_present": bool(readiness["safe_run_commands_text_only"]["windows_powershell"])
        and bool(readiness["safe_run_commands_text_only"]["linux_vps_bash"]),
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
    readiness, summary = generate_reports()
    print("ECHO localhost service readiness complete.")
    print(f"allowed_bind_host={summary['allowed_bind_host']}")
    print(f"recommended_port={summary['recommended_port']}")
    print(f"auth_required={summary['auth_required']}")
    print(f"public_exposure_allowed={summary['public_exposure_allowed']}")
    print(f"reload_allowed={summary['reload_allowed']}")
    print(f"safe_run_command_text_present={summary['safe_run_command_text_present']}")
    print(f"safety_result={summary['safety_result']}")
    print(f"next_recommended_step={summary['next_recommended_step']}")
    if readiness["failures"]:
        print("failures=" + "; ".join(readiness["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
