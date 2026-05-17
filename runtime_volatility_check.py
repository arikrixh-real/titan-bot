import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


VOLATILITY_CHECK_STATUS_PATH = Path("data") / "runtime" / "volatility_check_status.json"


def run_volatility_check():
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "VOLATILITY_CHECK_MARKER_UPDATED",
    }

    VOLATILITY_CHECK_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOLATILITY_CHECK_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
