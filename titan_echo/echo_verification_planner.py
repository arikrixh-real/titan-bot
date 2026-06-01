"""Plan verification checks for future ECHO missions without running them."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

MISSION_PLAN_PATH = ECHO_RUNTIME / "mission_plan.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
ARCHITECTURE_MAP_PATH = ECHO_RUNTIME / "titan_architecture_map.json"
WRITER_OWNERSHIP_REGISTRY_PATH = ECHO_RUNTIME / "writer_ownership_registry.json"
KNOWN_RISKS_PATH = ECHO_RUNTIME / "titan_known_risks.json"
OUTPUT_PATH = ECHO_RUNTIME / "verification_plan.json"

IST = timezone(timedelta(hours=5, minutes=30))

FORBIDDEN_CHANGES = [
    "Do not execute verification checks yet.",
    "Do not deploy.",
    "Do not push.",
    "Do not restart TITAN.",
    "Do not modify scanner pipeline.",
    "Do not modify Master Brain.",
    "Do not modify Unified Brain.",
    "Do not modify Consciousness Core.",
    "Do not modify broker/order execution.",
    "Do not modify risk logic.",
    "Do not change live order behavior.",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def normalized_scope(plan: dict[str, Any]) -> str:
    values = [
        plan.get("title", ""),
        plan.get("objective", ""),
        " ".join(str(item) for item in plan.get("affected_systems", []) if item),
        json.dumps(plan.get("architecture_context", {}), sort_keys=True)[:2000],
        json.dumps(plan.get("ownership_context", {}), sort_keys=True)[:2000],
    ]
    return " ".join(str(value).lower() for value in values)


def existing_file(path: str) -> bool:
    return (REPO_ROOT / path).exists()


def add_check(checks: list[dict[str, Any]], command: str, reason: str, required: bool = True) -> None:
    if any(item["command"] == command for item in checks):
        return
    checks.append({"command": command, "reason": reason, "required": required})


def echo_checks_for_scope(scope: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    add_check(checks, "python titan_echo/echo_memory_foundation_check.py", "Verify ECHO memory foundation.")
    if "echo" in scope or "mission" in scope or "approval" in scope:
        for script in [
            "echo_knowledge_indexer_check.py",
            "echo_architecture_mapper_check.py",
            "echo_context_builder_check.py",
            "echo_memory_check.py",
            "echo_observer_check.py",
            "echo_observation_summarizer_check.py",
            "echo_runtime_truth_audit_check.py",
            "echo_writer_ownership_registry_check.py",
            "echo_alert_engine_check.py",
            "echo_approval_check.py",
            "echo_mission_planner_check.py",
        ]:
            path = f"titan_echo/{script}"
            if existing_file(path):
                add_check(checks, f"python {path}", f"Verify ECHO component {script}.")
    return checks


def build_checks(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    scope = normalized_scope(plan)
    required: list[dict[str, Any]] = echo_checks_for_scope(scope)
    optional: list[dict[str, Any]] = []
    blocked: list[str] = []

    if any(term in scope for term in ["outcome", "trade result", "trade_results", "trade outcome"]):
        add_check(required, "python tools/trade_pipeline_check.py", "Outcome/trade result verification.")

    if any(term in scope for term in ["scanner", "setup", "truth gate", "truth_gate"]):
        add_check(required, "python tools/truth_gate_check.py", "Scanner/setup/truth gate verification.")
        add_check(optional, "scanner diagnostics if available", "Scanner diagnostics requested when available.", False)

    if any(term in scope for term in ["runtime", "daemon", "worker health", "worker"]):
        add_check(required, "python runtime_status.py", "Runtime/daemon status verification.")
        add_check(optional, "worker health check if available", "Worker health verification when available.", False)

    if any(term in scope for term in ["learning", "evolution"]):
        diagnostics = sorted(
            path.as_posix()
            for path in REPO_ROOT.glob("**/*")
            if path.is_file()
            and path.suffix == ".py"
            and ("learning" in path.as_posix().lower() or "evolution" in path.as_posix().lower())
            and ("diagnostic" in path.as_posix().lower() or "check" in path.as_posix().lower())
            and ".git" not in path.parts
            and ".venv" not in path.parts
        )
        if diagnostics:
            for diagnostic in diagnostics[:5]:
                add_check(required, f"python {diagnostic}", "Learning/evolution diagnostic available.")
        else:
            add_check(optional, "learning/evolution diagnostics if present", "No concrete diagnostic found.", False)

    if "supabase" in scope:
        add_check(optional, "Supabase connectivity/status check if available", "Supabase scope detected.", False)

    if any(term in scope for term in ["broker", "risk", "execution", "order execution", "live order"]):
        risk_level = str(plan.get("risk_level", "")).upper()
        approval = str(plan.get("approval_status", "")).upper()
        if not (risk_level == "CRITICAL" and approval == "APPROVED"):
            blocked.append("Broker/risk/execution scope is BLOCKED unless CRITICAL explicit Ari approval exists.")

    if any(term in scope for term in ["unified brain", "unified_brain", "consciousness core", "consciousness_core"]):
        add_check(required, "read-only architecture/integration audit", "Unified Brain or Consciousness Core scope detected.")
        add_check(required, "read-only protected core audit first", "Protected core requires read-only audit before patch.")

    return required, optional, blocked


def safety_notes(plan: dict[str, Any], blocked: list[str]) -> list[str]:
    notes = [
        "Verification plan is PLANNED_ONLY and does not run checks.",
        "execution_allowed is false.",
        "Run checks manually only after Ari approves the mission scope.",
    ]
    if str(plan.get("approval_status", "")).upper() != "APPROVED":
        notes.append("Mission is not approved; verification remains a draft plan.")
    if blocked:
        notes.append("Blocked conditions must be resolved before any execution or patch.")
    return notes


def build_plan() -> dict[str, Any]:
    mission = load_json(MISSION_PLAN_PATH)
    load_json(MODULE_REGISTRY_PATH)
    load_json(ARCHITECTURE_MAP_PATH)
    load_json(WRITER_OWNERSHIP_REGISTRY_PATH)
    load_json(KNOWN_RISKS_PATH)

    required, optional, blocked = build_checks(mission)

    return {
        "schema": "titan_echo.verification_plan.v1",
        "timestamp_ist": timestamp_ist(),
        "mission_id": mission.get("mission_id", "unknown"),
        "mission_title": mission.get("title", "unknown"),
        "risk_level": mission.get("risk_level", "UNKNOWN"),
        "approval_status": mission.get("approval_status", "UNKNOWN"),
        "touched_or_affected_systems": mission.get("affected_systems", []),
        "required_checks": required,
        "optional_checks": optional,
        "blocked_if_missing_checks": blocked,
        "forbidden_changes": FORBIDDEN_CHANGES,
        "safety_notes": safety_notes(mission, blocked),
        "verification_status": "PLANNED_ONLY",
        "execution_allowed": False,
    }


def command_plan(_: argparse.Namespace) -> int:
    plan = build_plan()
    write_json(OUTPUT_PATH, plan)
    print("TITAN ECHO verification planner plan: PASSED")
    print(f"Mission ID: {plan['mission_id']}")
    print(f"Required checks: {len(plan['required_checks'])}")
    print(f"Blocked conditions: {len(plan['blocked_if_missing_checks'])}")
    print(f"Verification status: {plan['verification_status']}")
    print(f"Execution allowed: {plan['execution_allowed']}")
    print("Checks executed: False")
    return 0


def command_summary(_: argparse.Namespace) -> int:
    plan = load_json(OUTPUT_PATH, {})
    print("TITAN ECHO verification planner summary: PASSED")
    print(f"Mission ID: {plan.get('mission_id', 'none')}")
    print(f"Required checks: {len(plan.get('required_checks', []))}")
    print(f"Optional checks: {len(plan.get('optional_checks', []))}")
    print(f"Verification status: {plan.get('verification_status', 'none')}")
    print(f"Execution allowed: {plan.get('execution_allowed', False)}")
    print("Checks executed: False")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TITAN ECHO verification planner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.set_defaults(func=command_plan)
    summary = subparsers.add_parser("summary")
    summary.set_defaults(func=command_summary)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
