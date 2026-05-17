import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


BROKER_HEALTH_CHECK_STATUS_PATH = (
    Path("data") / "runtime" / "broker_health_check_status.json"
)


def run_broker_health_check():
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "BROKER_HEALTH_CHECK_MARKER_UPDATED",
    }

    BROKER_HEALTH_CHECK_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    BROKER_HEALTH_CHECK_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
