"""Map TITAN modules to required validation checks."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import now_utc, output_path, write_json


OUTPUT_PATH = output_path("test_registry.json")


def build_test_registry() -> dict[str, Any]:
    registry = {
        "scanner": ["scanner diagnostics", "filter diagnostics check", "scanner publication continuity tests"],
        "runtime": ["runtime status checks", "runtime topology tests", "runtime health tests"],
        "brain": ["orchestration checks", "master brain runtime tests", "decision path diagnostics"],
        "journal": ["trade lifecycle reconciliation tests", "outcome tracker diagnostics"],
        "learning": ["learning/evolution diagnostics", "confidence calibration tests"],
        "evolution": ["evolution adapter tests", "mutation containment tests"],
        "memory": ["memory health checks", "memory cleanup checks"],
        "api": ["route import checks", "API auth smoke tests"],
        "dashboard": ["dashboard truth tests", "dashboard sync checks"],
        "news": ["news engine tests", "news pulse status checks"],
        "research": ["replay/backtest validation checks"],
        "echo": ["ECHO import checks", "registry generation tests", "read-only route checks"],
    }
    return {
        "schema": "titan_echo.knowledge.test_registry.v1",
        "generated_at_utc": now_utc(),
        "module_tests": registry,
        "default_rule": "Run focused checks for the changed module before completion.",
        "prohibited_validation": [
            "runtime deployment",
            "service installation",
            "broker execution",
            "public exposure",
        ],
    }


def write_test_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = payload or build_test_registry()
    write_json(OUTPUT_PATH, registry)
    return registry


def main() -> int:
    write_test_registry()
    print("ECHO test registry: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
