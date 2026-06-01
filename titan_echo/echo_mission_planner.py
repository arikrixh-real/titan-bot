"""Generate safe, non-executing ECHO mission plans."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_RUNTIME = REPO_ROOT / "data" / "runtime" / "echo"

APPROVAL_QUEUE_PATH = ECHO_RUNTIME / "approval_queue.json"
ALERT_QUEUE_PATH = ECHO_RUNTIME / "alert_queue.json"
OBSERVATION_SUMMARY_PATH = ECHO_RUNTIME / "observation_summary.json"
RUNTIME_TRUTH_AUDIT_PATH = ECHO_RUNTIME / "runtime_truth_audit.json"
WRITER_OWNERSHIP_REGISTRY_PATH = ECHO_RUNTIME / "writer_ownership_registry.json"
ECHO_CONTEXT_REPORT_PATH = ECHO_RUNTIME / "echo_context_report.json"
ARCHITECTURE_MAP_PATH = ECHO_RUNTIME / "titan_architecture_map.json"
MODULE_REGISTRY_PATH = ECHO_RUNTIME / "titan_module_registry.json"
CONNECTION_GRAPH_PATH = ECHO_RUNTIME / "titan_connection_graph.json"

MISSION_PLAN_PATH = ECHO_RUNTIME / "mission_plan.json"
MISSION_PROMPT_PATH = ECHO_RUNTIME / "mission_prompt.txt"
MISSION_HISTORY_PATH = ECHO_RUNTIME / "mission_history.jsonl"

IST = timezone(timedelta(hours=5, minutes=30))
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

FORBIDDEN_ACTIONS = [
    "Do not execute automatically.",
    "Do not deploy.",
    "Do not push.",
    "Do not restart.",
    "Do not change broker execution.",
    "Do not change risk logic.",
    "Do not change live trading or live order behavior.",
    "Do not bypass Ari approval.",
]

ALLOWED_ACTIONS = {
    "LOW": ["read-only audit", "health check", "status report", "documentation/planning only"],
    "MEDIUM": ["draft code patch only after separate approval", "diagnostic module proposal"],
    "HIGH": ["planning only", "manual approval gate review"],
    "CRITICAL": ["planning only", "read-only audit only", "explicit Ari approval required"],
}


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


def append_history(plan: dict[str, Any]) -> None:
    MISSION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MISSION_HISTORY_PATH.open("a", encoding="utf-8") as handle:
        json.dump(plan, handle, sort_keys=True)
        handle.write("\n")


def mission_id_for(title: str, risk_level: str, source: str) -> str:
    raw = f"{title}|{risk_level}|{source}|{timestamp_ist()}"
    return "echo-plan-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def find_approval(mission_id: str) -> dict[str, Any] | None:
    queue = load_json(APPROVAL_QUEUE_PATH, {"approvals": []})
    approvals = queue.get("approvals", [])
    if not isinstance(approvals, list):
        return None
    for item in approvals:
        if isinstance(item, dict) and item.get("mission_id") == mission_id:
            return item
    return None


def collect_context() -> dict[str, Any]:
    alerts = load_json(ALERT_QUEUE_PATH, {"alerts": []})
    observation_summary = load_json(OBSERVATION_SUMMARY_PATH, {})
    truth_audit = load_json(RUNTIME_TRUTH_AUDIT_PATH, {})
    ownership = load_json(WRITER_OWNERSHIP_REGISTRY_PATH, {})
    context = load_json(ECHO_CONTEXT_REPORT_PATH, {})
    architecture = load_json(ARCHITECTURE_MAP_PATH, {})
    modules = load_json(MODULE_REGISTRY_PATH, {})
    load_json(CONNECTION_GRAPH_PATH, {})

    top_alerts = []
    for alert in alerts.get("alerts", [])[:5]:
        if isinstance(alert, dict):
            top_alerts.append(
                {
                    "severity": alert.get("severity"),
                    "title": alert.get("title"),
                    "affected_systems": alert.get("affected_systems", []),
                }
            )

    architecture_context = {
        "overall_health": observation_summary.get("overall_health", "UNKNOWN"),
        "affected_layers": observation_summary.get("affected_layers", []),
        "top_issues": observation_summary.get("top_issues", [])[:5],
        "top_alerts": top_alerts,
        "architecture_hierarchy": architecture.get("top_level_hierarchy", {}),
        "module_count": len(modules.get("modules", [])) if isinstance(modules.get("modules"), list) else 0,
    }

    ownership_context = {
        "confirmed_owner_count": ownership.get("confirmed_owner_count", 0),
        "possible_owner_count": ownership.get("possible_owner_count", 0),
        "reader_only_count": ownership.get("reader_only_count", 0),
        "no_reference_count": ownership.get("no_reference_count", 0),
        "highest_risk_truth_files": ownership.get("highest_risk_truth_files", [])[:8],
        "runtime_truth_missing_files": truth_audit.get("missing_files", []),
    }

    return {
        "architecture_context": architecture_context,
        "ownership_context": ownership_context,
        "context_report_keyword": context.get("issue_keyword", "general"),
    }


def required_inputs() -> list[str]:
    return [
        "data/runtime/echo/approval_queue.json",
        "data/runtime/echo/alert_queue.json",
        "data/runtime/echo/observation_summary.json",
        "data/runtime/echo/runtime_truth_audit.json",
        "data/runtime/echo/writer_ownership_registry.json",
        "data/runtime/echo/echo_context_report.json",
        "data/runtime/echo/titan_architecture_map.json",
        "data/runtime/echo/titan_module_registry.json",
        "data/runtime/echo/titan_connection_graph.json",
    ]


def required_verification(risk_level: str, approval_status: str) -> list[str]:
    checks = [
        "Verify mission_plan.json has execution_allowed=false.",
        "Review affected systems and forbidden actions before any follow-up.",
        "Run only read-only checks unless separate Ari approval exists.",
    ]
    if approval_status != "APPROVED":
        checks.append("WAITING_FOR_ARI_APPROVAL")
    if risk_level in {"HIGH", "CRITICAL"}:
        checks.append("Explicit Ari approval required for HIGH/CRITICAL risk.")
        checks.append("No broker, risk, live order, deploy, push, or restart actions allowed.")
    return checks


def build_plan(
    title: str,
    risk_level: str,
    approval_status: str,
    source: str,
    mission_id: str | None = None,
    summary: str = "",
    affected_systems: list[str] | None = None,
) -> dict[str, Any]:
    risk = risk_level.upper()
    if risk not in RISK_LEVELS:
        raise ValueError(f"Unsupported risk level: {risk}")
    context = collect_context()
    approval_gate = "APPROVED" if approval_status == "APPROVED" else "WAITING_FOR_ARI_APPROVAL"
    plan_id = mission_id or mission_id_for(title, risk, source)
    return {
        "schema": "titan_echo.mission_plan.v1",
        "mission_id": plan_id,
        "timestamp_ist": timestamp_ist(),
        "title": title,
        "objective": summary or f"Create a safe mission plan for: {title}",
        "risk_level": risk,
        "approval_status": approval_status,
        "approval_gate": approval_gate,
        "source": source,
        "affected_systems": affected_systems or context["architecture_context"].get("affected_layers", []),
        "architecture_context": context["architecture_context"],
        "ownership_context": context["ownership_context"],
        "allowed_actions": ALLOWED_ACTIONS[risk],
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "required_inputs": required_inputs(),
        "expected_outputs": [
            "mission_plan.json",
            "mission_prompt.txt",
            "mission_history.jsonl",
            "read-only findings only unless separately approved",
        ],
        "required_verification": required_verification(risk, approval_status),
        "rollback_required": False,
        "execution_allowed": False,
    }


def prompt_for(plan: dict[str, Any]) -> str:
    warning = ""
    if plan["risk_level"] in {"HIGH", "CRITICAL"}:
        warning = "\nEXTRA WARNING: HIGH/CRITICAL mission. Explicit Ari approval is required. Execution remains forbidden.\n"
    return f"""MISSION: {plan['title']}

