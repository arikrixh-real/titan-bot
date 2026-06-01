"""Disabled rollback plan skeleton for ECHO Batch 2."""

from __future__ import annotations

from typing import Any

from titan_echo.echo_batch2_common import echo_path, now_utc, safety, write_echo_json


OUTPUT_PATH = echo_path("rollback_plan.json")


def build_rollback_plan() -> dict[str, Any]:
    return {
        "schema": "titan.echo.rollback_plan.v1",
        "generated_at_utc": now_utc(),
        "status": "ROLLBACK_DISABLED_PLAN_ONLY",
        "rollback_enabled": False,
        "git_commands_enabled": False,
        "service_restart_enabled": False,
        "steps": [
            "Identify operator-approved restore point outside ECHO.",
            "Review affected files manually.",
            "Execute rollback manually only after explicit operator approval.",
        ],
        "safety": safety(),
    }


def write_rollback_plan() -> dict[str, Any]:
    payload = build_rollback_plan()
    write_echo_json(OUTPUT_PATH, payload)
    return payload


def main() -> int:
    payload = write_rollback_plan()
    print(f"ECHO rollback status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
