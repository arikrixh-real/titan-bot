import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


JOURNAL_STATUS_PATH = Path("data") / "runtime" / "journal_status.json"


def run_journal():
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "JOURNAL_MARKER_UPDATED",
    }

    JOURNAL_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL_STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    print(json.dumps(run_journal(), indent=2, sort_keys=True))
