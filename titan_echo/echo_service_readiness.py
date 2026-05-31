"""Persistent localhost-only ECHO service readiness plan.

This generator writes a systemd service plan as evidence/documentation only.
It does not install a service, run sudo, start uvicorn, expose a port, restart
TITAN, or write secrets.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
DOCS_DIR = REPO_ROOT / "docs"
READINESS_PATH = ECHO_DIR / "echo_service_readiness.json"
SUMMARY_PATH = ECHO_DIR / "echo_service_readiness_summary.json"
DOC_PATH = DOCS_DIR / "echo_systemd_service_plan.md"
RUNTIME_SUMMARY_PATH = ECHO_DIR / "runtime_evidence_summary.json"
API_STATUS_PATH = ECHO_DIR / "echo_api_status.json"
AUTH_SUMMARY_PATH = ECHO_DIR / "echo_api_auth_summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

SERVICE_NAME = "echo-api.service"
VPS_WORKING_DIRECTORY = "/home/ubuntu/titan-bot"
VPS_PYTHON = "/home/ubuntu/titan-bot/.venv/bin/python"
ENV_FILE = "/home/ubuntu/titan-bot/.config/echo-api.env"
HOST = "127.0.0.1"
PORT = 8765
AUTH_HEADER = "X-ECHO-API-KEY"
ENV_VAR = "ECHO_API_KEY"


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    allowed_roots = [ECHO_DIR.resolve()]
    resolved = path.resolve()
    if not any(root in (resolved, *resolved.parents) for root in allowed_roots):
        raise ValueError("service readiness JSON writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_doc(path: Path, text: str) -> None:
    resolved_docs = DOCS_DIR.resolve()
    resolved = path.resolve()
    if resolved_docs not in (resolved, *resolved.parents):
        raise ValueError("service readiness docs write only under docs")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def service_file_content() -> str:
    return f"""[Unit]
Description=ECHO read-only localhost API
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory={VPS_WORKING_DIRECTORY}
EnvironmentFile={ENV_FILE}
ExecStart={VPS_PYTHON} -m uvicorn titan_echo.echo_api:app --host {HOST} --port {PORT}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=false

[Install]
WantedBy=multi-user.target
"""


def env_file_template() -> str:
    return f"""# Create this file on the VPS only. Do not commit it.
