"""Disabled-by-default read-only relay skeleton for ECHO evidence endpoints.

This module is safe to import. It defines a FastAPI app when FastAPI is
available but does not start a service, open ports, or contact ECHO at import
time.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from urllib import error, request

from titan_echo.echo_relay_auth import require_relay_key
from titan_echo.echo_git_vps_bridge import verify_request, push_committed_changes, pull_committed_changes
from titan_echo.echo_mission_brain import (
    approve_step,
    create_mission,
    mission_status,
    resume_mission,
    rollback_request,
    rollback_run_approved,
    rollback_status,
)
import subprocess
from titan_echo.echo_relay_config import (
    ECHO_INTERNAL_HEADER_NAME,
    RELAY_HEADER_NAME,
    endpoint_allowed,
    internal_api_key,
    internal_base_url,
    relay_enabled,
    relay_safety,
    relay_status_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "data" / "runtime" / "echo"
CODEX_RUNNER_REQUEST_PATH = ECHO_DIR / "codex_runner_request.json"
GIT_VPS_BRIDGE_REQUEST_PATH = ECHO_DIR / "git_vps_bridge_request.json"
GIT_VPS_BRIDGE_POLICY_PATH = ECHO_DIR / "git_vps_bridge_policy.json"


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import Body, FastAPI, Header
else:  # pragma: no cover - depends on local dependency set
    Body = None  # type: ignore[assignment, misc]
    FastAPI = None  # type: ignore[assignment, misc]
    Header = None  # type: ignore[assignment, misc]



def _codex_prompt_safety_check(prompt: str) -> dict[str, Any]:
    lowered = prompt.lower()

    blocked_terms = [
        "rm -rf",
        "sudo ",
        "systemctl",
        "restart",
        "deploy",
        "git push",
        "git pull",
        "broker",
        "live order",
        "place order",
        "api key",
        ".env",
        "delete ",
        "chmod",
        "chown",
        "kill ",
        "pkill",
    ]

    hits = [term for term in blocked_terms if term in lowered]

    allowed_prefixes = [
        "create a harmless proof file",
        "inspect",
        "read",
        "summarize",
        "verify",
        "report",
    ]

    prefix_ok = any(lowered.strip().startswith(x) for x in allowed_prefixes)

    if hits:
        return {
            "allowed": False,
            "reason": "blocked_terms_present",
            "hits": hits,
        }

    if not prefix_ok:
        return {
            "allowed": False,
            "reason": "prompt_does_not_match_safe_prefix",
            "allowed_prefixes": allowed_prefixes,
        }

    return {
        "allowed": True,
        "reason": "safe_prompt_shape",
        "hits": [],
    }


def _read_echo_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _compact_evidence(payload: dict[str, Any], source: str) -> dict[str, Any]:
    if not payload:
        return {"source": source, "present": False}
    return {
        "source": source,
        "present": True,
        "status": payload.get("status"),
        "request_id": payload.get("request_id"),
        "execution_performed": bool(payload.get("execution_performed")),
        "blockers": list(payload.get("blockers") or [])[:8],
    }


def _post_action_contract(
    *,
    action: str,
    post_endpoint: str,
    approval_id: str | None = None,
    latest: dict[str, Any] | None = None,
    evidence_source: str = "",
    next_step: str = "",
) -> dict[str, Any]:
    latest = latest if isinstance(latest, dict) else {}
    latest_status = str(latest.get("status") or "")
    blocked = any(token in latest_status.upper() for token in ("BLOCKED", "FAILED", "EXCEPTION", "NOT_RECORDED"))
    accepted = bool(latest) and not blocked and any(
        token in latest_status.upper()
        for token in ("OK", "RECORDED", "EXECUTED")
    )
    resolved_approval_id = approval_id or str(latest.get("approval_id") or "").strip() or None
    return {
        "status": "ACTION_STATUS_PRESENT" if latest else "ACTION_STATUS_NO_RESULT_RECORDED",
        "action": action,
        "accepted": accepted,
        "blocked": blocked,
        "approval_required": True,
        "approval_id": resolved_approval_id,
        "next_step": next_step or f"Use POST {post_endpoint} only after explicit approval; this GET endpoint is read-only.",
        "evidence_summary": _compact_evidence(latest, evidence_source or post_endpoint),
        "safety": {
            "read_only_get_fallback": True,
            "execution_allowed": False,
            "codex_execution": False,
            "git_push_pull": False,
            "deploy_or_restart": False,
            "broker_changed": False,
            "risk_changed": False,
            "runtime_workers_changed": False,
        },
    }


def relay_verify_run_approved_status(approval_id: str | None = None) -> dict[str, Any]:
    return _post_action_contract(
        action="verify_run_approved",
        post_endpoint="/relay/verify/run-approved",
        approval_id=approval_id,
        latest={
            "status": "VERIFY_POST_BACKEND_AVAILABLE",
            "approval_id": approval_id,
            "execution_performed": False,
        },
        evidence_source="relay_verify_status_fallback",
        next_step="If approved, call POST /relay/verify/run-approved; use this GET only for compact UI status.",
    )


def relay_codex_run_approved_status(approval_id: str | None = None) -> dict[str, Any]:
    latest = _read_echo_json(CODEX_RUNNER_REQUEST_PATH)
    return _post_action_contract(
        action="codex_run_approved",
        post_endpoint="/relay/codex/run-approved",
        approval_id=approval_id,
        latest=latest,
        evidence_source="data/runtime/echo/codex_runner_request.json",
        next_step="Review approval and prompt safety; POST remains the only path that can request Codex.",
    )


def relay_git_push_approved_status(approval_id: str | None = None) -> dict[str, Any]:
    latest = _read_echo_json(GIT_VPS_BRIDGE_REQUEST_PATH)
    if latest.get("action") not in ("git_push", ""):
        latest = {}
    policy = _read_echo_json(GIT_VPS_BRIDGE_POLICY_PATH)
    payload = _post_action_contract(
        action="git_push_approved",
        post_endpoint="/relay/git/push-approved",
        approval_id=approval_id,
        latest=latest,
        evidence_source="data/runtime/echo/git_vps_bridge_request.json",
        next_step="Confirm approval token, then use POST /relay/git/push-approved only if push is explicitly approved.",
    )
    payload["evidence_summary"]["policy_status"] = policy.get("status") if policy else "POLICY_FILE_NOT_PRESENT"
    return payload


def relay_vps_pull_approved_status(approval_id: str | None = None) -> dict[str, Any]:
    latest = _read_echo_json(GIT_VPS_BRIDGE_REQUEST_PATH)
    if latest.get("action") not in ("vps_pull", ""):
        latest = {}
    policy = _read_echo_json(GIT_VPS_BRIDGE_POLICY_PATH)
    payload = _post_action_contract(
        action="vps_pull_approved",
        post_endpoint="/relay/vps/pull-approved",
        approval_id=approval_id,
        latest=latest,
        evidence_source="data/runtime/echo/git_vps_bridge_request.json",
        next_step="Confirm approval token, then use POST /relay/vps/pull-approved only after approved push workflow.",
    )
    payload["evidence_summary"]["policy_status"] = policy.get("status") if policy else "POLICY_FILE_NOT_PRESENT"
    return payload


def relay_post_action_status(action: str = "all", approval_id: str | None = None) -> dict[str, Any]:
    actions = {
        "verify": relay_verify_run_approved_status,
        "codex": relay_codex_run_approved_status,
        "git_push": relay_git_push_approved_status,
        "vps_pull": relay_vps_pull_approved_status,
    }
    selected = str(action or "all").strip().lower()
    if selected in actions:
        return actions[selected](approval_id)
    return {
        "status": "ACTION_STATUS_PRESENT",
        "action": "all",
        "accepted": False,
        "blocked": False,
        "approval_required": True,
        "approval_id": approval_id,
        "next_step": "Choose one compact fallback: verify, codex, git_push, or vps_pull.",
        "evidence_summary": {name: fn(approval_id)["evidence_summary"] for name, fn in actions.items()},
        "safety": relay_safety(),
    }


def _disabled_payload() -> dict[str, Any]:
    payload = relay_status_payload()
    payload["status"] = "RELAY_DISABLED"
    payload["relay_enabled"] = False
    return payload


def _blocked_payload(path: str) -> dict[str, Any]:
    return {
        "status": "RELAY_BLOCKED",
        "path": path,
        "reason": "Endpoint is not in the read-only relay allowlist.",
        "safety": relay_safety(),
    }


def _not_configured_payload() -> dict[str, Any]:
    return {
        "status": "RELAY_NOT_CONFIGURED",
        "reason": "ECHO_INTERNAL_API_KEY is required when the relay is enabled.",
        "safety": relay_safety(),
    }


def _forward_to_echo(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    if not endpoint_allowed(path):
        return _blocked_payload(path)
    api_key = internal_api_key()
    if not api_key:
        return _not_configured_payload()

    body = None
    headers = {ECHO_INTERNAL_HEADER_NAME: api_key}
    if method.upper() == "POST":
        body = json.dumps(payload or {}).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(
        internal_base_url() + path,
        data=body,
        headers=headers,
        method=method.upper(),
    )
    try:
        with request.urlopen(req, timeout=5) as response:  # nosec B310 - localhost-only relay when enabled
            response_body = response.read().decode("utf-8", errors="ignore")
            data = json.loads(response_body) if response_body else None
            return {
                "status": "RELAY_FORWARDED",
                "path": path,
                "upstream_status": response.status,
                "data": data,
                "safety": relay_safety(),
            }
    except error.HTTPError as exc:
        return {
            "status": "RELAY_UPSTREAM_HTTP_ERROR",
            "path": path,
            "upstream_status": exc.code,
            "safety": relay_safety(),
        }
    except Exception as exc:
        return {
            "status": "RELAY_UPSTREAM_UNAVAILABLE",
            "path": path,
            "error": type(exc).__name__,
            "safety": relay_safety(),
        }


def relay_health(x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return relay_status_payload()


def relay_jarvis_ask(payload: dict[str, Any], x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("POST", "/jarvis/ask", payload if isinstance(payload, dict) else {})


def relay_jarvis_ask_compact(payload: dict[str, Any], x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("POST", "/jarvis/ask/compact", payload if isinstance(payload, dict) else {})


def relay_titan_status(x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("GET", "/titan/status")


def relay_titan_status_summary(x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("GET", "/titan/status/summary")


def relay_chatgpt_integration_status(x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("GET", "/chatgpt/integration/status")


def relay_chatgpt_evidence_contract(x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("GET", "/chatgpt/evidence/contract")


def relay_chatgpt_evidence_catalog(x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("GET", "/chatgpt/evidence/catalog")


def relay_chatgpt_evidence_manifest() -> dict[str, Any]:
    return {
        "schema": "titan.evidence.manifest.v1",
        "status": "EVIDENCE_INDEX_PRESENT",
        "read_only": True,
        "write_permitted": False,
    }


def relay_chatgpt_evidence_manifest_batch1() -> dict[str, Any]:
    return {
        "schema": "titan.evidence.manifest.v1",
        "status": "EVIDENCE_INDEX_PRESENT",
        "read_only": True,
        "write_permitted": False,
    }


def relay_mission_create(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return create_mission(payload or {})


def relay_mission_status(mission_id: str | None = None) -> dict[str, Any]:
    return mission_status(mission_id)


def relay_mission_resume(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return resume_mission(payload or {})


def relay_mission_approve_step(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return approve_step(payload or {})


def relay_rollback_status(mission_id: str | None = None) -> dict[str, Any]:
    return rollback_status(mission_id)


def relay_rollback_request(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return rollback_request(payload or {})


def relay_rollback_run_approved(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return rollback_run_approved(payload or {})


app = None
if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="ECHO Secure Relay Skeleton",
        version="0.1.0",
        description="Disabled-by-default read-only relay skeleton for ECHO evidence.",
    )



    @app.get("/relay/chatgpt/evidence/manifest")
    def relay_chatgpt_evidence_manifest(x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME)):
        require_relay_key(x_echo_relay_key)
        return {
            "schema": "titan.evidence.manifest.v1",
            "status": "EVIDENCE_INDEX_PRESENT",
            "read_only": True,
            "write_permitted": False,
            "shell_execution": False,
            "runtime_changed": False,
            "trade_execution_permitted": False,
            "sources": [
                {"name": "runtime_heartbeat", "endpoint": "/relay/chatgpt/evidence/manifest/batch1", "status": "PRESENT"},
                {"name": "runtime_workers", "endpoint": "/relay/chatgpt/evidence/manifest/batch1", "status": "PRESENT"},
                {"name": "logs_index", "endpoint": "/relay/chatgpt/evidence/manifest/batch1", "status": "PRESENT"},
                {"name": "files_tree", "endpoint": "/relay/chatgpt/evidence/manifest/batch1", "status": "PRESENT"}
            ]
        }

    @app.get("/relay/chatgpt/evidence/manifest/batch1")
    def relay_chatgpt_evidence_manifest_batch1(x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME)):
        require_relay_key(x_echo_relay_key)
        return {
            "schema": "titan.evidence.manifest.batch1.v1",
            "status": "BATCH1_READ_ONLY_PRESENT",
            "read_only": True,
            "write_permitted": False,
            "shell_execution": False,
            "runtime_changed": False,
            "trade_execution_permitted": False,
            "endpoints": [
                "/relay/chatgpt/evidence/manifest",
                "/relay/chatgpt/evidence/manifest/batch1"
            ]
        }

    @app.get("/relay/health")
    def route_relay_health(x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME)) -> dict[str, Any]:
        return relay_health(x_echo_relay_key)

    @app.post("/relay/jarvis/ask")
    def route_relay_jarvis_ask(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        return relay_jarvis_ask(payload or {}, x_echo_relay_key)

    @app.post("/relay/jarvis/ask/compact")
    def route_relay_jarvis_ask_compact(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        return relay_jarvis_ask_compact(payload or {}, x_echo_relay_key)

    @app.get("/relay/titan/status")
    def route_relay_titan_status(x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME)) -> dict[str, Any]:
        return relay_titan_status(x_echo_relay_key)

    @app.get("/relay/titan/status/summary")
    def route_relay_titan_status_summary(
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        return relay_titan_status_summary(x_echo_relay_key)

    @app.get("/relay/chatgpt/integration/status")
    def route_relay_chatgpt_integration_status(
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        return relay_chatgpt_integration_status(x_echo_relay_key)

    @app.get("/relay/chatgpt/evidence/contract")
    def route_relay_chatgpt_evidence_contract(
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        return relay_chatgpt_evidence_contract(x_echo_relay_key)

    @app.get("/relay/chatgpt/evidence/catalog")
    def route_relay_chatgpt_evidence_catalog(
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        return relay_chatgpt_evidence_catalog(x_echo_relay_key)

    @app.get("/relay/actions/status")
    def route_relay_post_action_status(
        action: str = "all",
        approval_id: str | None = None,
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_post_action_status(action, approval_id)

    @app.get("/relay/verify/run-approved/status")
    def route_relay_verify_run_approved_status(
        approval_id: str | None = None,
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_verify_run_approved_status(approval_id)

    @app.get("/relay/codex/run-approved/status")
    def route_relay_codex_run_approved_status(
        approval_id: str | None = None,
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_codex_run_approved_status(approval_id)

    @app.get("/relay/git/push-approved/status")
    def route_relay_git_push_approved_status(
        approval_id: str | None = None,
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_git_push_approved_status(approval_id)

    @app.get("/relay/vps/pull-approved/status")
    def route_relay_vps_pull_approved_status(
        approval_id: str | None = None,
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_vps_pull_approved_status(approval_id)

    @app.post("/relay/mission/create")
    def route_relay_mission_create(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_mission_create(payload or {})

    @app.get("/relay/mission/status")
    def route_relay_mission_status(
        mission_id: str | None = None,
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_mission_status(mission_id)

    @app.post("/relay/mission/resume")
    def route_relay_mission_resume(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_mission_resume(payload or {})

    @app.post("/relay/mission/approve-step")
    def route_relay_mission_approve_step(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_mission_approve_step(payload or {})

    @app.get("/relay/rollback/status")
    def route_relay_rollback_status(
        mission_id: str | None = None,
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_rollback_status(mission_id)

    @app.post("/relay/rollback/request")
    def route_relay_rollback_request(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_rollback_request(payload or {})

    @app.post("/relay/rollback/run-approved")
    def route_relay_rollback_run_approved(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        return relay_rollback_run_approved(payload or {})


    @app.post("/relay/verify/run-approved")
    def route_relay_verify_run_approved(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)
        result = verify_request()
        result["relay_endpoint"] = "/relay/verify/run-approved"
        result["approval_required"] = True
        result["direct_git_push"] = False
        result["direct_vps_pull"] = False
        result["direct_deploy_or_restart"] = False
        return result



    @app.post("/relay/codex/run-approved")
    def route_relay_codex_run_approved(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)

        body = payload or {}
        approval_id = str(body.get("approval_id") or "").strip()
        prompt = str(body.get("prompt") or "").strip()

        if not approval_id:
            return {"status": "CODEX_BLOCKED", "reason": "approval_id required"}
        if not prompt:
            return {"status": "CODEX_BLOCKED", "reason": "prompt required"}

        safety_check = _codex_prompt_safety_check(prompt)
        if not safety_check.get("allowed"):
            return {
                "status": "CODEX_BLOCKED",
                "reason": "prompt_safety_check_failed",
                "safety_check": safety_check,
                "execution_performed": False,
            }

        cmd = [
            "codex", "exec",
            "--skip-git-repo-check",
            "-m", "gpt-5.4",
            prompt,
        ]

        try:
            r = subprocess.run(
                cmd,
                cwd="/home/ubuntu/titan-bot",
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "schema": "titan.echo.codex_run_approved.v1",
                "status": "CODEX_EXECUTED" if r.returncode == 0 else "CODEX_FAILED",
                "approval_id": approval_id,
                "returncode": r.returncode,
                "stdout": r.stdout[-4000:],
                "stderr": r.stderr[-2000:],
                "safety": {
                    "git_push_pull": False,
                    "deploy_or_restart": False,
                    "titan_runtime_changed": False,
                    "broker_changed": False,
                    "risk_changed": False
                }
            }
        except Exception as e:
            return {
                "schema": "titan.echo.codex_run_approved.v1",
                "status": "CODEX_EXCEPTION",
                "error": type(e).__name__,
                "detail": str(e)
            }



    @app.post("/relay/git/push-approved")
    def route_relay_git_push_approved(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)

        body = payload or {}
        approval_id = str(body.get("approval_id") or "").strip()
        confirm = str(body.get("confirm") or "").strip()

        if not approval_id:
            return {"status": "GIT_PUSH_BLOCKED", "reason": "approval_id required"}
        if confirm != "I_APPROVE_GIT_PUSH":
            return {"status": "GIT_PUSH_BLOCKED", "reason": "confirm must be I_APPROVE_GIT_PUSH"}

        result = push_committed_changes()
        result["relay_endpoint"] = "/relay/git/push-approved"
        result["approval_required"] = True
        result["direct_vps_pull"] = False
        result["direct_deploy_or_restart"] = False
        return result



    @app.post("/relay/vps/pull-approved")
    def route_relay_vps_pull_approved(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        require_relay_key(x_echo_relay_key)

        body = payload or {}
        approval_id = str(body.get("approval_id") or "").strip()
        confirm = str(body.get("confirm") or "").strip()

        if not approval_id:
            return {"status": "VPS_PULL_BLOCKED", "reason": "approval_id required"}
        if confirm != "I_APPROVE_VPS_PULL":
            return {"status": "VPS_PULL_BLOCKED", "reason": "confirm must be I_APPROVE_VPS_PULL"}

        result = pull_committed_changes()
        result["relay_endpoint"] = "/relay/vps/pull-approved"
        result["approval_required"] = True
        result["direct_deploy_or_restart"] = False
        result["services_restarted"] = False
        return result



__all__ = [
    "FASTAPI_AVAILABLE",
    "app",
    "relay_chatgpt_evidence_catalog",
    "relay_chatgpt_evidence_contract",
    "relay_chatgpt_evidence_manifest",
    "relay_chatgpt_evidence_manifest_batch1",
    "relay_chatgpt_integration_status",
    "relay_codex_run_approved_status",
    "relay_git_push_approved_status",
    "relay_health",
    "relay_jarvis_ask",
    "relay_jarvis_ask_compact",
    "relay_mission_approve_step",
    "relay_mission_create",
    "relay_mission_resume",
    "relay_mission_status",
    "relay_post_action_status",
    "relay_rollback_request",
    "relay_rollback_run_approved",
    "relay_rollback_status",
    "relay_titan_status",
    "relay_titan_status_summary",
    "relay_verify_run_approved_status",
    "relay_vps_pull_approved_status",
]
