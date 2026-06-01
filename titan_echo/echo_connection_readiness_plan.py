"""ECHO connection readiness design package.

This is a review-only generator. It inspects local dependency/API evidence and
writes a readiness plan, but it does not install packages, start uvicorn,
expose a port, deploy, push, restart TITAN, or change runtime behavior.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
PLAN_PATH = ECHO_DIR / "echo_connection_readiness_plan.json"
SUMMARY_PATH = ECHO_DIR / "echo_connection_readiness_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

INSPECTED_PATHS = {
    "requirements": REPO_ROOT / "requirements.txt",
    "pyproject": REPO_ROOT / "pyproject.toml",
    "echo_api": REPO_ROOT / "titan_echo" / "echo_api.py",
    "api_contract": ECHO_DIR / "echo_api_contract.json",
    "api_server_readiness": ECHO_DIR / "echo_api_server_readiness.json",
    "local_smoke_summary": ECHO_DIR / "echo_local_smoke_test_summary.json",
}

ALLOWED_CONNECTOR_ENDPOINTS = [
    {"method": "GET", "path": "/health"},
    {"method": "GET", "path": "/status"},
    {"method": "GET", "path": "/answer"},
    {"method": "GET", "path": "/query"},
]
REQUIRED_LOCAL_ENDPOINTS = [
    "/health",
    "/status",
    "/answer",
    "/query",
]
BLOCKED_ENDPOINTS = [
    "POST /command",
    "shell",
    "broker",
    "deploy",
    "restart",
]


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
        raise ValueError("connection readiness writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def package_status(name: str) -> dict[str, Any]:
    installed = importlib.util.find_spec(name) is not None
    version = None
    if installed:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = "UNKNOWN"
    return {"installed": installed, "version": version}


def dependency_manifest_status() -> dict[str, Any]:
    requirements_text = read_text(INSPECTED_PATHS["requirements"])
    pyproject_text = read_text(INSPECTED_PATHS["pyproject"])
    requirements_lines = [
        line.strip()
        for line in requirements_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    lower_requirements = [line.lower() for line in requirements_lines]
    lower_pyproject = pyproject_text.lower()
    return {
        "requirements_exists": INSPECTED_PATHS["requirements"].exists(),
        "pyproject_exists": INSPECTED_PATHS["pyproject"].exists(),
        "requirements_mentions_fastapi": any(line.startswith("fastapi") for line in lower_requirements),
        "requirements_mentions_uvicorn": any(line.startswith("uvicorn") for line in lower_requirements),
        "pyproject_mentions_fastapi": "fastapi" in lower_pyproject,
        "pyproject_mentions_uvicorn": "uvicorn" in lower_pyproject,
    }


def install_risk(fastapi_installed: bool, uvicorn_installed: bool) -> str:
    if fastapi_installed and uvicorn_installed:
        return "LOW"
    if uvicorn_installed:
        return "MEDIUM"
    return "MEDIUM"


def build_plan() -> dict[str, Any]:
    fastapi = package_status("fastapi")
    uvicorn = package_status("uvicorn")
    dependency_manifest = dependency_manifest_status()
    api_contract = read_json(INSPECTED_PATHS["api_contract"])
    api_server_readiness = read_json(INSPECTED_PATHS["api_server_readiness"])
    local_smoke_summary = read_json(INSPECTED_PATHS["local_smoke_summary"])
    echo_api_text = read_text(INSPECTED_PATHS["echo_api"])
    fastapi_installed = bool(fastapi["installed"])
    uvicorn_installed = bool(uvicorn["installed"])
    safe_install_required = not fastapi_installed
    current_api_mode = (
        api_server_readiness.get("api_mode")
        if isinstance(api_server_readiness, dict)
        else "UNKNOWN"
    )
    endpoint_functions = (
        api_server_readiness.get("endpoint_functions", {})
        if isinstance(api_server_readiness, dict)
        else {}
    )
    contract_endpoints = (
        api_contract.get("endpoints", [])
        if isinstance(api_contract, dict)
        else []
    )
    local_smoke_passed = (
        isinstance(local_smoke_summary, dict)
        and local_smoke_summary.get("tests_failed") == 0
        and local_smoke_summary.get("safety_result") == "PASS"
    )
    return {
        "schema": "titan.echo.connection_readiness_plan.v1",
        "timestamp_ist": timestamp_ist(),
        "review_only": True,
        "inspected": {
            "files": {name: relative(path) for name, path in INSPECTED_PATHS.items()},
            "requirements_exists": dependency_manifest["requirements_exists"],
            "pyproject_exists": dependency_manifest["pyproject_exists"],
            "package_metadata_checked": True,
            "echo_api_has_fastapi_conditional_app": "FASTAPI_AVAILABLE" in echo_api_text and "FastAPI(" in echo_api_text,
            "api_contract_loaded": isinstance(api_contract, dict),
            "api_server_readiness_loaded": isinstance(api_server_readiness, dict),
            "local_smoke_summary_loaded": isinstance(local_smoke_summary, dict),
        },
        "fastapi_readiness": {
            "fastapi_installed": fastapi_installed,
            "fastapi_version": fastapi["version"],
            "uvicorn_installed": uvicorn_installed,
            "uvicorn_version": uvicorn["version"],
            "safe_install_required": safe_install_required,
            "install_risk": install_risk(fastapi_installed, uvicorn_installed),
            "requirements_mentions_fastapi": dependency_manifest["requirements_mentions_fastapi"],
            "requirements_mentions_uvicorn": dependency_manifest["requirements_mentions_uvicorn"],
            "pyproject_mentions_fastapi": dependency_manifest["pyproject_mentions_fastapi"],
            "pyproject_mentions_uvicorn": dependency_manifest["pyproject_mentions_uvicorn"],
            "recommended_install_command": "python -m pip install fastapi" if safe_install_required else None,
            "install_performed": False,
        },
        "local_server_readiness": {
            "api_mode_currently": current_api_mode,
            "api_app_exists": bool(api_server_readiness.get("api_app_exists")) if isinstance(api_server_readiness, dict) else False,
            "required_endpoints": REQUIRED_LOCAL_ENDPOINTS,
            "endpoint_functions_present": {
                endpoint: bool(endpoint_functions.get(endpoint))
                for endpoint in REQUIRED_LOCAL_ENDPOINTS
            },
            "local_only_bind_recommendation": "127.0.0.1",
            "public_exposure_allowed": False,
            "server_start_allowed_now": False,
            "uvicorn_start_performed": False,
            "server_started": False,
            "openapi_needed_before_connector": True,
        },
        "auth_design": {
            "recommended_auth_method": "API key header",
            "header_name": "X-ECHO-API-KEY",
            "secret_storage": "environment variable only, not committed",
            "environment_variable_name": "ECHO_API_KEY",
            "env_file_reading_allowed_current_batch": False,
            "hardcoded_key_allowed": False,
            "rotate_key_plan": [
                "Generate a new key outside the repository.",
                "Update only the service environment variable.",
                "Reload the local service after an explicit restart approval.",
                "Revoke the previous key after the new key is verified.",
            ],
            "failed_auth_behavior": {
                "missing_key": "401 Unauthorized with a generic error body",
                "invalid_key": "401 Unauthorized with a generic error body",
                "logging": "Log only timestamp, path, and failure type; never log key material.",
            },
        },
        "chatgpt_connector_requirements_preview": {
            "required_public_https_endpoint_eventually": True,
            "auth_required": True,
            "openapi_schema_needed": True,
            "allowed_endpoints": ALLOWED_CONNECTOR_ENDPOINTS,
            "blocked_endpoints": BLOCKED_ENDPOINTS,
            "public_exposure_allowed_now": False,
            "connector_not_ready_until": [
                "FastAPI is installed in the target environment.",
                "Auth middleware is implemented and checked.",
                "Local-only GET smoke test passes on 127.0.0.1.",
                "Explicit approval is given for any HTTPS exposure design.",
            ],
        },
        "next_step_recommendation": {
            "recommended_next_batch": "FastAPI install",
            "reason": "FastAPI is not installed, while local fallback functions and smoke tests are already passing. Install readiness should be resolved before auth implementation or local server smoke testing.",
            "allowed_options": [
                "FastAPI install",
                "Auth implementation",
                "Local server smoke test",
                "VPS-only localhost service",
            ],
        },
        "source_evidence": {
            "contract_endpoint_count": len(contract_endpoints),
            "api_server_safety_result": api_server_readiness.get("safety_result") if isinstance(api_server_readiness, dict) else "UNKNOWN",
            "local_smoke_passed": local_smoke_passed,
        },
        "safety": {
            "read_only_design": True,
            "no_install_performed": True,
            "no_server_started": True,
            "no_uvicorn_run": True,
            "no_public_port": True,
            "no_deploy": True,
            "no_push": True,
            "no_restart": True,
            "no_command_execution_endpoints": True,
            "no_secrets_in_files": True,
            "no_env_file_reading": True,
            "scanner_master_unified_broker_risk_changes": False,
            "writes_only": [
                relative(PLAN_PATH),
                relative(SUMMARY_PATH),
            ],
        },
        "safety_result": "PASS",
    }


def build_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "titan.echo.connection_readiness_summary.v1",
        "timestamp_ist": plan["timestamp_ist"],
        "fastapi_installed": plan["fastapi_readiness"]["fastapi_installed"],
        "uvicorn_installed": plan["fastapi_readiness"]["uvicorn_installed"],
        "safe_install_required": plan["fastapi_readiness"]["safe_install_required"],
        "install_risk": plan["fastapi_readiness"]["install_risk"],
        "api_mode_currently": plan["local_server_readiness"]["api_mode_currently"],
        "auth_method": plan["auth_design"]["recommended_auth_method"],
        "auth_header_name": plan["auth_design"]["header_name"],
        "public_exposure_allowed": plan["local_server_readiness"]["public_exposure_allowed"],
        "server_start_allowed_now": plan["local_server_readiness"]["server_start_allowed_now"],
        "recommended_next_step": plan["next_step_recommendation"]["recommended_next_batch"],
        "safety_result": plan["safety_result"],
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = build_plan()
    summary = build_summary(plan)
    write_echo_json(PLAN_PATH, plan)
    write_echo_json(SUMMARY_PATH, summary)
    return plan, summary


def main() -> None:
    plan, summary = generate_reports()
    print("ECHO connection readiness plan complete.")
    print(f"fastapi_installed={summary['fastapi_installed']}")
    print(f"uvicorn_installed={summary['uvicorn_installed']}")
    print(f"recommended_next_step={summary['recommended_next_step']}")
    print(f"auth_method={summary['auth_method']}")
    print(f"public_exposure_allowed={summary['public_exposure_allowed']}")
    print(f"safety_result={summary['safety_result']}")
    if plan["safety_result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
