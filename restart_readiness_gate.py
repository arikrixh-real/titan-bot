import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from master_brain_activation_guard import BROKER_APPROVAL_TOKEN, TELEGRAM_APPROVAL_TOKEN
from runtime_truth import process_visible
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
LOCK_DIR = RUNTIME_DIR / "locks"
RESTART_READINESS_GATE_PATH = RUNTIME_DIR / "restart_readiness_gate.json"
AUTHORITATIVE_RUNTIME_TRUTH_PATH = RUNTIME_DIR / "authoritative_runtime_truth.json"
JOURNAL_TRUTH_PATH = RUNTIME_DIR / "journal_truth_unification.json"
DASHBOARD_TRUTH_PATH = RUNTIME_DIR / "dashboard_truth_consolidation.json"
MASTER_BRAIN_GUARD_PATH = RUNTIME_DIR / "master_brain_activation_guard.json"
SCANNER_OHLC_SETUP_TRUTH_PATH = RUNTIME_DIR / "scanner_ohlc_setup_truth.json"

LOCK_TTL_SECONDS = 5 * 60
SAFE_MASTER_GUARD_STATUSES = {"READ_ONLY", "ADVISORY_ONLY", "PAPER_ONLY", "REAL_BLOCKED", "DISABLED"}
RESTART_OK_SCANNER_STATUSES = {"LIVE", "SCAN_LIVE", "SCAN_IDLE", "SCAN_WAITING_FOR_MARKET"}
RESTART_OK_SETUP_STATUSES = {"REAL_SETUP_ENGINE_CONNECTED", "DIAGNOSTIC_SKIPPED"}
WORKER_START_ALLOWED_ACTIVE_LOCKS = {"titan_daemon", "task_runtime_status"}


def _now_ist():
    return datetime.now(IST).isoformat()


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


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
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def parse_timestamp(value):
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _file_timestamp(path):
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
    return max(0.0, (now.astimezone(IST) - timestamp.astimezone(IST)).total_seconds())


def classify_lock(path, now=None, ttl_seconds=LOCK_TTL_SECONDS, process_checker=process_visible):
    now_ist = as_ist_datetime(now).astimezone(IST)
    path = Path(path)
    payload = _read_json(path)
    timestamp = parse_timestamp(payload.get("acquired_at_ist") or payload.get("timestamp_ist")) or _file_timestamp(path)
    age = _age_seconds(timestamp, now_ist)
    pid = payload.get("pid")
    visible = None
    if pid not in (None, ""):
        visible = process_checker(pid)
    if visible is True:
        status = "ACTIVE_LOCK"
        reason = "lock_pid_process_visible"
    elif visible is False and age is not None and age > ttl_seconds:
        status = "STALE_LOCK"
        reason = "lock_stale_and_pid_not_visible"
    else:
        status = "UNKNOWN_LOCK"
        if pid in (None, ""):
            reason = "lock_pid_missing"
        elif visible is None:
            reason = "lock_process_evidence_unavailable"
        else:
            reason = "lock_not_old_enough_to_classify_stale"
    return {
        "path": str(path).replace("\\", "/"),
        "name": payload.get("name") or path.stem,
        "status": status,
        "reason": reason,
        "pid": pid,
        "process_visible": visible,
        "acquired_at": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "ttl_seconds": ttl_seconds,
    }


def classify_locks(lock_dir=LOCK_DIR, now=None, process_checker=process_visible):
    lock_dir = Path(lock_dir)
    if not lock_dir.exists():
        return []
    return [
        classify_lock(path, now=now, process_checker=process_checker)
        for path in sorted(lock_dir.glob("*.lock"))
    ]


def _component_status(runtime_truth, name):
    components = runtime_truth.get("components") if isinstance(runtime_truth, dict) else {}
    record = components.get(name) if isinstance(components, dict) else {}
    return str((record or {}).get("status") or "UNKNOWN").upper()


def _component_record(runtime_truth, name):
    components = runtime_truth.get("components") if isinstance(runtime_truth, dict) else {}
    record = components.get(name) if isinstance(components, dict) else {}
    return record if isinstance(record, dict) else {}


def _daemon_pid(runtime_truth):
    daemon = _component_record(runtime_truth, "daemon")
    pid = daemon.get("process_pid") or daemon.get("pid")
    return str(pid).strip() if pid not in (None, "") else None


def _active_lock_allowed_for_worker_start(lock, *, daemon_status, daemon_pid):
    lock_name = str(lock.get("name") or "").strip()
    lock_pid = str(lock.get("pid") or "").strip()
    return bool(
        lock_name in WORKER_START_ALLOWED_ACTIVE_LOCKS
        and daemon_status == "LIVE"
        and daemon_pid
        and lock_pid == daemon_pid
        and lock.get("process_visible") is True
    )


