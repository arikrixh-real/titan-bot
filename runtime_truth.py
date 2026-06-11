import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from utils.market_hours import IST, as_ist_datetime
from scanner_ohlc_setup_truth import (
    classify_ohlc_status,
    classify_scanner_status,
    classify_setup_engine_status,
)


RUNTIME_DIR = Path("data") / "runtime"
AUTHORITATIVE_RUNTIME_TRUTH_PATH = RUNTIME_DIR / "authoritative_runtime_truth.json"
RUNTIME_OWNER_TRANSITION_PATH = RUNTIME_DIR / "runtime_owner_transition.json"

DAEMON_HEALTH_PATH = RUNTIME_DIR / "daemon_health.json"
HEARTBEAT_PATH = RUNTIME_DIR / "titan_heartbeat.json"
WORKER_HEALTH_PATH = RUNTIME_DIR / "worker_health.json"
SCANNER_SCHEDULER_STATUS_PATH = RUNTIME_DIR / "scanner_scheduler_status.json"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
FINAL_VALIDATED_SETUPS_PATH = RUNTIME_DIR / "final_validated_setups.json"
SETUP_ENGINE_STATUS_PATH = RUNTIME_DIR / "setup_engine_status.json"
MASTER_BRAIN_STATUS_PATH = RUNTIME_DIR / "master_brain_status.json"
OUTCOME_TRACKER_STATUS_PATH = RUNTIME_DIR / "outcome_tracker_status.json"
PAPER_ENGINE_STATUS_PATH = RUNTIME_DIR / "paper_engine_status.json"
DASHBOARD_SYNC_STATUS_PATH = RUNTIME_DIR / "dashboard_sync_status.json"
OHLC_HEALTH_PATH = RUNTIME_DIR / "ohlc_health.json"
DAEMON_LOCK_PATH = RUNTIME_DIR / "locks" / "titan_daemon.lock"

DEFAULT_TTL_SECONDS = 15 * 60
DATA_TTL_SECONDS = 24 * 60 * 60
WORKER_TTL_SECONDS = 15 * 60
LOCK_TTL_SECONDS = 5 * 60

LIVE_STATUSES = {"ALIVE", "RUNNING", "OK", "ACTIVE", "SCAN_ONLY_COMPLETE", "COMPLETED"}
STOPPED_STATUSES = {"STOPPED", "INACTIVE", "SHUTDOWN", "EXITED"}
DEGRADED_MARKERS = ("DEGRADED", "ERROR", "FAIL", "FAILED", "UNAVAILABLE")
SAFETY_STATUSES = {"DISABLED", "READ_ONLY", "ADVISORY_ONLY", "PAPER_ONLY", "REAL_BLOCKED"}


def read_json_safe(path):
    path = Path(path)
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def parse_timestamp(value):
    if value in (None, ""):
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


