"""VPS localhost deployment readiness plan for ECHO.

Documentation only. This does not deploy, push, pull, start services, expose a
public port, configure nginx/Cloudflare/HTTPS, or connect a ChatGPT Action.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
PLAN_PATH = ECHO_DIR / "echo_vps_deployment_readiness_plan.json"
SMOKE_PATH = ECHO_DIR / "echo_uvicorn_local_smoke_test.json"
IST = timezone(timedelta(hours=5, minutes=30))


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
        raise ValueError("VPS readiness plan writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_plan() -> dict[str, Any]:
    smoke = read_json(SMOKE_PATH)
    local_smoke_passed = isinstance(smoke, dict) and smoke.get("safety_result") == "PASS"
    failures: list[str] = []
    if not local_smoke_passed:
        failures.append("local uvicorn smoke test has not passed")
    return {
        "schema": "titan.echo.vps_deployment_readiness_plan.v1",
        "timestamp_ist": timestamp_ist(),
        "documentation_only": True,
        "vps_required_path": "/home/ubuntu/titan-bot",
        "bind_host": "127.0.0.1",
        "port": 8765,
        "env_var": "ECHO_API_KEY",
        "public_exposure_allowed": False,
        "nginx_allowed_now": False,
        "cloudflare_allowed_now": False,
        "https_allowed_now": False,
        "chatgpt_action_allowed_now": False,
        "deploy_performed": False,
        "push_performed": False,
        "restart_performed": False,
        "safe_future_steps": [
            "copy/push code safely",
            "pull on VPS",
            "set ECHO_API_KEY on VPS",
            "run localhost test on VPS",
            "only later add HTTPS tunnel/proxy",
            "only later connect ChatGPT Action",
        ],
        "vps_localhost_test_command_text_only": {
            "set_key": 'export ECHO_API_KEY="temporary-test-key"',
            "run_localhost": "python -m uvicorn titan_echo.echo_api:app --host 127.0.0.1 --port 8765 --workers 1",
            "stop": "CTRL+C",
            "executed": False,
        },
        "blocked_until_later": [
            "public bind",
            "0.0.0.0 bind",
            "public port exposure",
            "nginx",
            "Cloudflare",
            "HTTPS tunnel/proxy",
            "ChatGPT Action connection",
            "command endpoints",
            "POST execution endpoints",
        ],
        "local_smoke_dependency": {
            "path": relative(SMOKE_PATH),
            "passed": local_smoke_passed,
            "server_stopped_confirmation": smoke.get("server_stopped_confirmation") if isinstance(smoke, dict) else None,
            "auth_result": smoke.get("auth_result") if isinstance(smoke, dict) else None,
        },
        "safety": {
            "documentation_only": True,
            "deploy": False,
            "push": False,
            "restart": False,
            "server_started": False,
            "public_exposure": False,
            "bind_0_0_0_0": False,
            "nginx_cloudflare_https": False,
            "chatgpt_action_connected": False,
            "command_endpoints": False,
            "post_execution_endpoints": False,
            "scanner_master_unified_broker_risk_changes": False,
            "real_secret_written": False,
            "writes_only": [relative(PLAN_PATH)],
        },
        "failures": failures,
        "vps_readiness_status": "READY_FOR_VPS_LOCALHOST_PLANNING" if not failures else "BLOCKED",
        "safety_result": "PASS" if not failures else "FAIL",
        "next_recommended_step": "If approved, perform a controlled code transfer/pull plan for the VPS, then run the same localhost-only smoke test on the VPS before any public exposure.",
    }


def generate_report() -> dict[str, Any]:
    plan = build_plan()
    write_echo_json(PLAN_PATH, plan)
    return plan


def main() -> None:
    plan = generate_report()
    print("ECHO VPS deployment readiness plan complete.")
    print(f"vps_readiness_status={plan['vps_readiness_status']}")
    print(f"bind_host={plan['bind_host']}")
    print(f"port={plan['port']}")
    print(f"public_exposure_allowed={plan['public_exposure_allowed']}")
    print(f"safety_result={plan['safety_result']}")
    print(f"next_recommended_step={plan['next_recommended_step']}")
    if plan["failures"]:
        print("failures=" + "; ".join(plan["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
