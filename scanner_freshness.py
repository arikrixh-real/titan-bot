import json
from datetime import datetime
from pathlib import Path

from utils.market_hours import IST, as_ist_datetime


SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
SCANNER_FILTER_TRUTH_STATUS_PATH = Path("data") / "runtime" / "scanner_filter_truth_status.json"
SCAN_SELECTION_STATE_PATH = Path("data") / "scan_selection_state.json"
SCANNER_FRESH_SECONDS = 15 * 60


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_timestamp(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _age_seconds(value, now):
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return max(0.0, (as_ist_datetime(now) - parsed).total_seconds())


def inspect_scanner_freshness(now=None, scanner_status_path=SCANNER_STATUS_PATH, selection_state_path=SCAN_SELECTION_STATE_PATH):
    now_ist = as_ist_datetime(now)
    scanner = _read_json_safe(scanner_status_path)
    scanner_truth = _read_json_safe(SCANNER_FILTER_TRUTH_STATUS_PATH)
    selection_state = _read_json_safe(selection_state_path)
    scanner_timestamp = (
        scanner.get("timestamp_ist")
        or scanner.get("scan_finished_at_ist")
        or scanner.get("scan_started_at_ist")
        or scanner.get("timestamp")
    )
    selection_timestamp = selection_state.get("timestamp")
    scanner_age_seconds = _age_seconds(scanner_timestamp, now_ist)
    selection_age_seconds = _age_seconds(selection_timestamp, now_ist)
    scan_only = bool(scanner.get("scan_only"))
    stale_ohlc = bool(
        scanner.get("ohlc_fallback_required")
        or str(scanner.get("status") or "").upper() == "SCAN_ONLY_STALE_OHLC"
        or (scanner.get("pipeline_health") or {}).get("ohlc_stale")
    )
    scanner_stale = scanner_age_seconds is None or scanner_age_seconds > SCANNER_FRESH_SECONDS
    selection_stale = selection_age_seconds is None or selection_age_seconds > SCANNER_FRESH_SECONDS

    warnings = []
    if not scanner:
        warnings.append("scanner_status_missing")
    if scanner_stale:
        warnings.append("scanner_status_stale_or_untimestamped")
    if selection_stale:
        warnings.append("scan_selection_state_stale_or_missing")
    if scan_only:
        warnings.append("scanner_scan_only_active")
    if stale_ohlc:
        warnings.append("scanner_reports_stale_ohlc")
    if bool(scanner.get("repeated_data_signature")):
        warnings.append("scanner_input_signature_repeated")

    status = "PASS"
    if warnings:
        status = "WARNING"
    if not scanner:
        status = "FAIL"

    return {
        "status": status,
        "scanner_status": scanner.get("status") or "MISSING",
        "scanner_mode": scanner.get("mode") or "UNKNOWN",
        "scanner_age_seconds": round(scanner_age_seconds, 3) if scanner_age_seconds is not None else None,
        "scanner_timestamp": scanner_timestamp,
        "scanner_cycle_id": scanner.get("scanner_cycle_id"),
        "scan_only": scan_only,
        "fallback_reason": scanner.get("fallback_reason"),
        "fallback_components": scanner.get("fallback_components") or [],
        "advisory_reason": scanner.get("advisory_reason"),
        "advisory_components": scanner.get("advisory_components") or [],
        "degraded_but_operational": bool(scanner.get("degraded_but_operational")),
        "pipeline_health": scanner.get("pipeline_health") or {},
        "scanner_data_health": scanner.get("scanner_data_health") or {},
        "stale_ohlc_detected": stale_ohlc,
        "stale_symbol_count": int(scanner.get("stale_symbol_count") or 0),
        "latest_candle_timestamp": scanner.get("latest_candle_timestamp"),
        "latest_candle_age_minutes": scanner.get("latest_candle_age_minutes"),
        "stale_policy": scanner.get("stale_policy"),
        "repeated_data_signature": bool(scanner.get("repeated_data_signature")),
        "selection_age_seconds": round(selection_age_seconds, 3) if selection_age_seconds is not None else None,
        "selection_timestamp": selection_timestamp,
        "selected_symbols_count": selection_state.get("selected_symbols_count"),
        "warnings": warnings,
        "scanner_filter_truth_status": scanner_truth.get("overall_status"),
        "counter_confidence": scanner_truth.get("counter_confidence"),
        "recommended_dashboard_display_mode": scanner_truth.get("recommended_dashboard_display_mode"),
    }
