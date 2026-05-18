import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from supabase import create_client
from dotenv import load_dotenv


DASHBOARD_SYNC_STATUS_PATH = Path("data") / "runtime" / "dashboard_sync_status.json"
HEARTBEAT_PATH = Path("data") / "runtime" / "titan_heartbeat.json"
RUNTIME_STATUS_PATH = Path("data") / "runtime" / "titan_runtime_status.json"
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
PAPER_ENGINE_STATUS_PATH = Path("data") / "runtime" / "paper_engine_status.json"
LIVE_PRICE_MONITOR_STATUS_PATH = Path("data") / "runtime" / "live_price_monitor_status.json"
DAEMON_HEALTH_PATH = Path("data") / "runtime" / "daemon_health.json"
RUNTIME_STATUS_TABLE = "runtime_status"
IST = timezone(timedelta(hours=5, minutes=30))


load_dotenv()


RUNTIME_STATUS_SOURCES = {
    "titan_heartbeat": HEARTBEAT_PATH,
    "daemon_health": DAEMON_HEALTH_PATH,
    "titan_runtime_status": RUNTIME_STATUS_PATH,
    "scanner_status": SCANNER_STATUS_PATH,
    "live_price_monitor_status": LIVE_PRICE_MONITOR_STATUS_PATH,
    "master_brain_status": MASTER_BRAIN_STATUS_PATH,
    "paper_engine_status": PAPER_ENGINE_STATUS_PATH,
}


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


def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    missing_env_vars = []
    if not url:
        missing_env_vars.append("SUPABASE_URL")
    if not key:
        missing_env_vars.append("SUPABASE_KEY")
    if missing_env_vars:
        for env_var in missing_env_vars:
            print(f"[DashboardSync ERROR] missing env var: {env_var}")
        return None, missing_env_vars, None
    try:
        return create_client(url, key), [], None
    except Exception as exc:
        error = f"Supabase client creation failed: {exc}"
        print(f"[DashboardSync ERROR] {error}")
        return None, [], error


def upsert_runtime_status_rows(payloads, dashboard_payload):
    client, missing_env_vars, client_error = get_supabase_client()
    sync_result = {
        "supabase_sync_enabled": client is not None,
        "rows_attempted": 0,
        "rows_written": 0,
        "sync_error": None,
    }
    if client is None:
        if missing_env_vars:
            sync_result["sync_error"] = "missing env var: " + ", ".join(missing_env_vars)
        else:
            sync_result["sync_error"] = client_error or "Supabase client unavailable"
        print(f"[DashboardSync RESULT] {json.dumps(sync_result, sort_keys=True)}")
        return sync_result

    now_ist = datetime.now(IST).isoformat()
    rows = []
    for status_key, payload in payloads.items():
        if not isinstance(payload, dict):
            continue
        rows.append(
            {
                "status_key": status_key,
                "payload": payload,
                "timestamp_ist": payload.get("timestamp_ist") or now_ist,
                "updated_at": now_ist,
            }
        )

    rows.append(
        {
            "status_key": "dashboard_sync",
            "payload": dashboard_payload,
            "timestamp_ist": (
                dashboard_payload.get("timestamp_ist")
                or dashboard_payload.get("autonomous_runtime_summary", {}).get("last_runtime_update")
                or now_ist
            ),
            "updated_at": now_ist,
        }
    )
    sync_result["rows_attempted"] = len(rows)

    try:
        response = client.table(RUNTIME_STATUS_TABLE).upsert(
            rows,
            on_conflict="status_key",
        ).execute()
        response_rows = getattr(response, "data", None)
        if isinstance(response_rows, list):
            sync_result["rows_written"] = len(response_rows)
        else:
            sync_result["rows_written"] = len(rows)
        print(f"[DashboardSync RESULT] {json.dumps(sync_result, sort_keys=True)}")
        return sync_result
    except Exception as exc:
        sync_result["sync_error"] = str(exc)
        print(f"[DashboardSync RESULT] {json.dumps(sync_result, sort_keys=True)}")
        return sync_result


def run_dashboard_sync(path=DASHBOARD_SYNC_STATUS_PATH):
    runtime_payloads = {
        status_key: read_json_safe(source_path)
        for status_key, source_path in RUNTIME_STATUS_SOURCES.items()
    }
    heartbeat = runtime_payloads["titan_heartbeat"]
    runtime_status = runtime_payloads["titan_runtime_status"]
    scanner_status = read_json_safe(SCANNER_STATUS_PATH)
    master_brain_status = runtime_payloads["master_brain_status"]
    paper_engine_status = runtime_payloads["paper_engine_status"]
    live_price_monitor_status = runtime_payloads["live_price_monitor_status"]
    daemon_health = runtime_payloads["daemon_health"]

    daemon_alive = (
        isinstance(daemon_health, dict)
        and str(daemon_health.get("status") or "").upper() == "RUNNING"
    ) or (
        isinstance(heartbeat, dict)
        and str(heartbeat.get("status") or "").upper() == "ALIVE"
    )
    open_paper_positions = get_nested_number(paper_engine_status, ("open_positions_count",))
    paper_equity = get_nested_number(paper_engine_status, ("paper_account_summary", "equity"), 0.0)
    runtime_mode = "UNKNOWN"
    if isinstance(daemon_health, dict):
        runtime_mode = daemon_health.get("mode") or runtime_mode
    if runtime_mode == "UNKNOWN" and isinstance(runtime_status, dict):
        runtime_mode = runtime_status.get("mode") or runtime_mode
    if runtime_mode == "UNKNOWN" and isinstance(heartbeat, dict):
        runtime_mode = heartbeat.get("mode") or runtime_mode

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
        "timestamp_ist": latest_timestamp(
            heartbeat,
            runtime_status,
            scanner_status,
            master_brain_status,
            paper_engine_status,
            live_price_monitor_status,
            daemon_health,
        ),
        "heartbeat": heartbeat or {},
        "daemon_health": daemon_health or {},
        "runtime_status": runtime_status or {},
        "live_price_monitor_status": live_price_monitor_status or {},
        "master_brain_status": master_brain_status or {},
        "paper_engine_status": paper_engine_status or {},
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
                heartbeat,
                runtime_status,
            ),
        }
    }

    sync_result = upsert_runtime_status_rows(runtime_payloads, payload)
    payload["supabase_sync"] = sync_result

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_dashboard_sync(), indent=2, sort_keys=True))