def payload_timestamp(payload, keys=None):
    if not isinstance(payload, dict):
        return None
    keys = keys or (
        "timestamp_ist",
        "generated_at_ist",
        "generated_at",
        "updated_at",
        "scan_finished_at_ist",
        "last_finished_at",
        "last_started_at",
        "last_completed_at_ist",
        "acquired_at_ist",
    )
    for key in keys:
        parsed = parse_timestamp(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def file_timestamp(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(IST)
    except OSError:
        return None


def age_seconds(timestamp, now):
    if timestamp is None:
        return None
    return max(0.0, (now.astimezone(IST) - timestamp.astimezone(IST)).total_seconds())


def process_visible(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
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
            return None
    try:
        return Path("/proc").joinpath(str(pid)).exists()
    except Exception:
        return None


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


def _source_timestamp(path, payload, timestamp_keys=None):
    return payload_timestamp(payload, timestamp_keys) or file_timestamp(path)


def _status_text(payload):
    return str((payload or {}).get("status") or "").strip().upper()


def _base_record(component, path, payload, now, ttl_seconds, timestamp_keys=None):
    timestamp = _source_timestamp(path, payload, timestamp_keys)
    age = age_seconds(timestamp, now)
    exists = Path(path).exists()
    filesystem_timestamp = file_timestamp(path)
    filesystem_age = age_seconds(filesystem_timestamp, now)
    return {
        "component": component,
        "status": "UNKNOWN",
        "source_file": str(path).replace("\\", "/"),
        "source_timestamp": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "age_minutes": round(age / 60, 3) if age is not None else None,
        "filesystem_mtime": filesystem_timestamp.isoformat() if filesystem_timestamp else None,
        "filesystem_age_seconds": round(filesystem_age, 3) if filesystem_age is not None else None,
        "ttl_seconds": ttl_seconds,
        "freshness_threshold_seconds": ttl_seconds,
        "reason": "unclassified",
        "confidence": "LOW",
        "restart_blocker": False,
        "source_exists": exists,
        "source_status": (payload or {}).get("status") if isinstance(payload, dict) else None,
    }


def _is_stale(record):
    return (not record["source_exists"]) or record["age_seconds"] is None or record["age_seconds"] > record["ttl_seconds"]


def classify_status_file(
    component,
    path,
    payload=None,
    now=None,
    ttl_seconds=DEFAULT_TTL_SECONDS,
    marker_only=False,
    execution_active_required=False,
    timestamp_keys=None,
):
    now_ist = as_ist_datetime(now).astimezone(IST)
    payload = payload if isinstance(payload, dict) else read_json_safe(path)
    record = _base_record(component, path, payload, now_ist, ttl_seconds, timestamp_keys=timestamp_keys)
    status_text = _status_text(payload)

    if not record["source_exists"]:
        record.update(status="UNKNOWN", reason="source_file_missing", confidence="LOW")
        return record
    if payload.get("_read_error"):
        record.update(status="UNKNOWN", reason=f"source_read_error:{payload.get('_read_error')}", confidence="LOW")
        return record
    if _is_stale(record):
        stale_claims_active = (
            status_text
            and status_text not in STOPPED_STATUSES
            and not any(marker in status_text for marker in DEGRADED_MARKERS)
            and status_text not in SAFETY_STATUSES
        )
        if stale_claims_active:
            record.update(
                status="STALE_LIVE_CLAIM",
                reason="source_timestamp_stale_with_historical_live_status",
                confidence="HIGH",
                restart_blocker=True,
                historical_status=status_text or None,
                stale_live_claim=True,
            )
        else:
            record.update(status="STALE", reason="source_timestamp_stale_or_missing", confidence="HIGH", restart_blocker=True)
        return record
    if marker_only or payload.get("marker_only") is True or "MARKER" in status_text:
        record.update(status="MARKER_ONLY", reason="marker_only_status_not_runtime_liveness", confidence="HIGH")
        return record
    if status_text in SAFETY_STATUSES:
        record.update(
            status=status_text,
            reason="fresh_master_brain_activation_guard_status",
            confidence="HIGH",
            restart_blocker=status_text == "REAL_BLOCKED",
        )
        return record
    if execution_active_required and (
        payload.get("observe_only") is True
        or payload.get("scan_only") is True
        or payload.get("live_execution_enabled") is False
        or payload.get("affects_execution") is False
        or str(payload.get("runtime_mode") or "").upper() in {"READ_ONLY", "HEALTH", "RESEARCH_ONLY", "SHADOW", "PAPER"}
    ):
        record.update(status="MARKER_ONLY", reason="fresh_but_not_execution_active", confidence="HIGH")
        return record
    if status_text in STOPPED_STATUSES:
        record.update(status="STOPPED", reason="source_status_stopped", confidence="HIGH", restart_blocker=True)
        return record
    if any(marker in status_text for marker in DEGRADED_MARKERS):
        record.update(status="DEGRADED", reason="source_status_degraded", confidence="HIGH", restart_blocker=True)
        return record
    if status_text in LIVE_STATUSES or status_text:
        record.update(status="LIVE", reason="fresh_active_status", confidence="MEDIUM")
        return record
    record.update(status="UNKNOWN", reason="fresh_source_without_status", confidence="LOW")
    return record


def _pid_value(payload):
    pid = (payload or {}).get("pid")
    return pid if pid not in (None, "") else None


def _pid_int(pid):
    try:
        return int(pid)
    except (TypeError, ValueError):
        return None


def _same_pid(left, right):
    left_pid = _pid_int(left)
    right_pid = _pid_int(right)
    return left_pid is not None and right_pid is not None and left_pid == right_pid


def _visible(process_checker, pid):
    if pid in (None, ""):
        return None
    return process_checker(pid)


def classify_daemon_process_tree(processes, lock_pid=None, runtime_writer_pid=None):
    records = []
    by_pid = {}
    writer_pids = set()
    lock_owner_pids = set()

    for process in processes or []:
        if not isinstance(process, dict):
            continue
        pid = _pid_int(process.get("pid"))
        if pid is None:
            continue
        by_pid[pid] = process
        if bool(process.get("lock_owner")) or _same_pid(pid, lock_pid):
            lock_owner_pids.add(pid)
        if process.get("writes_runtime") is True or _same_pid(pid, runtime_writer_pid):
            writer_pids.add(pid)

    independent_writers = set(writer_pids)
    duplicate_conflict = len(independent_writers) >= 2 or len(lock_owner_pids) >= 2

    for pid, process in by_pid.items():
        ppid = _pid_int(process.get("ppid"))
        command = str(process.get("command") or "")
        lock_owner = pid in lock_owner_pids
        writes_runtime = True if pid in writer_pids else process.get("writes_runtime")
        evidence_paths = list(process.get("evidence_paths") or [])
        classification = "UNKNOWN"
        confidence = "LOW"

        if duplicate_conflict and (lock_owner or writes_runtime is True):
            classification = "DUPLICATE_OWNER"
            confidence = "HIGH"
        elif lock_owner and writes_runtime is True:
            classification = "ACTIVE_OWNER"
            confidence = "HIGH"
        elif lock_owner:
            classification = "ACTIVE_OWNER"
            confidence = "MEDIUM"
        elif writes_runtime is True:
            classification = "RUNTIME_WRITER"
            confidence = "MEDIUM"
        elif any(_same_pid(child.get("ppid"), pid) for child in by_pid.values()) and "titan_daemon.py" in command:
            classification = "WRAPPER_PARENT"
            confidence = "HIGH"
        elif ppid in by_pid and "titan_daemon.py" in command:
            classification = "LAUNCHER_CHILD"
            confidence = "MEDIUM"

        records.append(
            {
                "pid": pid,
                "ppid": ppid,
                "command": command,
                "lock_owner": lock_owner,
                "writes_runtime": writes_runtime if writes_runtime in (True, False) else "unknown",
                "classification": classification,
                "confidence": confidence,
                "evidence_paths": evidence_paths,
            }
        )

    return {
        "duplicate_owner_conflict": duplicate_conflict,
        "active_owner_pids": sorted(lock_owner_pids),
        "runtime_writer_pids": sorted(writer_pids),
        "processes": sorted(records, key=lambda item: item["pid"]),
    }


def runtime_lock_weakness_diagnostic():
    return {
        "status": "THEORETICAL_WEAKNESS",
        "lock_module": "runtime_lock.py",
        "validates_live_pid_before_stale_overwrite": False,
        "stale_time_overwrite_can_overwrite_live_lock": True,
        "current_duplicate_daemon_cause": False,
        "reason": "runtime_lock.acquire_lock uses timestamp staleness before overwrite and does not prove owner PID is dead",
        "semantics_changed": False,
    }


def _transition_payload(record, now):
    return {
        "generated_at": now.isoformat(),
        "runtime_owner": record.get("runtime_owner"),
        "transition_reason": record.get("transition_reason"),
        "old_daemon_pid": record.get("old_daemon_pid"),
        "new_heartbeat_pid": record.get("new_heartbeat_pid"),
        "daemon_pid_visible": record.get("daemon_pid_visible"),
        "heartbeat_pid_visible": record.get("heartbeat_pid_visible"),
        "daemon_status": record.get("source_status"),
        "heartbeat_status": record.get("heartbeat_status"),
        "daemon_source_timestamp": record.get("source_timestamp"),
        "heartbeat_source_timestamp": record.get("heartbeat_timestamp"),
        "daemon_age_seconds": record.get("age_seconds"),
        "heartbeat_age_seconds": record.get("heartbeat_age_seconds"),
        "status": record.get("status"),
        "safety": {
            "daemon_restart": False,
            "daemon_stop": False,
            "worker_start": False,
            "broker_enabled": False,
            "telegram_enabled": False,
            "journal_mutation": False,
            "hft_enabled": False,
        },
    }


def classify_daemon(now=None, process_checker=None, write_transition=True):
    now_ist = as_ist_datetime(now).astimezone(IST)
    process_checker = process_checker or process_visible
    daemon = read_json_safe(DAEMON_HEALTH_PATH)
    heartbeat = read_json_safe(HEARTBEAT_PATH)
    lock = read_json_safe(DAEMON_LOCK_PATH)
    daemon_record = _base_record("daemon", DAEMON_HEALTH_PATH, daemon, now_ist, DEFAULT_TTL_SECONDS)
    heartbeat_record = _base_record("daemon_heartbeat", HEARTBEAT_PATH, heartbeat, now_ist, DEFAULT_TTL_SECONDS)
    lock_record = _base_record("daemon_lock", DAEMON_LOCK_PATH, lock, now_ist, LOCK_TTL_SECONDS, timestamp_keys=("acquired_at_ist", "timestamp_ist"))

    daemon_status = _status_text(daemon)
    heartbeat_status = _status_text(heartbeat)
    daemon_fresh = not _is_stale(daemon_record)
    heartbeat_fresh = not _is_stale(heartbeat_record)
    lock_fresh = lock_record["source_exists"] and not _is_stale(lock_record)
    daemon_pid = _pid_value(daemon)
    heartbeat_pid = _pid_value(heartbeat)
    lock_pid = _pid_value(lock)
    daemon_visible = _visible(process_checker, daemon_pid)
    heartbeat_visible = _visible(process_checker, heartbeat_pid)
    lock_visible = _visible(process_checker, lock_pid)
    pid = daemon_pid or heartbeat_pid or lock_pid
    visible = daemon_visible if daemon_pid is not None else (heartbeat_visible if heartbeat_pid is not None else lock_visible)

    record = dict(daemon_record)
    record["process_pid"] = pid
    record["process_visible"] = visible
    record["runtime_owner"] = "unknown"
    record["transition_reason"] = None
    record["old_daemon_pid"] = daemon_pid
    record["new_heartbeat_pid"] = heartbeat_pid
    record["daemon_pid_visible"] = daemon_visible
    record["heartbeat_pid_visible"] = heartbeat_visible
    record["lock_pid"] = lock_pid
    record["lock_pid_visible"] = lock_visible
    record["heartbeat_status"] = heartbeat.get("status")
    record["heartbeat_timestamp"] = heartbeat_record["source_timestamp"]
    record["heartbeat_age_seconds"] = heartbeat_record["age_seconds"]
    record["lock_fresh"] = lock_fresh
    record["lock_owner_matches_daemon"] = _same_pid(lock_pid, daemon_pid)
    record["lock_owner_matches_heartbeat"] = _same_pid(lock_pid, heartbeat_pid)
    record["daemon_writes_runtime"] = bool(daemon_fresh and daemon_pid is not None)
    record["heartbeat_writes_runtime"] = bool(heartbeat_fresh and heartbeat_pid is not None)
    record["lock_weakness_diagnostic"] = runtime_lock_weakness_diagnostic()

    process_rows = []
    if daemon_pid is not None:
        process_rows.append(
            {
                "pid": daemon_pid,
                "ppid": daemon.get("ppid"),
                "command": daemon.get("command") or "titan_daemon.py",
                "lock_owner": _same_pid(lock_pid, daemon_pid),
                "writes_runtime": bool(daemon_fresh),
                "evidence_paths": [str(DAEMON_HEALTH_PATH).replace("\\", "/")],
            }
        )
    if heartbeat_pid is not None and not _same_pid(heartbeat_pid, daemon_pid):
        process_rows.append(
            {
                "pid": heartbeat_pid,
                "ppid": heartbeat.get("ppid"),
                "command": heartbeat.get("command") or "titan_daemon.py",
                "lock_owner": _same_pid(lock_pid, heartbeat_pid),
                "writes_runtime": bool(heartbeat_fresh),
                "evidence_paths": [str(HEARTBEAT_PATH).replace("\\", "/")],
            }
        )
    if lock_pid is not None and not any(_same_pid(lock_pid, row.get("pid")) for row in process_rows):
        process_rows.append(
            {
                "pid": lock_pid,
                "ppid": None,
                "command": "UNKNOWN",
                "lock_owner": True,
                "writes_runtime": "unknown",
                "evidence_paths": [str(DAEMON_LOCK_PATH).replace("\\", "/")],
            }
        )
    record["process_classification_summary"] = classify_daemon_process_tree(
        process_rows,
        lock_pid=lock_pid,
        runtime_writer_pid=daemon_pid if daemon_fresh else (heartbeat_pid if heartbeat_fresh else None),
    )

    def finish(**updates):
        record.update(**updates)
        if write_transition:
            _atomic_write_json(RUNTIME_OWNER_TRANSITION_PATH, _transition_payload(record, now_ist))
        return record

    if (
        daemon_pid is not None
        and daemon_visible is False
        and heartbeat_pid is not None
        and heartbeat_visible is True
        and heartbeat_fresh
        and heartbeat_status in LIVE_STATUSES
    ):
        return finish(
            process_pid=heartbeat_pid,
            process_visible=True,
            runtime_owner="heartbeat",
            transition_reason="OWNER_ROTATED",
            status="LIVE",
            reason="dead_daemon_pid_rotated_to_fresh_heartbeat_owner",
            confidence="HIGH",
            restart_blocker=False,
        )
    if daemon_status in STOPPED_STATUSES and (not heartbeat_fresh or daemon_visible is False):
        return finish(status="STOPPED", reason="daemon_health_stopped_overrides_heartbeat_without_process", confidence="HIGH", restart_blocker=True)
    if daemon_status in STOPPED_STATUSES and daemon_fresh:
        return finish(status="STOPPED", reason="fresh_daemon_health_stopped", confidence="HIGH", restart_blocker=True)
    if (
        daemon_fresh
        and daemon_status in LIVE_STATUSES.union({"RUNNING"})
        and daemon_visible is True
        and lock_pid is not None
        and lock_visible is True
        and not _same_pid(lock_pid, daemon_pid)
    ):
        return finish(
            status="CONFLICT",
            reason="fresh_daemon_evidence_lock_owner_mismatch",
            confidence="HIGH",
            restart_blocker=True,
        )
    if daemon_fresh and daemon_status in LIVE_STATUSES.union({"RUNNING"}) and daemon_visible is True:
        return finish(
            runtime_owner="daemon_health",
            transition_reason="OWNER_STABLE",
            status="LIVE",
            runtime_state="RUNNING_READ_ONLY_PROOF"
            if str(daemon.get("runtime_mode") or daemon.get("mode") or "").upper() in {"READ_ONLY", "DAEMON_PROOF_IDLE"}
            else "RUNNING_PROOF_ONLY",
            classification="ACTIVE_OWNER",
            reason="fresh_daemon_health_and_visible_process",
            confidence="HIGH",
        )
    if heartbeat_fresh and heartbeat_status in LIVE_STATUSES and heartbeat_visible is True:
        return finish(
            process_pid=heartbeat_pid,
            process_visible=True,
            runtime_owner="heartbeat",
            transition_reason="OWNER_HEARTBEAT_ONLY",
            status="LIVE",
            reason="fresh_heartbeat_and_visible_process",
            confidence="HIGH",
        )
    if daemon_fresh and daemon_status in LIVE_STATUSES.union({"RUNNING"}) and daemon_visible is None:
        return finish(status="UNKNOWN", reason="fresh_daemon_health_but_process_evidence_unavailable", confidence="MEDIUM")
    if heartbeat_fresh and heartbeat_status in LIVE_STATUSES and heartbeat_visible is None:
        return finish(status="UNKNOWN", reason="fresh_heartbeat_but_process_evidence_unavailable", confidence="MEDIUM")
    if daemon_status in LIVE_STATUSES.union({"RUNNING"}) or heartbeat_status in LIVE_STATUSES:
        return finish(status="STALE", reason="active_marker_stale_or_process_missing", confidence="HIGH", restart_blocker=True)
    if _is_stale(daemon_record) and _is_stale(heartbeat_record):
        return finish(status="STALE", reason="daemon_and_heartbeat_stale_or_missing", confidence="HIGH", restart_blocker=True)
    return finish(status="UNKNOWN", reason="daemon_liveness_not_proven", confidence="LOW", restart_blocker=True)


def classify_workers(now=None, process_checker=None):
    now_ist = as_ist_datetime(now).astimezone(IST)
    process_checker = process_checker or process_visible
    payload = read_json_safe(WORKER_HEALTH_PATH)
    record = _base_record("workers", WORKER_HEALTH_PATH, payload, now_ist, WORKER_TTL_SECONDS)
    if not record["source_exists"]:
        record.update(status="UNKNOWN", reason="worker_health_missing", confidence="LOW")
        return record
    if payload.get("_read_error"):
        record.update(status="UNKNOWN", reason=f"worker_health_read_error:{payload.get('_read_error')}", confidence="LOW")
        return record

    worker_records = {}
    stale_running = []
    degraded = []
    fresh_live = []
    proof_live = []
    stale_pid_workers = []
    proof_expired_workers = []
    for name, worker in payload.items():
        if not isinstance(worker, dict):
            continue
        worker_record = _base_record(name, WORKER_HEALTH_PATH, worker, now_ist, WORKER_TTL_SECONDS)
        status_text = _status_text(worker)
        stale = _is_stale(worker_record)
        active_pid = worker.get("active_pid") or worker.get("pid")
        active_pid_visible = _visible(process_checker, active_pid)
        expired_proof_pid = bool(
            worker.get("proof_mode") is True
            and stale
            and active_pid not in (None, "")
            and active_pid_visible is False
        )
        pid_missing_for_live_claim = (
            active_pid not in (None, "")
            and active_pid_visible is False
            and status_text in {"RUNNING", "STARTING", "OK", "ALIVE"}
            and not expired_proof_pid
        )
        if expired_proof_pid:
            worker_status = "PROOF_EXPIRED"
        elif pid_missing_for_live_claim:
            worker_status = "STALE_PID"
        else:
            worker_status = "STALE" if stale else status_text or "UNKNOWN"
        worker_records[name] = {
            "status": worker_status,
            "source_status": worker.get("status"),
            "age_seconds": worker_record["age_seconds"],
            "last_started_at": worker.get("last_started_at"),
            "last_finished_at": worker.get("last_finished_at"),
            "active_pid": active_pid,
            "active_pid_visible": active_pid_visible,
            "proof_mode": bool(worker.get("proof_mode") is True),
        }
        if expired_proof_pid:
            proof_expired_workers.append(name)
        elif pid_missing_for_live_claim:
            stale_pid_workers.append(name)
        elif stale and status_text in {"RUNNING", "STARTING", "OK", "ALIVE"}:
            stale_running.append(name)
        elif any(marker in status_text for marker in DEGRADED_MARKERS):
            degraded.append(name)
        elif not stale and status_text in LIVE_STATUSES.union({"RUNNING", "STARTING"}):
            fresh_live.append(name)
            if worker.get("proof_mode") is True:
                proof_live.append(name)

    record["workers"] = worker_records
    record["stale_running_workers"] = stale_running
    record["degraded_workers"] = degraded
    record["fresh_live_workers"] = fresh_live
    record["fresh_proof_workers"] = proof_live
    record["stale_pid_workers"] = stale_pid_workers
    record["proof_expired_workers"] = proof_expired_workers
    required_proof_workers = {"heartbeat", "runtime_status", "dashboard_sync"}
    if required_proof_workers.issubset(set(proof_live)):
        record.update(
            status="LIVE",
            reason="fresh_controlled_worker_proof_tasks",
            confidence="HIGH",
            restart_blocker=False,
        )
        return record
    if stale_pid_workers:
        record.update(status="STALE_PID", reason="worker_active_pid_missing", confidence="HIGH", restart_blocker=True)
    elif proof_expired_workers:
        record.update(status="PROOF_EXPIRED", reason="controlled_worker_proof_pid_expired", confidence="HIGH", restart_blocker=False)
    elif stale_running:
        record.update(status="STALE", reason="running_worker_timestamps_stale", confidence="HIGH", restart_blocker=True)
    elif degraded:
        record.update(status="DEGRADED", reason="worker_health_reports_degraded_workers", confidence="HIGH", restart_blocker=True)
    elif fresh_live:
        record.update(status="LIVE", reason="fresh_worker_health_reports_live_workers", confidence="MEDIUM")
    else:
        record.update(status="UNKNOWN", reason="no_fresh_live_worker_evidence", confidence="LOW")
    return record


def build_authoritative_runtime_truth(path=AUTHORITATIVE_RUNTIME_TRUTH_PATH, now=None, write=True):
    now_ist = as_ist_datetime(now).astimezone(IST)
    components = {
        "daemon": classify_daemon(now_ist, write_transition=write),
        "workers": classify_workers(now_ist),
        "scheduler": classify_status_file("scheduler", SCANNER_SCHEDULER_STATUS_PATH, now=now_ist),
        "scanner": classify_scanner_status(SCANNER_STATUS_PATH, FINAL_VALIDATED_SETUPS_PATH, now=now_ist),
        "setup_engine": classify_setup_engine_status(SETUP_ENGINE_STATUS_PATH, FINAL_VALIDATED_SETUPS_PATH, now=now_ist),
        "master_brain": classify_status_file(
            "master_brain",
            MASTER_BRAIN_STATUS_PATH,
            now=now_ist,
            execution_active_required=True,
        ),
        "outcome_tracker": classify_status_file("outcome_tracker", OUTCOME_TRACKER_STATUS_PATH, now=now_ist),
        "paper_engine": classify_status_file("paper_engine", PAPER_ENGINE_STATUS_PATH, now=now_ist),
        "dashboard_sync": classify_status_file("dashboard_sync", DASHBOARD_SYNC_STATUS_PATH, now=now_ist),
        "ohlc_health": classify_ohlc_status(OHLC_HEALTH_PATH, now=now_ist),
    }
    restart_blockers = [name for name, record in components.items() if record.get("restart_blocker")]
    live_components = [name for name, record in components.items() if record.get("status") == "LIVE"]
    stale_components = [name for name, record in components.items() if record.get("status") == "STALE"]
    stale_live_claim_components = [name for name, record in components.items() if record.get("status") == "STALE_LIVE_CLAIM"]
    stopped_components = [name for name, record in components.items() if record.get("status") == "STOPPED"]
    degraded_components = [name for name, record in components.items() if record.get("status") == "DEGRADED"]
    conflict_components = [name for name, record in components.items() if str(record.get("status") or "").startswith("CONFLICT")]
    payload = {
        "generated_at": now_ist.isoformat(),
        "schema": "titan.runtime.authoritative_truth.v1",
        "diagnostic_only": True,
        "components": components,
        "summary": {
            "live_components": live_components,
            "stale_components": stale_components,
            "stale_live_claim_components": stale_live_claim_components,
            "stopped_components": stopped_components,
            "degraded_components": degraded_components,
            "conflict_components": conflict_components,
            "restart_blockers": restart_blockers,
            "overall_status": "CONFLICT"
            if conflict_components
            else (
                "DEGRADED"
                if degraded_components
                else ("STOPPED" if stopped_components else ("STALE" if stale_components or stale_live_claim_components else "LIVE"))
            ),
        },
        "safety": {
            "broker_calls": False,
            "trade_placement": False,
            "service_restart": False,
            "journal_row_mutation": False,
            "diagnostic_status_write_only": bool(write),
        },
    }
    if write:
        _atomic_write_json(path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(build_authoritative_runtime_truth(), indent=2, sort_keys=True))
