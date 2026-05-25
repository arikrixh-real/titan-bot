import json
import hashlib
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from signal_path_diagnostics import add_example, build_scan_report, save_scan_report
from trend_diagnostics import apply_adaptive_trend, explain_trend, save_trend_diagnostics
from engines.setup_engine import (
    breakout_ready,
    get_last_load_debug,
    load_cached_stock_data,
    strong_momentum,
    structure_ok,
    trend_direction,
)
from engines.market_filter import market_regime_status
from engines.time_filter import current_bot_mode


IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
SCANNER_PREVIOUS_SIGNATURE_PATH = Path("data") / "runtime" / "scanner_previous_signature.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
SETUP_ENGINE_STATUS_PATH = Path("data") / "runtime" / "setup_engine_status.json"
WORKER_HEALTH_PATH = Path("data") / "runtime" / "worker_health.json"
FINAL_REJECTION_DEBUG_PATH = Path("data") / "debug" / "final_rejection_breakdown.json"
LIVE_PRICE_CACHE_PATH = Path("data") / "live_price_cache.json"
OHLC_REFRESH_STATUS_PATH = Path("data") / "runtime" / "ohlc_refresh_status.json"
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


def _task_availability_state(task, status_path):
    payload = _read_json(status_path)
    worker_ok = _worker_health_task_ok(task)
    fresh = _payload_fresh(payload)
    active = _payload_active(payload)
    present = bool(payload)
    truly_unavailable = bool((not present and not worker_ok) or (present and not active and not worker_ok))
    return {
        "payload": payload,
        "ok": bool((fresh and active) or worker_ok),
        "present": present,
        "fresh": fresh,
        "active": active,
        "worker_ok": worker_ok,
        "truly_unavailable": truly_unavailable,
        "advisory_stale": bool(present and active and not fresh and not worker_ok),
        "status": payload.get("status") if isinstance(payload, dict) else None,
        "timestamp": _final_count_timestamp(payload),
    }


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


def _optional_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _list_count(payload, key):
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return len(value) if isinstance(value, list) else None


def _nested_selected_count(payload, key):
    if not isinstance(payload, dict):
        return None
    nested = payload.get(key)
    if not isinstance(nested, dict):
        return None
    selected = nested.get("selected")
    return len(selected) if isinstance(selected, list) else None


def _first_count(payload, keys):
    if not isinstance(payload, dict):
        return None, None
    for key in keys:
        value = _optional_int(payload.get(key))
        if value is not None:
            return value, key
    return None, None


def _final_count_timestamp(payload):
    dt = _payload_dt(payload)
    return dt.isoformat() if dt else None


