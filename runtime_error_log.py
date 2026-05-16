import json
import os
from pathlib import Path

from utils.market_hours import IST, as_ist_datetime


DAEMON_ERROR_LOG_PATH = Path("data") / "runtime" / "daemon_errors.jsonl"


def log_runtime_error(source, error, mode=None):
    now_ist = as_ist_datetime().astimezone(IST)
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "source": source,
        "mode": mode,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "pid": os.getpid(),
    }

    DAEMON_ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DAEMON_ERROR_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload, sort_keys=True) + "\n")

    return payload


if __name__ == "__main__":
    try:
        raise RuntimeError("test error")
    except Exception as exc:
        log_runtime_error("self_test", exc, mode="TEST_MODE")
