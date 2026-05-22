import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


RUNTIME_DIR = Path("data") / "runtime"
RUNTIME_RESILIENCE_STATUS_PATH = RUNTIME_DIR / "runtime_resilience_status.json"
OFFICIAL_RUNTIME_PATH = "titan_daemon.py"
STALE_PACKET_SECONDS = 24 * 60 * 60
WORKER_STUCK_GRACE_SECONDS = 60

DAEMON_HEALTH_PATH = RUNTIME_DIR / "daemon_health.json"
WORKER_HEALTH_PATH = RUNTIME_DIR / "worker_health.json"
PYRAMID_CHAIN_STATUS_PATH = RUNTIME_DIR / "pyramid_chain_status.json"
PYRAMID_GOVERNANCE_STATUS_PATH = RUNTIME_DIR / "pyramid_governance_status.json"
LOAD_CONTROL_STATUS_PATH = RUNTIME_DIR / "intelligence_load_control_status.json"

CRITICAL_PACKET_PATHS = {
    RUNTIME_DIR / "daemon_health.json",
    RUNTIME_DIR / "worker_health.json",
    RUNTIME_DIR / "titan_heartbeat.json",
    RUNTIME_DIR / "titan_runtime_status.json",
    RUNTIME_DIR / "scanner_status.json",
    RUNTIME_DIR / "master_brain_status.json",
    RUNTIME_DIR / "ohlc_refresh_status.json",
    Path("data") / "runtime" / "pyramid_chain_status.json",
    Path("data") / "runtime" / "pyramid_governance_status.json",
    Path("data") / "execution_safety" / "latest_execution_safety_report.json",
    Path("data") / "report_vault" / "latest_aggregated_packet.json",
    Path("data") / "consciousness_core" / "consciousness_context.json",
}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


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


def read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {"status": "CORRUPT"}
    except Exception as exc:
        return {"status": "CORRUPT", "error": str(exc)}


def _file_age(path):
    path = Path(path)
    if not path.exists():
        return None, None
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - modified_at).total_seconds()), modified_at.isoformat()


def _parse_iso(value):
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _last_good_output_path(task):
    path = RUNTIME_DIR / f"{task}_status.json"
    return str(path).replace("\\", "/") if path.exists() else None


def build_worker_health_summary(worker_health=None):
    worker_health = worker_health if isinstance(worker_health, dict) else read_json_safe(WORKER_HEALTH_PATH)
    worker_health = worker_health if isinstance(worker_health, dict) else {}
    now = datetime.now(timezone.utc)
    workers = {}
    degraded_components = []
    last_good_outputs_used = []
    recovery_actions = []

    for task, item in sorted(worker_health.items()):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "UNKNOWN").upper()
        active_started_at = _parse_iso(item.get("active_run_started_at") or item.get("last_started_at"))
        timeout_seconds = int(item.get("active_timeout_seconds") or item.get("last_timeout_seconds") or 0)
        stuck = False
        active_age_seconds = None
        if status == "RUNNING" and active_started_at is not None and timeout_seconds > 0:
            active_age_seconds = max(0.0, (now - active_started_at).total_seconds())
            stuck = active_age_seconds > timeout_seconds + WORKER_STUCK_GRACE_SECONDS

        effective_status = "DEGRADED" if stuck else status
        last_good_output_path = item.get("last_good_output_path") or _last_good_output_path(task)
        last_good_output_used = bool(item.get("last_good_output_used")) or (
            effective_status in {"DEGRADED", "TIMEOUT", "ERROR"} and bool(last_good_output_path)
        )

        workers[task] = {
            "status": effective_status,
            "raw_status": status,
            "stuck": stuck,
            "active_age_seconds": None if active_age_seconds is None else round(active_age_seconds, 3),
            "last_finished_at": item.get("last_finished_at"),
            "last_error": item.get("last_error"),
            "retry_backoff_seconds": item.get("retry_backoff_seconds", 0),
            "last_good_output_path": last_good_output_path,
            "last_good_output_used": last_good_output_used,
        }
        if effective_status in {"DEGRADED", "TIMEOUT", "ERROR"}:
            degraded_components.append(task)
        if last_good_output_used:
            last_good_outputs_used.append({"task": task, "path": last_good_output_path})
        if stuck:
            recovery_actions.append(
                {
                    "component": task,
                    "action": "marked_degraded_stuck_worker",
                    "last_good_output_path": last_good_output_path,
                }
            )

    return {
        "total_workers": len(workers),
        "degraded_count": len(set(degraded_components)),
        "degraded_components": sorted(set(degraded_components)),
        "workers": workers,
        "recovery_actions": recovery_actions,
        "last_good_outputs_used": last_good_outputs_used,
    }


