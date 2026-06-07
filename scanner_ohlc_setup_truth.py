import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from utils.market_hours import IST, as_ist_datetime, is_trade_window, market_state


RUNTIME_DIR = Path("data") / "runtime"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
OHLC_HEALTH_PATH = RUNTIME_DIR / "ohlc_health.json"
SETUP_ENGINE_STATUS_PATH = RUNTIME_DIR / "setup_engine_status.json"
FINAL_VALIDATED_SETUPS_PATH = RUNTIME_DIR / "final_validated_setups.json"
SCANNER_OHLC_SETUP_TRUTH_PATH = RUNTIME_DIR / "scanner_ohlc_setup_truth.json"

RUNTIME_TTL_SECONDS = 15 * 60
OHLC_TTL_SECONDS = 24 * 60 * 60
LIVE_SCANNER_STATUSES = {"LIVE", "SCAN_LIVE", "SCAN_ONLY_COMPLETE", "FULL_RUNTIME_PIPELINE_COMPLETE", "COMPLETED", "OK"}
ACCEPTABLE_SCANNER_STATUSES = {"SCAN_LIVE", "SCAN_IDLE", "SCAN_WAITING_FOR_MARKET"}
ACCEPTABLE_SETUP_STATUSES = {"REAL_SETUP_ENGINE_CONNECTED", "DIAGNOSTIC_SKIPPED"}
STOPPED_STATUSES = {"STOPPED", "INACTIVE", "SHUTDOWN", "EXITED"}


def read_json_safe(path):
    try:
        path = Path(path)
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
        "generated_at",
        "generated_at_ist",
        "timestamp_ist",
        "scanner_timestamp",
        "scan_finished_at_ist",
        "updated_at",
        "timestamp",
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


def _status_text(payload):
    return str((payload or {}).get("status") or "").strip().upper()


def _base_status(component, path, payload, now, ttl_seconds, timestamp_keys=None):
    timestamp = payload_timestamp(payload, timestamp_keys) or file_timestamp(path)
    age = age_seconds(timestamp, now)
    exists = Path(path).exists()
    return {
        "component": component,
        "status": "UNKNOWN",
        "source_file": str(path).replace("\\", "/"),
        "source_timestamp": timestamp.isoformat() if timestamp else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "ttl_seconds": ttl_seconds,
        "reason": "unclassified",
        "restart_blocker": False,
        "source_exists": exists,
        "source_status": payload.get("status") if isinstance(payload, dict) else None,
    }


def _is_stale(record):
    return (not record["source_exists"]) or record["age_seconds"] is None or record["age_seconds"] > record["ttl_seconds"]


