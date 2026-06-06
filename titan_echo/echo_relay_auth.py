"""Authentication helpers for the disabled-by-default ECHO relay skeleton."""

from __future__ import annotations

import hmac
import importlib.util
import os
from typing import Any

from titan_echo.echo_relay_config import RELAY_HEADER_NAME, relay_api_key, relay_enabled


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import HTTPException
else:  # pragma: no cover - depends on local dependency set
    HTTPException = None  # type: ignore[assignment, misc]


def validate_relay_key(provided_key: str | None, expected_key: str | None = None) -> bool:
    expected = expected_key if expected_key is not None else relay_api_key()
    if not expected or not provided_key:
        return False
    return hmac.compare_digest(provided_key, expected)


def require_relay_key(provided_key: str | None) -> bool:
    if validate_relay_key(provided_key):
        return True
    if HTTPException is None:  # pragma: no cover - FastAPI unavailable path
        raise PermissionError("Unauthorized")
    raise HTTPException(status_code=401, detail="Unauthorized")


LOCALHOST_ONLY_ENV = "ECHO_RELAY_LOCALHOST_ONLY"
LOCALHOST_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def localhost_only_execution_enabled() -> bool:
    return os.environ.get(LOCALHOST_ONLY_ENV, "true").strip().lower() == "true"


def is_localhost_client(client_host: str | None) -> bool:
    host = str(client_host or "").strip().lower()
    if not host:
        return False
    if host.startswith("::ffff:"):
        host = host.removeprefix("::ffff:")
    return host in LOCALHOST_HOSTS


def relay_execution_hardening_status(
    *,
    provided_key: str | None,
    client_host: str | None,
    execution_requested: bool = True,
) -> dict[str, Any]:
    enabled = relay_enabled()
    expected_key = relay_api_key()
    auth_configured = bool(expected_key)
    auth_valid = validate_relay_key(provided_key, expected_key)
    localhost_only = localhost_only_execution_enabled()
    localhost_request = is_localhost_client(client_host)
    reason = ""

    if not enabled:
        reason = "RELAY_DISABLED"
    elif not auth_configured:
        reason = "AUTH_NOT_CONFIGURED"
    elif not provided_key:
        reason = "AUTH_MISSING"
    elif not auth_valid:
        reason = "AUTH_INVALID"
    elif not localhost_only:
        reason = "LOCALHOST_ONLY_CONFIG_UNSAFE"
    elif execution_requested and not localhost_request:
        reason = "NON_LOCALHOST_EXECUTION_BLOCKED"

    execution_allowed = not reason and bool(execution_requested)
    return {
        "schema": "titan.echo.relay_execution_hardening.v1",
        "relay_enabled": enabled,
        "auth_configured": auth_configured,
        "auth_valid": auth_valid,
        "localhost_only_execution": localhost_only,
        "localhost_request": localhost_request,
        "client_host": str(client_host or ""),
        "execution_allowed": execution_allowed,
        "reason": reason,
    }


def require_relay_execution_allowed(provided_key: str | None, client_host: str | None) -> dict[str, Any]:
    status = relay_execution_hardening_status(
        provided_key=provided_key,
        client_host=client_host,
        execution_requested=True,
    )
    if status["execution_allowed"]:
        return status
    if HTTPException is None:  # pragma: no cover - FastAPI unavailable path
        raise PermissionError(str(status["reason"] or "RELAY_EXECUTION_BLOCKED"))
    if status["reason"] in {"AUTH_MISSING", "AUTH_INVALID", "AUTH_NOT_CONFIGURED"}:
        raise HTTPException(status_code=401, detail=status["reason"])
    raise HTTPException(status_code=403, detail=status)


def relay_auth_design() -> dict[str, Any]:
    return {
        "schema": "titan.echo.relay_auth_design.v1",
        "auth_required_when_enabled": True,
        "header_name": RELAY_HEADER_NAME,
        "key_source": "environment variable",
        "hardcoded_key": False,
        "disabled_mode_behavior": "returns RELAY_DISABLED",
        "localhost_only_execution_default": True,
    }


__all__ = [
    "LOCALHOST_ONLY_ENV",
    "is_localhost_client",
    "localhost_only_execution_enabled",
    "relay_auth_design",
    "relay_execution_hardening_status",
    "require_relay_execution_allowed",
    "require_relay_key",
    "validate_relay_key",
]
