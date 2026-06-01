"""Alert queue skeleton for ECHO Batch 2.

This module writes draft alert artifacts only. It does not send Telegram,
execute commands, restart services, or mutate TITAN runtime systems.
"""

from __future__ import annotations

import json
from typing import Any

from titan_echo.echo_batch2_common import echo_path, now_utc, read_json, safety, write_echo_json


QUEUE_PATH = echo_path("alert_queue.json")
HISTORY_PATH = echo_path("alert_history.jsonl")
OBSERVATIONS_PATH = echo_path("observations.json")


def build_alert_queue() -> dict[str, Any]:
    observations, error = read_json(OBSERVATIONS_PATH)
    items = observations.get("observations", []) if isinstance(observations, dict) else []
    alerts = []
    for item in items:
        if not isinstance(item, dict) or item.get("severity") not in {"ISSUE_DETECTED", "UNKNOWN"}:
            continue
        alerts.append(
            {
                "title": "ECHO observation requires operator review",
                "source": item.get("source", "unknown"),
                "severity": "WARNING" if item.get("severity") == "UNKNOWN" else "CRITICAL",
                "status": "DRAFT_ONLY",
                "recommended_action": "Review evidence manually. No automated execution is permitted.",
                "evidence": item.get("signals", []),
            }
        )
    return {
        "schema": "titan.echo.alert_queue.v1",
        "generated_at_utc": now_utc(),
        "status": "ALERT_ENGINE_DRAFT_ONLY",
        "telegram_sending_enabled": False,
        "source": "data/runtime/echo/observations.json",
        "source_error": error,
        "summary": {"alerts": len(alerts)},
        "alerts": alerts,
        "safety": safety(),
    }


def write_alert_artifacts() -> dict[str, Any]:
    payload = build_alert_queue()
    write_echo_json(QUEUE_PATH, payload)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"generated_at_utc": payload["generated_at_utc"], "status": payload["status"], "alerts": payload["alerts"], "safety": safety()}, sort_keys=True))
        handle.write("\n")
    return payload


def main() -> int:
    payload = write_alert_artifacts()
    print(f"ECHO alert engine status: {payload['status']}")
    print(f"Alerts drafted: {payload['summary']['alerts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
