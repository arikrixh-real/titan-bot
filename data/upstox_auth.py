"""
Shared read-only Upstox market-data authentication.

Market-data callers must use the long-lived analytics token. Broker/account
and order-placement code paths intentionally do not import this helper.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


class UpstoxMarketDataAuthError(RuntimeError):
    """Raised when read-only market-data auth is not available."""


def _jwt_payload(token: str) -> dict:
    try:
        parts = str(token).split(".")
        if len(parts) < 2:
            return {}
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
    except Exception:
        return {}


def classify_market_data_token(token: str | None = None) -> str:
    token = token if token is not None else os.getenv("UPSTOX_ANALYTICS_TOKEN")
    if not token or not str(token).strip():
        return "MISSING"
    payload = _jwt_payload(str(token).strip())
    exp = payload.get("exp")
    if exp is not None:
        try:
            if float(exp) <= time.time():
                return "INVALID"
        except Exception:
            return "UNKNOWN"
    return "READY"


def redact_token(token: str | None) -> str | None:
    if not token:
        return None
    token = str(token)
    if len(token) <= 10:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def get_market_data_token() -> str:
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN")
    if not token or not str(token).strip():
        raise UpstoxMarketDataAuthError(
            "UPSTOX_ANALYTICS_TOKEN missing; read-only market-data APIs require analytics auth"
        )
    token = str(token).strip()
    status = classify_market_data_token(token)
    if status == "INVALID":
        raise UpstoxMarketDataAuthError("UPSTOX_ANALYTICS_TOKEN is expired or invalid")
    return token


def market_data_headers(*, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {get_market_data_token()}",
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def market_data_token_info() -> dict:
    token = get_market_data_token()
    return {
        "token_found": True,
        "token_redacted": redact_token(token),
        "token_type": "ANALYTICS_TOKEN",
        "auth_status": classify_market_data_token(token),
    }


def configure_market_data_sdk(configuration):
    configuration.access_token = get_market_data_token()
    return configuration
