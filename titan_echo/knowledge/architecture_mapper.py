"""Build high-level TITAN architecture map for ECHO."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import now_utc, output_path, write_json


OUTPUT_PATH = output_path("architecture_map.json")


def build_architecture_map() -> dict[str, Any]:
    flows = {
        "scanner_flow": [
            "runtime_scanner coordinates scan cycle",
            "setup_engine and scanner/filter modules evaluate setups",
            "scanner status artifacts publish visibility",
            "master brain consumes scanner context for decisions",
        ],
        "journal_flow": [
            "trade journal records trade lifecycle state",
            "outcome tracker reads/writes outcomes",
            "learning and reporting consume journal evidence",
        ],
        "learning_flow": [
            "outcome evidence feeds learning engines",
            "memory and calibration layers retain lessons",
            "evolution layers propose or score improvements behind safety gates",
        ],
        "evolution_flow": [
            "evolution engines analyze outcomes and strategy memory",
            "promotion and containment checks protect runtime behavior",
            "runtime evolution status remains evidence-only unless explicitly wired",
        ],
        "master_brain_flow": [
            "input aggregation builds decision context",
            "reasoning and final decision engines evaluate candidate actions",
            "execution and alert filters remain protected high-danger boundaries",
        ],
        "runtime_flow": [
            "runtime workers publish health/status JSON",
            "dashboard and ECHO read evidence files",
            "ECHO knowledge layer remains read-only and does not start workers",
        ],
    }
    return {
        "schema": "titan_echo.knowledge.architecture_map.v1",
        "generated_at_utc": now_utc(),
        "mode": "human_readable_architecture_summary",
        "architecture": flows,
        "protected_boundaries": [
            "broker execution",
            "risk logic",
            "scanner filters",
            "runtime worker orchestration",
            "master brain decisions",
            "deployment/restart paths",
        ],
        "safety": {
            "actual_execution_permitted": False,
            "broker_modification": False,
            "risk_modification": False,
            "scanner_modification": False,
            "deployment_modification": False,
        },
    }


def write_architecture_map(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    architecture = payload or build_architecture_map()
    write_json(OUTPUT_PATH, architecture)
    return architecture


def main() -> int:
    write_architecture_map()
    print("ECHO architecture mapper: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