def _scanner_setup_truth(scanner_truth, key):
    record = scanner_truth.get(key) if isinstance(scanner_truth, dict) else {}
    return str((record or {}).get("status") or "UNKNOWN").upper()


def _journal_status(journal_truth):
    if not isinstance(journal_truth, dict) or not journal_truth:
        return "UNKNOWN"
    try:
        canonical_count = int(journal_truth.get("canonical_open_trade_count", 0))
    except (TypeError, ValueError):
        canonical_count = -1
    if canonical_count != 0:
        return "CURRENT_TRADE_CONFLICT"
    if journal_truth.get("legacy_open_rows_warning"):
        return "CANONICAL_CLEAN_LEGACY_WARNING"
    return "CLEAN"


def _execution_disabled(master_guard, env):
    broker_disabled = env.get("TITAN_BROKER_LIVE_EXECUTION") != BROKER_APPROVAL_TOKEN and not master_guard.get("can_call_broker")
    telegram_disabled = env.get("TITAN_TELEGRAM_ALERTS") != TELEGRAM_APPROVAL_TOKEN and not master_guard.get("can_send_telegram")
    return broker_disabled, telegram_disabled


def build_restart_readiness_gate(
    *,
    runtime_truth=None,
    journal_truth=None,
    dashboard_truth=None,
    master_guard=None,
    scanner_truth=None,
    lock_dir=LOCK_DIR,
    output_path=RESTART_READINESS_GATE_PATH,
    env=None,
    now=None,
    write=True,
    process_checker=process_visible,
):
    env = env if isinstance(env, dict) else os.environ
    runtime_truth = runtime_truth if isinstance(runtime_truth, dict) else _read_json(AUTHORITATIVE_RUNTIME_TRUTH_PATH)
    journal_truth = journal_truth if isinstance(journal_truth, dict) else _read_json(JOURNAL_TRUTH_PATH)
    dashboard_truth = dashboard_truth if isinstance(dashboard_truth, dict) else _read_json(DASHBOARD_TRUTH_PATH)
    master_guard = master_guard if isinstance(master_guard, dict) else _read_json(MASTER_BRAIN_GUARD_PATH)
    scanner_truth = scanner_truth if isinstance(scanner_truth, dict) else _read_json(SCANNER_OHLC_SETUP_TRUTH_PATH)

    locks = classify_locks(lock_dir, now=now, process_checker=process_checker)
    stale_locks = [lock for lock in locks if lock["status"] == "STALE_LOCK"]
    active_locks = [lock for lock in locks if lock["status"] == "ACTIVE_LOCK"]
    unknown_locks = [lock for lock in locks if lock["status"] == "UNKNOWN_LOCK"]
    safe_to_clear_locks = bool(stale_locks and not active_locks and not unknown_locks)

    daemon_status = _component_status(runtime_truth, "daemon")
    worker_status = _component_status(runtime_truth, "workers")
    scheduler_status = _component_status(runtime_truth, "scheduler")
    scanner_status = _scanner_setup_truth(scanner_truth, "scanner_status") or _component_status(runtime_truth, "scanner")
    ohlc_status = _scanner_setup_truth(scanner_truth, "ohlc_status") or _component_status(runtime_truth, "ohlc_health")
    setup_status = _scanner_setup_truth(scanner_truth, "setup_engine_status") or _component_status(runtime_truth, "setup_engine")
    master_guard_status = str(master_guard.get("status") or "UNKNOWN").upper()
    journal_status = _journal_status(journal_truth)
    dashboard_status = str(dashboard_truth.get("dashboard_overall_status") or "UNKNOWN").upper()
    runtime_loaded = bool(runtime_truth)
    dashboard_loaded = bool(dashboard_truth)
    broker_disabled, telegram_disabled = _execution_disabled(master_guard, env)
    daemon_pid = _daemon_pid(runtime_truth)
    allowed_worker_active_locks = [
        lock
        for lock in active_locks
        if _active_lock_allowed_for_worker_start(lock, daemon_status=daemon_status, daemon_pid=daemon_pid)
    ]
    blocking_active_locks = [lock for lock in active_locks if lock not in allowed_worker_active_locks]

    scanner_setup_stale = (
        scanner_status not in RESTART_OK_SCANNER_STATUSES
        or ohlc_status != "LIVE"
        or setup_status not in RESTART_OK_SETUP_STATUSES
    )
    safe_to_refresh_data = bool(
        broker_disabled
        and telegram_disabled
        and master_guard_status in SAFE_MASTER_GUARD_STATUSES
        and journal_status in {"CLEAN", "CANONICAL_CLEAN_LEGACY_WARNING"}
        and runtime_loaded
    )

    blockers = []
    warnings = []
    if blocking_active_locks:
        blockers.append("active_locks_present")
    if unknown_locks:
        blockers.append("unknown_locks_present")
    if stale_locks:
        warnings.append("stale_locks_present_safe_to_clear_later" if safe_to_clear_locks else "stale_locks_present")
    if master_guard_status not in SAFE_MASTER_GUARD_STATUSES:
        blockers.append(f"master_brain_guard_unsafe:{master_guard_status}")
    if journal_status == "CURRENT_TRADE_CONFLICT":
        blockers.append("canonical_open_trades_not_zero")
    if journal_status == "UNKNOWN":
        blockers.append("journal_truth_unknown")
    if journal_status == "CANONICAL_CLEAN_LEGACY_WARNING":
        warnings.append("legacy_open_rows_quarantined_warning")
    if not dashboard_loaded:
        blockers.append("dashboard_truth_missing")
    if not runtime_loaded:
        blockers.append("authoritative_runtime_truth_missing")
    if scanner_setup_stale:
        blockers.append("scanner_ohlc_setup_refresh_required")
    if not broker_disabled:
        blockers.append("broker_live_execution_enabled")
    if not telegram_disabled:
        blockers.append("telegram_sending_enabled")

    safe_to_start_daemon = bool(
        not blockers
        and not blocking_active_locks
        and not unknown_locks
        and daemon_status != "LIVE"
    )
    safe_to_start_workers = bool(
        not blockers
        and not blocking_active_locks
        and not unknown_locks
        and daemon_status == "LIVE"
    )
    overall_restart_allowed = bool(safe_to_start_daemon or safe_to_start_workers)

    required_next_actions = []
    if safe_to_clear_locks:
        required_next_actions.append("Mission 015 may explicitly clear STALE_LOCK files after operator approval; do not delete them in Mission 014.")
    if scanner_setup_stale and safe_to_refresh_data:
        required_next_actions.append("Run controlled data-only refresh plan for OHLC, scanner scan-only, and setup diagnostic proof.")
    if broker_disabled:
        required_next_actions.append("Keep broker live execution disabled during refresh.")
    if telegram_disabled:
        required_next_actions.append("Keep Telegram sending disabled during refresh.")
    if blockers:
        required_next_actions.append("Do not start daemon/workers until blockers are cleared and gate is regenerated.")

    payload = {
        "generated_at": _now_ist(),
        "overall_restart_allowed": overall_restart_allowed,
        "daemon_status": daemon_status,
        "worker_status": worker_status,
        "scheduler_status": scheduler_status,
        "scanner_status": scanner_status,
        "ohlc_status": ohlc_status,
        "setup_engine_status": setup_status,
        "master_brain_guard_status": master_guard_status,
        "journal_truth_status": journal_status,
        "dashboard_truth_status": dashboard_status,
        "lock_status": "ACTIVE_LOCK" if active_locks else ("UNKNOWN_LOCK" if unknown_locks else ("STALE_LOCK" if stale_locks else "NO_LOCKS")),
        "stale_locks": stale_locks,
        "active_locks": active_locks,
        "worker_start_allowed_active_locks": allowed_worker_active_locks,
        "blocking_active_locks": blocking_active_locks,
        "unknown_locks": unknown_locks,
        "safe_to_clear_locks": safe_to_clear_locks,
        "safe_to_refresh_data": safe_to_refresh_data,
        "safe_to_start_daemon": safe_to_start_daemon,
        "safe_to_start_workers": safe_to_start_workers,
        "controlled_refresh_plan": {
            "ohlc_data_only_refresh_possible": safe_to_refresh_data,
            "scanner_scan_only_possible": safe_to_refresh_data,
            "setup_engine_diagnostic_only_possible": safe_to_refresh_data,
            "actual_refresh_executed": False,
        },
        "blockers": blockers,
        "warnings": warnings,
        "required_next_actions": required_next_actions,
        "safety": {
            "service_restart": False,
            "worker_start": False,
            "broker_order_calls": False,
            "trade_placement": False,
            "journal_mutation": False,
            "telegram_sent": False,
            "lock_deletion": False,
            "diagnostic_status_write_only": bool(write),
        },
    }
    if write:
        _atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(build_restart_readiness_gate(write=True), indent=2, sort_keys=True))
