import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


MARKET_PRESSURE_CHECK_STATUS_PATH = (
    Path("data") / "runtime" / "market_pressure_check_status.json"
)


def run_market_pressure_check():
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "MARKET_PRESSURE_CHECK_MARKER_UPDATED",
    }

    MARKET_PRESSURE_CHECK_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKET_PRESSURE_CHECK_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
