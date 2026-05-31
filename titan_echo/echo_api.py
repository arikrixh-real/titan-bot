"""Read-only local ECHO API surface.

This module is safe to import without starting a server. When FastAPI is
installed it defines an ``app`` with GET-only routes. When FastAPI is missing
it still exposes fallback functions for local callers.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from titan_echo.echo_api_auth import require_echo_api_key
from titan_echo.echo_api_status import build_status, read_sources


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import Depends, FastAPI
else:  # pragma: no cover - depends on local dependency set
    Depends = None  # type: ignore[assignment, misc]
    FastAPI = None  # type: ignore[assignment, misc]


READ_ONLY_EVIDENCE = {
    "answer": ECHO_DIR / "echo_answer.json",
    "mission_center": ECHO_DIR / "echo_mission_center.json",
    "query_router": ECHO_DIR / "echo_query_router.json",
    "approval_queue": ECHO_DIR / "approval_queue.json",
    "mission_plan": ECHO_DIR / "mission_plan.json",
    "verification_report": ECHO_DIR / "verification_report.json",
}

SECRET_MARKERS = (
    "api_key",
    "apikey",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key).lower()
            if any(marker in text_key for marker in SECRET_MARKERS):
                clean[key] = "REDACTED"
            else:
                clean[key] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _evidence_payload(name: str) -> dict[str, Any]:
    path = READ_ONLY_EVIDENCE[name]
    data = _sanitize(_read_json(path))
    return {
        "source": _relative(path),
        "data": data,
        "status": "EVIDENCE_PRESENT" if data is not None else "UNKNOWN",
    }


def _source_status(name: str, missing_status: str) -> dict[str, Any]:
    path = READ_ONLY_EVIDENCE[name]
    data = _sanitize(_read_json(path))
    return {
        "source": _relative(path),
        "data": data,
        "status": "EVIDENCE_PRESENT" if data is not None else missing_status,
    }


def get_health() -> dict[str, Any]:
    return {
        "echo_api": "AVAILABLE",
        "api_mode": "FASTAPI_APP" if FASTAPI_AVAILABLE else "FALLBACK_FUNCTIONS",
        "fastapi_available": FASTAPI_AVAILABLE,
        "read_only": True,
        "shell_execution": False,
        "codex_execution": False,
        "broker_risk_scanner_changes": False,
        "deploy_or_restart": False,
        "public_exposure": False,
    }


def get_status() -> dict[str, Any]:
    status = build_status()
    status["api_mode"] = "FASTAPI_APP" if FASTAPI_AVAILABLE else "FALLBACK_FUNCTIONS"
    status["fastapi_available"] = FASTAPI_AVAILABLE
    return status


def get_projects() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/project_state_registry.json",
        "data": sources["projects"],
        "status": "EVIDENCE_PRESENT" if sources["projects"] is not None else "UNKNOWN",
    }


def get_unified_brain() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/unified_brain_status.json",
        "data": sources["unified_brain"],
        "status": "EVIDENCE_PRESENT" if sources["unified_brain"] is not None else "UNKNOWN",
    }


def get_lineage() -> dict[str, Any]:
    sources = read_sources()
    return {
        "sources": [
            "data/runtime/echo/final_lineage_truth_summary.json",
            "data/runtime/echo/natural_run_lineage_proof.json",
        ],
        "final_lineage_truth": sources["lineage"],
        "natural_run_lineage_proof": sources["natural_run"],
    }


def get_alerts() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/alert_queue.json",
        "data": sources["alerts"],
        "status": "EVIDENCE_PRESENT" if sources["alerts"] is not None else "UNKNOWN",
    }


def get_missions() -> dict[str, Any]:
    sources = read_sources()
    return {
        "source": "data/runtime/echo/mission_plan.json",
        "data": sources["missions"],
        "status": "EVIDENCE_PRESENT" if sources["missions"] is not None else "UNKNOWN",
    }


def get_answer() -> dict[str, Any]:
    answer_payload = _evidence_payload("answer")
    if answer_payload["data"] is not None:
        return answer_payload
    mission_payload = _evidence_payload("mission_center")
    mission_payload["fallback_source"] = mission_payload["source"]
    mission_payload["source"] = answer_payload["source"]
    return mission_payload


def get_query(intent: str = "status") -> dict[str, Any]:
    requested_intent = intent or "status"
    router_payload = _evidence_payload("query_router")
    router_data = router_payload["data"]
    if not isinstance(router_data, dict):
        return {
            "source": router_payload["source"],
            "intent": requested_intent,
            "status": "UNKNOWN",
            "data": None,
        }
    responses = router_data.get("responses")
    if not isinstance(responses, dict):
        return {
            "source": router_payload["source"],
            "intent": requested_intent,
            "status": "UNKNOWN",
            "data": router_data,
        }
    selected = responses.get(requested_intent) or responses.get("unknown")
    resolved_intent = requested_intent if requested_intent in responses else "unknown"
    return {
        "source": router_payload["source"],
        "intent": requested_intent,
        "resolved_intent": resolved_intent,
        "status": "EVIDENCE_PRESENT" if selected is not None else "UNKNOWN",
        "data": selected,
    }


def get_approval_pending() -> dict[str, Any]:
    payload = _source_status("approval_queue", "WAITING_FOR_DATA")
    data = payload["data"]
    approvals = data.get("approvals") if isinstance(data, dict) else []
    if not isinstance(approvals, list):
        approvals = []
    pending = [
        item
        for item in approvals
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "PENDING"
    ]
    return {
        "source": payload["source"],
        "status": payload["status"],
        "pending": pending,
        "pending_count": len(pending),
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


def get_mission_current() -> dict[str, Any]:
    payload = _source_status("mission_plan", "UNKNOWN_NOT_PROVEN")
    data = payload["data"]
    active_mission = None
    if isinstance(data, dict):
        active_mission = (
            data.get("current_mission")
            or data.get("active_mission")
            or data.get("mission")
        )
    return {
        "source": payload["source"],
        "status": payload["status"],
        "active_mission": active_mission,
        "active_mission_proven": active_mission is not None,
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


def get_verification_latest() -> dict[str, Any]:
    payload = _source_status("verification_report", "UNKNOWN_NOT_PROVEN")
    return {
        "source": payload["source"],
        "status": payload["status"],
        "verification_report": payload["data"],
        "verification_proven": payload["data"] is not None,
        "read_only": True,
        "execution_allowed": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
    }


# Compatibility aliases for existing local imports and FastAPI route names.
health = get_health
status = get_status
projects = get_projects
unified_brain = get_unified_brain
lineage = get_lineage
alerts = get_alerts
missions = get_missions
answer = get_answer
query = get_query
approval_pending = get_approval_pending
mission_current = get_mission_current
verification_latest = get_verification_latest


app = None
if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="ECHO Read-Only API",
        version="0.2.0",
        description="Read-only local ECHO API for existing TITAN evidence files.",
    )
    auth_dependency = [Depends(require_echo_api_key)]
    app.get("/health")(get_health)
    app.get("/status", dependencies=auth_dependency)(get_status)
    app.get("/projects", dependencies=auth_dependency)(get_projects)
    app.get("/unified-brain", dependencies=auth_dependency)(get_unified_brain)
    app.get("/lineage", dependencies=auth_dependency)(get_lineage)
    app.get("/alerts", dependencies=auth_dependency)(get_alerts)
    app.get("/missions", dependencies=auth_dependency)(get_missions)
    app.get("/answer", dependencies=auth_dependency)(get_answer)
    app.get("/query", dependencies=auth_dependency)(get_query)
    app.get("/approval/pending", dependencies=auth_dependency)(get_approval_pending)
    app.get("/mission/current", dependencies=auth_dependency)(get_mission_current)
    app.get("/verification/latest", dependencies=auth_dependency)(get_verification_latest)


__all__ = [
    "FASTAPI_AVAILABLE",
    "app",
    "get_health",
    "get_status",
    "get_projects",
    "get_unified_brain",
    "get_lineage",
    "get_alerts",
    "get_missions",
    "get_answer",
    "get_query",
    "get_approval_pending",
    "get_mission_current",
    "get_verification_latest",
    "health",
    "status",
    "projects",
    "unified_brain",
    "lineage",
    "alerts",
    "missions",
    "answer",
    "query",
    "approval_pending",
    "mission_current",
    "verification_latest",
]