def _final_setups_count(payload):
    if not isinstance(payload, dict):
        return None
    setups = payload.get("setups")
    if isinstance(setups, list):
        return len(setups)
    try:
        value = payload.get("validated_setup_count")
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def classify_ohlc_status(path=OHLC_HEALTH_PATH, now=None):
    now_ist = as_ist_datetime(now).astimezone(IST)
    payload = read_json_safe(path)
    record = _base_status("ohlc_health", path, payload, now_ist, OHLC_TTL_SECONDS)
    symbol_results = payload.get("symbol_results") if isinstance(payload.get("symbol_results"), list) else []
    requested = int(payload.get("requested_count") or len(symbol_results) or 0) if isinstance(payload, dict) else 0
    fresh_count = int(payload.get("valid_count") or 0) if isinstance(payload, dict) else 0
    stale_count = 0
    missing_count = 0
    oldest_age = 0.0
    for item in symbol_results:
        freshness = item.get("freshness") if isinstance(item, dict) else {}
        if not isinstance(freshness, dict):
            continue
        age_hours = freshness.get("age_hours")
        try:
            age = float(age_hours) * 3600
            oldest_age = max(oldest_age, age)
            if freshness.get("status") != "PASS":
                stale_count += 1
        except (TypeError, ValueError):
            missing_count += 1
    if requested and not symbol_results:
        missing_count = int(payload.get("invalid_count") or 0)
    if not record["source_exists"]:
        status, reason = "UNKNOWN", "ohlc_health_missing"
    elif payload.get("_read_error"):
        status, reason = "UNKNOWN", f"ohlc_health_read_error:{payload.get('_read_error')}"
    elif _is_stale(record):
        status, reason = "STALE", "ohlc_health_timestamp_stale_or_missing"
    else:
        source_status = _status_text(payload)
        if source_status in {"PASS", "LIVE", "OK", "VALID_MARKET_CACHE"} or payload.get("ohlc_status") == "VALID_MARKET_CACHE":
            status, reason = "LIVE", payload.get("reason") or payload.get("ohlc_status") or "ohlc_health_fresh_pass"
        elif source_status == "DEGRADED":
            status, reason = "DEGRADED", payload.get("reason") or "ohlc_health_degraded"
        elif source_status in {"FAIL", "FAILED", "ERROR"}:
            status = "STALE" if str(payload.get("reason") or "").startswith("OHLC_INVALID_SYMBOLS") else "DEGRADED"
            reason = payload.get("reason") or "ohlc_health_failed"
        else:
            status, reason = "UNKNOWN", "ohlc_health_status_unknown"
    record.update(
        status=status,
        reason=reason,
        restart_blocker=status != "LIVE",
        generated_at=payload.get("generated_at") or payload.get("timestamp_ist"),
        source=payload.get("source") or "data/runtime/ohlc_health.json",
        symbols_checked=requested,
        fresh_count=fresh_count,
        stale_count=stale_count,
        missing_count=missing_count,
        oldest_age_seconds=round(oldest_age, 3) if oldest_age else record["age_seconds"],
    )
    return record


def classify_scanner_status(path=SCANNER_STATUS_PATH, final_setups_path=FINAL_VALIDATED_SETUPS_PATH, now=None):
    now_ist = as_ist_datetime(now).astimezone(IST)
    payload = read_json_safe(path)
    final_payload = read_json_safe(final_setups_path)
    record = _base_status(
        "scanner",
        path,
        payload,
        now_ist,
        RUNTIME_TTL_SECONDS,
        timestamp_keys=("generated_at", "timestamp_ist", "scanner_timestamp", "scan_finished_at_ist"),
    )
    final_count = _final_setups_count(final_payload)
    source_status = _status_text(payload)
    if not record["source_exists"]:
        status, reason = "UNKNOWN", "scanner_status_missing"
    elif payload.get("_read_error"):
        status, reason = "UNKNOWN", f"scanner_status_read_error:{payload.get('_read_error')}"
    elif _is_stale(record):
        scanned = int(payload.get("stocks_checked") or payload.get("symbols_scanned") or 0)
        idle_statuses = {
            "FULL_RUNTIME_PIPELINE_COMPLETE",
            "SCAN_ONLY_COMPLETE",
            "COMPLETED",
            "SCAN_LIVE",
            "LIVE",
            "WAITING_FOR_MARKET",
            "MARKET_CLOSED",
            "OFF_HOURS",
        }
        if not is_trade_window(now_ist) and scanned == 0 and source_status in idle_statuses:
            status, reason = "SCAN_IDLE", "stale_scanner_timestamp_accepted_as_idle_outside_trade_window"
        else:
            status, reason = "STALE", "scanner_status_timestamp_stale_or_missing"
    elif source_status in STOPPED_STATUSES:
        status, reason = "SCAN_STOPPED", "scanner_status_stopped"
    elif not is_trade_window(now_ist) and source_status in {"WAITING_FOR_MARKET", "MARKET_CLOSED", "OFF_HOURS"}:
        status, reason = "SCAN_WAITING_FOR_MARKET", "scanner_waiting_for_market_session"
    elif not is_trade_window(now_ist) and int(payload.get("stocks_checked") or payload.get("symbols_scanned") or 0) == 0:
        status, reason = "SCAN_IDLE", "scanner_idle_outside_trade_window"
    elif payload.get("errors") or "ERROR" in source_status or "FAIL" in source_status:
        status, reason = "DEGRADED", payload.get("reason") or payload.get("fallback_reason") or "scanner_error_or_degraded"
    elif payload.get("ohlc_fallback_required") or payload.get("scan_only") or payload.get("fallback_reason"):
        status, reason = "DEGRADED", payload.get("fallback_reason") or "scanner_fallback_or_scan_only"
    elif source_status in LIVE_SCANNER_STATUSES or payload.get("real_scanner_called"):
        status, reason = "SCAN_LIVE", "fresh_scanner_status"
    else:
        status, reason = "UNKNOWN", "scanner_status_unknown"
    record.update(
        status=status,
        reason=reason,
        restart_blocker=status not in ACCEPTABLE_SCANNER_STATUSES,
        generated_at=payload.get("generated_at") or payload.get("timestamp_ist"),
        scan_mode=payload.get("scan_mode") or payload.get("mode"),
        market_session=payload.get("market_session") or ("TRADE_WINDOW" if is_trade_window(now_ist) else "OFF_HOURS"),
        symbols_scanned=int(payload.get("symbols_scanned") or payload.get("stocks_checked") or 0) if isinstance(payload, dict) else 0,
        passed_count=int(payload.get("passed_count") or payload.get("passed_setups") or payload.get("final_passed") or 0) if isinstance(payload, dict) else 0,
        final_setups_count=final_count,
        source_files_used=payload.get("source_files_used") or ["data/runtime/scanner_status.json", "data/runtime/final_validated_setups.json"],
        final_setups_file=str(final_setups_path).replace("\\", "/"),
    )
    return record