# Replace the placeholder with a real strong secret on the VPS.
{ENV_VAR}=replace-with-vps-only-secret
"""


def verification_commands() -> list[str]:
    return [
        "systemctl cat echo-api.service",
        "systemctl status echo-api.service --no-pager",
        "ss -ltnp | grep 8765",
        "curl -s http://127.0.0.1:8765/health",
        f"curl -s -H '{AUTH_HEADER}: <redacted>' http://127.0.0.1:8765/status",
        f"curl -s -H '{AUTH_HEADER}: <redacted>' 'http://127.0.0.1:8765/query?intent=what_next'",
    ]


def rollback_commands() -> list[str]:
    return [
        "sudo systemctl stop echo-api.service",
        "sudo systemctl disable echo-api.service",
        "sudo rm /etc/systemd/system/echo-api.service",
        "sudo systemctl daemon-reload",
        "ss -ltnp | grep 8765 || true",
    ]


def install_commands_text_only() -> list[str]:
    return [
        f"sudo install -o ubuntu -g ubuntu -m 600 /dev/null {ENV_FILE}",
        f"sudoedit {ENV_FILE}",
        "sudo cp docs/echo-api.service /etc/systemd/system/echo-api.service",
        "sudo systemctl daemon-reload",
        "sudo systemctl enable --now echo-api.service",
    ]


def build_readiness() -> dict[str, Any]:
    runtime = read_json(RUNTIME_SUMMARY_PATH) or {}
    api_status = read_json(API_STATUS_PATH) or {}
    auth_summary = read_json(AUTH_SUMMARY_PATH) or {}
    service = service_file_content()
    failures: list[str] = []
    if f"--host {HOST}" not in service:
        failures.append("service does not bind to 127.0.0.1")
    if "--host 0.0.0.0" in service:
        failures.append("service contains public bind")
    if "ECHO_API_KEY=" in service:
        failures.append("service file contains inline API key assignment")
    if "titan_echo.echo_api:app" not in service:
        failures.append("service does not start ECHO API app")

    return {
        "schema": "titan.echo.service_readiness.v1",
        "timestamp_ist": timestamp_ist(),
        "plan_only": True,
        "service_name": SERVICE_NAME,
        "startup_command_audited": f"{VPS_PYTHON} -m uvicorn titan_echo.echo_api:app --host {HOST} --port {PORT}",
        "systemd_unit_path_recommendation": f"/etc/systemd/system/{SERVICE_NAME}",
        "env_file_path_recommendation": ENV_FILE,
        "env_file_template": env_file_template(),
        "systemd_service_file_content": service,
        "bind_host": HOST,
        "port": PORT,
        "working_directory": VPS_WORKING_DIRECTORY,
        "python_path": VPS_PYTHON,
        "auth_required": True,
        "auth_header": AUTH_HEADER,
        "api_key_source": f"safe env file containing {ENV_VAR}; do not commit",
        "auto_restart_on_failure": True,
        "public_exposure_allowed": False,
        "starts_titan": False,
        "restarts_titan": False,
        "installs_service_now": False,
        "runs_sudo_now": False,
        "starts_server_now": False,
        "verification_commands": verification_commands(),
        "rollback_commands": rollback_commands(),
        "install_commands_text_only_for_future_approval": install_commands_text_only(),
        "current_evidence": {
            "runtime_fail_count": runtime.get("fail_count"),
            "runtime_unknown_count": runtime.get("unknown_count"),
            "current_runtime_truth_verdict": runtime.get("current_runtime_truth_verdict"),
            "api_mode": api_status.get("api_mode"),
            "auth_summary_safety": auth_summary.get("safety_result") if isinstance(auth_summary, dict) else None,
        },
        "forbidden_actions": [
            "Do not install the systemd service in this batch.",
            "Do not run sudo in this batch.",
            "Do not start uvicorn in this batch.",
            "Do not bind 0.0.0.0.",
            "Do not expose a public port.",
            "Do not restart TITAN.",
            "Do not modify scanner, broker, risk, execution, Master Brain, Unified Brain, or runtime workers.",
            "Do not commit real API keys.",
        ],
        "safety": {
            "readiness_only": True,
            "sudo_executed": False,
            "server_started": False,
            "public_port_exposed": False,
            "binds_public_interface": False,
            "real_secret_written": False,
            "titan_restart": False,
            "scanner_changed": False,
            "broker_changed": False,
            "risk_changed": False,
            "execution_changed": False,
            "master_brain_behavior_changed": False,
            "unified_brain_behavior_changed": False,
            "runtime_workers_changed": False,
        },
        "risk_level": "LOW",
        "failures": failures,
        "safety_result": "PASS" if not failures else "FAIL",
        "next_recommended_step": "After explicit approval on VPS, create the env file, install the unit, daemon-reload, start echo-api.service, then verify it listens only on 127.0.0.1:8765.",
    }


def build_summary(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "titan.echo.service_readiness_summary.v1",
        "timestamp_ist": readiness["timestamp_ist"],
        "service_name": readiness["service_name"],
        "bind_host": readiness["bind_host"],
        "port": readiness["port"],
        "env_file_path_recommendation": readiness["env_file_path_recommendation"],
        "public_exposure_allowed": readiness["public_exposure_allowed"],
        "starts_titan": readiness["starts_titan"],
        "restarts_titan": readiness["restarts_titan"],
        "installs_service_now": readiness["installs_service_now"],
        "runs_sudo_now": readiness["runs_sudo_now"],
        "starts_server_now": readiness["starts_server_now"],
        "auto_restart_on_failure": readiness["auto_restart_on_failure"],
        "safety_result": readiness["safety_result"],
        "risk_level": readiness["risk_level"],
        "next_recommended_step": readiness["next_recommended_step"],
    }


def build_doc(readiness: dict[str, Any]) -> str:
    commands = "\n".join(f"- `{cmd}`" for cmd in readiness["verification_commands"])
    rollback = "\n".join(f"- `{cmd}`" for cmd in readiness["rollback_commands"])
    return f"""# ECHO systemd service plan

Plan only. Do not install until explicitly approved.

## Service file: /etc/systemd/system/{SERVICE_NAME}

```ini
{readiness["systemd_service_file_content"]}```

## Env file

Path: `{ENV_FILE}`

```bash
{readiness["env_file_template"]}```

## Verification commands

{commands}

## Rollback commands

{rollback}

## Safety

- Binds only to `{HOST}:{PORT}`.
- Requires `{ENV_VAR}` from the env file.
- Does not start or restart TITAN.
- Does not expose a public port.
- Does not modify scanner, broker, risk, execution, Master Brain, Unified Brain, or runtime workers.
"""


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    readiness = build_readiness()
    summary = build_summary(readiness)
    write_json(READINESS_PATH, readiness)
    write_json(SUMMARY_PATH, summary)
    write_doc(DOC_PATH, build_doc(readiness))
    return readiness, summary


def main() -> None:
    readiness, summary = generate_reports()
    print("ECHO persistent service readiness plan generated.")
    print(f"service_name={summary['service_name']}")
    print(f"bind_host={summary['bind_host']}")
    print(f"port={summary['port']}")
    print(f"env_file={summary['env_file_path_recommendation']}")
    print(f"public_exposure_allowed={summary['public_exposure_allowed']}")
    print(f"starts_server_now={summary['starts_server_now']}")
    print(f"safety_result={summary['safety_result']}")
    print(f"risk_level={summary['risk_level']}")
    if readiness["failures"]:
        print("failures=" + "; ".join(readiness["failures"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
