import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


MEMORY_COMPRESSION_STATUS_PATH = (
    Path("data") / "runtime" / "memory_compression_status.json"
)


def run_memory_compression():
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "MEMORY_COMPRESSION_MARKER_UPDATED",
    }

    MEMORY_COMPRESSION_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_COMPRESSION_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
