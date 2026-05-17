import json
from pathlib import Path

from utils.market_hours import as_ist_datetime


DASHBOARD_SYNC_STATUS_PATH = Path("data") / "runtime" / "dashboard_sync_status.json"
DAEMON_HEALTH_PATH = Path("data") / "runtime" / "daemon_health.json"
HEARTBEAT_PATH = Path("data") / "runtime" / "titan_heartbeat.json"
RUNTIME_STATUS_PATH = Path("data") / "runtime" / "titan_runtime_status.json"
DISPATCH_LOG_PATH = Path("data") / "runtime" / "dispatch_log.jsonl"
DISPATCH_TAIL_LINES = 20


def read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def tail_jsonl_safe(path, limit=DISPATCH_TAIL_LINES):
    events = []
    try:
        path = Path(path)
        if not path.exists():
            return events
        with path.open("r", encoding="utf-8") as file:
            lines = file.readlines()[-limit:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            if isinstance(event, dict):
                events.append(event)
    except Exception:
        return []
    return events


def run_dashboard_sync(path=DASHBOARD_SYNC_STATUS_PATH):
    now_ist = as_ist_datetime()
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "status": "DASHBOARD_RUNTIME_SYNC_UPDATED",
        "daemon_health": read_json_safe(DAEMON_HEALTH_PATH),
        "heartbeat": read_json_safe(HEARTBEAT_PATH),
        "runtime_status": read_json_safe(RUNTIME_STATUS_PATH),
        "recent_dispatch_events": tail_jsonl_safe(DISPATCH_LOG_PATH),
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_dashboard_sync(), indent=2, sort_keys=True))
