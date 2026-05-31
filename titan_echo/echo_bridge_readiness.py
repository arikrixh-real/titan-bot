"""Approval-gated ECHO bridge readiness plan.

This is documentation/readiness only. It does not expose endpoints, run Codex,
run git, pull on VPS, deploy, restart, rollback, or modify TITAN runtime
systems.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
DOCS_DIR = REPO_ROOT / "docs"
READINESS_PATH = ECHO_DIR / "echo_bridge_readiness.json"
SUMMARY_PATH = ECHO_DIR / "echo_bridge_readiness_summary.json"
DOC_PATH = DOCS_DIR / "echo_chatgpt_codex_bridge_plan.md"
IST = timezone(timedelta(hours=5, minutes=30))

READ_ENDPOINTS = [
    ("GET", "/health", "Public health only; no secrets, no runtime actions."),
    ("GET", "/status", "Protected read-only ECHO/TITAN status from evidence files."),
    ("GET", "/answer", "Protected read-only current ECHO answer."),
    ("GET", "/query", "Protected read-only intent query from ECHO evidence."),
    ("GET", "/approval/pending", "Protected read-only pending approval records."),
    ("GET", "/mission/current", "Protected read-only current mission plan/status."),
    ("GET", "/verification/latest", "Protected read-only latest verification result."),
]

APPROVAL_GATED_ENDPOINTS = [
    ("POST", "/mission/prepare", "Create a mission plan record only; no execution."),
    ("POST", "/approval/approve", "Create signed Ari approval record for a prepared action."),
    ("POST", "/approval/reject", "Create rejection record for a prepared action."),
    ("POST", "/codex/run-approved", "Run only an approved Codex mission; never raw ChatGPT execution."),
    ("POST", "/git/push-approved", "Push only selected staged files after explicit approval."),
    ("POST", "/vps/pull-approved", "VPS pull only after approved push workflow."),
    ("POST", "/verify/run-approved", "Run approved verification after pull/deploy step."),
    ("POST", "/deploy/approved", "Deploy/start/restart only under separate explicit approval."),
    ("POST", "/rollback/approved", "Rollback only under separate explicit approval."),
]

FORBIDDEN_ACTIONS = [
    "No public unauthenticated API.",
    "No raw shell endpoint.",
    "ChatGPT cannot directly run Codex.",
    "ChatGPT cannot directly run git push.",
    "ChatGPT cannot directly run git pull.",
    "ChatGPT cannot directly deploy, restart, rollback, or verify.",
    "No broker/risk/execution endpoint.",
    "No live trade or broker control.",
    "No secrets committed.",
    "No approval bypass.",
]


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def write_echo_json(path: Path, payload: dict[str, Any]) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved = path.resolve()
    if resolved_echo not in (resolved, *resolved.parents):
        raise ValueError("bridge readiness writes JSON only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_doc(path: Path, text: str) -> None:
    resolved_docs = DOCS_DIR.resolve()
    resolved = path.resolve()
    if resolved_docs not in (resolved, *resolved.parents):
        raise ValueError("bridge readiness docs write only under docs")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def endpoint(method: str, path: str, purpose: str, mode: str) -> dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "mode": mode,
        "purpose": purpose,
        "auth_required": path != "/health",
        "approval_required": mode == "APPROVAL_GATED",
        "direct_execution_allowed": False if mode == "APPROVAL_GATED" else None,
        "writes_allowed": (
            ["data/runtime/echo approval/mission/log records"]
            if mode == "APPROVAL_GATED"
            else []
        ),
    }


def approval_workflow() -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "name": "read_context",
            "actor": "ChatGPT or Ari",
            "allowed": "GET /status, /answer, /query, /approval/pending, /mission/current, /verification/latest",
            "effect": "Read evidence only.",
        },
        {
            "step": 2,
            "name": "prepare_mission",
            "actor": "ECHO",
            "allowed": "POST /mission/prepare",
            "effect": "Writes mission plan and approval request only; no Codex/git/VPS/deploy action.",
        },
        {
            "step": 3,
            "name": "ari_decision",
            "actor": "Ari",
            "allowed": "POST /approval/approve or POST /approval/reject",
            "effect": "Creates signed approval/rejection record in data/runtime/echo.",
        },
        {
            "step": 4,
            "name": "run_codex_if_approved",
            "actor": "Bridge executor",
            "allowed": "POST /codex/run-approved",
            "effect": "Runs only the exact approved mission. No raw shell prompt.",
        },
        {
            "step": 5,
            "name": "push_if_approved",
            "actor": "Bridge executor",
            "allowed": "POST /git/push-approved",
            "effect": "Pushes only selected staged files named in the approval record.",
        },
        {
            "step": 6,
            "name": "vps_pull_if_approved",
            "actor": "Bridge executor on VPS",
            "allowed": "POST /vps/pull-approved",
            "effect": "Pulls only after push approval and records result.",
        },
        {
            "step": 7,
            "name": "verify_if_approved",
            "actor": "Bridge executor",
            "allowed": "POST /verify/run-approved",
            "effect": "Runs approved verification commands and records output summary.",
        },
        {
            "step": 8,
            "name": "deploy_or_rollback_separate_gate",
            "actor": "Ari plus bridge executor",
            "allowed": "POST /deploy/approved or POST /rollback/approved",
            "effect": "Requires separate explicit approval; never implied by code/test approval.",
        },
    ]


def build_readiness() -> dict[str, Any]:
    read_endpoints = [endpoint(method, path, purpose, "READ_ONLY") for method, path, purpose in READ_ENDPOINTS]
    gated_endpoints = [
        endpoint(method, path, purpose, "APPROVAL_GATED")
        for method, path, purpose in APPROVAL_GATED_ENDPOINTS
    ]
    all_endpoints = read_endpoints + gated_endpoints
    unsafe = [
        item
        for item in all_endpoints
        if item["path"] in {"/shell", "/command", "/broker", "/risk", "/execution"}
        or ("approved" not in item["path"] and item["method"] == "POST" and item["path"] != "/mission/prepare" and not item["path"].startswith("/approval/"))
    ]
    return {
        "schema": "titan.echo.bridge_readiness.v1",
        "timestamp_ist": timestamp_ist(),
        "plan_only": True,
        "chatgpt_to_echo_api": {
            "allowed": "Authenticated HTTPS/private-tunnel GET reads only until approval-gated writes are implemented.",
            "blocked": "Unauthenticated public API and direct executor access.",
            "auth_required": True,
            "api_key_header": "X-ECHO-API-KEY",
        },
        "echo_to_codex": {
            "allowed": "Mission plan creation and approved mission execution only.",
            "blocked": "Raw shell, arbitrary prompt execution, deploy/restart without separate approval.",
        },
        "echo_to_github": {
            "allowed": "Selected staged file push after approval record names files and target branch.",
            "blocked": "Unreviewed push, push with secrets, push from ChatGPT directly.",
        },
        "echo_to_vps": {
            "allowed": "Pull approved commit on VPS after push approval.",
            "blocked": "Public exposure, direct deploy, restart, rollback without separate approval.",
        },
        "echo_to_verification": {
            "allowed": "Approved verification command sets with logged outputs.",
            "blocked": "Ad hoc shell endpoint and unapproved command execution.",
        },
        "read_endpoints": read_endpoints,
        "approval_gated_endpoints": gated_endpoints,
        "approval_workflow": approval_workflow(),
        "approval_record_requirements": [
            "approval_id",
            "mission_id",
            "requested_action",
            "exact_scope",
            "allowed_files",
            "allowed_commands",
            "risk_level",
            "ari_approval_phrase_or_signature",
            "created_at_ist",
            "decision_at_ist",
            "status",
            "result_log_path",
        ],
        "action_log_paths": {
            "approval_queue": "data/runtime/echo/approval_queue.json",
            "approval_history": "data/runtime/echo/approval_history.jsonl",
            "mission_plan": "data/runtime/echo/mission_plan.json",
            "bridge_action_log": "data/runtime/echo/bridge_action_log.jsonl",
            "verification_latest": "data/runtime/echo/verification_latest.json",
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "unsafe_endpoint_count": len(unsafe),
        "unsafe_endpoints": unsafe,
        "implementation_status": {
            "endpoints_added_now": False,
            "executor_added_now": False,
            "github_push_enabled_now": False,
            "vps_pull_enabled_now": False,
            "deploy_enabled_now": False,
            "rollback_enabled_now": False,
            "current_running_service_modified": False,
        },
        "safety": {
            "readiness_only": True,
            "public_unauthenticated_api": False,
            "raw_shell_endpoint": False,
            "chatgpt_direct_codex": False,
            "chatgpt_direct_git_push": False,
            "chatgpt_direct_vps_pull": False,
            "chatgpt_direct_deploy_restart_rollback": False,
            "broker_endpoint": False,
            "risk_endpoint": False,
            "execution_endpoint": False,
            "live_trade_control": False,
            "secret_committed": False,
            "running_service_modified": False,
            "deploy": False,
            "push": False,
            "restart": False,
        },
        "risk_level": "LOW",
        "next_implementation_mission": "Implement read-only bridge endpoints first: GET /approval/pending, GET /mission/current, and GET /verification/latest, with auth and no action execution.",
        "outputs": [rel(READINESS_PATH), rel(SUMMARY_PATH), rel(DOC_PATH)],
        "safety_result": "PASS" if not unsafe else "FAIL",
    }


def build_summary(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "titan.echo.bridge_readiness_summary.v1",
        "timestamp_ist": readiness["timestamp_ist"],
        "read_endpoint_count": len(readiness["read_endpoints"]),
        "approval_gated_endpoint_count": len(readiness["approval_gated_endpoints"]),
        "unsafe_endpoint_count": readiness["unsafe_endpoint_count"],
        "approval_required_for_writes": True,
        "raw_shell_endpoint": False,
        "public_unauthenticated_api": False,
        "broker_risk_execution_endpoint": False,
        "running_service_modified": False,
        "risk_level": readiness["risk_level"],
        "safety_result": readiness["safety_result"],
        "next_implementation_mission": readiness["next_implementation_mission"],
    }


def build_doc(readiness: dict[str, Any]) -> str:
    def table(items: list[dict[str, Any]]) -> str:
        rows = ["| Method | Path | Purpose | Gate |", "|---|---|---|---|"]
        for item in items:
            rows.append(
                f"| {item['method']} | `{item['path']}` | {item['purpose']} | {item['mode']} |"
            )
        return "\n".join(rows)

    workflow = "\n".join(
        f"{item['step']}. **{item['name']}**: {item['effect']}"
        for item in readiness["approval_workflow"]
    )
    forbidden = "\n".join(f"- {item}" for item in readiness["forbidden_actions"])
    return f"""# ECHO ChatGPT-Codex bridge plan

