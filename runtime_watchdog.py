import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from runtime_dependency_graph import SAFETY_FLAGS
from runtime_health import _process_visible
from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
LOCK_DIR = RUNTIME_DIR / "locks"

TITAN_RUNTIME_WATCHDOG_PATH = RUNTIME_DIR / "titan_runtime_watchdog.json"
RUNTIME_RECOVERY_POLICY_PATH = RUNTIME_DIR / "runtime_recovery_policy.json"
STALE_WRITER_AUDIT_PATH = RUNTIME_DIR / "stale_writer_audit.json"
RUNTIME_RECONCILIATION_STATUS_PATH = RUNTIME_DIR / "runtime_reconciliation_status.json"

RUNTIME_FRESH_SECONDS = 15 * 60
LOCK_FRESH_SECONDS = 5 * 60
SECONDARY_RUNTIME_FRESH_SECONDS = 15 * 60
DAEMON_COMMAND_MARKER = "titan_daemon.py"

RUNTIME_SOURCES = {
    "daemon_health": {
        "path": RUNTIME_DIR / "daemon_health.json",
        "owner_rank": 10,
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "ownership_signal": True,
    },
    "heartbeat": {
        "path": RUNTIME_DIR / "titan_heartbeat.json",
        "owner_rank": 20,
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "ownership_signal": True,
    },
    "daemon_lock": {
        "path": LOCK_DIR / "titan_daemon.lock",
        "owner_rank": 30,
        "fresh_seconds": LOCK_FRESH_SECONDS,
        "ownership_signal": True,
    },
    "authoritative_runtime_health": {
        "path": RUNTIME_DIR / "titan_authoritative_runtime_health.json",
        "owner_rank": 40,
        "fresh_seconds": RUNTIME_FRESH_SECONDS,
        "ownership_signal": False,
    },
    "runtime_status": {
        "path": RUNTIME_DIR / "titan_runtime_status.json",
        "owner_rank": 50,
        "fresh_seconds": SECONDARY_RUNTIME_FRESH_SECONDS,
        "ownership_signal": False,
    },
    "scanner_status": {
        "path": RUNTIME_DIR / "scanner_status.json",
        "owner_rank": 60,
        "fresh_seconds": SECONDARY_RUNTIME_FRESH_SECONDS,
        "ownership_signal": False,
    },
    "worker_health": {
        "path": RUNTIME_DIR / "worker_health.json",
        "owner_rank": 70,
        "fresh_seconds": SECONDARY_RUNTIME_FRESH_SECONDS,
        "ownership_signal": False,
    },
    "runtime_resilience_status": {
        "path": RUNTIME_DIR / "runtime_resilience_status.json",
        "owner_rank": 80,
        "fresh_seconds": SECONDARY_RUNTIME_FRESH_SECONDS,
        "ownership_signal": False,
    },
}

RUNNING_STATUSES = {"ALIVE", "RUNNING", "STARTING"}
STOPPED_STATUSES = {"STOPPED", "STOPPING", "EXITED", "DEAD"}


def _path_key(path):
    return str(Path(path)).replace("\\", "/")


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def _parse_timestamp(value):
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