def build_stale_packet_summary(paths=None, fresh_seconds=STALE_PACKET_SECONDS):
    paths = paths or sorted(CRITICAL_PACKET_PATHS, key=lambda item: str(item))
    packets = []
    stale_packets = []
    degraded_components = []
    for path in paths:
        path = Path(path)
        age_seconds, modified_at = _file_age(path)
        available = age_seconds is not None
        stale = (not available) or age_seconds > fresh_seconds
        status = "MISSING" if not available else ("STALE" if stale else "OK")
        item = {
            "path": str(path).replace("\\", "/"),
            "critical": path in CRITICAL_PACKET_PATHS,
            "available": available,
            "status": status,
            "age_seconds": None if age_seconds is None else round(age_seconds, 3),
            "modified_at_utc": modified_at,
            "fresh_seconds": fresh_seconds,
            "action": "marked_degraded_no_delete" if stale else "none",
        }
        packets.append(item)
        if stale:
            stale_packets.append(item)
            degraded_components.append(str(path).replace("\\", "/"))

    return {
        "total_packets_checked": len(packets),
        "stale_count": len(stale_packets),
        "stale_packets": stale_packets,
        "packets": packets,
        "degraded_components": degraded_components,
        "cleanup_policy": "mark_stale_or_degraded_only_no_deletes",
    }


def build_daemon_status(daemon_health=None):
    daemon_health = daemon_health if isinstance(daemon_health, dict) else read_json_safe(DAEMON_HEALTH_PATH)
    daemon_health = daemon_health if isinstance(daemon_health, dict) else {}
    status = str(daemon_health.get("status") or "UNKNOWN").upper()
    return {
        "status": status,
        "pid": daemon_health.get("pid"),
        "mode": daemon_health.get("mode"),
        "ticks_completed": daemon_health.get("ticks_completed"),
        "last_dispatch_count": daemon_health.get("last_dispatch_count"),
        "timestamp_ist": daemon_health.get("timestamp_ist"),
        "official_runtime_path": OFFICIAL_RUNTIME_PATH,
        "duplicate_prevention": daemon_health.get("duplicate_prevention") or "runtime_lock:titan_daemon",
        "shutdown_marker": daemon_health.get("shutdown_marker"),
        "restart_marker": daemon_health.get("restart_marker"),
    }


def build_runtime_resilience_status():
    daemon_status = build_daemon_status()
    worker_summary = build_worker_health_summary()
    stale_summary = build_stale_packet_summary()
    degraded_components = sorted(
        set(worker_summary["degraded_components"])
        | set(stale_summary["degraded_components"])
    )
    recovery_actions = []
    recovery_actions.extend(worker_summary["recovery_actions"])
    recovery_actions.extend(
        {
            "component": packet["path"],
            "action": packet["action"],
            "status": packet["status"],
        }
        for packet in stale_summary["stale_packets"]
    )

    payload = {
        "generated_at": utc_now_iso(),
        "status": "DEGRADED" if degraded_components else "OK",
        "official_runtime_path": OFFICIAL_RUNTIME_PATH,
        "daemon": daemon_status,
        "worker_health_summary": worker_summary,
        "stale_packet_summary": stale_summary,
        "recovery_actions_taken": recovery_actions,
        "degraded_components": degraded_components,
        "last_good_outputs_used": worker_summary["last_good_outputs_used"],
        "safety_scope": {
            "advisory_only": True,
            "broker_orders": False,
            "telegram_changes": False,
            "scoring_mutation": False,
            "strategy_weight_mutation": False,
            "live_memory_mixed_with_external_simulated_memory": False,
        },
    }
    return payload


def write_runtime_resilience_status(path=RUNTIME_RESILIENCE_STATUS_PATH):
    payload = build_runtime_resilience_status()
    _atomic_write_json(path, payload)
    return payload


def update_existing_status_outputs(resilience_status=None):
    resilience_status = resilience_status if isinstance(resilience_status, dict) else write_runtime_resilience_status()
    marker = {
        "official_runtime_path": OFFICIAL_RUNTIME_PATH,
        "runtime_resilience_status": {
            "status": resilience_status.get("status"),
            "degraded_components": resilience_status.get("degraded_components", []),
            "stale_packet_count": resilience_status.get("stale_packet_summary", {}).get("stale_count"),
            "worker_degraded_count": resilience_status.get("worker_health_summary", {}).get("degraded_count"),
            "last_good_outputs_used": resilience_status.get("last_good_outputs_used", []),
        },
    }
    for path in (
        PYRAMID_CHAIN_STATUS_PATH,
        PYRAMID_GOVERNANCE_STATUS_PATH,
        LOAD_CONTROL_STATUS_PATH,
    ):
        payload = read_json_safe(path)
        if not isinstance(payload, dict):
            continue
        payload.update(marker)
        _atomic_write_json(path, payload)
    return marker


if __name__ == "__main__":
    status = write_runtime_resilience_status()
    update_existing_status_outputs(status)
    print(json.dumps(status, indent=2, sort_keys=True))