Objective:
{plan['objective']}

Approval status:
{plan['approval_status']} ({plan['approval_gate']})

Risk level:
{plan['risk_level']}
{warning}
Execution:
- Do not execute automatically.
- execution_allowed is false.
- Do not deploy.
- Do not push.
- Do not restart.
- Do not change broker/risk/live trading.
- Read-only unless separately approved.

Allowed actions:
{chr(10).join('- ' + item for item in plan['allowed_actions'])}

Forbidden actions:
{chr(10).join('- ' + item for item in plan['forbidden_actions'])}

Affected systems:
{chr(10).join('- ' + str(item) for item in plan['affected_systems'])}

Required inputs:
{chr(10).join('- ' + item for item in plan['required_inputs'])}

Required verification:
{chr(10).join('- ' + item for item in plan['required_verification'])}

Ownership context:
- confirmed_owner_count: {plan['ownership_context'].get('confirmed_owner_count')}
- possible_owner_count: {plan['ownership_context'].get('possible_owner_count')}
- reader_only_count: {plan['ownership_context'].get('reader_only_count')}
- no_reference_count: {plan['ownership_context'].get('no_reference_count')}

Codex instruction:
Use this as a planning prompt only. Do not modify protected TITAN systems. Do not execute the mission. Produce read-only findings or a proposed patch plan only if Ari separately approves that scope.
"""


def save_plan(plan: dict[str, Any]) -> None:
    write_json(MISSION_PLAN_PATH, plan)
    MISSION_PROMPT_PATH.write_text(prompt_for(plan), encoding="utf-8")
    append_history(plan)


def command_plan(args: argparse.Namespace) -> int:
    plan = build_plan(
        title=args.title,
        risk_level=args.risk_level,
        approval_status="DRAFT",
        source="manual_plan_cli",
        summary=args.summary,
    )
    save_plan(plan)
    print("TITAN ECHO mission planner plan: PASSED")
    print(f"Mission ID: {plan['mission_id']}")
    print(f"Approval status: {plan['approval_status']}")
    print(f"Execution allowed: {plan['execution_allowed']}")
    print("Executed: False")
    return 0


def command_from_approval(args: argparse.Namespace) -> int:
    approval = find_approval(args.mission_id)
    if not approval:
        raise ValueError(f"Approval mission not found: {args.mission_id}")
    plan = build_plan(
        title=str(approval.get("title", "")),
        risk_level=str(approval.get("risk_level", "LOW")),
        approval_status=str(approval.get("status", "PENDING")),
        source="approval_queue",
        mission_id=str(approval.get("mission_id")),
        summary=str(approval.get("summary", "")),
        affected_systems=approval.get("affected_systems", []),
    )
    save_plan(plan)
    print("TITAN ECHO mission planner from-approval: PASSED")
    print(f"Mission ID: {plan['mission_id']}")
    print(f"Approval status: {plan['approval_status']}")
    print(f"Execution allowed: {plan['execution_allowed']}")
    print("Executed: False")
    return 0


def command_summary(_: argparse.Namespace) -> int:
    plan = load_json(MISSION_PLAN_PATH, {})
    history_count = 0
    if MISSION_HISTORY_PATH.exists():
        with MISSION_HISTORY_PATH.open("r", encoding="utf-8") as handle:
            history_count = sum(1 for line in handle if line.strip())
    print("TITAN ECHO mission planner summary: PASSED")
    print(f"Current mission ID: {plan.get('mission_id', 'none')}")
    print(f"Approval status: {plan.get('approval_status', 'none')}")
    print(f"Execution allowed: {plan.get('execution_allowed', False)}")
    print(f"History count: {history_count}")
    print("Executed: False")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TITAN ECHO mission planner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--title", required=True)
    plan.add_argument("--risk-level", required=True, choices=sorted(RISK_LEVELS))
    plan.add_argument("--summary", default="")
    plan.set_defaults(func=command_plan)

    from_approval = subparsers.add_parser("from-approval")
    from_approval.add_argument("--mission-id", required=True)
    from_approval.set_defaults(func=command_from_approval)

    summary = subparsers.add_parser("summary")
    summary.set_defaults(func=command_summary)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
