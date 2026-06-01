"""Disabled deployment plan skeleton for ECHO Batch 2."""

from __future__ import annotations

from typing import Any

from titan_echo.echo_batch2_common import echo_path, now_utc, safety, write_echo_json


OUTPUT_PATH = echo_path("deployment_plan.json")


def build_deployment_plan() -> dict[str, Any]:
    return {
        "schema": "titan.echo.deployment_plan.v1",
        "generated_at_utc": now_utc(),
        "status": "DEPLOYER_DISABLED_PLAN_ONLY",
        "deployment_enabled": False,
        "git_commands_enabled": False,
        "service_restart_enabled": False,
        "steps": [
            "Review generated ECHO reports manually.",
            "Confirm auth remains required before any service exposure.",
            "Create an operator-approved deployment ticket outside ECHO if needed.",
        ],
        "safety": safety(),
    }


def write_deployment_plan() -> dict[str, Any]:
    payload = build_deployment_plan()
    write_echo_json(OUTPUT_PATH, payload)
    return payload


def main() -> int:
    payload = write_deployment_plan()
    print(f"ECHO deployer status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
