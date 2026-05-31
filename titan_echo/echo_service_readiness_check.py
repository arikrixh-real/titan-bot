"""Check the persistent ECHO localhost service readiness plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
READINESS_PATH = ECHO_DIR / "echo_service_readiness.json"
SUMMARY_PATH = ECHO_DIR / "echo_service_readiness_summary.json"
DOC_PATH = REPO_ROOT / "docs" / "echo_systemd_service_plan.md"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    failures: list[str] = []
    readiness = read_json(READINESS_PATH)
    summary = read_json(SUMMARY_PATH)
    doc_text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    if not isinstance(readiness, dict):
        failures.append("readiness JSON missing or invalid")
        readiness = {}
    if not isinstance(summary, dict):
        failures.append("summary JSON missing or invalid")
        summary = {}
    service = str(readiness.get("systemd_service_file_content") or "")
    env_template = str(readiness.get("env_file_template") or "")

    checks = {
        "bind_localhost": "--host 127.0.0.1" in service,
        "no_public_bind": "--host 0.0.0.0" not in service and "0.0.0.0" not in readiness.get("bind_host", ""),
        "vps_path": "/home/ubuntu/titan-bot" in service,
        "venv_python": "/home/ubuntu/titan-bot/.venv/bin/python" in service,
        "env_file_required": "EnvironmentFile=/home/ubuntu/titan-bot/.config/echo-api.env" in service,
        "no_inline_secret": "ECHO_API_KEY=" not in service,
        "env_template_placeholder_only": "replace-with-vps-only-secret" in env_template,
        "does_not_start_titan": readiness.get("starts_titan") is False,
        "does_not_restart_titan": readiness.get("restarts_titan") is False,
        "no_install_now": readiness.get("installs_service_now") is False,
        "no_sudo_now": readiness.get("runs_sudo_now") is False,
        "no_server_now": readiness.get("starts_server_now") is False,
        "public_exposure_false": readiness.get("public_exposure_allowed") is False,
        "doc_written": bool(doc_text),
    }
    for name, ok in checks.items():
        if not ok:
            failures.append(f"check failed: {name}")

    safety = readiness.get("safety", {}) if isinstance(readiness.get("safety"), dict) else {}
    for key in (
        "sudo_executed",
        "server_started",
        "public_port_exposed",
        "binds_public_interface",
        "real_secret_written",
        "titan_restart",
        "scanner_changed",
        "broker_changed",
        "risk_changed",
        "execution_changed",
        "master_brain_behavior_changed",
        "unified_brain_behavior_changed",
        "runtime_workers_changed",
    ):
        if safety.get(key) is not False:
            failures.append(f"safety.{key} must be false")

    print("ECHO service readiness check")
    print(f"service_name={summary.get('service_name')}")
    print(f"bind_host={summary.get('bind_host')}")
    print(f"port={summary.get('port')}")
    print(f"env_file={summary.get('env_file_path_recommendation')}")
    print(f"public_exposure_allowed={summary.get('public_exposure_allowed')}")
    print(f"safety_result={'PASS' if not failures else 'FAIL'}")
    if failures:
        for failure in failures:
            print(f"failure={failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
