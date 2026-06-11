from __future__ import annotations

import json
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from data.live_price import get_upstox_token, safe_float
from runtime_safe_json import safe_atomic_write_json
from utils.market_hours import as_ist_datetime


IST = timezone(timedelta(hours=5, minutes=30))
ACCOUNT_DIR = Path("data") / "runtime" / "upstox" / "account"
FUNDS_PATH = ACCOUNT_DIR / "funds.json"
POSITIONS_PATH = ACCOUNT_DIR / "positions.json"
FUNDS_URL = "https://api.upstox.com/v2/user/get-funds-and-margin"
POSITIONS_URL = "https://api.upstox.com/v2/portfolio/short-term-positions"


def _now_ist() -> str:
    return as_ist_datetime().isoformat()


def _inactive_payload(status: str, reason: str, token_type: str = "MISSING") -> dict[str, Any]:
    return {
        "timestamp_ist": _now_ist(),
        "status": status,
        "reason": reason,
        "token_type_used": token_type,
        "account_balance": None,
        "available_margin": None,
        "equity": None,
        "current_pnl": None,
        "unrealized_pnl": None,
        "daily_pnl": None,
        "realized_pnl": None,
        "read_only": True,
    }


def _first_number(payload: Any, keys: tuple[str, ...]) -> float | None:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            number = safe_float(value)
            if number is not None:
                return number
        for value in payload.values():
            number = _first_number(value, keys)
            if number is not None:
                return number
    elif isinstance(payload, list):
        for item in payload:
            number = _first_number(item, keys)
            if number is not None:
                return number
    return None


def _positions_list(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("positions", "net", "day"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _sum_positions(positions: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    total = 0.0
    found = False
    for position in positions:
        for key in keys:
            number = safe_float(position.get(key))
            if number is not None:
                total += number
                found = True
                break
    return round(total, 4) if found else None


def _request_json(url: str, token: str) -> tuple[int | None, dict[str, Any]]:
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return response.status_code, payload if isinstance(payload, dict) else {}
    except requests.RequestException as exc:
        return None, {"error_type": type(exc).__name__, "error_message": str(exc)}


def refresh_upstox_account() -> dict[str, Any]:
    token, token_type = get_upstox_token()
    if not token:
        payload = _inactive_payload("AUTH_REQUIRED", "Upstox access token missing", token_type)
        safe_atomic_write_json(FUNDS_PATH, payload)
        safe_atomic_write_json(POSITIONS_PATH, dict(payload))
        return {"status": "AUTH_REQUIRED", "funds": payload, "positions": payload}

    funds_status, funds_raw = _request_json(FUNDS_URL, token)
    positions_status, positions_raw = _request_json(POSITIONS_URL, token)
    now = _now_ist()

    if funds_status in {401, 403} or positions_status in {401, 403}:
        payload = _inactive_payload("AUTH_REQUIRED", "Upstox token invalid or expired", token_type)
        payload["http_status"] = {"funds": funds_status, "positions": positions_status}
        safe_atomic_write_json(FUNDS_PATH, payload)
        safe_atomic_write_json(POSITIONS_PATH, dict(payload))
        return {"status": "AUTH_REQUIRED", "funds": payload, "positions": payload}

    if funds_status != 200:
        funds_payload = _inactive_payload("INACTIVE", "Upstox funds API unavailable", token_type)
        funds_payload.update({"http_status": funds_status, "raw_status": funds_raw.get("status")})
    else:
        available_margin = _first_number(
            funds_raw,
            ("available_margin", "available_balance", "available_cash", "available_funds"),
        )
        used_margin = _first_number(funds_raw, ("used_margin", "utilised_margin", "margin_used"))
        account_balance = _first_number(funds_raw, ("equity", "cash", "available_margin", "available_balance"))
        equity = account_balance
        if available_margin is not None and used_margin is not None:
            equity = round(available_margin + used_margin, 4)
        funds_payload = {
            "timestamp_ist": now,
            "status": "ACTIVE",
            "account_balance": account_balance,
            "available_margin": available_margin,
            "equity": equity,
            "current_pnl": None,
            "unrealized_pnl": None,
            "daily_pnl": None,
            "realized_pnl": None,
            "token_type_used": token_type,
            "http_status": funds_status,
            "read_only": True,
        }

    if positions_status != 200:
        positions_payload = _inactive_payload("INACTIVE", "Upstox positions API unavailable", token_type)
        positions_payload.update({"http_status": positions_status, "raw_status": positions_raw.get("status")})
    else:
        positions = _positions_list(positions_raw)
        unrealized = _sum_positions(positions, ("unrealised", "unrealized_pnl", "pnl", "day_pnl"))
        realized = _sum_positions(positions, ("realised", "realized_pnl"))
        daily_pnl = _sum_positions(positions, ("day_pnl", "pnl"))
        positions_payload = {
            "timestamp_ist": now,
            "status": "ACTIVE",
            "position_count": len(positions),
            "account_balance": funds_payload.get("account_balance"),
            "available_margin": funds_payload.get("available_margin"),
            "equity": funds_payload.get("equity"),
            "current_pnl": unrealized,
            "unrealized_pnl": unrealized,
            "daily_pnl": daily_pnl,
            "realized_pnl": realized,
            "token_type_used": token_type,
            "http_status": positions_status,
            "read_only": True,
        }

    safe_atomic_write_json(FUNDS_PATH, funds_payload)
    safe_atomic_write_json(POSITIONS_PATH, positions_payload)
    status = "ACTIVE" if funds_payload.get("status") == "ACTIVE" or positions_payload.get("status") == "ACTIVE" else "INACTIVE"
    return {"status": status, "funds": funds_payload, "positions": positions_payload}


if __name__ == "__main__":
    print(json.dumps(refresh_upstox_account(), indent=2, sort_keys=True))
