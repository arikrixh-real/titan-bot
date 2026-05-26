import json
from datetime import datetime, timezone
from pathlib import Path

from runtime_dependency_graph import SAFETY_FLAGS
from utils.market_hours import IST, as_ist_datetime, is_trade_window


RUNTIME_DIR = Path("data") / "runtime"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
SCANNER_FILTER_TRUTH_STATUS_PATH = RUNTIME_DIR / "scanner_filter_truth_status.json"
SCANNER_RUNTIME_HEARTBEAT_PATH = RUNTIME_DIR / "scanner_runtime_heartbeat.json"
SCANNER_PUBLICATION_HEALTH_PATH = RUNTIME_DIR / "scanner_publication_health.json"
SCANNER_SCHEDULER_STATUS_PATH = RUNTIME_DIR / "scanner_scheduler_status.json"
WORKER_HEALTH_PATH = RUNTIME_DIR / "worker_health.json"
FRESH_SECONDS = 15 * 60
CADENCE_DEGRADED_SECONDS = 12 * 60


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _parse_timestamp(value):
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _payload_timestamp(payload):
    for key in ("latest_publish_time", "scan_finished_at_ist", "timestamp_ist", "scanner_timestamp", "generated_at_ist", "timestamp"):
        parsed = _parse_timestamp(payload.get(key))
        if parsed:
            return parsed
    return None


def _age_seconds(timestamp, now_ist):
    if timestamp is None:
        return None
    return max(0.0, (now_ist - timestamp).total_seconds())


def _worker_scanner_active(worker_health, now_ist):
    scanner = worker_health.get("runtime_scanner") or worker_health.get("scanner") or {}
    if not isinstance(scanner, dict):
        return False
    timestamp = _payload_timestamp(scanner)
    age = _age_seconds(timestamp, now_ist)
    status = str(scanner.get("status") or "").upper()
    return bool(age is not None and age <= FRESH_SECONDS and status not in {"FAILED", "ERROR", "STOPPED", "STALE"})


def _scheduler_scanner_active(scheduler_status, now_ist):
    if not isinstance(scheduler_status, dict):
        return False
    timestamp = _payload_timestamp(scheduler_status)
    age = _age_seconds(timestamp, now_ist)
    return bool(
        scheduler_status.get("scheduler_active")
        and scheduler_status.get("scanner_invocation_enabled")
        and age is not None
        and age <= FRESH_SECONDS
    )


