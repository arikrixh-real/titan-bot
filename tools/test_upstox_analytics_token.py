"""Read-only analytics token readiness check.

This script never prints the raw token.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.upstox_auth import UpstoxMarketDataAuthError, market_data_token_info


def check_token() -> dict:
    try:
        info = market_data_token_info()
    except UpstoxMarketDataAuthError as exc:
        return {
            "status": "AUTH_REQUIRED",
            "token_found": False,
            "token_redacted": None,
            "token_type": "MISSING_ANALYTICS_TOKEN",
            "auth_status": "MISSING",
            "reason": str(exc),
            "read_only": True,
        }
    return {
        "status": "READY" if info.get("auth_status") == "READY" else "DEGRADED",
        "token_found": bool(info.get("token_found")),
        "token_redacted": info.get("token_redacted"),
        "token_type": info.get("token_type"),
        "auth_status": info.get("auth_status"),
        "read_only": True,
    }


def main() -> int:
    print(json.dumps(check_token(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
