import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"


def run_master_brain():
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "MASTER_BRAIN_MARKER_UPDATED",
    }

    MASTER_BRAIN_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MASTER_BRAIN_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
