import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


MARKET_REGIME_UPDATE_STATUS_PATH = (
    Path("data") / "runtime" / "market_regime_update_status.json"
)


def run_market_regime_update():
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "MARKET_REGIME_UPDATE_MARKER_UPDATED",
    }

    MARKET_REGIME_UPDATE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKET_REGIME_UPDATE_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload
