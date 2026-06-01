"""Auto-report artifact writer for ECHO Batch 2."""

from __future__ import annotations

from typing import Any

from titan_echo.echo_batch2_common import echo_path, now_utc, read_json, safety, write_echo_json


OUTPUT_PATH = echo_path("auto_report.json")

REPORT_SOURCES = {
    "observations": echo_path("observations.json"),
    "alerts": echo_path("alert_queue.json"),
    "integration_proof": echo_path("integration_proof_report.json"),
    "evolution_proof": echo_path("evolution_proof_report.json"),
    "verification_plan": echo_path("verification_plan.json"),
    "deployment_plan": echo_path("deployment_plan.json"),
    "rollback_plan": echo_path("rollback_plan.json"),
}


def build_auto_report() -> dict[str, Any]:
    sections = {}
    for name, path in REPORT_SOURCES.items():
        payload, error = read_json(path)
        sections[name] = {
            "source": f"data/runtime/echo/{path.name}",
            "status": payload.get("status") if isinstance(payload, dict) else "UNKNOWN_NOT_PROVEN",
            "error": error,
            "summary": payload.get("summary") if isinstance(payload, dict) else None,
        }
    return {
        "schema": "titan.echo.auto_report.v1",
        "generated_at_utc": now_utc(),
        "status": "AUTO_REPORT_READY",
        "sections": sections,
        "safety": safety(),
    }


def write_auto_report() -> dict[str, Any]:
    payload = build_auto_report()
    write_echo_json(OUTPUT_PATH, payload)
    return payload


def main() -> int:
    payload = write_auto_report()
    print(f"ECHO auto reporter status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
