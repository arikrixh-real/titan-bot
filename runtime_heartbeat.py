import json
import os
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import IST, as_ist_datetime


HEARTBEAT_PATH = Path("data/runtime/titan_heartbeat.json")


def write_heartbeat():
    now_ist = as_ist_datetime().astimezone(IST)
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "status": "ALIVE",
        "mode": current_bot_mode(now_ist),
        "pid": os.getpid(),
    }

    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    write_heartbeat()
