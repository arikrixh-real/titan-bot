import ctypes
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from engines.time_filter import current_bot_mode
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
DAEMON_HEALTH_PATH = RUNTIME_DIR / "daemon_health.json"
HEARTBEAT_PATH = RUNTIME_DIR / "titan_heartbeat.json"
AUTHORITATIVE_RUNTIME_HEALTH_PATH = RUNTIME_DIR / "titan_authoritative_runtime_health.json"
DAEMON_LOCK_PATH = RUNTIME_DIR / "locks" / "titan_daemon.lock"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
MASTER_BRAIN_STATUS_PATH = RUNTIME_DIR / "master_brain_status.json"
REPLAY_STATUS_PATH = RUNTIME_DIR / "historical_replay_status.json"
REPLAY_PROGRESS_PATH = RUNTIME_DIR / "historical_replay_progress.json"
REINFORCEMENT_LEARNING_STATUS_PATH = RUNTIME_DIR / "reinforcement_learning_status.json"
REINFORCEMENT_LEARNING_MEMORY_PATH = Path("data") / "memory" / "reinforcement_learning_memory.json"
DASHBOARD_SYNC_STATUS_PATH = RUNTIME_DIR / "dashboard_sync_status.json"

FRESH_SECONDS = 15 * 60
RESEARCH_FRESH_SECONDS = 24 * 60 * 60
LOCK_STALE_SECONDS = 5 * 60
RUNNING_STATUSES = {"ALIVE", "RUNNING", "STARTING"}


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def _parse_datetime_safe(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _file_modified_at(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(IST)
    except OSError:
        return None


def _age_seconds(timestamp, now):
    if timestamp is None:
        return None
    return max(0.0, (now - timestamp.astimezone(IST)).total_seconds())


def _timestamp_from_payload(payload, keys):
    if not isinstance(payload, dict):
        return None
    for key in keys:
        parsed = _parse_datetime_safe(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _artifact_freshness(name, path, payload, now, timestamp_keys=None, fresh_seconds=FRESH_SECONDS):
    timestamp_keys = timestamp_keys or (
        "timestamp_ist",
        "generated_at_ist",
        "generated_at",
        "last_completed_at_ist",
        "scan_finished_at_ist",
        "last_runtime_update",
    )
    path = Path(path)
    timestamp = _timestamp_from_payload(payload, timestamp_keys) or _file_modified_at(path)
    age = _age_seconds(timestamp, now)
    present = path.exists()
    stale = (not present) or age is None or age > fresh_seconds
    return {
        "name": name,
        "path": str(path).replace("\\", "/"),
        "present": present,
        "timestamp_ist": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "fresh_seconds": fresh_seconds,
        "stale": stale,
        "status": "MISSING" if not present else ("STALE" if stale else "FRESH"),
    }


def _windows_process_visible(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        process_query_limited_information = 0x1000
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def _process_visible(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_process_visible(pid)
    return Path("/proc").joinpath(str(pid)).exists()


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True, default=str)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def write_daemon_health(
    mode,
    ticks_completed,
    dispatch_count,
    status="RUNNING",
):
    now_ist = as_ist_datetime().astimezone(IST)
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "mode": mode,
        "ticks_completed": ticks_completed,
        "last_dispatch_count": dispatch_count,
        "status": status,
        "pid": os.getpid(),
    }

    DAEMON_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    DAEMON_HEALTH_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def run_authoritative_runtime_health_check(path=AUTHORITATIVE_RUNTIME_HEALTH_PATH, now=None):
    now_ist = as_ist_datetime(now).astimezone(IST)
    daemon_health = _read_json_safe(DAEMON_HEALTH_PATH)
    heartbeat = _read_json_safe(HEARTBEAT_PATH)
    lock_payload = _read_json_safe(DAEMON_LOCK_PATH)
    scanner_status = _read_json_safe(SCANNER_STATUS_PATH)
    master_brain_status = _read_json_safe(MASTER_BRAIN_STATUS_PATH)
    replay_status = _read_json_safe(REPLAY_STATUS_PATH)
    replay_progress = _read_json_safe(REPLAY_PROGRESS_PATH)
    reinforcement_status = _read_json_safe(REINFORCEMENT_LEARNING_STATUS_PATH)
    reinforcement_memory = _read_json_safe(REINFORCEMENT_LEARNING_MEMORY_PATH)
    dashboard_sync_status = _read_json_safe(DASHBOARD_SYNC_STATUS_PATH)

    daemon_pid = daemon_health.get("pid") or heartbeat.get("pid") or lock_payload.get("pid")
    process_visible = _process_visible(daemon_pid)
    daemon_lock_present = DAEMON_LOCK_PATH.exists()
    lock_timestamp = _timestamp_from_payload(lock_payload, ("acquired_at_ist", "timestamp_ist"))
    lock_age = _age_seconds(lock_timestamp, now_ist)
    daemon_lock_stale = daemon_lock_present and (lock_age is None or lock_age > LOCK_STALE_SECONDS or not process_visible)

    daemon_status = str(daemon_health.get("status") or "").upper()
    heartbeat_status = str(heartbeat.get("status") or "").upper()
    running_artifacts = []
    if daemon_status in RUNNING_STATUSES:
        running_artifacts.append("daemon_health")
    if heartbeat_status in RUNNING_STATUSES:
        running_artifacts.append("titan_heartbeat")

    contradiction_flags = []
    if running_artifacts and not process_visible:
        contradiction_flags.append("running_artifact_without_visible_process")
    if daemon_lock_present and daemon_lock_stale:
        contradiction_flags.append("daemon_lock_present_but_stale_or_owner_missing")
    if daemon_status == "STOPPED" and heartbeat_status in RUNNING_STATUSES:
        contradiction_flags.append("daemon_stopped_but_heartbeat_alive")
    if process_visible and not daemon_lock_present:
        contradiction_flags.append("visible_process_without_daemon_lock")

    current_mode = (
        daemon_health.get("runtime_mode")
        or daemon_health.get("mode")
        or heartbeat.get("mode")
        or scanner_status.get("mode")
        or current_bot_mode(now_ist)
    )
    if process_visible:
        runtime_owner = "daemon_pid"
    elif daemon_lock_present and daemon_lock_stale:
        runtime_owner = "stale_lock_only"
    elif running_artifacts:
        runtime_owner = "running_artifact_only"
    else:
        runtime_owner = "none_visible"

    replay_payload = replay_progress if replay_progress else replay_status
    reinforcement_payload = reinforcement_status if reinforcement_status else reinforcement_memory
    scanner_freshness = _artifact_freshness(
        "scanner",
        SCANNER_STATUS_PATH,
        scanner_status,
        now_ist,
        timestamp_keys=("scan_finished_at_ist", "timestamp_ist"),
    )
    master_brain_freshness = _artifact_freshness(
        "master_brain",
        MASTER_BRAIN_STATUS_PATH,
        master_brain_status,
        now_ist,
    )
    replay_freshness = _artifact_freshness(
        "replay",
        REPLAY_PROGRESS_PATH if replay_progress else REPLAY_STATUS_PATH,
        replay_payload,
        now_ist,
        timestamp_keys=("last_completed_at_ist", "timestamp_ist", "generated_at"),
        fresh_seconds=RESEARCH_FRESH_SECONDS,
    )
    reinforcement_learning_freshness = _artifact_freshness(
        "reinforcement_learning",
        REINFORCEMENT_LEARNING_STATUS_PATH if reinforcement_status else REINFORCEMENT_LEARNING_MEMORY_PATH,
        reinforcement_payload,
        now_ist,
        fresh_seconds=RESEARCH_FRESH_SECONDS,
    )
    dashboard_sync_freshness = _artifact_freshness(
        "dashboard_sync",
        DASHBOARD_SYNC_STATUS_PATH,
        dashboard_sync_status,
        now_ist,
    )

    freshness_items = [
        scanner_freshness,
        master_brain_freshness,
        replay_freshness,
        reinforcement_learning_freshness,
        dashboard_sync_freshness,
    ]
    stale_artifacts = [
        {
            "name": item["name"],
            "path": item["path"],
            "status": item["status"],
            "age_seconds": item["age_seconds"],
            "fresh_seconds": item["fresh_seconds"],
        }
        for item in freshness_items
        if item["stale"]
    ]
    if daemon_lock_stale:
        stale_artifacts.append(
            {
                "name": "titan_daemon_lock",
                "path": str(DAEMON_LOCK_PATH).replace("\\", "/"),
                "status": "STALE",
                "age_seconds": round(lock_age, 3) if lock_age is not None else None,
                "fresh_seconds": LOCK_STALE_SECONDS,
            }
        )

    safety_flags = {
        "advisory_only": True,
        "research_only": True,
        "affects_live_ranking": False,
        "affects_execution": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "supabase_mutation": False,
        "live_order_behavior": False,
        "recommended_live_weight": 0.0,
        "rank_adjustment": 0.0,
    }

    if any(flag.endswith("without_visible_process") for flag in contradiction_flags):
        overall_status = "FAIL"
    elif contradiction_flags or stale_artifacts:
        overall_status = "WARNING"
    else:
        overall_status = "PASS"

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": overall_status,
        "current_mode": current_mode,
        "process_visible": process_visible,
        "daemon_pid": daemon_pid,
        "daemon_lock_present": daemon_lock_present,
        "daemon_lock_age_seconds": round(lock_age, 3) if lock_age is not None else None,
        "daemon_lock_stale": daemon_lock_stale,
        "runtime_owner": runtime_owner,
        "scanner_freshness": scanner_freshness,
        "master_brain_freshness": master_brain_freshness,
        "replay_freshness": replay_freshness,
        "reinforcement_learning_freshness": reinforcement_learning_freshness,
        "dashboard_sync_freshness": dashboard_sync_freshness,
        "contradiction_flags": contradiction_flags,
        "stale_artifacts": stale_artifacts,
        "safety_flags": safety_flags,
    }
    _atomic_write_json(path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run_authoritative_runtime_health_check(), indent=2, sort_keys=True, default=str))
