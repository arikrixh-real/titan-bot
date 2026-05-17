import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


DASHBOARD_SYNC_STATUS_PATH = Path("data") / "runtime" / "dashboard_sync_status.json"
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
PAPER_ENGINE_STATUS_PATH = Path("data") / "runtime" / "paper_engine_status.json"
LIVE_PRICE_MONITOR_STATUS_PATH = Path("data") / "runtime" / "live_price_monitor_status.json"
DAEMON_HEALTH_PATH = Path("data") / "runtime" / "daemon_health.json"
IST = timezone(timedelta(hours=5, minutes=30))


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


def is_active_status(payload):
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").upper()
    if not status:
        return False
    inactive_markers = ("STOPPED", "FAILED", "ERROR", "INACTIVE")
    return not any(marker in status for marker in inactive_markers)


def get_nested_number(payload, keys, default=0):
    current = payload if isinstance(payload, dict) else {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if isinstance(current, (int, float)) and not isinstance(current, bool) else default


def latest_timestamp(*payloads):
    timestamps = [
        payload.get("timestamp_ist")
        for payload in payloads
        if isinstance(payload, dict) and payload.get("timestamp_ist")
    ]
    return max(timestamps) if timestamps else datetime.now(IST).isoformat()


def run_dashboard_sync(path=DASHBOARD_SYNC_STATUS_PATH):
    scanner_status = read_json_safe(SCANNER_STATUS_PATH)
    master_brain_status = read_json_safe(MASTER_BRAIN_STATUS_PATH)
    paper_engine_status = read_json_safe(PAPER_ENGINE_STATUS_PATH)
    live_price_monitor_status = read_json_safe(LIVE_PRICE_MONITOR_STATUS_PATH)
    daemon_health = read_json_safe(DAEMON_HEALTH_PATH)

    daemon_alive = isinstance(daemon_health, dict) and str(daemon_health.get("status") or "").upper() == "RUNNING"
    open_paper_positions = get_nested_number(paper_engine_status, ("open_positions_count",))
    paper_equity = get_nested_number(paper_engine_status, ("paper_account_summary", "equity"), 0.0)
    runtime_mode = "UNKNOWN"
    if isinstance(daemon_health, dict):
        runtime_mode = daemon_health.get("mode") or runtime_mode

    runtime_health_checks = {
        "daemon_alive": (daemon_alive, "daemon_not_alive"),
        "scanner_active": (is_active_status(scanner_status), "scanner_inactive"),
        "master_brain_active": (is_active_status(master_brain_status), "master_brain_inactive"),
        "paper_engine_active": (is_active_status(paper_engine_status), "paper_engine_inactive"),
        "live_price_monitor_active": (
            is_active_status(live_price_monitor_status),
            "live_price_monitor_inactive",
        ),
    }
    attention_reasons = [
        reason for is_active, reason in runtime_health_checks.values() if not is_active
    ]
    recovery_suggestion_map = {
        "daemon_not_alive": "Start titan_daemon.py",
        "scanner_inactive": "Check runtime_scanner.py",
        "master_brain_inactive": "Check runtime_master_brain.py",
        "paper_engine_inactive": "Check runtime_paper_engine.py",
        "live_price_monitor_inactive": "Check runtime_live_price_monitor.py",
    }
    recovery_suggestions = list(
        dict.fromkeys(
            recovery_suggestion_map[reason]
            for reason in attention_reasons
            if reason in recovery_suggestion_map
        )
    )

    payload = {
        "autonomous_runtime_summary": {
            "daemon_alive": runtime_health_checks["daemon_alive"][0],
            "scanner_active": runtime_health_checks["scanner_active"][0],
            "master_brain_active": runtime_health_checks["master_brain_active"][0],
            "paper_engine_active": runtime_health_checks["paper_engine_active"][0],
            "live_price_monitor_active": runtime_health_checks["live_price_monitor_active"][0],
            "needs_attention": bool(attention_reasons),
            "attention_reasons": attention_reasons,
            "recovery_suggestions": recovery_suggestions,
            "open_paper_positions": open_paper_positions,
            "paper_equity": paper_equity,
            "runtime_mode": runtime_mode,
            "last_runtime_update": latest_timestamp(
                scanner_status,
                master_brain_status,
                paper_engine_status,
                live_price_monitor_status,
                daemon_health,
            ),
        }
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_dashboard_sync(), indent=2, sort_keys=True))
