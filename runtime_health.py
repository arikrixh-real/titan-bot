import json
import os
from pathlib import Path

from utils.market_hours import IST, as_ist_datetime


DAEMON_HEALTH_PATH = Path("data") / "runtime" / "daemon_health.json"


def write_daemon_health(
    mode,
    ticks_completed,
    dispatch_count,
    status="RUNNING",
):
    now_ist = as_ist_datetime().astimezone(IST)
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": mode,
        "ticks_completed": ticks_completed,
        "last_dispatch_count": dispatch_count,
        "status": status,
        "pid": os.getpid(),
    }

    DAEMON_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    DAEMON_HEALTH_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    write_daemon_health(
        mode="TEST_MODE",
        ticks_completed=1,
        dispatch_count=2,
    )
