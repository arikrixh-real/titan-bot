"""VPS localhost deployment plan and safety gate for ECHO.

Plan/readiness only. This script does not push, pull on VPS, start a server,
restart TITAN, expose a public port, bind 0.0.0.0, or write real API keys.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
PLAN_PATH = ECHO_DIR / "echo_vps_localhost_deployment_plan.json"
SUMMARY_PATH = ECHO_DIR / "echo_vps_localhost_deployment_summary.json"
BATCH9A_SUMMARY_PATH = ECHO_DIR / "echo_batch9a_summary.json"
VPS_READINESS_PATH = ECHO_DIR / "echo_vps_deployment_readiness_plan.json"
OPENAPI_SUMMARY_PATH = ECHO_DIR / "echo_openapi_schema_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

APPROVAL_PHRASE = "I_APPROVE_ECHO_VPS_LOCALHOST_TEST"
VPS_PATH = "/home/ubuntu/titan-bot"
VENV_PATH = "/home/ubuntu/titan-bot/.venv"
HOST = "127.0.0.1"
PORT = 8765
ENV_VAR = "ECHO_API_KEY"
AUTH_HEADER = "X-ECHO-API-KEY"


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
        raise ValueError("VPS localhost deployment plan writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_plan() -> dict[str, Any]:
    batch9a = read_json(BATCH9A_SUMMARY_PATH)
    vps_readiness = read_json(VPS_READINESS_PATH)
    openapi_summary = read_json(OPENAPI_SUMMARY_PATH)
    preflight_status = {
        "local_uvicorn_smoke_passed": isinstance(batch9a, dict)
        and batch9a.get("local_server_smoke_result") == "PASS",
        "auth_passed": isinstance(batch9a, dict) and batch9a.get("auth_result") == "PASS",
        "server_stopped": isinstance(batch9a, dict)
        and batch9a.get("server_stopped_confirmation") is True,
        "unsafe_endpoints_zero": isinstance(batch9a, dict)
        and batch9a.get("unsafe_endpoint_count") == 0
        and isinstance(openapi_summary, dict)
        and openapi_summary.get("unsafe_endpoint_count") == 0,
        "prior_vps_plan_ready": isinstance(vps_readiness, dict)
        and vps_readiness.get("vps_readiness_status") == "READY_FOR_VPS_LOCALHOST_PLANNING",
    }
    failures = [name for name, passed in preflight_status.items() if not passed]
    vps_localhost_test_ready = not failures
    return {
        "schema": "titan.echo.vps_localhost_deployment_plan.v1",
        "timestamp_ist": timestamp_ist(),
        "plan_only": True,
        "preflight_requirements": {
            "vps_path": VPS_PATH,
            "python_venv_path": VENV_PATH,
            "required_packages": ["fastapi", "uvicorn"],
            "required_env_var": ENV_VAR,
            "bind_host": f"{HOST} only",
            "port": PORT,
        },
        "safe_transfer_options": {
            "preferred": "GitHub push/pull only after approval",
            "alternative": "manual file transfer only if approved",
            "secret_rule": "never copy secrets into repo",
            "push_performed": False,
            "pull_on_vps_performed": False,
            "manual_transfer_performed": False,
        },
        "vps_local_test_command_text_only": {
            "set_env": 'export ECHO_API_KEY="temporary-test-key"',
            "run": "python -m uvicorn titan_echo.echo_api:app --host 127.0.0.1 --port 8765",
            "executed": False,
        },
        "vps_test_urls_text_only": [
            "http://127.0.0.1:8765/health",
            "http://127.0.0.1:8765/answer",
            "http://127.0.0.1:8765/query?intent=status",
        ],
        "auth_test_plan": [
            "/health without key should pass",
            f"/answer without key should fail",
            f"/answer with {AUTH_HEADER} should pass",
            f"/query with {AUTH_HEADER} should pass",
            "wrong key should fail",
        ],
        "forbidden_actions": [
            "no 0.0.0.0 bind",
            "no public IP bind",
            "no nginx yet",
            "no Cloudflare tunnel yet",
            "no HTTPS yet",
            "no ChatGPT Action yet",
            "no Codex executor yet",
            "no deploy automation yet",
            "no GitHub push before approval",
            "no VPS pull before approval",
            "no TITAN restart",
            "no broker/risk/scanner/Master Brain/Unified Brain changes",
            "no real API keys in files",
        ],
        "approval_gate": {
            "approval_required": True,
            "required_approval_phrase": APPROVAL_PHRASE,
            "approved_now": False,
            "vps_localhost_test_ready": vps_localhost_test_ready,
            "public_exposure_allowed": False,
            "chatgpt_connection_allowed": False,
            "codex_execution_allowed": False,
        },
        "rollback_stop_plan": {
            "manual_test_stop": "CTRL+C",
            "systemd_service_allowed": False,
            "auto_start_allowed": False,
            "restart_titan_allowed": False,
        },
        "preflight_status": preflight_status,
        "safety": {
            "documentation_readiness_only": True,
            "push_github": False,
            "pull_on_vps": False,
            "vps_server_started": False,
            "titan_restart": False,
            "public_port_exposed": False,
            "bind_0_0_0_0": False,
            "broker_risk_scanner_master_unified_changes": False,
            "real_api_key_written": False,
            "vps_commands_executed": False,
            "deploy_automation": False,
            "command_endpoints": False,
            "post_execution_endpoints": False,
            "writes_only": [
                relative(PLAN_PATH),
                relative(SUMMARY_PATH),
            ],
        },
        "failures": failures,
        "safety_result": "PASS" if not failures else "FAIL",
        "next_recommended_step": (
            f"Wait for Ari to explicitly approve {APPROVAL_PHRASE}; only then run a VPS localhost-only test on "
            "127.0.0.1:8765 with a temporary VPS session ECHO_API_KEY."
        ),
    }


def build_summary(plan: dict[str, Any]) -> dict[str, Any]:
    gate = plan["approval_gate"]
    return {
        "schema": "titan.echo.vps_localhost_deployment_summary.v1",
        "timestamp_ist": plan["timestamp_ist"],
        "vps_localhost_test_ready": gate["vps_localhost_test_ready"],
        "approval_required": gate["approval_required"],
        "required_approval_phrase": gate["required_approval_phrase"],
        "bind_host": HOST,
        "port": PORT,
        "public_exposure_allowed": gate["public_exposure_allowed"],
        "chatgpt_connection_allowed": gate["chatgpt_connection_allowed"],
        "codex_execution_allowed": gate["codex_execution_allowed"],
        "safety_result": plan["safety_result"],
        "next_recommended_step": plan["next_recommended_step"],
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = build_plan()
    summary = build_summary(plan)
    write_echo_json(PLAN_PATH, plan)
    write_echo_json(SUMMARY_PATH, summary)
    return plan, summary


def main() -> None:
    plan, summary = generate_reports()
    print("ECHO VPS localhost deployment plan complete.")
    print(f"vps_localhost_test_ready={summary['vps_localhost_test_ready']}")
    print(f"approval_required={summary['approval_required']}")
    print(f"required_approval_phrase={summary['required_approval_phrase']}")
    print(f"bind_host={summary['bind_host']}")
    print(f"port={summary['port']}")
    print(f"public_exposure_allowed={summary['public_exposure_allowed']}")
    print(f"next_recommended_step={summary['next_recommended_step']}")
    print(f"safety_result={summary['safety_result']}")
    if plan["failures"]:
        print("failures=" + "; ".join(plan["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
