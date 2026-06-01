"""ECHO change rule registry."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import now_utc, output_path, write_json


OUTPUT_PATH = output_path("change_rules.json")


def build_change_rules() -> dict[str, Any]:
    return {
        "schema": "titan_echo.knowledge.change_rules.v1",
        "generated_at_utc": now_utc(),
        "allowed_changes": [
            "ECHO knowledge files and generated read-only registry artifacts",
            "documentation updates",
            "focused tests/checks for knowledge registry generation",
        ],
        "restricted_changes": [
            "scanner filters or scanner runtime behavior",
            "risk and position sizing behavior",
            "broker/order/execution behavior",
            "runtime worker scheduling or deployment behavior",
            "master brain final decision behavior",
        ],
        "protected_areas": [
            ".env and credential locations",
            "broker credentials",
            "API keys and Telegram/Supabase tokens",
            "trade execution paths",
            "risk management paths",
            "deployment/restart scripts",
        ],
        "mission_safety": {
            "actual_execution_permitted": False,
            "codex_execution": False,
            "shell_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "public_exposure_allowed": False,
        },
    }


def write_change_rules(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = payload or build_change_rules()
    write_json(OUTPUT_PATH, rules)
    return rules


def main() -> int:
    write_change_rules()
    print("ECHO change rules: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