def _payload_timestamp(payload):
    for key in (
        "generated_at_ist",
        "timestamp_ist",
        "acquired_at_ist",
        "generated_at",
        "updated_at",
        "last_completed_at_ist",
        "scan_finished_at_ist",
        "timestamp",
    ):
        parsed = _parse_timestamp(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _file_timestamp(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(IST)
    except OSError:
        return None


def _source_record(name, spec, now_ist):
    path = Path(spec["path"])
    payload = _read_json_safe(path)
    timestamp = _payload_timestamp(payload) or _file_timestamp(path)
    age = max(0.0, (now_ist - timestamp).total_seconds()) if timestamp else None
    fresh_seconds = int(spec.get("fresh_seconds") or RUNTIME_FRESH_SECONDS)
    present = path.exists()
    stale = (not present) or age is None or age > fresh_seconds
    pid = payload.get("pid") or payload.get("daemon_pid")
    visible = _process_visible(pid) if pid is not None else False
    status = str(payload.get("overall_status") or payload.get("status") or ("PRESENT" if present else "MISSING")).upper()
    return {
        "name": name,
        "path": _path_key(path),
        "present": present,
        "status": status,
        "mode": payload.get("mode") or payload.get("current_mode") or payload.get("runtime_mode"),
        "pid": pid,
        "pid_visible": visible,
        "timestamp_ist": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "fresh_seconds": fresh_seconds,
        "fresh": bool(present and not stale),
        "stale": stale,
        "ownership_signal": bool(spec.get("ownership_signal")),
        "owner_rank": spec.get("owner_rank"),
        "runtime_owner": payload.get("runtime_owner"),
        "raw": {
            "run_id": payload.get("run_id"),
            "ticks_completed": payload.get("ticks_completed"),
            "last_dispatch_count": payload.get("last_dispatch_count"),
            "duplicate_prevention": payload.get("duplicate_prevention"),
        },
    }


def _discover_visible_daemon_processes():
    processes = []
    proc_root = Path("/proc")
    if proc_root.exists():
        for path in proc_root.iterdir():
            if not path.name.isdigit():
                continue
            try:
                cmdline = (path / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()
            except OSError:
                continue
            if DAEMON_COMMAND_MARKER in cmdline:
                processes.append({"pid": int(path.name), "command": cmdline, "source": "proc_cmdline"})
        if processes:
            return sorted(processes, key=lambda item: item["pid"])

    try:
        result = subprocess.run(
            ["pgrep", "-af", DAEMON_COMMAND_MARKER],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        try:
            pid = int(parts[0])
        except (ValueError, IndexError):
            continue
        command = parts[1] if len(parts) > 1 else ""
        if DAEMON_COMMAND_MARKER in command:
            processes.append({"pid": pid, "command": command, "source": "pgrep"})
    return sorted(processes, key=lambda item: item["pid"])


def _collect_sources(now_ist):
    return {
        name: _source_record(name, spec, now_ist)
        for name, spec in RUNTIME_SOURCES.items()
    }


def _ownership_candidates(sources):
    candidates = []
    for name, source in sources.items():
        if not source.get("ownership_signal"):
            continue
        status = source.get("status")
        running = status in RUNNING_STATUSES
        stopped = status in STOPPED_STATUSES
        if source.get("pid_visible") and (running or name == "daemon_lock"):
            confidence = "HIGH"
            classification = "visible_runtime_owner"
        elif source.get("fresh") and running:
            confidence = "MEDIUM"
            classification = "fresh_running_artifact_without_process_visibility"
        elif source.get("present") and source.get("stale"):
            confidence = "LOW"
            classification = "stale_runtime_writer"
        elif stopped:
            confidence = "NONE"
            classification = "stopped_runtime_artifact"
        else:
            confidence = "NONE"
            classification = "non_owner_signal"
        candidates.append(
            {
                "name": name,
                "path": source.get("path"),
                "status": status,
                "pid": source.get("pid"),
                "pid_visible": source.get("pid_visible"),
                "fresh": source.get("fresh"),
                "stale": source.get("stale"),
                "confidence": confidence,
                "classification": classification,
                "owner_rank": source.get("owner_rank"),
            }
        )
    return sorted(candidates, key=lambda item: item.get("owner_rank") or 999)


def _pid_reconciliation(sources, visible_daemon_processes=None):
    visible_daemon_processes = visible_daemon_processes if visible_daemon_processes is not None else _discover_visible_daemon_processes()
    pid_sources = {
        "daemon_health_pid": sources.get("daemon_health", {}),
        "heartbeat_pid": sources.get("heartbeat", {}),
        "lock_pid": sources.get("daemon_lock", {}),
    }
    by_pid = {}
    stale_pid_flags = []
    ghost_pid_flags = []
    for role, source in pid_sources.items():
        pid = source.get("pid")
        if pid is None:
            continue
        key = str(pid)
        item = by_pid.setdefault(
            key,
            {
                "pid": pid,
                "roles": [],
                "visible_process_pid": bool(source.get("pid_visible")),
                "fresh_sources": [],
                "stale_sources": [],
                "statuses": {},
            },
        )
        item["roles"].append(role)
        item["visible_process_pid"] = item["visible_process_pid"] or bool(source.get("pid_visible"))
        item["statuses"][role] = source.get("status")
        if source.get("fresh"):
            item["fresh_sources"].append(role)
        if source.get("stale"):
            item["stale_sources"].append(role)

    for process in visible_daemon_processes:
        pid = process.get("pid")
        if pid is None:
            continue
        key = str(pid)
        item = by_pid.setdefault(
            key,
            {
                "pid": pid,
                "roles": [],
                "visible_process_pid": True,
                "fresh_sources": [],
                "stale_sources": [],
                "statuses": {},
            },
        )
        if "visible_process_pid" not in item["roles"]:
            item["roles"].append("visible_process_pid")
        item["visible_process_pid"] = True
        item["command"] = process.get("command")
        item["process_source"] = process.get("source")
        item["statuses"]["visible_process_pid"] = "RUNNING"

    visible = []
    stale = []
    ghost = []
    for item in by_pid.values():
        item["classification"] = "visible_process_pid" if item["visible_process_pid"] else "ghost_pid"
        if item["stale_sources"]:
            stale.append(item["pid"])
            stale_pid_flags.append(
                {
                    "pid": item["pid"],
                    "roles": list(item["roles"]),
                    "stale_sources": list(item["stale_sources"]),
                }
            )
        if item["visible_process_pid"]:
            visible.append(item)
        else:
            ghost.append(item)
            ghost_pid_flags.append(
                {
                    "pid": item["pid"],
                    "roles": list(item["roles"]),
                    "statuses": dict(item["statuses"]),
                }
            )

    authoritative = None
    if visible:
        visible.sort(
            key=lambda item: (
                0 if "daemon_health_pid" in item["roles"] else 1,
                0 if "lock_pid" in item["roles"] else 1,
                str(item["pid"]),
            )
        )
        authoritative = visible[0]["pid"]

    return {
        "authoritative_pid": authoritative,
        "visible_process_pids": [item["pid"] for item in visible],
        "ghost_pids": [item["pid"] for item in ghost],
        "stale_pids": stale,
        "pid_mismatch": len(by_pid) > 1,
        "pids": sorted(by_pid.values(), key=lambda item: str(item["pid"])),
        "stale_pid_flags": stale_pid_flags,
        "ghost_pid_flags": ghost_pid_flags,
    }


def _reconcile_owner(sources):
    candidates = _ownership_candidates(sources)
    pid_reconciliation = _pid_reconciliation(sources)
    authoritative_pid = pid_reconciliation.get("authoritative_pid")
    visible = [item for item in candidates if item["classification"] == "visible_runtime_owner"]
    fresh_running = [
        item
        for item in candidates
        if item["classification"] == "fresh_running_artifact_without_process_visibility"
    ]
    stale = [item for item in candidates if item["classification"] == "stale_runtime_writer"]
    if authoritative_pid is not None:
        owner = "confirmed_daemon_pid"
        status = "PASS"
        reason = "visible_daemon_related_pid_confirmed"
        confidence = "HIGH"
    elif visible:
        owner = "confirmed_daemon_pid"
        authoritative_pid = visible[0]["pid"]
        status = "PASS"
        reason = "visible_process_backed_runtime_owner"
        confidence = "HIGH"
    elif fresh_running:
        owner = fresh_running[0]["name"]
        status = "WARNING"
        reason = "fresh_running_artifact_but_process_visibility_missing"
        confidence = "MEDIUM"
    elif stale:
        owner = "none_confirmed"
        status = "WARNING"
        reason = "only_stale_runtime_writer_artifacts_visible"
        confidence = "LOW"
    else:
        owner = "none_confirmed"
        status = "WARNING"
        reason = "no_runtime_owner_visible"
        confidence = "NONE"
    return {
        "reconciliation_status": status,
        "deterministic_runtime_owner": owner,
        "authoritative_pid": authoritative_pid,
        "pid_reconciliation": pid_reconciliation,
        "owner_confidence": confidence,
        "reconciliation_reason": reason,
        "ownership_candidates": candidates,
    }


def _detect_inconsistencies(sources):
    inconsistencies = []
    daemon = sources.get("daemon_health", {})
    heartbeat = sources.get("heartbeat", {})
    lock = sources.get("daemon_lock", {})
    runtime_health = sources.get("authoritative_runtime_health", {})

    if daemon.get("status") in STOPPED_STATUSES and heartbeat.get("status") in RUNNING_STATUSES:
        inconsistencies.append("daemon_stopped_but_heartbeat_alive")
    if heartbeat.get("status") in RUNNING_STATUSES and heartbeat.get("stale"):
        inconsistencies.append("heartbeat_alive_but_stale")
    if lock.get("present") and lock.get("stale"):
        inconsistencies.append("daemon_lock_stale_or_owner_missing")
    if runtime_health.get("runtime_owner") == "stale_lock_only" and heartbeat.get("status") in RUNNING_STATUSES:
        inconsistencies.append("runtime_health_reports_stale_lock_while_heartbeat_alive")
    if daemon.get("pid") and heartbeat.get("pid") and daemon.get("pid") != heartbeat.get("pid"):
        inconsistencies.append("daemon_health_heartbeat_pid_mismatch")
    return inconsistencies


def _stale_writer_recommendation(source):
    if source.get("name") == "daemon_lock":
        return "manual_review_lock_owner_before_restart_or_cleanup"
    if source.get("ownership_signal"):
        return "manual_review_runtime_owner_before_any_action"
    if source.get("present"):
        return "refresh_visibility_artifact_by_normal_writer_path"
    return "no_action_missing_visibility_only"


def build_stale_writer_audit(now=None, sources=None):
    now_ist = as_ist_datetime(now)
    sources = sources or _collect_sources(now_ist)
    stale_writers = []
    for source in sources.values():
        if not source.get("stale"):
            continue
        stale_writers.append(
            {
                "name": source["name"],
                "path": source["path"],
                "status": source["status"],
                "pid": source.get("pid"),
                "pid_visible": source.get("pid_visible"),
                "age_seconds": source.get("age_seconds"),
                "fresh_seconds": source.get("fresh_seconds"),
                "classification": "stale_runtime_owner_signal" if source.get("ownership_signal") else "stale_secondary_runtime_source",
                "recovery_recommendation": _stale_writer_recommendation(source),
                "automatic_restart_allowed": False,
                "automatic_kill_allowed": False,
                "auto_healing_mutation_allowed": False,
            }
        )
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "stale_writer_audit_status": "WARNING" if stale_writers else "PASS",
        "stale_writer_count": len(stale_writers),
        "stale_writers": stale_writers,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    STALE_WRITER_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    STALE_WRITER_AUDIT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_runtime_recovery_policy(now=None):
    now_ist = as_ist_datetime(now)
    policy = {
        "generated_at_ist": now_ist.isoformat(),
        "runtime_recovery_policy_status": "PASS",
        "policy_mode": "advisory_recommendation_only",
        "automatic_restart_allowed": False,
        "automatic_process_kill_allowed": False,
        "automatic_lock_delete_allowed": False,
        "automatic_broker_mutation_allowed": False,
        "automatic_telegram_mutation_allowed": False,
        "automatic_supabase_mutation_allowed": False,
        "safe_self_healing_classification": {
            "visibility_refresh": {
                "allowed": True,
                "mutation_scope": "write_advisory_status_json_only",
            },
            "daemon_restart": {
                "allowed": False,
                "requires_user_approval": True,
            },
            "process_kill": {
                "allowed": False,
                "requires_user_approval": True,
            },
            "lock_removal": {
                "allowed": False,
                "requires_user_approval": True,
            },
            "runtime_writer_recovery": {
                "allowed": False,
                "recommendation_only": True,
            },
        },
        "recommendation_matrix": {
            "stale_lock_only": "manual_review_then_user_approved_restart_or_lock_cleanup",
            "heartbeat_alive_but_stale": "manual_review_runtime_process_and_refresh_normal_heartbeat_writer",
            "daemon_stopped_but_heartbeat_alive": "reconcile_owner_before_any_restart",
            "secondary_runtime_source_stale": "refresh_normal_visibility_writer_path",
            "no_runtime_owner_visible": "manual_start_only_after_user_approval",
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    RUNTIME_RECOVERY_POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_RECOVERY_POLICY_PATH.write_text(json.dumps(policy, indent=2, sort_keys=True), encoding="utf-8")
    return policy


def build_runtime_reconciliation_status(now=None, sources=None):
    now_ist = as_ist_datetime(now)
    sources = sources or _collect_sources(now_ist)
    reconciliation = _reconcile_owner(sources)
    inconsistencies = _detect_inconsistencies(sources)
    if inconsistencies and reconciliation["reconciliation_status"] == "PASS":
        reconciliation_status = "WARNING"
    else:
        reconciliation_status = reconciliation["reconciliation_status"]
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "runtime_reconciliation_status": reconciliation_status,
        "deterministic_runtime_owner": reconciliation["deterministic_runtime_owner"],
        "authoritative_pid": reconciliation.get("authoritative_pid"),
        "pid_reconciliation": reconciliation.get("pid_reconciliation") or {},
        "owner_confidence": reconciliation.get("owner_confidence"),
        "reconciliation_reason": reconciliation["reconciliation_reason"],
        "ownership_candidates": reconciliation["ownership_candidates"],
        "heartbeat_daemon_inconsistencies": inconsistencies,
        "stale_pid_flags": (reconciliation.get("pid_reconciliation") or {}).get("stale_pid_flags") or [],
        "ghost_pid_flags": (reconciliation.get("pid_reconciliation") or {}).get("ghost_pid_flags") or [],
        "remaining_contradictions": inconsistencies,
        "runtime_ownership_deterministic": True,
        "restart_recommended": False,
        "kill_recommended": False,
        "auto_healing_mutation_allowed": False,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    RUNTIME_RECONCILIATION_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_RECONCILIATION_STATUS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_titan_runtime_watchdog(now=None):
    now_ist = as_ist_datetime(now)
    sources = _collect_sources(now_ist)
    stale_audit = build_stale_writer_audit(now=now_ist, sources=sources)
    recovery_policy = build_runtime_recovery_policy(now=now_ist)
    reconciliation = build_runtime_reconciliation_status(now=now_ist, sources=sources)
    inconsistencies = reconciliation.get("heartbeat_daemon_inconsistencies") or []
    status = "PASS"
    if reconciliation.get("runtime_reconciliation_status") == "FAIL":
        status = "FAIL"
    elif stale_audit.get("stale_writer_count") or inconsistencies:
        status = "WARNING"
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "watchdog_status": status,
        "watchdog_mode": "visibility_only_advisory",
        "runtime_sources": sources,
        "runtime_owner": reconciliation.get("deterministic_runtime_owner"),
        "authoritative_pid": reconciliation.get("authoritative_pid"),
        "pid_reconciliation": reconciliation.get("pid_reconciliation") or {},
        "owner_confidence": reconciliation.get("owner_confidence"),
        "stale_pid_flags": reconciliation.get("stale_pid_flags") or [],
        "ghost_pid_flags": reconciliation.get("ghost_pid_flags") or [],
        "remaining_contradictions": inconsistencies,
        "runtime_ownership_deterministic": reconciliation.get("runtime_ownership_deterministic"),
        "stale_writer_count": stale_audit.get("stale_writer_count"),
        "heartbeat_daemon_inconsistencies": inconsistencies,
        "recovery_policy_path": _path_key(RUNTIME_RECOVERY_POLICY_PATH),
        "stale_writer_audit_path": _path_key(STALE_WRITER_AUDIT_PATH),
        "runtime_reconciliation_status_path": _path_key(RUNTIME_RECONCILIATION_STATUS_PATH),
        "automatic_restart_allowed": recovery_policy.get("automatic_restart_allowed"),
        "automatic_process_kill_allowed": recovery_policy.get("automatic_process_kill_allowed"),
        "auto_healing_mutation_allowed": False,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    TITAN_RUNTIME_WATCHDOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    TITAN_RUNTIME_WATCHDOG_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def run_batch8_runtime_watchdog(now=None):
    watchdog = build_titan_runtime_watchdog(now=now)
    return {
        "generated_at_ist": watchdog.get("generated_at_ist"),
        "batch": "BATCH_8_RUNTIME_SELF_HEALING_WATCHDOG_HARDENING",
        "status": watchdog.get("watchdog_status"),
        "artifacts": {
            "titan_runtime_watchdog": _path_key(TITAN_RUNTIME_WATCHDOG_PATH),
            "runtime_recovery_policy": _path_key(RUNTIME_RECOVERY_POLICY_PATH),
            "stale_writer_audit": _path_key(STALE_WRITER_AUDIT_PATH),
            "runtime_reconciliation_status": _path_key(RUNTIME_RECONCILIATION_STATUS_PATH),
        },
        "summary": {
            "runtime_owner": watchdog.get("runtime_owner"),
            "authoritative_pid": watchdog.get("authoritative_pid"),
            "owner_confidence": watchdog.get("owner_confidence"),
            "runtime_ownership_deterministic": watchdog.get("runtime_ownership_deterministic"),
            "stale_writer_count": watchdog.get("stale_writer_count"),
            "heartbeat_daemon_inconsistencies": watchdog.get("heartbeat_daemon_inconsistencies"),
            "automatic_restart_allowed": watchdog.get("automatic_restart_allowed"),
            "automatic_process_kill_allowed": watchdog.get("automatic_process_kill_allowed"),
            "auto_healing_mutation_allowed": watchdog.get("auto_healing_mutation_allowed"),
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }


if __name__ == "__main__":
    print(json.dumps(run_batch8_runtime_watchdog(), indent=2, sort_keys=True))
