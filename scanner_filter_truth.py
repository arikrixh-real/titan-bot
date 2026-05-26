import json
from datetime import datetime, timezone
from pathlib import Path

from runtime_dependency_graph import SAFETY_FLAGS
from utils.market_hours import IST, as_ist_datetime, is_trade_window


RUNTIME_DIR = Path("data") / "runtime"
SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
SCANNER_PREVIOUS_SIGNATURE_PATH = RUNTIME_DIR / "scanner_previous_signature.json"
SCAN_SELECTION_STATE_PATH = Path("data") / "scan_selection_state.json"
SETUP_ENGINE_STATUS_PATH = RUNTIME_DIR / "setup_engine_status.json"
SIGNAL_PATH_DIAGNOSTICS_PATH = RUNTIME_DIR / "signal_path_diagnostics.json"
DASHBOARD_TRUTH_REGISTRY_PATH = RUNTIME_DIR / "dashboard_truth_registry.json"
TRADE_LIFECYCLE_HEALTH_PATH = RUNTIME_DIR / "trade_lifecycle_health.json"
SCANNER_FILTER_TRUTH_STATUS_PATH = RUNTIME_DIR / "scanner_filter_truth_status.json"
LIVE_SCANNER_SYNC_AUDIT_PATH = RUNTIME_DIR / "live_scanner_sync_audit.json"
MASTER_BRAIN_RUNTIME_HEALTH_PATH = RUNTIME_DIR / "master_brain_runtime_health.json"
SETUP_ENGINE_RUNTIME_HEALTH_PATH = RUNTIME_DIR / "setup_engine_runtime_health.json"
RUNTIME_FALLBACK_RESOLUTION_PATH = RUNTIME_DIR / "runtime_fallback_resolution.json"
SCANNER_PUBLICATION_HEALTH_PATH = RUNTIME_DIR / "scanner_publication_health.json"
FRESH_SECONDS = 15 * 60
BRIEF_REFRESH_GAP_SECONDS = 2 * 60
SCAN_COUNTER_KEYS = ("trend_passed", "momentum_passed", "structure_passed", "breakout_ready")


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
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _payload_timestamp(payload):
    for key in ("scan_finished_at_ist", "timestamp_ist", "generated_at_ist", "updated_at_ist", "timestamp"):
        parsed = _parse_timestamp(payload.get(key))
        if parsed:
            return parsed
    return None


def _age_seconds(timestamp, now_ist):
    if timestamp is None:
        return None
    return max(0.0, (now_ist - timestamp).total_seconds())


