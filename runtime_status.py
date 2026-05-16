import json
from pathlib import Path

from engines.time_filter import get_mode_permissions
from utils.market_hours import IST, as_ist_datetime


STATUS_PATH = Path("data") / "runtime" / "titan_runtime_status.json"


def build_runtime_status(value=None):
    now = as_ist_datetime(value)
    permissions = get_mode_permissions(now)

    return {
        "timestamp_ist": now.astimezone(IST).isoformat(),
        "mode": permissions["mode"],
        "live_allowed_engines": permissions["live_allowed_engines"],
        "research_allowed_engines": permissions["research_allowed_engines"],
        "blocked_engines": permissions["blocked_engines"],
        "reason": permissions["reason"],
    }


def write_runtime_status(path=STATUS_PATH, value=None):
    status = build_runtime_status(value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


if __name__ == "__main__":
    write_runtime_status()
