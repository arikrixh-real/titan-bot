import json
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import as_ist_datetime


SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"


def run_scanner(path=SCANNER_STATUS_PATH):
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": current_bot_mode(now_ist),
        "status": "SCAN_ONLY_PLACEHOLDER_READY",
        "scan_only": True,
        "real_scanner_called": False,
        "trade_creation": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": False,
        "next_step": "build_safe_scan_only_loop",
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_scanner(), indent=2, sort_keys=True))