def classify_setup_engine_status(path=SETUP_ENGINE_STATUS_PATH, final_setups_path=FINAL_VALIDATED_SETUPS_PATH, now=None):
    now_ist = as_ist_datetime(now).astimezone(IST)
    payload = read_json_safe(path)
    final_payload = read_json_safe(final_setups_path)
    record = _base_status("setup_engine", path, payload, now_ist, RUNTIME_TTL_SECONDS)
    source_status = _status_text(payload)
    real_called = bool(payload.get("real_setup_engine_called") or payload.get("actual_setup_generation"))
    marker_only = bool(payload.get("marker_only") is True or "MARKER" in source_status)
    final_count = _final_setups_count(final_payload)
    final_timestamp = payload_timestamp(final_payload)
    final_age = age_seconds(final_timestamp, now_ist)
    final_fresh = bool(final_age is not None and final_age <= RUNTIME_TTL_SECONDS)
    if not record["source_exists"]:
        status, reason = "UNKNOWN", "setup_engine_status_missing"
    elif payload.get("_read_error"):
        status, reason = "UNKNOWN", f"setup_engine_status_read_error:{payload.get('_read_error')}"
    elif _is_stale(record):
        if source_status == "DIAGNOSTIC_SKIPPED":
            status, reason = "DIAGNOSTIC_SKIPPED", "stale_setup_skip_marker_accepted_outside_trade_window"
        else:
            status, reason = "STALE", "setup_engine_timestamp_stale_or_missing"
    elif source_status == "DIAGNOSTIC_SKIPPED":
        status, reason = "DIAGNOSTIC_SKIPPED", payload.get("reason") or "setup_diagnostic_intentionally_skipped"
    elif marker_only and not real_called:
        status, reason = "MARKER_ONLY", "marker_only_status_not_runtime_liveness"
    elif real_called and final_fresh and final_count is not None:
        status, reason = "REAL_SETUP_ENGINE_CONNECTED", "fresh_real_setup_generation_proof"
    elif real_called and not final_fresh:
        status, reason = "DISCONNECTED", "real_setup_generation_without_fresh_final_setups"
    else:
        status, reason = "UNKNOWN", "setup_engine_real_generation_not_proven"
    record.update(
        status=status,
        reason=reason,
        restart_blocker=status not in ACCEPTABLE_SETUP_STATUSES,
        generated_at=payload.get("generated_at") or payload.get("timestamp_ist"),
        real_setup_engine_called=real_called,
        marker_only=marker_only,
        final_setups_file=str(final_setups_path).replace("\\", "/"),
        final_setups_count=final_count,
        final_setups_source_timestamp=final_timestamp.isoformat() if final_timestamp else None,
        final_setups_age_seconds=round(final_age, 3) if final_age is not None else None,
    )
    return record