def run_scanner_publication_health_check(
    now=None,
    scanner_status_path=SCANNER_STATUS_PATH,
    scanner_truth_path=SCANNER_FILTER_TRUTH_STATUS_PATH,
    heartbeat_path=SCANNER_RUNTIME_HEARTBEAT_PATH,
    scheduler_status_path=SCANNER_SCHEDULER_STATUS_PATH,
    worker_health_path=WORKER_HEALTH_PATH,
    output_path=SCANNER_PUBLICATION_HEALTH_PATH,
):
    now_ist = as_ist_datetime(now)
    scanner = _read_json_safe(scanner_status_path)
    truth = _read_json_safe(scanner_truth_path)
    heartbeat = _read_json_safe(heartbeat_path)
    scheduler_status = _read_json_safe(scheduler_status_path)
    worker_health = _read_json_safe(worker_health_path)

    latest_scan_cycle_id = (
        scanner.get("scanner_cycle_id")
        or truth.get("authoritative_scan_cycle_id")
        or heartbeat.get("latest_cycle")
    )
    latest_scan_dt = _payload_timestamp(scanner) or _parse_timestamp(truth.get("authoritative_scan_timestamp"))
    latest_publish_dt = _payload_timestamp(heartbeat) or latest_scan_dt
    previous_publish_dt = _parse_timestamp(heartbeat.get("previous_publish_time"))
    scan_age = _age_seconds(latest_scan_dt, now_ist)
    publish_age = _age_seconds(latest_publish_dt, now_ist)
    publish_cadence = None
    if latest_publish_dt and previous_publish_dt:
        publish_cadence = max(0.0, (latest_publish_dt - previous_publish_dt).total_seconds())
    elif publish_age is not None:
        publish_cadence = publish_age

    market_hours_publish_expected = is_trade_window(now_ist)
    scanner_loop_active = bool(
        heartbeat.get("scanner_loop_health") in {"RUNNING", "ACTIVE", "PUBLISHING", "OK"}
        or _worker_scanner_active(worker_health, now_ist)
        or _scheduler_scanner_active(scheduler_status, now_ist)
        or (publish_age is not None and publish_age <= FRESH_SECONDS)
    )
    scanner_publish_active = bool(publish_age is not None and publish_age <= FRESH_SECONDS and heartbeat.get("publish_status") != "FAILED")
    publish_exception_detected = bool(heartbeat.get("last_publish_exception"))
    publish_stall_detected = bool(market_hours_publish_expected and (publish_age is None or publish_age > FRESH_SECONDS))
    stale_cycle_detected = bool(market_hours_publish_expected and (scan_age is None or scan_age > FRESH_SECONDS))
    cadence_degraded = bool(
        market_hours_publish_expected
        and publish_cadence is not None
        and publish_cadence > CADENCE_DEGRADED_SECONDS
    )
    zero_overwrite = bool(truth.get("zero_overwrite_detected"))
    scan_publish_skipped = bool(heartbeat.get("publish_status") == "SKIPPED")

    warnings = []
    if publish_exception_detected:
        warnings.append("publish_exception_detected")
    if publish_stall_detected:
        warnings.append("publish_stall_detected")
    if stale_cycle_detected:
        warnings.append("stale_cycle_detected")
    if cadence_degraded:
        warnings.append("publish_cadence_degradation")
    if zero_overwrite:
        warnings.append("invalid_zero_overwrite_detected")
    if scan_publish_skipped:
        warnings.append("scan_publish_skipped")
    if market_hours_publish_expected and not scanner_loop_active:
        warnings.append("scanner_loop_not_active")

    publish_health = "PASS"
    if publish_exception_detected:
        publish_health = "DEGRADED"
    if publish_stall_detected or stale_cycle_detected or scan_publish_skipped:
        publish_health = "STALE"
    if market_hours_publish_expected and not scanner and not heartbeat:
        publish_health = "UNAVAILABLE"

    runtime_scheduler_health = "ACTIVE" if scanner_loop_active else ("OFF_HOURS_IDLE" if not market_hours_publish_expected else "STALLED")
    if scheduler_status and scheduler_status.get("last_skip_reason") == "scanner_task_lock_active":
        runtime_scheduler_health = "LOCKED_BY_WORKER"
    overall_status = "PASS" if not warnings else "WARNING"
    if publish_health == "UNAVAILABLE":
        overall_status = "FAIL"

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": overall_status,
        "scanner_loop_active": scanner_loop_active,
        "scanner_publish_active": scanner_publish_active,
        "latest_scan_cycle_id": latest_scan_cycle_id,
        "latest_scan_timestamp": latest_scan_dt.isoformat() if latest_scan_dt else None,
        "scan_age_seconds": round(scan_age, 3) if scan_age is not None else None,
        "publish_cadence_seconds": round(publish_cadence, 3) if publish_cadence is not None else None,
        "scanner_writer_heartbeat": heartbeat,
        "publish_exception_detected": publish_exception_detected,
        "publish_stall_detected": publish_stall_detected,
        "stale_cycle_detected": stale_cycle_detected,
        "publish_health": publish_health,
        "runtime_scheduler_health": runtime_scheduler_health,
        "scanner_scheduler_status": scheduler_status,
        "market_hours_publish_expected": market_hours_publish_expected,
        "scan_write_race": bool(scanner.get("_read_error") or truth.get("_read_error")),
        "invalid_zero_overwrite": zero_overwrite,
        "scan_publish_skipped": scan_publish_skipped,
        "publish_cadence_degraded": cadence_degraded,
        "warnings": warnings,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    _write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run_scanner_publication_health_check(), indent=2, sort_keys=True))
