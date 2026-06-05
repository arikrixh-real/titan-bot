"""Authentication helpers for the disabled-by-default ECHO relay skeleton."""

from __future__ import annotations

import hmac
import importlib.util
from typing import Any

from titan_echo.echo_relay_config import RELAY_HEADER_NAME, relay_api_key


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


def relay_auth_design() -> dict[str, Any]:
    return {
        "schema": "titan.echo.relay_auth_design.v1",
        "auth_required_when_enabled": True,
        "header_name": RELAY_HEADER_NAME,
        "key_source": "environment variable",
        "hardcoded_key": False,
        "disabled_mode_behavior": "returns RELAY_DISABLED",
    }


__all__ = [
    "relay_auth_design",
    "require_relay_key",
    "validate_relay_key",
]