def _resolve_final_count(master_payload, setup_payload, final_debug):
    """
    Read-only resolver for actual final candidate counts already emitted by
    setup_engine/master_brain outputs. Zero is a valid count; None means no
    usable source exists.
    """
    count, key = _first_count(
        master_payload,
        (
            "final_passed",
            "final_selected_count",
            "selected_count",
            "selected_candidates_count",
        ),
    )
    if count is None:
        count = _nested_selected_count(master_payload, "final_decisions")
        key = "final_decisions.selected" if count is not None else None
    if count is None:
        count = _list_count(master_payload, "selected")
        key = "selected" if count is not None else None
    if count is not None:
        return {
            "entry_passed": _optional_int(master_payload.get("entry_passed")),
            "final_passed": count,
            "final_count_source": "master_brain_status",
            "final_passed_note": (
                f"Real final count read from data/runtime/master_brain_status.json field {key}."
            ),
            "entry_stage_available": _optional_int(master_payload.get("entry_passed")) is not None,
            "available": True,
            "timestamp": _final_count_timestamp(master_payload),
        }

    count, key = _first_count(
        setup_payload,
        (
            "final_passed",
            "final_selected_count",
            "selected_count",
            "selected_candidates_count",
        ),
    )
    if count is not None:
        return {
            "entry_passed": _optional_int(setup_payload.get("entry_passed")),
            "final_passed": count,
            "final_count_source": "setup_engine_status",
            "final_passed_note": (
                f"Real final count read from data/runtime/setup_engine_status.json field {key}."
            ),
            "entry_stage_available": _optional_int(setup_payload.get("entry_passed")) is not None,
            "available": True,
            "timestamp": _final_count_timestamp(setup_payload),
        }

    debug_count, debug_key = _first_count(final_debug, ("final_passed",))
    if debug_count is not None:
        return {
            "entry_passed": _optional_int(final_debug.get("entry_passed")),
            "final_passed": debug_count,
            "final_count_source": "setup_engine_status",
            "final_passed_note": (
                "Real setup_engine final count read from "
                f"data/debug/final_rejection_breakdown.json field {debug_key}."
            ),
            "entry_stage_available": _optional_int(final_debug.get("entry_passed")) is not None,
            "available": True,
            "timestamp": _final_count_timestamp(final_debug),
        }

    missing = []
    if not isinstance(setup_payload, dict) or not setup_payload:
        missing.append("data/runtime/setup_engine_status.json missing or empty")
    else:
        missing.append("setup_engine_status has no final count field")
    if not isinstance(master_payload, dict) or not master_payload:
        missing.append("data/runtime/master_brain_status.json missing or empty")
    else:
        missing.append("master_brain_status has no selected/final count field")
    if not isinstance(final_debug, dict) or not final_debug:
        missing.append("data/debug/final_rejection_breakdown.json missing or empty")
    else:
        missing.append("final_rejection_breakdown has no final_passed field")

    return {
        "entry_passed": None,
        "final_passed": None,
        "final_count_source": "unavailable",
        "final_passed_note": "Final count unavailable: " + "; ".join(missing) + ".",
        "entry_stage_available": False,
        "available": False,
        "timestamp": None,
    }


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
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(path)
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
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


