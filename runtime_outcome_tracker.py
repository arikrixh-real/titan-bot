import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import IST, as_ist_datetime


OUTCOME_TRACKER_STATUS_PATH = Path("data") / "runtime" / "outcome_tracker_status.json"


def run_outcome_tracker():
    now_ist = as_ist_datetime().astimezone(IST)
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "OUTCOME_TRACKER_MARKER_UPDATED",
    }

    OUTCOME_TRACKER_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTCOME_TRACKER_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    print(json.dumps(run_outcome_tracker(), indent=2, sort_keys=True))
