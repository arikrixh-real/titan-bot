import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


PNL_REFRESH_STATUS_PATH = Path("data") / "runtime" / "pnl_refresh_status.json"


def run_pnl_refresh():
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "PNL_REFRESH_MARKER_UPDATED",
    }

    PNL_REFRESH_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PNL_REFRESH_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
