import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


NEWS_PULSE_STATUS_PATH = Path("data") / "runtime" / "news_pulse_status.json"


def run_news_pulse(path=NEWS_PULSE_STATUS_PATH):
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "status": "NEWS_PULSE_MARKER_UPDATED",
        "mode": current_bot_mode(now_ist),
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_news_pulse(), indent=2, sort_keys=True))