def build_scanner_ohlc_setup_truth(
    *,
    scanner_path=SCANNER_STATUS_PATH,
    ohlc_path=OHLC_HEALTH_PATH,
    setup_path=SETUP_ENGINE_STATUS_PATH,
    final_setups_path=FINAL_VALIDATED_SETUPS_PATH,
    output_path=SCANNER_OHLC_SETUP_TRUTH_PATH,
    now=None,
    write=True,
):
    now_ist = as_ist_datetime(now).astimezone(IST)
    ohlc_status = classify_ohlc_status(ohlc_path, now_ist)
    scanner_status = classify_scanner_status(scanner_path, final_setups_path, now_ist)
    setup_status = classify_setup_engine_status(setup_path, final_setups_path, now_ist)
    final_payload = read_json_safe(final_setups_path)
    final_count = _final_setups_count(final_payload)
    paths = {
        "scanner_status": scanner_path,
        "ohlc_health": ohlc_path,
        "setup_engine_status": setup_path,
        "final_validated_setups": final_setups_path,
    }
    status_records = {
        "scanner_status": scanner_status,
        "ohlc_status": ohlc_status,
        "setup_engine_status": setup_status,
    }
    stale_files = [
        record["source_file"]
        for record in status_records.values()
        if record.get("status") == "STALE"
    ]
    missing_files = [
        str(path).replace("\\", "/")
        for path in paths.values()
        if not Path(path).exists()
    ]
    marker_only_files = [
        setup_status["source_file"]
    ] if setup_status.get("status") == "MARKER_ONLY" else []
    restart_blockers = []
    if scanner_status.get("status") not in ACCEPTABLE_SCANNER_STATUSES:
        restart_blockers.append(f"scanner {scanner_status.get('status')}")
    if ohlc_status.get("status") != "LIVE":
        restart_blockers.append(f"OHLC {ohlc_status.get('status')}")
    if setup_status.get("status") not in ACCEPTABLE_SETUP_STATUSES:
        restart_blockers.append(f"setup {setup_status.get('status')}")
    if final_count is None:
        restart_blockers.append("final setups UNKNOWN")
    remaining_unknowns = [
        name
        for name, record in status_records.items()
        if record.get("status") == "UNKNOWN"
    ]
    payload = {
        "generated_at": now_ist.isoformat(),
        "ohlc_status": ohlc_status,
        "scanner_status": scanner_status,
        "setup_engine_status": setup_status,
        "final_setups_file": str(final_setups_path).replace("\\", "/"),
        "final_setups_count": final_count,
        "stale_files": stale_files,
        "missing_files": missing_files,
        "marker_only_files": marker_only_files,
        "restart_blocker": bool(restart_blockers),
        "restart_blockers": restart_blockers,
        "remaining_unknowns": remaining_unknowns,
        "safety": {
            "broker_order_calls": False,
            "live_trading": False,
            "daemon_restart": False,
            "journal_mutation": False,
            "diagnostic_status_write_only": bool(write),
        },
        "market_state": market_state(now_ist),
    }
    if write:
        _atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(build_scanner_ohlc_setup_truth(write=True), indent=2, sort_keys=True))
