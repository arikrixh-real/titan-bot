"""Configuration helpers for the disabled-by-default ECHO relay skeleton."""

from __future__ import annotations

import os
from typing import Any


RELAY_ENABLED_ENV = "ECHO_RELAY_ENABLED"
RELAY_API_KEY_ENV = "ECHO_RELAY_API_KEY"
ECHO_INTERNAL_BASE_URL_ENV = "ECHO_INTERNAL_BASE_URL"
ECHO_INTERNAL_API_KEY_ENV = "ECHO_INTERNAL_API_KEY"
RELAY_HEADER_NAME = "X-ECHO-RELAY-KEY"
ECHO_INTERNAL_HEADER_NAME = "X-ECHO-API-KEY"
DEFAULT_INTERNAL_BASE_URL = "http://127.0.0.1:8765"

ALLOWED_ECHO_ENDPOINTS = {
    "/chatgpt/integration/status",
    "/chatgpt/evidence/contract",
    "/chatgpt/evidence/catalog",
    "/jarvis/ask",
    "/titan/status",
}

BLOCKED_PREFIXES = (
    "/mission",
    "/approval",
    "/execution",
    "/codex",
    "/deploy",
    "/rollback",
)


def relay_enabled() -> bool:
    return os.environ.get(RELAY_ENABLED_ENV, "false").strip().lower() == "true"


def relay_api_key() -> str | None:
    return os.environ.get(RELAY_API_KEY_ENV)


def internal_base_url() -> str:
    return os.environ.get(ECHO_INTERNAL_BASE_URL_ENV, DEFAULT_INTERNAL_BASE_URL).rstrip("/")


def internal_api_key() -> str | None:
    return os.environ.get(ECHO_INTERNAL_API_KEY_ENV)


def relay_safety() -> dict[str, bool]:
    return {
        "shell_execution": False,
        "codex_execution": False,
        "git_push_pull": False,
        "deploy_or_restart": False,
        "titan_runtime_changed": False,
        "trade_execution_permitted": False,
        "broker_changed": False,
        "risk_changed": False,
        "scanner_changed": False,
        "master_brain_changed": False,
        "runtime_workers_changed": False,
    }


def relay_status_payload() -> dict[str, Any]:
    return {
        "status": "RELAY_DISABLED" if not relay_enabled() else "RELAY_ENABLED_LOCAL_ONLY",
        "enabled": relay_enabled(),
        "public_exposure_allowed": False,
        "allowed_echo_endpoints": sorted(ALLOWED_ECHO_ENDPOINTS),
        "blocked_prefixes": list(BLOCKED_PREFIXES),
        "safety": relay_safety(),
    }


def endpoint_allowed(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        return False
    return path in ALLOWED_ECHO_ENDPOINTS


__all__ = [
    "ALLOWED_ECHO_ENDPOINTS",
    "BLOCKED_PREFIXES",
    "DEFAULT_INTERNAL_BASE_URL",
    "ECHO_INTERNAL_API_KEY_ENV",
    "ECHO_INTERNAL_BASE_URL_ENV",
    "ECHO_INTERNAL_HEADER_NAME",
    "RELAY_API_KEY_ENV",
    "RELAY_ENABLED_ENV",
    "RELAY_HEADER_NAME",
    "endpoint_allowed",
    "internal_api_key",
    "internal_base_url",
    "relay_api_key",
    "relay_enabled",
    "relay_safety",
    "relay_status_payload",
]
