import json
import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from engines.setup_engine import (
    breakout_ready,
    get_last_load_debug,
    load_cached_stock_data,
    strong_momentum,
    structure_ok,
    trend_direction,
)
from engines.time_filter import current_bot_mode


IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
SCANNER_PREVIOUS_SIGNATURE_PATH = Path("data") / "runtime" / "scanner_previous_signature.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
SETUP_ENGINE_STATUS_PATH = Path("data") / "runtime" / "setup_engine_status.json"
WORKER_HEALTH_PATH = Path("data") / "runtime" / "worker_health.json"
FINAL_REJECTION_DEBUG_PATH = Path("data") / "debug" / "final_rejection_breakdown.json"
RUNTIME_FRESH_SECONDS = 15 * 60
MARKET_CANDLE_STALE_MINUTES = 45
PARTIAL_STALE_TOLERANCE_RATIO = 0.15


def _timestamp_ist():
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


def _payload_dt(payload):
    if not isinstance(payload, dict):
        return None
    value = (
        payload.get("timestamp_ist")
        or payload.get("last_finished_at")
        or payload.get("last_started_at")
        or payload.get("timestamp")
        or payload.get("updated_at")
        or payload.get("created_at")
    )
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _payload_fresh(payload, fresh_seconds=RUNTIME_FRESH_SECONDS):
    dt = _payload_dt(payload)
    if not dt:
        return False
    return (datetime.now(IST) - dt).total_seconds() <= fresh_seconds


def _payload_active(payload):
    if not isinstance(payload, dict) or not payload:
        return False
    status = str(payload.get("status") or "").upper()
    if not status:
        return False
    inactive_markers = ("FAILED", "ERROR", "STOPPED", "INACTIVE", "TIMEOUT", "STALE")
    return not any(marker in status for marker in inactive_markers)


def _fresh_active_payload(path):
    payload = _read_json(path)
    return payload, bool(_payload_fresh(payload) and _payload_active(payload))


def _worker_health_task_ok(task):
    payload = _read_json(WORKER_HEALTH_PATH)
    task_payload = payload.get(task) if isinstance(payload, dict) else None
    return bool(_payload_fresh(task_payload) and _payload_active(task_payload))


def _task_available(task, status_path):
    payload, payload_ok = _fresh_active_payload(status_path)
    return payload, bool(payload_ok or _worker_health_task_ok(task))


def _fresh_int(payload, key):
    if not _payload_fresh(payload):
        return None
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_previous_run_count(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        run_count = payload.get("run_count") if isinstance(payload, dict) else None
        if isinstance(run_count, int) and not isinstance(run_count, bool):
            return run_count
    except Exception:
        return None
    return None


def _read_previous_data_signature(path=SCANNER_PREVIOUS_SIGNATURE_PATH):
    try:
        path = Path(path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        signature = payload.get("data_signature") if isinstance(payload, dict) else None
        return signature if isinstance(signature, str) and signature else None
    except Exception:
        return None


def _write_previous_data_signature(signature, scanner_cycle_id, timestamp_ist, path=SCANNER_PREVIOUS_SIGNATURE_PATH):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "data_signature": signature,
            "scanner_cycle_id": scanner_cycle_id,
            "timestamp_ist": timestamp_ist,
        }
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)
    except Exception:
        pass


def _scan_mode(load_debug, scan_only):
    if not scan_only:
        return "FULL_RUNTIME_PIPELINE"

    if not isinstance(load_debug, dict):
        return "SCAN_ONLY"

    selected_count = load_debug.get("selected_symbols_count")
    if selected_count is None:
        return "SCAN_ONLY"

    return f"SCAN_ONLY_CACHED_{selected_count}"


def _side_from_trend(trend):
    if trend == "BULLISH":
        return "LONG"
    if trend == "BEARISH":
        return "SHORT"
    if trend == "UP":
        return "LONG"
    if trend == "DOWN":
        return "SHORT"
    return None


def _last_ohlc(data):
    try:
        if data is None or data.empty:
            return None

        for column in ["High", "Low", "Close"]:
            if column not in data.columns:
                return None

        last = data.iloc[-1]
        return {
            "High": float(last["High"]),
            "Low": float(last["Low"]),
            "Close": float(last["Close"]),
        }
    except Exception:
        return None


def _last_close(data):
    try:
        if data is None or data.empty or "Close" not in data.columns:
            return None
        return float(data["Close"].iloc[-1])
    except Exception:
        return None


def _parse_candle_timestamp(value):
    try:
        if value is None:
            return None
        parsed = __import__("pandas").to_datetime(value, errors="coerce")
        if parsed is None or parsed is __import__("pandas").NaT:
            return None
        if getattr(parsed, "tzinfo", None) is None:
            parsed = parsed.tz_localize(timezone.utc)
        return parsed.to_pydatetime().astimezone(IST)
    except Exception:
        return None


