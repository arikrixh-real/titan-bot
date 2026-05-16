import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


RISK_WATCHDOG_STATUS_PATH = Path("data") / "runtime" / "risk_watchdog_status.json"


def run_risk_watchdog(path=RISK_WATCHDOG_STATUS_PATH):
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "RISK_WATCHDOG_MARKER_UPDATED",
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_risk_watchdog(), indent=2, sort_keys=True))
