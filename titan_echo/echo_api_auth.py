"""API-key auth helpers for the local ECHO FastAPI surface.

The key source is the ECHO_API_KEY environment variable. This module does not
read .env files, does not contain a real key, and fails closed when no key is
configured.
"""

from __future__ import annotations

import hmac
import importlib.util
import os
from typing import Any


HEADER_NAME = "X-ECHO-API-KEY"
ENV_VAR_NAME = "ECHO_API_KEY"
PROTECTED_ENDPOINTS = (
    "/status",
    "/projects",
    "/unified-brain",
    "/lineage",
    "/alerts",
    "/missions",
    "/answer",
    "/query",
    "/approval/pending",
    "/mission/current",
    "/verification/latest",
    "/mission/prepare",
    "/approval/approve",
    "/approval/reject",
    "/execution/readiness",
    "/execution/readiness/check",
    "/execution/preview",
    "/execution/preview/generate",
    "/execution/authorization",
    "/execution/authorize",
    "/execution/lock",
    "/execution/lock/create",
    "/execution/evidence",
    "/execution/ledger",
    "/execution/policy",
    "/execution/gate",
    "/execution/gate/evaluate",
    "/chatgpt/readiness",
    "/chatgpt/readiness/check",
    "/chat/session",
    "/chat/session/create",
    "/echo/context",
    "/echo/runtime",
    "/echo/evidence",
    "/jarvis/status",
    "/jarvis/question",
    "/jarvis/ask",
    "/jarvis/explain",
    "/jarvis/investigate",
    "/jarvis/mission",
    "/titan/status",
    "/titan/health",
    "/titan/workers",
    "/titan/scanner",
    "/titan/trades",
    "/titan/brain",
    "/titan/runtime/context",
    "/chatgpt/bridge/readiness",
    "/chatgpt/connector/plan",
    "/chatgpt/handshake/status",
    "/chatgpt/handshake/test",
    "/chatgpt/evidence/contract",
    "/chatgpt/evidence/catalog",
    "/chatgpt/integration/status",
    "/chatgpt/secure-relay/plan",
    "/chatgpt/custom-action/plan",
    "/codex/runner/status",
    "/codex/runner/policy",
    "/codex/runner/request",
)
PUBLIC_ENDPOINTS = ("/health",)

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import Header, HTTPException
else:  # pragma: no cover - depends on local dependency set
    Header = None  # type: ignore[assignment, misc]
    HTTPException = None  # type: ignore[assignment, misc]


def get_auth_design() -> dict[str, Any]:
    configured = bool(os.environ.get(ENV_VAR_NAME))
    return {
        "schema": "titan.echo.api_auth_design.v1",
        "auth_required": True,
        "auth_method": "API key header",
        "header_name": HEADER_NAME,
        "key_source": "environment variable",
        "environment_variable_name": ENV_VAR_NAME,
        "env_file_reading": False,
        "hardcoded_key": False,
        "key_configured": configured,
        "missing_key_behavior": "fail_closed",
        "public_endpoints": list(PUBLIC_ENDPOINTS),
        "protected_endpoints": list(PROTECTED_ENDPOINTS),
        "failed_auth_status_code": 401,
        "failed_auth_body": {"detail": "Unauthorized"},
        "test_override_allowed": "temporary in-memory key in local smoke test only",
    }


def expected_key_from_environment() -> str | None:
    return os.environ.get(ENV_VAR_NAME)


def validate_api_key(provided_key: str | None, expected_key: str | None = None) -> bool:
    expected = expected_key if expected_key is not None else expected_key_from_environment()
    if not expected or not provided_key:
        return False
    return hmac.compare_digest(provided_key, expected)


def require_echo_api_key(x_echo_api_key: str | None = None) -> bool:
    if validate_api_key(x_echo_api_key):
        return True
    if HTTPException is None:  # pragma: no cover - FastAPI unavailable path
        raise PermissionError("Unauthorized")
    raise HTTPException(status_code=401, detail="Unauthorized")


if Header is not None:
    require_echo_api_key.__signature__ = None  # type: ignore[attr-defined]

    def require_echo_api_key(
        x_echo_api_key: str | None = Header(default=None, alias=HEADER_NAME),
    ) -> bool:
        if validate_api_key(x_echo_api_key):
            return True
        raise HTTPException(status_code=401, detail="Unauthorized")


__all__ = [
    "ENV_VAR_NAME",
    "HEADER_NAME",
    "PROTECTED_ENDPOINTS",
    "PUBLIC_ENDPOINTS",
    "get_auth_design",
    "expected_key_from_environment",
    "validate_api_key",
    "require_echo_api_key",
]
