"""Read-only ECHO API status and contract generator.

This module reads approved TITAN evidence files and writes ECHO API metadata
under data/runtime/echo only. It does not execute commands, read secrets, or
modify TITAN runtime behavior.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
STATUS_PATH = ECHO_DIR / "echo_api_status.json"
CONTRACT_PATH = ECHO_DIR / "echo_api_contract.json"
IST = timezone(timedelta(hours=5, minutes=30))

READ_SOURCES = {
    "answer": REPO_ROOT / "data" / "runtime" / "echo" / "echo_answer.json",
    "final_readiness": REPO_ROOT / "data" / "runtime" / "echo" / "final_readiness_summary.json",
    "unified_brain": REPO_ROOT / "data" / "runtime" / "unified_brain_status.json",
    "brain_state": REPO_ROOT / "data" / "runtime" / "brain_state.json",
    "lineage": REPO_ROOT / "data" / "runtime" / "echo" / "final_lineage_truth_summary.json",
    "natural_run": REPO_ROOT / "data" / "runtime" / "echo" / "natural_run_lineage_proof.json",
    "alerts": REPO_ROOT / "data" / "runtime" / "echo" / "alert_queue.json",
    "missions": REPO_ROOT / "data" / "runtime" / "echo" / "mission_plan.json",
    "projects": REPO_ROOT / "data" / "runtime" / "echo" / "project_state_registry.json",
    "runtime_evidence": REPO_ROOT / "data" / "runtime" / "echo" / "runtime_evidence_summary.json",
    "worker_scanner_focus": REPO_ROOT / "data" / "runtime" / "echo" / "worker_scanner_failure_focus_summary.json",
    "query_router": REPO_ROOT / "data" / "runtime" / "echo" / "echo_query_router.json",
}

ENDPOINTS = [
    {
        "method": "GET",
        "path": "/health",
        "read_only": True,
        "description": "Return ECHO API skeleton health and safety metadata.",
        "sources": [],
    },
    {
        "method": "GET",
        "path": "/status",
        "read_only": True,
        "description": "Return combined ECHO/TITAN status from approved evidence files.",
        "sources": ["answer", "final_readiness", "unified_brain", "brain_state", "lineage", "natural_run", "alerts", "missions", "projects", "runtime_evidence", "worker_scanner_focus"],
    },
    {
        "method": "GET",
        "path": "/projects",
        "read_only": True,
        "description": "Return project registry evidence if present.",
        "sources": ["projects"],
    },
    {
        "method": "GET",
        "path": "/unified-brain",
        "read_only": True,
        "description": "Return Unified Brain summary evidence.",
        "sources": ["unified_brain"],
    },
    {
        "method": "GET",
        "path": "/lineage",
        "read_only": True,
        "description": "Return final lineage truth and natural-run proof evidence.",
        "sources": ["lineage", "natural_run"],
    },
    {
        "method": "GET",
        "path": "/alerts",
        "read_only": True,
        "description": "Return alert queue evidence if present.",
        "sources": ["alerts"],
    },
    {
        "method": "GET",
        "path": "/missions",
        "read_only": True,
        "description": "Return mission plan evidence if present.",
        "sources": ["missions"],
    },
    {
        "method": "GET",
        "path": "/answer",
        "read_only": True,
        "description": "Return the current human-style ECHO answer generated from latest evidence. Intent-specific answering is available through GET /query?intent=status.",
        "sources": ["answer", "runtime_evidence", "worker_scanner_focus", "unified_brain", "brain_state", "lineage", "natural_run", "alerts", "projects"],
    },
    {
        "method": "GET",
        "path": "/query",
        "read_only": True,
        "description": "Return an intent-specific ECHO answer from the query router. Use intent=status, runtime, scanner, workers, master_brain, unified_brain, outcome_tracking, lineage, alerts, missions, what_next, what_not_to_do, or unknown.",
        "sources": ["query_router", "answer", "runtime_evidence", "worker_scanner_focus", "unified_brain", "brain_state", "lineage", "natural_run", "alerts", "projects"],
        "query_parameters": {
            "intent": "Optional supported query intent. Defaults to status.",
        },
    },
]

SECRET_MARKERS = ("secret", "token", "password", "api_key", "apikey", "credential", "private_key")


def timestamp_ist() -> str:
    return datetime.now(IST).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def write_echo_json(path: Path, payload: Any) -> None:
    resolved_echo = ECHO_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_echo not in (resolved_path, *resolved_path.parents):
        raise ValueError("ECHO API status generator writes only under data/runtime/echo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            text_key = str(key).lower()
            if any(marker in text_key for marker in SECRET_MARKERS):
                clean[key] = "REDACTED"
            else:
                clean[key] = sanitize(item)
        return clean
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def pick(data: Any, keys: tuple[str, ...], default: Any = "UNKNOWN") -> Any:
    if not isinstance(data, dict):
        return default
    for key in keys:
        current: Any = data
        found = True
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found and current not in (None, ""):
            return current
    return default


def read_sources() -> dict[str, Any]:
    return {name: sanitize(read_json(path)) for name, path in READ_SOURCES.items()}


def alerts_count(alerts: Any) -> int:
    if isinstance(alerts, list):
        return len(alerts)
    if isinstance(alerts, dict):
        for key in ("alerts", "queue", "items"):
            value = alerts.get(key)
            if isinstance(value, list):
                return len(value)
        return 1 if alerts else 0
    return 0


def current_focus(projects: Any, missions: Any) -> str:
    project_focus = pick(projects, ("current_focus", "active_project", "focus"), None)
    if project_focus:
        return str(project_focus)
    mission_focus = pick(missions, ("current_focus", "active_mission", "mission", "title"), None)
    if mission_focus:
        return str(mission_focus)
    return "UNKNOWN"


def next_action(sources: dict[str, Any]) -> str:
    for source_name, keys in (
        ("natural_run", ("recommended_next_titan_project", "recommended_next_action")),
        ("lineage", ("recommended_next_titan_project", "next_recommended_titan_project")),
        ("final_readiness", ("recommended_next_action", "next_recommended_action")),
        ("missions", ("next_recommended_action", "next_action")),
    ):
        value = pick(sources.get(source_name), keys, None)
        if value:
            return str(value)
    return "UNKNOWN"


def project_by_name(projects: Any, name: str) -> dict[str, Any] | None:
    if not isinstance(projects, dict):
        return None
    entries = projects.get("projects")
    if not isinstance(entries, list):
        return None
    for item in entries:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def project_status(projects: Any, name: str, fallback: Any = "UNKNOWN") -> Any:
    item = project_by_name(projects, name)
    if not item:
        return fallback
    return item.get("status") or fallback


def build_status() -> dict[str, Any]:
    sources = read_sources()
    answer = sources["answer"]
    final_readiness = sources["final_readiness"]
    unified_brain = sources["unified_brain"]
    lineage = sources["lineage"]
    natural_run = sources["natural_run"]
    alerts = sources["alerts"]
    missions = sources["missions"]
    projects = sources["projects"]
    runtime_evidence = sources["runtime_evidence"]
    echo_project_status = project_status(projects, "ECHO", None)
    titan_runtime_status = pick(runtime_evidence, ("titan_runtime_status", "current_runtime_truth_verdict"), None)
    unified_runtime_status = pick(runtime_evidence, ("unified_brain_runtime_status",), None)
    titan_project_status = titan_runtime_status or project_status(projects, "Runtime Workers", None)
    unified_project_status = unified_runtime_status or project_status(projects, "Unified Brain", None)
    outcome_project_status = project_status(projects, "Outcome Tracking Truth Upgrade", None)
    natural_project_status = project_status(projects, "Natural-Run Lineage Proof", None)
    status = {
        "schema": "titan.echo.api_status.v1",
        "timestamp_ist": timestamp_ist(),
        "api_mode": "READ_ONLY",
        "echo_status": echo_project_status or pick(final_readiness, ("echo_status", "status", "verdict")),
        "titan_status": titan_project_status or pick(final_readiness, ("titan_status", "runtime_status", "status", "verdict")),
        "unified_brain_status": unified_project_status or pick(unified_brain, ("unified_brain_status", "status", "verdict")),
        "outcome_tracking_status": outcome_project_status or pick(lineage, ("outcome_tracking_truth_upgrade_status", "outcome_tracking_status")),
        "lineage_status": pick(lineage, ("final_verdict", "lineage_status")),
        "natural_run_status": natural_project_status or pick(natural_run, ("verdict", "natural_run_status")),
        "alerts_count": alerts_count(alerts),
        "current_human_answer": pick(answer, ("short_answer",), "UNKNOWN"),
        "current_focus": current_focus(projects, missions),
        "next_recommended_action": next_action(sources),
        "evidence_files": {
            name: {
                "path": relative(path),
                "exists": path.exists(),
            }
            for name, path in READ_SOURCES.items()
        },
        "safety": {
            "read_only": True,
            "shell_execution": False,
            "codex_execution": False,
            "reads_env": False,
            "writes_outside_echo_runtime": False,
            "broker_risk_scanner_changes": False,
            "deploy_or_restart": False,
        },
    }
    return status


def build_contract() -> dict[str, Any]:
    return {
        "schema": "titan.echo.api_contract.v1",
        "timestamp_ist": timestamp_ist(),
        "api_mode": "READ_ONLY",
        "endpoints": ENDPOINTS,
        "allowed_read_sources": {
            name: relative(path)
            for name, path in READ_SOURCES.items()
        },
        "allowed_write_outputs": [
            relative(STATUS_PATH),
            relative(CONTRACT_PATH),
            "data/runtime/echo/echo_query_router.json",
            "data/runtime/echo/echo_query_router_summary.json",
        ],
        "forbidden_capabilities": [
            "shell_execution",
            "codex_execution",
            "broker_order_execution",
            "risk_changes",
            "scanner_changes",
            "deploy",
            "restart",
            "secret_exposure",
            ".env_reads",
        ],
    }


def generate_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    status = build_status()
    contract = build_contract()
    write_echo_json(STATUS_PATH, status)
    write_echo_json(CONTRACT_PATH, contract)
    return status, contract


def main() -> None:
    status, contract = generate_reports()
    print("ECHO API status generated.")
    print(f"echo_status={status['echo_status']}")
    print(f"titan_status={status['titan_status']}")
    print(f"unified_brain_status={status['unified_brain_status']}")
    print(f"outcome_tracking_status={status['outcome_tracking_status']}")
    print(f"lineage_status={status['lineage_status']}")
    print(f"natural_run_status={status['natural_run_status']}")
    print(f"alerts_count={status['alerts_count']}")
    print(f"current_focus={status['current_focus']}")
    print(f"next_recommended_action={status['next_recommended_action']}")
    print("endpoints=" + ", ".join(endpoint["path"] for endpoint in contract["endpoints"]))


if __name__ == "__main__":
    main()