def _live_price_for_symbol(live_price_cache, symbol):
    if not isinstance(live_price_cache, dict):
        return None
    candidates = [
        live_price_cache.get(symbol),
        live_price_cache.get(str(symbol).upper()),
        live_price_cache.get(str(symbol).lower()),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("ltp", "last_price", "price", "close"):
                value = _optional_float(candidate.get(key))
                if value is not None:
                    return value
        value = _optional_float(candidate)
        if value is not None:
            return value
    nested = live_price_cache.get("prices")
    if isinstance(nested, dict):
        return _live_price_for_symbol(nested, symbol)
    return None


def _optional_float(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _live_price_check(live_price_cache, symbol, close):
    live_price = _live_price_for_symbol(live_price_cache, symbol)
    if live_price is None or close in (None, 0):
        return {
            "available": live_price is not None,
            "live_price": live_price,
            "cached_close": close,
            "mismatch_pct": None,
            "mismatch_warning": False,
        }
    mismatch_pct = round(abs(live_price - close) / abs(close) * 100.0, 4)
    return {
        "available": True,
        "live_price": live_price,
        "cached_close": close,
        "mismatch_pct": mismatch_pct,
        "mismatch_warning": mismatch_pct >= 1.0,
    }


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


def _load_cached_symbols_with_debug():
    cached_symbols = load_cached_stock_data() or {}
    return cached_symbols, (get_last_load_debug() or {})


def _market_mode_stale_symbols(cached_symbols, now_ist):
    today_ist = now_ist.date()
    stale = []
    latest_candle_dt = None
    for symbol, data in (cached_symbols or {}).items():
        candle_dt = _last_candle_timestamp(data)
        latest_candle_dt = _latest_timestamp(latest_candle_dt, candle_dt)
        if candle_dt is None or candle_dt.date() < today_ist:
            stale.append(str(symbol))
    latest_candle_age_minutes = _candle_age_minutes(latest_candle_dt, now_ist)
    return stale, latest_candle_dt, latest_candle_age_minutes


def _refresh_ohlc_for_market_scan(cached_symbols, load_debug, market_mode):
    diagnostics = {
        "attempted": False,
        "reason": None,
        "status": "NOT_REQUIRED",
        "refresh_status_path": str(OHLC_REFRESH_STATUS_PATH).replace("\\", "/"),
        "before_stale_cache_count": int((load_debug or {}).get("stale_cache_count") or 0),
        "before_market_stale_symbol_count": 0,
        "before_latest_candle_timestamp": None,
        "before_latest_candle_age_minutes": None,
        "after_stale_cache_count": None,
        "after_market_stale_symbol_count": None,
        "after_latest_candle_timestamp": None,
        "after_latest_candle_age_minutes": None,
        "refresh_result_status": None,
        "refreshed_count": None,
        "failed_count": None,
        "skipped_count": None,
        "error": None,
        "fake_trend_forced": False,
    }
    if not market_mode:
        diagnostics["status"] = "SKIPPED_NOT_MARKET_MODE"
        return cached_symbols, load_debug, diagnostics

    before_stale, before_latest_dt, before_age = _market_mode_stale_symbols(
        cached_symbols,
        datetime.now(IST),
    )
    diagnostics.update(
        {
            "before_market_stale_symbol_count": len(before_stale),
            "before_latest_candle_timestamp": before_latest_dt.isoformat() if before_latest_dt else None,
            "before_latest_candle_age_minutes": before_age,
        }
    )

    refresh_required = bool(
        diagnostics["before_stale_cache_count"] > 0
        or before_stale
        or before_latest_dt is None
        or (before_age is not None and before_age > MARKET_CANDLE_STALE_MINUTES)
    )
    if not refresh_required:
        diagnostics["status"] = "FRESH"
        return cached_symbols, load_debug, diagnostics

    diagnostics["attempted"] = True
    diagnostics["reason"] = "MARKET_MODE_STALE_OHLC_REFRESH_REQUIRED"
    try:
        from runtime_ohlc_refresh import run_ohlc_refresh

        refresh_result = run_ohlc_refresh()
        diagnostics["refresh_result_status"] = refresh_result.get("status") if isinstance(refresh_result, dict) else None
        diagnostics["refreshed_count"] = refresh_result.get("refreshed_count") if isinstance(refresh_result, dict) else None
        diagnostics["failed_count"] = refresh_result.get("failed_count") if isinstance(refresh_result, dict) else None
        diagnostics["skipped_count"] = refresh_result.get("skipped_count") if isinstance(refresh_result, dict) else None
        cached_symbols, load_debug = _load_cached_symbols_with_debug()
        after_stale, after_latest_dt, after_age = _market_mode_stale_symbols(
            cached_symbols,
            datetime.now(IST),
        )
        diagnostics.update(
            {
                "after_stale_cache_count": int((load_debug or {}).get("stale_cache_count") or 0),
                "after_market_stale_symbol_count": len(after_stale),
                "after_latest_candle_timestamp": after_latest_dt.isoformat() if after_latest_dt else None,
                "after_latest_candle_age_minutes": after_age,
                "status": "REFRESHED_RELOADED" if not after_stale else "REFRESH_ATTEMPTED_STALE_REMAINS",
            }
        )
    except Exception as exc:
        diagnostics["status"] = "REFRESH_FAILED_USING_EXISTING_CACHE"
        diagnostics["error"] = f"{type(exc).__name__}:{exc}"
    return cached_symbols, load_debug, diagnostics


def _status_payload(
    *,
    mode,
    stocks_checked,
    trend_passed,
    strict_trend_passed,
    adaptive_trend_passed,
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
    final_passed_note,
    fallback_reason,
    fallback_components,
    pipeline_health,
    final_count_source,
    ohlc_refresh_diagnostics,
    degraded_but_operational=False,
    advisory_reason=None,
    advisory_components=None,
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
        "scanner_timestamp": scan_finished_at_ist,
        "scanner_cycle_id": scanner_cycle_id,
        "scan_started_at_ist": scan_started_at_ist,
        "scan_finished_at_ist": scan_finished_at_ist,
        "scan_duration_seconds": scan_duration_seconds,
        "mode": mode,
        "status": status,
        "source": "VPS_RUNTIME_SCANNER",
        "scan_only": scan_only,
        "fallback_reason": fallback_reason,
        "fallback_components": fallback_components,
        "advisory_reason": advisory_reason,
        "advisory_components": advisory_components or [],
        "degraded_but_operational": bool(degraded_but_operational),
        "pipeline_health": pipeline_health,
        "ohlc_refresh_diagnostics": ohlc_refresh_diagnostics,
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
        "trend_passed_count": trend_passed,
        "strict_trend_passed": strict_trend_passed,
        "adaptive_trend_passed": adaptive_trend_passed,
        "momentum_passed": momentum_passed,
        "momentum_passed_count": momentum_passed,
        "structure_passed": structure_passed,
        "structure_passed_count": structure_passed,
        "entry_passed": entry_passed,
        "entry_passed_count": entry_passed,
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
        "final_passed_count": final_passed,
        "final_passed_note": (
            final_passed_note
            or (
                "Final count unavailable from current runtime output."
                if final_passed is None
                else None
            )
        ),
        "alerts_sent": 0,
        "alerts_this_scan": 0,
        "breakout_ready_count": breakout_ready_count,
        "selected_symbols_count": stocks_checked,
        "counter_confidence": "LOW" if scan_only or final_passed is None else "HIGH",
        "counter_source": "runtime_scanner_independent_stage_counters",
        "counter_sources": {
            "stocks_checked": "runtime_scanner.loop.stocks_checked",
            "trend_passed": "runtime_scanner.loop.trend_direction",
            "momentum_passed": "runtime_scanner.loop.strong_momentum",
            "structure_passed": "runtime_scanner.loop.structure_ok",
            "breakout_ready": "runtime_scanner.loop.breakout_ready",
            "final_passed": final_count_source,
            "alerts_this_scan": "runtime_scanner.alerts_disabled_readonly_status",
        },
        "passed_setups": passed_setups,
        "missing_fields": missing_fields,
        "candidate_symbols": candidate_symbols[:5],
        "candidate_details": candidate_details[:5],
        "latest_candle_timestamp": latest_candle_timestamp,
        "latest_market_candle": latest_candle_timestamp,
        "latest_candle_age_minutes": latest_candle_age_minutes,
        "data_signature": data_signature,
        "repeated_data_signature": repeated_data_signature,
        "repeated_data_warning": repeated_data_warning,
        "fresh_symbol_count": max(int(stocks_checked or 0) - int(stale_symbol_count or 0), 0),
        "stale_symbol_count": stale_symbol_count,
        "stale_symbols": stale_symbols[:20],
        "stale_data_warning": stale_data_warning,
        "ohlc_fallback_required": ohlc_fallback_required,
        "scanner_data_health": {
            "stocks_checked": stocks_checked,
            "fresh_symbol_count": max(int(stocks_checked or 0) - int(stale_symbol_count or 0), 0),
            "stale_symbol_count": stale_symbol_count,
            "latest_market_candle": latest_candle_timestamp,
            "latest_candle_age_minutes": latest_candle_age_minutes,
            "stale_policy": stale_policy,
            "refresh_attempted": bool((ohlc_refresh_diagnostics or {}).get("attempted")),
            "refresh_status": (ohlc_refresh_diagnostics or {}).get("status"),
            "degraded_but_operational": bool(degraded_but_operational),
        },
        "errors": errors,
    }
    if run_count is not None:
        payload["run_count"] = run_count
    return payload


def _full_pipeline_health(ohlc_fallback_required, partial_stale_tolerated, stale_symbol_ratio, stale_policy):
    master_state = _task_availability_state("master_brain", MASTER_BRAIN_STATUS_PATH)
    setup_state = _task_availability_state("setup_engine", SETUP_ENGINE_STATUS_PATH)
    master_payload = master_state["payload"]
    setup_payload = setup_state["payload"]
    master_ok = master_state["ok"]
    setup_ok = setup_state["ok"]

    final_debug = _read_json(FINAL_REJECTION_DEBUG_PATH)
    final_count = _resolve_final_count(master_payload, setup_payload, final_debug)

    fallback_reasons = []
    advisory_reasons = []
    if ohlc_fallback_required:
        fallback_reasons.append("OHLC_STALE")
    if master_state["truly_unavailable"] and not final_count["available"]:
        fallback_reasons.append("MASTER_BRAIN_UNAVAILABLE")
    elif not master_ok:
        advisory_reasons.append("MASTER_BRAIN_STALE_ADVISORY")
    if setup_state["truly_unavailable"] and not final_count["available"]:
        fallback_reasons.append("SETUP_ENGINE_UNAVAILABLE")
    elif not setup_ok:
        advisory_reasons.append("SETUP_ENGINE_STALE_ADVISORY")

    scan_only = bool(fallback_reasons)
    return {
        "scan_only": scan_only,
        "fallback_reason": "|".join(fallback_reasons) if fallback_reasons else None,
        "fallback_components": fallback_reasons,
        "advisory_reason": "|".join(advisory_reasons) if advisory_reasons else None,
        "advisory_components": advisory_reasons,
        "degraded_but_operational": bool(partial_stale_tolerated or advisory_reasons),
        "pipeline_health": {
            "scanner_ok": True,
            "master_brain_ok": master_ok,
            "setup_engine_ok": setup_ok,
            "master_brain_truly_unavailable": master_state["truly_unavailable"],
            "setup_engine_truly_unavailable": setup_state["truly_unavailable"],
            "master_brain_advisory_stale": master_state["advisory_stale"],
            "setup_engine_advisory_stale": setup_state["advisory_stale"],
            "ohlc_refresh_ok": not ohlc_fallback_required,
            "ohlc_stale": ohlc_fallback_required,
            "partial_stale_tolerated": partial_stale_tolerated,
            "stale_symbol_ratio": stale_symbol_ratio,
            "stale_policy": stale_policy,
            "final_counts_available": final_count["available"],
            "final_count_timestamp": final_count["timestamp"],
        },
        "entry_passed": final_count["entry_passed"],
        "final_passed": final_count["final_passed"],
        "final_passed_note": final_count["final_passed_note"],
        "final_count_source": final_count["final_count_source"],
        "entry_stage_available": final_count["entry_stage_available"],
        "master_status": master_payload.get("status"),
        "setup_status": setup_payload.get("status"),
        "master_brain_state": {k: v for k, v in master_state.items() if k != "payload"},
        "setup_engine_state": {k: v for k, v in setup_state.items() if k != "payload"},
        "final_debug": final_debug,
    }


def _market_filter_diagnostics(pipeline, stale_policy_result):
    health = pipeline.get("pipeline_health") if isinstance(pipeline, dict) else {}
    final_debug = pipeline.get("final_debug") if isinstance(pipeline, dict) else {}
    return {
        "market_regime": final_debug.get("market_status") if isinstance(final_debug, dict) else None,
        "volatility_filter": {
            "ohlc_stale": bool(health.get("ohlc_stale")),
            "stale_policy": stale_policy_result.get("stale_policy"),
            "stale_symbol_ratio": stale_policy_result.get("stale_symbol_ratio"),
            "partial_stale_tolerated": stale_policy_result.get("partial_stale_tolerated"),
        },
        "news_filter": None,
        "risk_filter": None,
        "runtime_filters": {
            "scan_only": bool(pipeline.get("scan_only")),
            "fallback_reason": pipeline.get("fallback_reason"),
            "advisory_reason": pipeline.get("advisory_reason"),
            "degraded_but_operational": bool(pipeline.get("degraded_but_operational")),
            "master_brain_ok": bool(health.get("master_brain_ok")),
            "setup_engine_ok": bool(health.get("setup_engine_ok")),
        },
    }


def _setup_engine_rejections_from_debug(final_debug, entry_passed, final_passed):
    if not isinstance(final_debug, dict) or not _payload_fresh(final_debug):
        return Counter(), {}, None

    reasons = Counter()
    for reason, count in (final_debug.get("breakdown") or {}).items():
        try:
            reasons[str(reason)] += int(count)
        except Exception:
            continue

    examples = {}
    symbols_by_reason = final_debug.get("symbols_by_reason") or {}
    if isinstance(symbols_by_reason, dict):
        for reason, symbols in symbols_by_reason.items():
            if isinstance(symbols, list):
                examples[str(reason)] = [str(symbol) for symbol in symbols[:8]]

    rejected = final_debug.get("total_final_rejections_after_entry")
    if rejected is None and final_passed is not None and entry_passed is not None:
        rejected = max(int(entry_passed) - int(final_passed), 0)
    return reasons, examples, rejected


def _regime_diagnostics():
    try:
        status = market_regime_status()
    except Exception as exc:
        status = {
            "market_ok": True,
            "reason": f"regime diagnostics unavailable: {exc}",
            "regime": "UNKNOWN",
            "status": "UNKNOWN",
        }

    if not isinstance(status, dict):
        status = {"market_ok": True, "regime": str(status or "UNKNOWN")}

    current_regime = (
        status.get("regime")
        or status.get("status")
        or status.get("direction")
        or "UNKNOWN"
    )
    blocked = "market_ok" in status and not bool(status.get("market_ok"))
    return {
        "current_regime": current_regime,
        "allowed_regimes": "fail-open market_regime_status",
        "rejected_regimes": [current_regime] if blocked else [],
        "candidates_blocked_by_regime_mismatch": 0,
        "market_status": status,
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
    strict_trend_passed = 0
    adaptive_trend_passed = 0
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
    ohlc_refresh_diagnostics = {}
    trend_reasons = Counter()
    structure_reasons = Counter()
    momentum_reasons = Counter()
    entry_reasons = Counter()
    trend_examples = {}
    structure_examples = {}
    momentum_examples = {}
    entry_examples = {}
    trend_diagnostic_symbols = []
    regime_diagnostics = _regime_diagnostics()
    live_price_cache = _read_json(LIVE_PRICE_CACHE_PATH)

    try:
        cached_symbols, load_debug = _load_cached_symbols_with_debug()
        cached_symbols, load_debug, ohlc_refresh_diagnostics = _refresh_ohlc_for_market_scan(
            cached_symbols,
            load_debug,
            market_mode,
        )
    except Exception:
        cached_symbols = {}
        errors += 1
        ohlc_refresh_diagnostics = {
            "status": "LOAD_OR_REFRESH_EXCEPTION",
            "attempted": False,
            "fake_trend_forced": False,
        }

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
            trend_diagnostic = apply_adaptive_trend(
                explain_trend(symbol, data, trend),
                regime_diagnostics,
            )
            close = _last_close(data)
            candle_age = _candle_age_minutes(candle_dt, datetime.now(IST))
            data_stale = bool(market_mode and (candle_dt is None or candle_dt.date() < today_ist))
            trend_diagnostic.update(
                {
                    "latest_candle_timestamp": candle_dt.isoformat() if candle_dt else None,
                    "latest_candle_age_minutes": candle_age,
                    "data_stale": data_stale,
                    "stale_reason": (
                        "missing_latest_candle_timestamp"
                        if market_mode and candle_dt is None
                        else (
                            "latest_candle_before_today"
                            if data_stale
                            else None
                        )
                    ),
                    "live_price_check": _live_price_check(live_price_cache, symbol, close),
                }
            )
            trend_diagnostic_symbols.append(trend_diagnostic)
            strict_side = _side_from_trend(trend)
            side = strict_side
            if side is None and trend_diagnostic.get("adaptive_accepted"):
                side = trend_diagnostic.get("adaptive_side")
            if side is None:
                reason = str(trend or "NO_VALID_TREND")
                trend_reasons[reason] += 1
                add_example(trend_examples, reason, symbol)
                continue
            trend_passed += 1
            if strict_side is None:
                adaptive_trend_passed += 1
            else:
                strict_trend_passed += 1

            if not structure_ok(data, side=side):
                structure_reasons["STRUCTURE_FAIL"] += 1
                add_example(structure_examples, "STRUCTURE_FAIL", symbol)
                continue
            structure_passed += 1

            if not strong_momentum(data, side=side):
                momentum_reasons["MOMENTUM_FAIL"] += 1
                add_example(momentum_examples, "MOMENTUM_FAIL", symbol)
                continue
            momentum_passed += 1

            if not breakout_ready(data, side=side):
                entry_reasons["NOT_READY"] += 1
                add_example(entry_examples, "NOT_READY", symbol)
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
    for item in trend_diagnostic_symbols:
        item["repeated_data_signature"] = repeated_data_signature
        if repeated_data_warning:
            item["stale_reason"] = item.get("stale_reason") or repeated_data_warning
    payload = _status_payload(
        mode=mode,
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        strict_trend_passed=strict_trend_passed,
        adaptive_trend_passed=adaptive_trend_passed,
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
        final_passed_note=pipeline["final_passed_note"],
        fallback_reason=pipeline["fallback_reason"],
        fallback_components=pipeline["fallback_components"],
        pipeline_health=pipeline["pipeline_health"],
        final_count_source=pipeline["final_count_source"],
        ohlc_refresh_diagnostics=ohlc_refresh_diagnostics,
        degraded_but_operational=pipeline["degraded_but_operational"],
        advisory_reason=pipeline["advisory_reason"],
        advisory_components=pipeline["advisory_components"],
        run_count=run_count,
    )

    setup_reasons, setup_examples, setup_rejected = _setup_engine_rejections_from_debug(
        pipeline.get("final_debug"),
        pipeline.get("entry_passed"),
        pipeline.get("final_passed"),
    )
    diagnostics_final_passed = None if scan_only else pipeline["final_passed"]
    diagnostics_report = build_scan_report(
        scan_cycle_id=scanner_cycle_id,
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        momentum_passed=momentum_passed,
        structure_passed=structure_passed,
        entry_passed=breakout_ready_count,
        final_passed=diagnostics_final_passed,
        alerts_sent=0,
        trend_reasons=trend_reasons,
        trend_examples=trend_examples,
        momentum_reasons=momentum_reasons,
        momentum_examples=momentum_examples,
        structure_reasons=structure_reasons,
        structure_examples=structure_examples,
        entry_reasons=entry_reasons,
        entry_examples=entry_examples,
        setup_reasons=setup_reasons,
        setup_examples=setup_examples,
        setup_received=0 if scan_only else breakout_ready_count,
        setup_rejected=0 if scan_only else setup_rejected,
        market_filters=_market_filter_diagnostics(pipeline, stale_policy_result),
        breakout_ready=breakout_ready_count,
    )
    save_scan_report(diagnostics_report)
    save_trend_diagnostics(
        scanner_cycle_id,
        trend_diagnostic_symbols,
        regime_diagnostics=regime_diagnostics,
    )

    _atomic_write_json(path, payload)
    _write_previous_data_signature(data_signature, scanner_cycle_id, scan_finished_at_ist)
    return payload


if __name__ == "__main__":
    print(json.dumps(run_scanner(), indent=2, sort_keys=True))
