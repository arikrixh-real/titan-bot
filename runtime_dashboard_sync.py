import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


DASHBOARD_SYNC_STATUS_PATH = Path("data") / "runtime" / "dashboard_sync_status.json"


def run_dashboard_sync(path=DASHBOARD_SYNC_STATUS_PATH):
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "status": "SYNC_MARKER_UPDATED",
        "mode": current_bot_mode(now_ist),
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_dashboard_sync(), indent=2, sort_keys=True))
