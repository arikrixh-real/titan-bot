"""Local-only smoke test for ECHO fallback API functions.

This file imports and calls safe local functions directly. It does not start a
server, install dependencies, expose ports, or modify runtime behavior.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan_echo import echo_api


ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
REPORT_PATH = ECHO_DIR / "echo_local_smoke_test.json"
SUMMARY_PATH = ECHO_DIR / "echo_local_smoke_test_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

QUERY_INTENTS = (
    "status",
    "runtime",
    "scanner",
    "workers",
    "unified_brain",
    "what_next",
    "what_not_to_do",
    "unknown_test",
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
        raise ValueError("local smoke test writes only under data/runtime/echo")
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


def has_evidence_or_safe_fallback(name: str, payload: dict[str, Any]) -> bool:
    if name == "get_health":
        return payload.get("read_only") is True and payload.get("public_exposure") is False
    if "evidence_files" in payload:
        return True
    if payload.get("source") or payload.get("fallback_source"):
        data = payload.get("data")
        if isinstance(data, dict) and data.get("evidence_used"):
            return True
        if payload.get("status") in {"EVIDENCE_PRESENT", "UNKNOWN"}:
            return True
    return False


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


def run_case(name: str, function: Callable[..., dict[str, Any]], *args: str) -> dict[str, Any]:
    function_exists = callable(function)
    payload: Any = None
    errors: list[str] = []
    if not function_exists:
        errors.append("function missing")
    else:
        try:
            payload = function(*args)
        except Exception as exc:  # pragma: no cover - captured in report
            errors.append(f"function raised {exc.__class__.__name__}: {exc}")
    returns_dict = isinstance(payload, dict)
    safe_payload = sanitize(payload) if returns_dict else payload
    if not returns_dict:
        errors.append("return value is not a JSON object/dict")
    elif not has_evidence_or_safe_fallback(name, safe_payload):
        errors.append("no evidence_used/source metadata or safe fallback marker")
    if returns_dict and contains_exposed_secret(safe_payload):
        errors.append("secret-like key was not redacted")
    if name == "get_query_unknown_test":
        if safe_payload.get("resolved_intent") != "unknown":
            errors.append("unknown intent did not resolve safely to unknown")
        data = safe_payload.get("data")
        if not isinstance(data, dict) or data.get("confidence") != "LOW":
            errors.append("unknown intent did not return low-confidence fallback")
    return {
        "name": name,
        "function_exists": function_exists,
        "returns_dict": returns_dict,
        "has_evidence_or_safe_fallback": returns_dict and has_evidence_or_safe_fallback(name, safe_payload),
        "exposes_secrets": returns_dict and contains_exposed_secret(safe_payload),
        "passed": not errors,
        "errors": errors,
        "sample": safe_payload,
    }


def build_report() -> dict[str, Any]:
    tests = [
        run_case("get_health", getattr(echo_api, "get_health", None)),
        run_case("get_status", getattr(echo_api, "get_status", None)),
        run_case("get_answer", getattr(echo_api, "get_answer", None)),
    ]
    for intent in QUERY_INTENTS:
        tests.append(
            run_case(
                f"get_query_{intent}",
                getattr(echo_api, "get_query", None),
                intent,
            )
        )
    passed = [test["name"] for test in tests if test["passed"]]
    failed = [test["name"] for test in tests if not test["passed"]]
    answer_sample = next(test["sample"] for test in tests if test["name"] == "get_answer")
    what_next_sample = next(test["sample"] for test in tests if test["name"] == "get_query_what_next")
    return {
        "schema": "titan.echo.local_smoke_test.v1",
        "timestamp_ist": timestamp_ist(),
        "api_mode": echo_api.get_health().get("api_mode"),
        "fastapi_available": echo_api.get_health().get("fastapi_available"),
        "local_only": True,
        "server_started": False,
        "tests": tests,
        "tests_passed": len(passed),
        "tests_failed": len(failed),
        "passed_test_names": passed,
        "failed_test_names": failed,
        "sample_get_answer_output": answer_sample,
        "sample_get_query_what_next_output": what_next_sample,
        "safety": {
            "read_only": True,
            "command_execution": False,
            "codex_execution": False,
            "shell_execution": False,
            "server_started": False,
            "uvicorn_started": False,
            "fastapi_install": False,
            "deploy": False,
            "push": False,
            "restart": False,
            "public_exposure": False,
            "broker_risk_scanner_changes": False,
            "master_unified_brain_changes": False,
            "writes_only": [
                relative(REPORT_PATH),
                relative(SUMMARY_PATH),
            ],
        },
        "safety_result": "PASS" if not failed else "FAIL",
        "next_recommended_step": "Keep ECHO in local fallback mode; next consider a local-only FastAPI dependency review before any install or server smoke test.",
    }


def build_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "titan.echo.local_smoke_test_summary.v1",
        "timestamp_ist": report["timestamp_ist"],
        "api_mode": report["api_mode"],
        "fastapi_available": report["fastapi_available"],
        "tests_passed": report["tests_passed"],
        "tests_failed": report["tests_failed"],
        "safety_result": report["safety_result"],
        "sample_get_answer_output": report["sample_get_answer_output"],
        "sample_get_query_what_next_output": report["sample_get_query_what_next_output"],
        "next_recommended_step": report["next_recommended_step"],
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    report = build_report()
    summary = build_summary(report)
    write_echo_json(REPORT_PATH, report)
    write_echo_json(SUMMARY_PATH, summary)
    return report, summary


def main() -> None:
    report, _ = generate_reports()
    print("ECHO local smoke test complete.")
    print(f"tests_passed={report['tests_passed']}")
    print(f"tests_failed={report['tests_failed']}")
    print(f"sample_get_answer_output={json.dumps(report['sample_get_answer_output'], sort_keys=True)}")
    print(f"sample_get_query_what_next_output={json.dumps(report['sample_get_query_what_next_output'], sort_keys=True)}")
    print(f"safety_result={report['safety_result']}")
    print(f"next_recommended_step={report['next_recommended_step']}")
    if report["tests_failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
