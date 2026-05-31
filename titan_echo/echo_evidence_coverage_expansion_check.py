"""Safety check for ECHO evidence coverage expansion artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"
ECHO_DIR = RUNTIME_DIR / "echo"

TARGETS = [
    RUNTIME_DIR / "unified_brain_status.json",
    RUNTIME_DIR / "brain_state.json",
    ECHO_DIR / "alert_queue.json",
    ECHO_DIR / "project_state_registry.json",
    ECHO_DIR / "runtime_repair_priority_summary.json",
    ECHO_DIR / "final_readiness_summary.json",
]
SUMMARY_PATH = ECHO_DIR / "echo_evidence_coverage_expansion_summary.json"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def main() -> int:
    failures: list[str] = []
    for path in TARGETS:
        if not path.exists():
            failures.append(f"missing target evidence file: {rel(path)}")
        elif read_json(path) is None:
            failures.append(f"invalid JSON: {rel(path)}")

    summary = read_json(SUMMARY_PATH)
    if not isinstance(summary, dict):
        failures.append("coverage expansion summary missing or invalid")
        summary = {}

    safety = summary.get("safety", {}) if isinstance(summary, dict) else {}
    required_false = [
        "commands_executed_by_script",
        "server_started",
        "deploy_or_restart",
        "push",
        "broker_changed",
        "risk_changed",
        "scanner_changed",
        "execution_changed",
        "runtime_behavior_changed",
        "master_brain_behavior_changed",
        "unified_brain_behavior_changed",
        "command_endpoints_added",
    ]
    for key in required_false:
        if safety.get(key) is not False:
            failures.append(f"safety.{key} must be false")
    if safety.get("read_only_inspection_only") is not True:
        failures.append("safety.read_only_inspection_only must be true")

    print("ECHO evidence coverage expansion check")
    print(f"target_files_present={len([path for path in TARGETS if path.exists()])}/{len(TARGETS)}")
    print(f"before_unknown_count={summary.get('before_unknowns', {}).get('combined_unknown_count')}")
    print(f"after_unknown_count={summary.get('after_unknowns', {}).get('combined_unknown_count')}")
    print(f"safety_result={'PASS' if not failures else 'FAIL'}")
    if failures:
        for failure in failures:
            print(f"failure={failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