def _int_or_none(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _counter_from(payload, *keys):
    for key in keys:
        value = _int_or_none(payload.get(key))
        if value is not None:
            return value, key
    return None, None


def _latest_scan_diagnostics():
    diagnostics = _read_json_safe(SIGNAL_PATH_DIAGNOSTICS_PATH)
    latest = diagnostics.get("latest") if isinstance(diagnostics.get("latest"), dict) else {}
    counters = {}
    sources = {}
    stage_map = {
        "trend_passed": ("trend", "passed"),
        "momentum_passed": ("momentum", "passed"),
        "structure_passed": ("structure", "passed"),
        "breakout_ready": ("final", "breakout_ready"),
        "final_passed": ("final", "final_passed"),
        "alerts_this_scan": ("final", "alerts_sent"),
    }
    for counter, (section, field) in stage_map.items():
        source = latest.get(section) if isinstance(latest.get(section), dict) else {}
        value = _int_or_none(source.get(field))
        if value is not None:
            counters[counter] = value
            sources[counter] = f"signal_path_diagnostics.latest.{section}.{field}"
    stocks = _int_or_none(latest.get("stocks_checked"))
    if stocks is not None:
        counters["stocks_checked"] = stocks
        sources["stocks_checked"] = "signal_path_diagnostics.latest.stocks_checked"
    if latest.get("scan_cycle_id"):
        counters["scan_cycle_id"] = latest.get("scan_cycle_id")
    return counters, sources, latest


def _identical_counter_warning(counters):
    stage_values = [
        counters.get("trend_passed"),
        counters.get("momentum_passed"),
        counters.get("structure_passed"),
        counters.get("breakout_ready"),
    ]
    known = [value for value in stage_values if value is not None]
    if len(known) < 3:
        return False
    if len(set(known)) != 1:
        return False
    copied_value = known[0]
    return copied_value not in (0, counters.get("stocks_checked"))


def _counter_confidence(scanner, counters, stale_snapshot_warning, identical_counter_warning, final_passed_mismatch):
    fallback_mode = bool(scanner.get("scan_only") or scanner.get("fallback_reason") or scanner.get("ohlc_fallback_required"))
    missing = [name for name, value in counters.items() if name != "live_trades_count" and value is None]
    if stale_snapshot_warning or fallback_mode or missing:
        return "LOW"
    if identical_counter_warning or final_passed_mismatch:
        return "LOW"
    return "HIGH"


def _has_nonzero_scan_gates(counters):
    return any(_int_or_none(counters.get(key)) not in (None, 0) for key in SCAN_COUNTER_KEYS)


def _has_counter_payload(counters):
    if not isinstance(counters, dict):
        return False
    if _int_or_none(counters.get("stocks_checked")) is not None:
        return True
    return any(_int_or_none(counters.get(key)) is not None for key in SCAN_COUNTER_KEYS)


def _counter_snapshot(counters):
    return {key: counters.get(key) for key in ("stocks_checked", *SCAN_COUNTER_KEYS, "final_passed", "alerts_this_scan")}


def _previous_authoritative_snapshot(previous):
    if not isinstance(previous, dict):
        return None
    counters = previous.get("authoritative_counters") if isinstance(previous.get("authoritative_counters"), dict) else previous.get("counters")
    if not _has_counter_payload(counters):
        return None
    timestamp = previous.get("authoritative_scan_timestamp") or previous.get("scanner_timestamp")
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return None
    return {
        "counters": dict(counters),
        "timestamp": parsed,
        "scan_cycle_id": previous.get("authoritative_scan_cycle_id") or previous.get("scan_cycle_id"),
        "scanner_publication_health": previous.get("scanner_publication_health"),
    }


def _build_live_scanner_sync_audit(
    *,
    now_ist,
    scanner,
    scanner_timestamp_dt,
    scanner_age,
    scan_cycle_id,
    previous_truth,
    counters,
    dashboard_truth_status,
    fallback_resolution,
    off_hours,
    stale_snapshot_warning,
    frozen_counter_warning,
    zero_overwrite,
    atomic_publish_race,
    dashboard_snapshot_age,
    scanner_publication_health,
    dashboard_scan_sync_status,
):
    previous_cycle = previous_truth.get("authoritative_scan_cycle_id") or previous_truth.get("scan_cycle_id")
    previous_timestamp = _parse_timestamp(previous_truth.get("authoritative_scan_timestamp") or previous_truth.get("scanner_timestamp"))
    timestamp_drift = None
    if scanner_timestamp_dt and previous_timestamp:
        timestamp_drift = abs((scanner_timestamp_dt - previous_timestamp).total_seconds())
    audit = {
        "generated_at_ist": now_ist.isoformat(),
        "market_hours": not off_hours,
        "scanner_status_present": bool(scanner),
        "scanner_status_timestamp": scanner_timestamp_dt.isoformat() if scanner_timestamp_dt else None,
        "scanner_status_age_seconds": round(scanner_age, 3) if scanner_age is not None else None,
        "scan_cycle_id": scan_cycle_id,
        "previous_authoritative_scan_cycle_id": previous_cycle,
        "scanner_counters": _counter_snapshot(counters),
        "stale_scan_publication": bool(stale_snapshot_warning and not off_hours),
        "frozen_scan_cycle_id": bool(previous_cycle and previous_cycle == scan_cycle_id and stale_snapshot_warning),
        "zero_overwrite": bool(zero_overwrite),
        "stale_dashboard_snapshot": bool(dashboard_truth_status == "WARNING"),
        "fallback_override_during_market_hours": bool((not off_hours) and fallback_resolution.get("fallback_active")),
        "atomic_publish_race": bool(atomic_publish_race),
        "scanner_dashboard_timestamp_drift_seconds": round(timestamp_drift, 3) if timestamp_drift is not None else None,
        "dashboard_scan_snapshot_age": dashboard_snapshot_age,
        "dashboard_scan_sync_status": dashboard_scan_sync_status,
        "scanner_publication_health": scanner_publication_health,
        "detected_conditions": {
            "stale_scan_publication": bool(stale_snapshot_warning and not off_hours),
            "frozen_scan_cycle_id": bool(frozen_counter_warning),
            "zero_overwrite": bool(zero_overwrite),
            "stale_dashboard_snapshot": bool(dashboard_truth_status == "WARNING"),
            "fallback_override_during_market_hours": bool((not off_hours) and fallback_resolution.get("fallback_active")),
            "atomic_publish_race": bool(atomic_publish_race),
            "scanner_dashboard_timestamp_drift": bool(timestamp_drift is not None and timestamp_drift > FRESH_SECONDS),
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    _write_json(LIVE_SCANNER_SYNC_AUDIT_PATH, audit)
    return audit


def _reconciled_counter_confidence(confidence, fallback_resolution, master_health, setup_health, stale_snapshot_warning):
    truthfulness = str(fallback_resolution.get("fallback_truthfulness") or "").upper()
    resolver_confidence = str(fallback_resolution.get("scanner_confidence") or "").upper()
    master_state = str(master_health.get("master_brain_runtime_health") or "").upper()
    setup_state = str(setup_health.get("setup_runtime_health") or "").upper()

    if truthfulness == "OFF_HOURS_RESEARCH_STANDBY":
        return "MEDIUM"
    if truthfulness in {"ENGINE_UNAVAILABLE", "DATA_DEGRADED", "REAL"} and fallback_resolution.get("fallback_active"):
        return "LOW"
    if resolver_confidence in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}:
        if confidence == "LOW" and resolver_confidence in {"HIGH", "MEDIUM"}:
            return "MEDIUM" if stale_snapshot_warning else resolver_confidence
        return resolver_confidence if confidence == "UNKNOWN" else confidence
    if confidence == "LOW" and master_state == "ACTIVE" and setup_state == "ACTIVE":
        return "MEDIUM" if stale_snapshot_warning else "HIGH"
    return confidence


def build_scanner_filter_truth_status(
    now=None,
    scanner_status_path=SCANNER_STATUS_PATH,
    scan_selection_state_path=SCAN_SELECTION_STATE_PATH,
    setup_engine_status_path=SETUP_ENGINE_STATUS_PATH,
    output_path=SCANNER_FILTER_TRUTH_STATUS_PATH,
):
    now_ist = as_ist_datetime(now)
    scanner = _read_json_safe(scanner_status_path)
    selection = _read_json_safe(scan_selection_state_path)
    setup = _read_json_safe(setup_engine_status_path)
    dashboard_truth = _read_json_safe(DASHBOARD_TRUTH_REGISTRY_PATH)
    lifecycle = _read_json_safe(TRADE_LIFECYCLE_HEALTH_PATH)
    master_runtime_health = _read_json_safe(MASTER_BRAIN_RUNTIME_HEALTH_PATH)
    setup_runtime_health = _read_json_safe(SETUP_ENGINE_RUNTIME_HEALTH_PATH)
    fallback_resolution = _read_json_safe(RUNTIME_FALLBACK_RESOLUTION_PATH)
    scanner_publication = _read_json_safe(SCANNER_PUBLICATION_HEALTH_PATH)
    previous_truth = _read_json_safe(output_path)
    diagnostics_counters, diagnostics_sources, diagnostics_latest = _latest_scan_diagnostics()
    off_hours = not is_trade_window(now_ist)
    off_hours_standby = bool(
        off_hours
        and str(fallback_resolution.get("fallback_truthfulness") or "").upper() == "OFF_HOURS_RESEARCH_STANDBY"
    )
    fallback_mode = bool(scanner.get("scan_only") or scanner.get("fallback_reason") or scanner.get("ohlc_fallback_required"))

    scanner_timestamp_dt = _payload_timestamp(scanner)
    scanner_age = _age_seconds(scanner_timestamp_dt, now_ist)
    stale_snapshot_warning = scanner_age is None or scanner_age > FRESH_SECONDS
    dashboard_snapshot_age = round(scanner_age, 3) if scanner_age is not None else None
    expected_off_hours_stale_snapshot = bool(off_hours_standby and stale_snapshot_warning)

    counters = {}
    counter_sources = {}
    aliases = {
        "stocks_checked": ("stocks_checked",),
        "trend_passed": ("trend_passed_count", "trend_passed"),
        "momentum_passed": ("momentum_passed_count", "momentum_passed"),
        "structure_passed": ("structure_passed_count", "structure_passed"),
        "breakout_ready": ("breakout_ready_count", "entry_passed_count"),
        "final_passed": ("final_passed_count", "final_passed"),
        "alerts_this_scan": ("alerts_this_scan", "alerts_sent"),
    }
    for counter, keys in aliases.items():
        value, key = _counter_from(scanner, *keys)
        if value is None and counter in diagnostics_counters and not (fallback_mode and counter in {"final_passed", "alerts_this_scan"}):
            value = diagnostics_counters[counter]
            counter_sources[counter] = diagnostics_sources.get(counter)
        else:
            counter_sources[counter] = f"scanner_status.{key}" if key else "unavailable"
        counters[counter] = value

    selected_symbols_count = _int_or_none(scanner.get("selected_symbols_count"))
    if selected_symbols_count is None:
        selected_symbols_count = _int_or_none(selection.get("selected_symbols_count"))
    if selected_symbols_count is None:
        selected = selection.get("selected_symbols")
        selected_symbols_count = len(selected) if isinstance(selected, list) else None

    live_trades_count = _int_or_none(lifecycle.get("open_trades_count"))
    counters["live_trades_count"] = live_trades_count if live_trades_count is not None else 0
    counter_sources["live_trades_count"] = "trade_lifecycle_health.open_trades_count" if lifecycle else "unavailable"

    scan_cycle_id = scanner.get("scanner_cycle_id") or diagnostics_counters.get("scan_cycle_id")
    previous = _read_json_safe(SCANNER_PREVIOUS_SIGNATURE_PATH)
    frozen_counter_warning = bool(scanner.get("repeated_data_signature"))
    if previous.get("scanner_cycle_id") and previous.get("scanner_cycle_id") != scan_cycle_id and scanner.get("data_signature") == previous.get("data_signature"):
        frozen_counter_warning = True
    if diagnostics_latest.get("scan_cycle_id") and scan_cycle_id and diagnostics_latest.get("scan_cycle_id") != scan_cycle_id:
        frozen_counter_warning = True
    atomic_publish_race = bool(scanner and scanner_timestamp_dt is None)
    previous_authoritative = _previous_authoritative_snapshot(previous_truth)
    zero_overwrite = bool(
        not off_hours
        and _has_counter_payload(counters)
        and not _has_nonzero_scan_gates(counters)
        and previous_authoritative
        and _has_nonzero_scan_gates(previous_authoritative.get("counters") or {})
        and scanner_age is not None
        and scanner_age <= BRIEF_REFRESH_GAP_SECONDS
    )
    preserve_previous_cycle = bool(zero_overwrite)
    if preserve_previous_cycle:
        preserved_counter_cycle_id = previous_authoritative.get("scan_cycle_id")
        counters.update(previous_authoritative["counters"])
        for counter in previous_authoritative["counters"]:
            counter_sources[counter] = "scanner_filter_truth.previous_authoritative_cycle_preserved"
        scanner_age = _age_seconds(scanner_timestamp_dt, now_ist)
        dashboard_snapshot_age = round(scanner_age, 3) if scanner_age is not None else None
        stale_snapshot_warning = scanner_age is None or scanner_age > FRESH_SECONDS
    else:
        preserved_counter_cycle_id = None

    raw_identical_warning = _identical_counter_warning(counters)
    identical_warning = False if off_hours_standby else raw_identical_warning
    setup_final = _int_or_none(setup.get("final_passed") or setup.get("final_passed_count"))
    final_passed_mismatch = bool(
        setup_final is not None
        and counters.get("final_passed") is not None
        and setup_final != counters.get("final_passed")
    )
    selected_symbols_mismatch = bool(
        selected_symbols_count is not None
        and counters.get("stocks_checked") is not None
        and abs(int(selected_symbols_count) - int(counters.get("stocks_checked"))) > 0
    )
    raw_confidence = _counter_confidence(scanner, counters, stale_snapshot_warning, identical_warning, final_passed_mismatch)
    confidence = _reconciled_counter_confidence(
        raw_confidence,
        fallback_resolution,
        master_runtime_health,
        setup_runtime_health,
        stale_snapshot_warning,
    )
    no_valid_counters = bool(
        not off_hours
        and not _has_counter_payload(counters)
        and not previous_authoritative
    )
    if no_valid_counters:
        confidence = "UNKNOWN"
    dashboard_truth_status = dashboard_truth.get("dashboard_truth_registry_status") or "UNKNOWN"
    dashboard_stale_read = bool(
        dashboard_truth_status == "WARNING"
        or "stale_runtime_critical_dashboard_metric" in (dashboard_truth.get("warnings") or [])
    )
    recommended_display = "exact"
    if off_hours_standby:
        recommended_display = "off_hours_research_standby"
    elif confidence != "HIGH":
        recommended_display = "low_confidence_fallback"
    if stale_snapshot_warning and not off_hours_standby:
        recommended_display = "stale_snapshot_with_timestamp"

    warnings = []
    if identical_warning:
        warnings.append("identical_counter_warning")
    if frozen_counter_warning:
        warnings.append("frozen_counter_warning")
    if stale_snapshot_warning and not off_hours_standby:
        warnings.append("stale_snapshot_warning")
    if final_passed_mismatch:
        warnings.append("final_passed_mismatch")
    if selected_symbols_mismatch:
        warnings.append("selected_symbols_mismatch")
    if dashboard_stale_read:
        warnings.append("dashboard_stale_read")
    if fallback_mode and not off_hours_standby:
        warnings.append("fallback_mode_counter_reliability_low")
    if preserve_previous_cycle:
        warnings.append("brief_refresh_gap_previous_cycle_preserved")
    if no_valid_counters:
        warnings.append("scan_pipeline_unavailable")

    scanner_publication_health = "HEALTHY"
    dashboard_scan_sync_status = "SYNCHRONIZED"
    if no_valid_counters:
        scanner_publication_health = "UNAVAILABLE"
        dashboard_scan_sync_status = "SCAN_PIPELINE_UNAVAILABLE"
        recommended_display = "SCAN_PIPELINE_UNAVAILABLE"
    elif preserve_previous_cycle:
        scanner_publication_health = "PRESERVED_PREVIOUS_VALID_CYCLE"
        dashboard_scan_sync_status = "PRESERVED_DURING_REFRESH_GAP"
    elif stale_snapshot_warning and not off_hours_standby:
        scanner_publication_health = "STALE"
        dashboard_scan_sync_status = "STALE"
    elif frozen_counter_warning:
        scanner_publication_health = "FROZEN_CYCLE_WARNING"
        dashboard_scan_sync_status = "WARNING"
    elif fallback_mode and not off_hours_standby:
        scanner_publication_health = "FALLBACK_ACTIVE"
        dashboard_scan_sync_status = "FALLBACK_VISIBLE"

    market_hours_runtime_sync = "OFF_HOURS" if off_hours else (
        "PASS" if dashboard_scan_sync_status == "SYNCHRONIZED" else "WARNING"
    )
    authoritative_scan_timestamp = scanner_timestamp_dt.isoformat() if scanner_timestamp_dt else None
    authoritative_scan_cycle_id = scan_cycle_id

    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": "FAIL" if not scanner else ("WARNING" if warnings else "PASS"),
        "scan_cycle_id": scan_cycle_id,
        "authoritative_scan_cycle_id": authoritative_scan_cycle_id,
        "authoritative_scan_timestamp": authoritative_scan_timestamp,
        "authoritative_counters": dict(counters),
        "dashboard_scan_snapshot_age": dashboard_snapshot_age,
        "dashboard_scan_sync_status": dashboard_scan_sync_status,
        "market_hours_runtime_sync": market_hours_runtime_sync,
        "scanner_publication_health": scanner_publication_health,
        "scanner_loop_health": scanner_publication.get("runtime_scheduler_health"),
        "publish_cadence_seconds": scanner_publication.get("publish_cadence_seconds"),
        "scanner_writer_heartbeat": scanner_publication.get("scanner_writer_heartbeat"),
        "stale_cycle_detected": scanner_publication.get("stale_cycle_detected"),
        "preserved_previous_valid_cycle": preserve_previous_cycle,
        "preserved_counter_cycle_id": preserved_counter_cycle_id,
        "zero_overwrite_detected": zero_overwrite,
        "scan_pipeline_unavailable": no_valid_counters,
        "scanner_timestamp": scanner_timestamp_dt.isoformat() if scanner_timestamp_dt else None,
        "scanner_age_seconds": round(scanner_age, 3) if scanner_age is not None else None,
        "selected_symbols_count": selected_symbols_count,
        "counters": counters,
        "counter_sources": counter_sources,
        "raw_counter_confidence": raw_confidence,
        "counter_confidence": confidence,
        "scanner_confidence": confidence,
        "off_hours_runtime_continuity": off_hours_standby,
        "runtime_fallback_resolution": {
            "fallback_truthfulness": fallback_resolution.get("fallback_truthfulness"),
            "scanner_confidence": fallback_resolution.get("scanner_confidence"),
            "fallback_reason": fallback_resolution.get("fallback_reason"),
        },
        "master_brain_runtime_health": {
            "master_brain_runtime_health": master_runtime_health.get("master_brain_runtime_health"),
            "master_brain_freshness_confidence": master_runtime_health.get("master_brain_freshness_confidence"),
        },
        "setup_engine_runtime_health": {
            "setup_runtime_health": setup_runtime_health.get("setup_runtime_health"),
            "setup_freshness_confidence": setup_runtime_health.get("setup_freshness_confidence"),
        },
        "identical_counter_warning": identical_warning,
        "raw_identical_counter_warning": raw_identical_warning,
        "identical_counter_warning_downgraded": bool(off_hours_standby and raw_identical_warning),
        "frozen_counter_warning": frozen_counter_warning,
        "stale_snapshot_warning": stale_snapshot_warning,
        "expected_off_hours_stale_snapshot": expected_off_hours_stale_snapshot,
        "fallback_mode": fallback_mode,
        "fallback_reason": scanner.get("fallback_reason"),
        "dashboard_truth_status": dashboard_truth_status,
        "dashboard_stale_read": dashboard_stale_read,
        "final_passed_mismatch": final_passed_mismatch,
        "selected_symbols_mismatch": selected_symbols_mismatch,
        "recommended_dashboard_display_mode": recommended_display,
        "warnings": warnings,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    audit = _build_live_scanner_sync_audit(
        now_ist=now_ist,
        scanner=scanner,
        scanner_timestamp_dt=scanner_timestamp_dt,
        scanner_age=scanner_age,
        scan_cycle_id=scan_cycle_id,
        previous_truth=previous_truth,
        counters=counters,
        dashboard_truth_status=dashboard_truth_status,
        fallback_resolution=fallback_resolution,
        off_hours=off_hours,
        stale_snapshot_warning=stale_snapshot_warning,
        frozen_counter_warning=frozen_counter_warning,
        zero_overwrite=zero_overwrite,
        atomic_publish_race=atomic_publish_race,
        dashboard_snapshot_age=dashboard_snapshot_age,
        scanner_publication_health=scanner_publication_health,
        dashboard_scan_sync_status=dashboard_scan_sync_status,
    )
    payload["live_scanner_sync_audit_path"] = str(LIVE_SCANNER_SYNC_AUDIT_PATH).replace("\\", "/")
    payload["live_scanner_sync_audit_status"] = "WARNING" if any(audit["detected_conditions"].values()) else "PASS"
    _write_json(output_path, payload)
    return payload


def run_scanner_filter_truth_audit():
    return build_scanner_filter_truth_status()


if __name__ == "__main__":
    print(json.dumps(run_scanner_filter_truth_audit(), indent=2, sort_keys=True))
