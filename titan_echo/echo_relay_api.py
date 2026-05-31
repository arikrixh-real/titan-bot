"""Disabled-by-default read-only relay skeleton for ECHO evidence endpoints.

This module is safe to import. It defines a FastAPI app when FastAPI is
available but does not start a service, open ports, or contact ECHO at import
time.
"""

from __future__ import annotations

import importlib.util
import json
from typing import Any
from urllib import error, request

from titan_echo.echo_relay_auth import require_relay_key
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


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import Body, FastAPI, Header
else:  # pragma: no cover - depends on local dependency set
    Body = None  # type: ignore[assignment, misc]
    FastAPI = None  # type: ignore[assignment, misc]
    Header = None  # type: ignore[assignment, misc]


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


def relay_allowlist(x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return relay_status_payload()


def relay_jarvis_ask(payload: dict[str, Any], x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("POST", "/jarvis/ask", payload if isinstance(payload, dict) else {})


def relay_titan_status(x_echo_relay_key: str | None = None) -> dict[str, Any]:
    if not relay_enabled():
        return _disabled_payload()
    require_relay_key(x_echo_relay_key)
    return _forward_to_echo("GET", "/titan/status")


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


app = None
if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="ECHO Secure Relay Skeleton",
        version="0.1.0",
        description="Disabled-by-default read-only relay skeleton for ECHO evidence.",
    )

    @app.get("/relay/health")
    def route_relay_health(x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME)) -> dict[str, Any]:
        return relay_health(x_echo_relay_key)

    @app.get("/relay/allowlist")
    def route_relay_allowlist(x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME)) -> dict[str, Any]:
        return relay_allowlist(x_echo_relay_key)

    @app.post("/relay/jarvis/ask")
    def route_relay_jarvis_ask(
        payload: dict[str, Any] | None = Body(default=None),
        x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME),
    ) -> dict[str, Any]:
        return relay_jarvis_ask(payload or {}, x_echo_relay_key)

    @app.get("/relay/titan/status")
    def route_relay_titan_status(x_echo_relay_key: str | None = Header(default=None, alias=RELAY_HEADER_NAME)) -> dict[str, Any]:
        return relay_titan_status(x_echo_relay_key)

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


__all__ = [
    "FASTAPI_AVAILABLE",
    "app",
    "relay_allowlist",
    "relay_chatgpt_evidence_catalog",
    "relay_chatgpt_evidence_contract",
    "relay_chatgpt_integration_status",
    "relay_health",
    "relay_jarvis_ask",
    "relay_titan_status",
]