def _last_candle_timestamp(data):
    try:
        if data is None or data.empty:
            return None

        for column in ["Datetime", "Date", "timestamp", "time"]:
            if column in data.columns:
                dt = _parse_candle_timestamp(data[column].iloc[-1])
                if dt:
                    return dt

        index = getattr(data, "index", None)
        if index is not None and len(index) > 0:
            return _parse_candle_timestamp(index[-1])
    except Exception:
        return None
    return None


def _latest_timestamp(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def _data_signature(signature_rows):
    normalized_rows = []
    for row in sorted(signature_rows, key=lambda item: item["symbol"]):
        normalized_rows.append(
            {
                "symbol": row["symbol"],
                "latest_candle_timestamp": row["latest_candle_timestamp"],
                "close": row["close"],
            }
        )
    raw = json.dumps(normalized_rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candle_age_minutes(latest_candle_dt, now_ist):
    if latest_candle_dt is None:
        return None
    try:
        return round(max((now_ist - latest_candle_dt).total_seconds(), 0) / 60, 2)
    except Exception:
        return None


def _stale_policy(stale_symbol_count, stocks_checked, latest_candle_age_minutes, market_mode):
    stale_symbol_ratio = (
        round(stale_symbol_count / stocks_checked, 4)
        if stocks_checked > 0
        else 0.0
    )
    global_stale = bool(
        market_mode
        and (
            latest_candle_age_minutes is None
            or latest_candle_age_minutes > MARKET_CANDLE_STALE_MINUTES
        )
    )
    partial_stale_tolerated = bool(
        market_mode
        and stale_symbol_count > 0
        and not global_stale
        and stale_symbol_ratio <= PARTIAL_STALE_TOLERANCE_RATIO
    )
    stale_ratio_fallback = bool(
        market_mode
        and stale_symbol_count > 0
        and stale_symbol_ratio > PARTIAL_STALE_TOLERANCE_RATIO
    )
    fallback_required = bool(global_stale or stale_ratio_fallback)

    if fallback_required and global_stale:
        policy = "GLOBAL_LATEST_CANDLE_STALE_FALLBACK"
    elif fallback_required:
        policy = "STALE_SYMBOL_RATIO_FALLBACK"
    elif partial_stale_tolerated:
        policy = "PARTIAL_STALE_TOLERATED_15_PERCENT"
    else:
        policy = "OHLC_FRESH"

    return {
        "fallback_required": fallback_required,
        "partial_stale_tolerated": partial_stale_tolerated,
        "stale_symbol_ratio": stale_symbol_ratio,
        "stale_policy": policy,
        "global_stale": global_stale,
    }


def _status_payload(
    *,
    mode,
    stocks_checked,
    trend_passed,
    structure_passed,
    momentum_passed,
    breakout_ready_count,
    passed_setups,
    candidate_symbols,
    candidate_details,
    errors,
    latest_candle_timestamp,
    latest_candle_age_minutes,
    data_signature,
    repeated_data_signature,
    repeated_data_warning,
    stale_symbol_count,
    stale_symbols,
    stale_data_warning,
    ohlc_fallback_required,
    partial_stale_tolerated,
    stale_symbol_ratio,
    stale_policy,
    scanner_cycle_id,
    scan_started_at_ist,
    scan_finished_at_ist,
    scan_duration_seconds,
    scan_only,
    entry_stage_available,
    entry_passed,
    final_passed,
    fallback_reason,
    pipeline_health,
    final_count_source,
    run_count=None,
):
    status = "FULL_RUNTIME_PIPELINE_COMPLETE"
    if ohlc_fallback_required:
        status = "SCAN_ONLY_STALE_OHLC"
    elif scan_only:
        status = "SCAN_ONLY_FALLBACK"

    if ohlc_fallback_required:
        dashboard_status_message = "True stale OHLC fallback active"
    elif partial_stale_tolerated:
        dashboard_status_message = "Partial stale symbols tolerated; warning only"
    elif final_passed is None:
        dashboard_status_message = "Final count unavailable from current runtime output"
    elif scan_only:
        dashboard_status_message = "Scanner-only fallback active"
    elif final_passed == 0:
        dashboard_status_message = "No setups found"
    else:
        dashboard_status_message = "Full runtime pipeline active"

    missing_fields = []
    if entry_passed is None:
        missing_fields.append("entry_passed")
    if final_passed is None:
        missing_fields.append("final_passed")

    payload = {
        "timestamp_ist": scan_finished_at_ist,
        "scanner_cycle_id": scanner_cycle_id,
        "scan_started_at_ist": scan_started_at_ist,
        "scan_finished_at_ist": scan_finished_at_ist,
        "scan_duration_seconds": scan_duration_seconds,
        "mode": mode,
        "status": status,
        "source": "VPS_RUNTIME_SCANNER",
        "scan_only": scan_only,
        "fallback_reason": fallback_reason,
        "pipeline_health": pipeline_health,
        "partial_stale_tolerated": partial_stale_tolerated,
        "stale_symbol_ratio": stale_symbol_ratio,
        "stale_policy": stale_policy,
        "final_count_source": final_count_source,
        "dashboard_status_message": dashboard_status_message,
        "real_scanner_called": True,
        "trade_creation": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": False,
        "stocks_checked": stocks_checked,
        "trend_passed": trend_passed,
        "momentum_passed": momentum_passed,
        "structure_passed": structure_passed,
        "entry_passed": entry_passed,
        "entry_stage_available": entry_stage_available,
        "entry_passed_note": (
            "Full setup engine entry count unavailable."
            if entry_passed is None and not scan_only
            else (
                "No independent entry-stage engine runs in scanner-only mode; use breakout_ready_count for this scanner gate."
                if scan_only
                else None
            )
        ),
        "final_passed": final_passed,
        "final_passed_note": (
            "Final count unavailable from current runtime output."
            if final_passed is None and not scan_only
            else (
                "Final quality filter not run in scanner-only mode."
                if scan_only
                else None
            )
        ),
        "alerts_sent": 0,
        "breakout_ready_count": breakout_ready_count,
        "passed_setups": passed_setups,
        "missing_fields": missing_fields,
        "candidate_symbols": candidate_symbols[:5],
        "candidate_details": candidate_details[:5],
        "latest_candle_timestamp": latest_candle_timestamp,
        "latest_candle_age_minutes": latest_candle_age_minutes,
        "data_signature": data_signature,
        "repeated_data_signature": repeated_data_signature,
        "repeated_data_warning": repeated_data_warning,
        "stale_symbol_count": stale_symbol_count,
        "stale_symbols": stale_symbols[:20],
        "stale_data_warning": stale_data_warning,
        "ohlc_fallback_required": ohlc_fallback_required,
        "errors": errors,
    }
    if run_count is not None:
        payload["run_count"] = run_count
    return payload


def _full_pipeline_health(ohlc_fallback_required, partial_stale_tolerated, stale_symbol_ratio, stale_policy):
    master_payload, master_ok = _task_available("master_brain", MASTER_BRAIN_STATUS_PATH)
    setup_payload, setup_ok = _task_available("setup_engine", SETUP_ENGINE_STATUS_PATH)

    final_debug = _read_json(FINAL_REJECTION_DEBUG_PATH)
    final_debug_fresh = _payload_fresh(final_debug)

    fallback_reasons = []
    if ohlc_fallback_required:
        fallback_reasons.append("OHLC_STALE")
    if not master_ok:
        fallback_reasons.append("MASTER_BRAIN_UNAVAILABLE")
    if not setup_ok:
        fallback_reasons.append("SETUP_ENGINE_UNAVAILABLE")

    scan_only = bool(fallback_reasons)
    return {
        "scan_only": scan_only,
        "fallback_reason": "|".join(fallback_reasons) if fallback_reasons else None,
        "pipeline_health": {
            "scanner_ok": True,
            "master_brain_ok": master_ok,
            "setup_engine_ok": setup_ok,
            "ohlc_refresh_ok": not ohlc_fallback_required,
            "ohlc_stale": ohlc_fallback_required,
            "partial_stale_tolerated": partial_stale_tolerated,
            "stale_symbol_ratio": stale_symbol_ratio,
            "stale_policy": stale_policy,
            "final_counts_available": final_debug_fresh,
        },
        "entry_passed": _fresh_int(final_debug, "entry_passed") if final_debug_fresh else None,
        "final_passed": _fresh_int(final_debug, "final_passed") if final_debug_fresh else None,
        "final_count_source": "final_rejection_breakdown" if final_debug_fresh else "unavailable",
        "entry_stage_available": final_debug_fresh,
        "master_status": master_payload.get("status"),
        "setup_status": setup_payload.get("status"),
    }


def run_scanner(path=SCANNER_STATUS_PATH):
    path = Path(path)
    started_monotonic = time.monotonic()
    scan_started_at_ist = _timestamp_ist()
    scanner_cycle_id = f"{scan_started_at_ist}-{uuid4()}"
    previous_run_count = _read_previous_run_count(path)
    run_count = previous_run_count + 1 if previous_run_count is not None else None
    previous_data_signature = _read_previous_data_signature()

    stocks_checked = 0
    trend_passed = 0
    structure_passed = 0
    momentum_passed = 0
    breakout_ready_count = 0
    passed_setups = 0
    candidate_symbols = []
    candidate_details = []
    errors = 0
    mode = "SCAN_ONLY"
    bot_mode = current_bot_mode(datetime.now(IST))
    market_mode = bot_mode == "MARKET_MODE"
    today_ist = datetime.now(IST).date()
    latest_candle_dt = None
    stale_symbols = []
    signature_rows = []
    load_debug = {}

    try:
        cached_symbols = load_cached_stock_data() or {}
        load_debug = get_last_load_debug() or {}
    except Exception:
        cached_symbols = {}
        errors += 1

    for symbol, data in cached_symbols.items():
        stocks_checked += 1
        candle_dt = _last_candle_timestamp(data)
        latest_candle_dt = _latest_timestamp(latest_candle_dt, candle_dt)
        signature_rows.append(
            {
                "symbol": str(symbol),
                "latest_candle_timestamp": candle_dt.isoformat() if candle_dt else None,
                "close": _last_close(data),
            }
        )
        if market_mode and (candle_dt is None or candle_dt.date() < today_ist):
            stale_symbols.append(symbol)

        try:
            trend = trend_direction(data)
            side = _side_from_trend(trend)
            if side is None:
                continue
            trend_passed += 1

            if not structure_ok(data, side=side):
                continue
            structure_passed += 1

            if not strong_momentum(data, side=side):
                continue
            momentum_passed += 1

            if not breakout_ready(data, side=side):
                continue
            breakout_ready_count += 1

            passed_setups += 1
            if len(candidate_symbols) < 5:
                candidate_symbols.append(symbol)
            if len(candidate_details) < 5:
                last_ohlc = _last_ohlc(data)
                if last_ohlc is not None:
                    candidate_details.append(
                        {
                            "symbol": symbol,
                            "side": side,
                            "last_ohlc": last_ohlc,
                        }
                    )

        except Exception:
            errors += 1
            continue

    scan_finished_at_ist = _timestamp_ist()
    finished_dt = datetime.now(IST)
    scan_duration_seconds = round(time.monotonic() - started_monotonic, 3)
    stale_symbol_count = len(stale_symbols)
    latest_candle_age_minutes = _candle_age_minutes(latest_candle_dt, finished_dt)
    stale_policy_result = _stale_policy(
        stale_symbol_count,
        stocks_checked,
        latest_candle_age_minutes,
        market_mode,
    )
    stale_data_warning = bool(
        market_mode
        and (
            stale_symbol_count > 0
            or stale_policy_result["fallback_required"]
        )
    )
    pipeline = _full_pipeline_health(
        stale_policy_result["fallback_required"],
        stale_policy_result["partial_stale_tolerated"],
        stale_policy_result["stale_symbol_ratio"],
        stale_policy_result["stale_policy"],
    )
    scan_only = pipeline["scan_only"]
    mode = _scan_mode(load_debug, scan_only)
    data_signature = _data_signature(signature_rows)
    repeated_data_signature = bool(previous_data_signature and previous_data_signature == data_signature)
    repeated_data_warning = (
        "Scanner input data unchanged from previous cycle"
        if repeated_data_signature
        else None
    )
    payload = _status_payload(
        mode=mode,
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        structure_passed=structure_passed,
        momentum_passed=momentum_passed,
        breakout_ready_count=breakout_ready_count,
        passed_setups=passed_setups,
        candidate_symbols=candidate_symbols,
        candidate_details=candidate_details,
        errors=errors,
        latest_candle_timestamp=latest_candle_dt.isoformat() if latest_candle_dt else None,
        latest_candle_age_minutes=latest_candle_age_minutes,
        data_signature=data_signature,
        repeated_data_signature=repeated_data_signature,
        repeated_data_warning=repeated_data_warning,
        stale_symbol_count=stale_symbol_count,
        stale_symbols=stale_symbols,
        stale_data_warning=stale_data_warning,
        ohlc_fallback_required=stale_policy_result["fallback_required"],
        partial_stale_tolerated=stale_policy_result["partial_stale_tolerated"],
        stale_symbol_ratio=stale_policy_result["stale_symbol_ratio"],
        stale_policy=stale_policy_result["stale_policy"],
        scanner_cycle_id=scanner_cycle_id,
        scan_started_at_ist=scan_started_at_ist,
        scan_finished_at_ist=scan_finished_at_ist,
        scan_duration_seconds=scan_duration_seconds,
        scan_only=scan_only,
        entry_stage_available=pipeline["entry_stage_available"],
        entry_passed=pipeline["entry_passed"],
        final_passed=pipeline["final_passed"],
        fallback_reason=pipeline["fallback_reason"],
        pipeline_health=pipeline["pipeline_health"],
        final_count_source=pipeline["final_count_source"],
        run_count=run_count,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_previous_data_signature(data_signature, scanner_cycle_id, scan_finished_at_ist)
    return payload


if __name__ == "__main__":
    print(json.dumps(run_scanner(), indent=2, sort_keys=True))
