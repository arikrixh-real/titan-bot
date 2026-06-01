"""Validate the TITAN ECHO alert engine generator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ALERT_ENGINE = REPO_ROOT / "titan_echo" / "echo_alert_engine.py"
LIVE_STATUS_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "live_status.json"
ALERT_QUEUE_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "alert_queue.json"
ALERT_HISTORY_PATH = REPO_ROOT / "data" / "runtime" / "echo" / "alert_history.jsonl"

REQUIRED_ALERT_FIELDS = {
    "severity",
    "title",
    "summary",
    "telegram_ready_text",
}


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_engine() -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(ALERT_ENGINE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def validate_stdout(stdout: str) -> list[str]:
    allowed_prefixes = (
        "TITAN ECHO alert engine:",
        "Alerts queued:",
        "Critical alerts:",
        "Warning alerts:",
        "Info alerts:",
        "Telegram sent:",
    )
    errors = []
    for line in stdout.splitlines():
        if not line.startswith(allowed_prefixes):
            errors.append("Alert engine printed unexpected output.")
            break
    if "Telegram sent: True" in stdout:
        errors.append("Alert engine reported Telegram send.")
    return errors


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None, f"Missing JSON file: {relative(path)}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {relative(path)} line {exc.lineno}"
    if not isinstance(data, dict):
        return None, f"JSON root must be object: {relative(path)}"
    return data, None


def validate_history() -> list[str]:
    if not ALERT_HISTORY_PATH.is_file():
        return [f"Missing history file: {relative(ALERT_HISTORY_PATH)}"]
    errors = []
    with ALERT_HISTORY_PATH.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                errors.append(f"Invalid history JSONL at line {line_number}")
                continue
            if not isinstance(data, dict):
                errors.append(f"History line {line_number} must be object.")
    return errors


def validate_queue(queue: dict[str, Any], live_status: dict[str, Any]) -> list[str]:
    errors = []
    alerts = queue.get("alerts")
    if not isinstance(alerts, list):
        return ["alert_queue alerts must be a list."]
    if live_status.get("overall_health") == "CRITICAL" and len(alerts) < 1:
        errors.append("At least one alert required when overall health is CRITICAL.")
    if queue.get("telegram_send_enabled") is not False:
        errors.append("telegram_send_enabled must be false.")
    for index, alert in enumerate(alerts):
        if not isinstance(alert, dict):
            errors.append(f"Alert {index} must be object.")
            continue
        missing = REQUIRED_ALERT_FIELDS - set(alert)
        if missing:
            errors.append(f"Alert {index} missing fields: {sorted(missing)}")
    return errors


def main() -> int:
    errors: list[str] = []

    if not ALERT_ENGINE.is_file():
        errors.append(f"Missing alert engine: {relative(ALERT_ENGINE)}")
    else:
        returncode, stdout, stderr = run_engine()
        if returncode != 0:
            errors.append(f"Alert engine failed with exit code {returncode}.")
        if stderr:
            errors.append("Alert engine wrote to stderr.")
        if stdout:
            errors.extend(validate_stdout(stdout))

    live_status, error = load_json(LIVE_STATUS_PATH)
    if error:
        errors.append(error)

    queue, error = load_json(ALERT_QUEUE_PATH)
    if error:
        errors.append(error)
    elif live_status is not None:
        errors.extend(validate_queue(queue, live_status))

    errors.extend(validate_history())

    if errors:
        print("TITAN ECHO alert engine check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    alerts = queue.get("alerts", []) if queue else []
    print("TITAN ECHO alert engine check: PASSED")
    print(f"Alerts queued: {len(alerts)}")
    print("Telegram sent: False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