Plan only. This document does not add endpoints, start services, run Codex,
push GitHub, pull on VPS, deploy, restart, or rollback.

## Read Endpoints

{table(readiness["read_endpoints"])}

## Approval-Gated Endpoints

{table(readiness["approval_gated_endpoints"])}

## Approval Workflow

{workflow}

## Safety Model

- Mission prepare writes a mission plan only.
- Approval creates a signed approval record.
- Codex only runs an approved mission.
- Git push only uses selected staged files after approval.
- VPS pull only follows push approval.
- Verification runs after pull and records results.
- Deploy/restart requires separate approval.
- Rollback requires separate approval.
- All action records are logged under `data/runtime/echo/`.

## Forbidden Actions

{forbidden}

## Next Implementation Mission

{readiness["next_implementation_mission"]}
"""


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    readiness = build_readiness()
    summary = build_summary(readiness)
    write_echo_json(READINESS_PATH, readiness)
    write_echo_json(SUMMARY_PATH, summary)
    write_doc(DOC_PATH, build_doc(readiness))
    return readiness, summary


def main() -> None:
    readiness, summary = generate_reports()
    print("ECHO bridge readiness plan generated.")
    print(f"read_endpoint_count={summary['read_endpoint_count']}")
    print(f"approval_gated_endpoint_count={summary['approval_gated_endpoint_count']}")
    print(f"unsafe_endpoint_count={summary['unsafe_endpoint_count']}")
    print(f"approval_required_for_writes={summary['approval_required_for_writes']}")
    print(f"safety_result={summary['safety_result']}")
    print(f"risk_level={summary['risk_level']}")
    print(f"next_implementation_mission={summary['next_implementation_mission']}")
    if readiness["unsafe_endpoint_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
