"""Verification plan skeleton for ECHO Batch 2."""

from __future__ import annotations

from typing import Any

from titan_echo.echo_batch2_common import echo_path, now_utc, safety, write_echo_json


OUTPUT_PATH = echo_path("verification_plan.json")


def build_verification_plan() -> dict[str, Any]:
    return {
        "schema": "titan.echo.verification_plan.v1",
        "generated_at_utc": now_utc(),
        "status": "VERIFIER_PLAN_ONLY",
        "checks": [
            {"name": "observer_artifact_present", "type": "read_only_file_check", "target": "data/runtime/echo/observations.json"},
            {"name": "alert_queue_present", "type": "read_only_file_check", "target": "data/runtime/echo/alert_queue.json"},
            {"name": "integration_proof_present", "type": "read_only_file_check", "target": "data/runtime/echo/integration_proof_report.json"},
            {"name": "evolution_proof_present", "type": "read_only_file_check", "target": "data/runtime/echo/evolution_proof_report.json"},
            {"name": "api_routes_auth_protected", "type": "import_only_route_check", "target": "titan_echo.echo_api"},
        ],
        "execution_model": "plan_only_no_commands",
        "safety": safety(),
    }


def write_verification_plan() -> dict[str, Any]:
    payload = build_verification_plan()
    write_echo_json(OUTPUT_PATH, payload)
    return payload


def main() -> int:
    payload = write_verification_plan()
    print(f"ECHO verifier status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
