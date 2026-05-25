import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from scanner_freshness import inspect_scanner_freshness
from utils.market_hours import IST, as_ist_datetime, is_trade_window


HEALTH_PATH = Path("data") / "runtime" / "titan_market_data_health.json"
OHLC_FRESHNESS_STATUS_PATH = Path("data") / "runtime" / "ohlc_freshness_status.json"
RUNTIME_LIVE_PRICE_CACHE_META_PATH = Path("data") / "runtime" / "live_price_cache_meta.json"
OHLC_CACHE_DIR = Path("data") / "cache"
LIVE_PRICE_CACHE_PATH = Path("data") / "live_price_cache.json"
LIVE_PRICE_CACHE_META_PATH = Path("data") / "live_price_cache_meta.json"
LIVE_PRICE_STATUS_PATH = Path("data") / "live_price_status.json"
OHLC_REFRESH_STATUS_PATH = Path("data") / "runtime" / "ohlc_refresh_status.json"
STALE_OHLC_MAX_AGE_MINUTES = 45
LIVE_PRICE_CACHE_MAX_AGE_SECONDS = 120
OHLC_FILE_MAX_AGE_HOURS = 24


SAFETY_FLAGS = {
    "advisory_only": True,
    "affects_live_ranking": False,
    "affects_execution": False,
    "broker_mutation": False,
    "telegram_mutation": False,
    "supabase_mutation": False,
    "live_order_behavior": False,
    "recommended_live_weight": 0.0,
    "rank_adjustment": 0.0,
}


def _read_json_safe(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_safe(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 9999999999 else value
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(IST)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _file_mtime_ist(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).astimezone(IST)
    except Exception:
        return None


def _age_seconds(value, now):
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return max(0.0, (as_ist_datetime(now) - parsed).total_seconds())


def _status_from_flags(fail_flags, warning_flags):
    if fail_flags:
        return "FAIL"
    if warning_flags:
        return "WARNING"
    return "PASS"


def _latest_csv_timestamp(path):
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            last_row = None
            for row in reader:
                last_row = row
        if not last_row:
            return None
        for key in ("Datetime", "Date", "timestamp", "time"):
            if key in last_row:
                parsed = _parse_timestamp(last_row.get(key))
                if parsed is not None:
                    return parsed
    except Exception:
        return None
    return None


def inspect_ohlc_freshness(now=None, cache_dir=OHLC_CACHE_DIR):
    now_ist = as_ist_datetime(now)
    latest_candle = None
    stale_symbols = []
    stale_files = []
    checked = 0
    try:
        files = sorted(Path(cache_dir).glob("*.csv"))
    except Exception:
        files = []

    for path in files:
        checked += 1
        symbol = path.stem
        candle_ts = _latest_csv_timestamp(path)
        if candle_ts is not None and (latest_candle is None or candle_ts > latest_candle):
            latest_candle = candle_ts
        age_minutes = None
        if candle_ts is not None:
            age_minutes = max(0.0, (now_ist - candle_ts).total_seconds() / 60.0)
        file_age_hours = None
        try:
            file_age_hours = max(0.0, (datetime.now(timezone.utc).timestamp() - os.path.getmtime(path)) / 3600.0)
        except Exception:
            pass
        is_stale = candle_ts is None or (
            is_trade_window(now_ist) and age_minutes is not None and age_minutes > STALE_OHLC_MAX_AGE_MINUTES
        )
        file_stale = file_age_hours is not None and file_age_hours > OHLC_FILE_MAX_AGE_HOURS
        if is_stale:
            stale_symbols.append(symbol)
        if file_stale:
            stale_files.append(
                {
                    "symbol": symbol,
                    "path": str(path).replace("\\", "/"),
                    "file_age_hours": round(file_age_hours, 3),
                }
            )

    latest_age_minutes = None
    if latest_candle is not None:
        latest_age_minutes = max(0.0, (now_ist - latest_candle).total_seconds() / 60.0)
    stale_detected = bool(stale_symbols or stale_files)
    return {
        "status": "WARNING" if stale_detected else "PASS",
        "cache_dir": str(cache_dir).replace("\\", "/"),
        "symbols_checked": checked,
        "latest_candle_timestamp": latest_candle.isoformat() if latest_candle else None,
        "latest_candle_age_minutes": round(latest_age_minutes, 3) if latest_age_minutes is not None else None,
        "stale_ohlc_detected": stale_detected,
        "stale_symbol_count": len(stale_symbols),
        "stale_symbols_sample": stale_symbols[:20],
        "stale_file_count": len(stale_files),
        "stale_files_sample": stale_files[:20],
        "threshold_minutes": STALE_OHLC_MAX_AGE_MINUTES,
        "file_age_threshold_hours": OHLC_FILE_MAX_AGE_HOURS,
    }


def _cache_timestamp(meta_item):
    if not isinstance(meta_item, dict):
        return None
    return (
        meta_item.get("updated_at_ist")
        or meta_item.get("updated_at")
        or meta_item.get("timestamp_ist")
        or meta_item.get("timestamp")
        or meta_item.get("cache_last_updated")
    )


def _authoritative_live_price_meta(cache, meta, cache_path, now_ist):
    if meta:
        source = "live_price_cache_meta"
        authoritative = dict(meta)
    else:
        source = "cache_file_mtime" if cache else "missing"
        mtime = _file_mtime_ist(cache_path)
        timestamp = mtime.isoformat() if mtime else None
        authoritative = {}
        for symbol, price in (cache or {}).items():
            authoritative[str(symbol)] = {
                "price": price,
                "updated_at_ist": timestamp,
                "source": source,
                "status": "SYNTHESIZED_META_FROM_CACHE_FILE",
            }

    ages = []
    stale_symbols = []
    latest_timestamp = None
    for symbol, item in authoritative.items():
        parsed = _parse_timestamp(_cache_timestamp(item))
        if parsed is not None and (latest_timestamp is None or parsed > latest_timestamp):
            latest_timestamp = parsed
        age = _age_seconds(_cache_timestamp(item), now_ist)
        if age is None:
            stale_symbols.append(str(symbol))
            continue
        ages.append(age)
        if age > LIVE_PRICE_CACHE_MAX_AGE_SECONDS:
            stale_symbols.append(str(symbol))

    cache_age_seconds = min(ages) if ages else None
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "cache_last_updated": latest_timestamp.isoformat() if latest_timestamp else None,
        "cache_age_seconds": round(cache_age_seconds, 3) if cache_age_seconds is not None else None,
        "cache_source": source,
        "cache_present": bool(cache),
        "root_meta_present": bool(meta),
        "runtime_meta_generated": True,
        "stale": bool(stale_symbols or (bool(cache) and not authoritative)),
        "stale_symbol_count": len(stale_symbols),
        "stale_symbols_sample": stale_symbols[:20],
        "symbols_tracked": len(authoritative),
        "metadata": authoritative,
        "safety_flags": dict(SAFETY_FLAGS),
    }
    _write_json_safe(RUNTIME_LIVE_PRICE_CACHE_META_PATH, payload)
    return payload


def inspect_live_price_cache(now=None, cache_path=LIVE_PRICE_CACHE_PATH, meta_path=LIVE_PRICE_CACHE_META_PATH, status_path=LIVE_PRICE_STATUS_PATH):
    now_ist = as_ist_datetime(now)
    cache = _read_json_safe(cache_path)
    meta = _read_json_safe(meta_path)
    status_payload = _read_json_safe(status_path)
    authoritative_meta = _authoritative_live_price_meta(cache, meta, cache_path, now_ist)
    effective_meta = authoritative_meta.get("metadata") if isinstance(authoritative_meta.get("metadata"), dict) else {}
    timestamps = []
    stale_symbols = []
    for symbol, item in effective_meta.items():
        if not isinstance(item, dict):
            stale_symbols.append(str(symbol))
            continue
        timestamp = _cache_timestamp(item)
        age = _age_seconds(timestamp, now_ist)
        if age is None:
            stale_symbols.append(str(symbol))
            continue
        timestamps.append(age)
        if age > LIVE_PRICE_CACHE_MAX_AGE_SECONDS:
            stale_symbols.append(str(symbol))

    cache_age_seconds = min(timestamps) if timestamps else None
    root_meta_present = bool(meta)
    meta_present = bool(effective_meta)
    cache_present = bool(cache)
    cache_stale = bool((cache_present and not meta_present) or stale_symbols)
    if cache_present and meta_present and cache_age_seconds is None:
        cache_stale = True

    source = status_payload.get("source") or status_payload.get("live_source_status") or "UNKNOWN"
    live_source_status = status_payload.get("live_source_status") or status_payload.get("status")
    cache_fallback_reason = status_payload.get("fallback_reason") or status_payload.get("reason")
    authoritative_meta.update(
        {
            "live_fetch_available": str(live_source_status or source).upper() in {"ACTIVE", "UPSTOX"},
            "fallback_active": bool(cache_fallback_reason or cache_stale),
            "fallback_reason": cache_fallback_reason or ("CACHE_STALE" if cache_stale else None),
            "cache_stale": cache_stale,
            "cache_status": "WARNING" if cache_stale else "PASS",
        }
    )
    _write_json_safe(RUNTIME_LIVE_PRICE_CACHE_META_PATH, authoritative_meta)
    return {
        "status": "WARNING" if cache_stale else "PASS",
        "cache_present": cache_present,
        "meta_present": meta_present,
        "root_meta_present": root_meta_present,
        "runtime_meta_path": str(RUNTIME_LIVE_PRICE_CACHE_META_PATH).replace("\\", "/"),
        "runtime_meta_generated": bool(authoritative_meta.get("runtime_meta_generated")),
        "cache_age_seconds": round(cache_age_seconds, 3) if cache_age_seconds is not None else None,
        "cache_stale": cache_stale,
        "stale_symbol_count": len(stale_symbols),
        "stale_symbols_sample": stale_symbols[:20],
        "source": source,
        "cache_source": authoritative_meta.get("cache_source"),
        "cache_last_updated": authoritative_meta.get("cache_last_updated"),
        "status_payload_present": bool(status_payload),
        "token_type_visible": bool(status_payload.get("token_type_used")),
        "token_type_used": status_payload.get("token_type_used") or "UNKNOWN",
        "runtime_visible": bool(status_payload),
        "live_source_status": live_source_status,
        "fallback_reason": cache_fallback_reason,
        "last_successful_live_fetch": status_payload.get("last_successful_live_fetch"),
        "stale_cache_detected": bool(status_payload.get("stale_cache_detected") or cache_stale),
    }


def _ohlc_refresh_visibility():
    payload = _read_json_safe(OHLC_REFRESH_STATUS_PATH)
    return {
        "present": bool(payload),
        "status": payload.get("status") or "MISSING",
        "source": payload.get("source"),
        "fallback_count": payload.get("fallback_count"),
        "skipped_reason": payload.get("skipped_reason"),
        "symbol_source": payload.get("symbol_source"),
    }


def _refresh_stale_ohlc_if_needed(ohlc, now_ist):
    if not is_trade_window(now_ist) or not ohlc.get("stale_ohlc_detected"):
        return {
            "refresh_attempted": False,
            "refresh_success": False,
            "refresh_status": "NOT_REQUIRED",
            "refresh_result": {},
        }
    try:
        from runtime_ohlc_refresh import run_ohlc_refresh

        result = run_ohlc_refresh()
    except Exception as exc:
        return {
            "refresh_attempted": True,
            "refresh_success": False,
            "refresh_status": "FAILED",
            "refresh_error": f"{type(exc).__name__}:{exc}",
            "refresh_result": {},
        }

    refreshed_count = int(result.get("refreshed_count") or 0) if isinstance(result, dict) else 0
    return {
        "refresh_attempted": True,
        "refresh_success": refreshed_count > 0,
        "refresh_status": result.get("status") if isinstance(result, dict) else "UNKNOWN",
        "refresh_result": result if isinstance(result, dict) else {},
    }


def _fallback_components(scanner, cache, ohlc, refresh):
    components = []
    scanner_reason = str(scanner.get("fallback_reason") or "")
    if ohlc.get("stale_ohlc_detected") or "OHLC_STALE" in scanner_reason:
        components.append("OHLC_STALE")
    live_status = str(cache.get("live_source_status") or cache.get("source") or "").upper()
    if live_status and live_status not in {"ACTIVE", "UPSTOX"}:
        components.append(f"UPSTOX_{live_status}")
    if "MASTER_BRAIN_UNAVAILABLE" in scanner_reason:
        components.append("MASTER_BRAIN_UNAVAILABLE")
    if "SETUP_ENGINE_UNAVAILABLE" in scanner_reason:
        components.append("SETUP_ENGINE_UNAVAILABLE")
    if cache.get("cache_stale"):
        components.append("CACHE_STALE")
    if refresh.get("refresh_attempted") and not refresh.get("refresh_success"):
        components.append("OHLC_REFRESH_UNSUCCESSFUL")

    deduped = []
    for item in components:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _write_ohlc_freshness_status(ohlc, cache, scanner, refresh_info, now_ist):
    fallback_reasons = _fallback_components(scanner, cache, ohlc, refresh_info)
    payload = {
        "generated_at_ist": now_ist.isoformat(),
        "latest_candle_timestamp": ohlc.get("latest_candle_timestamp"),
        "latest_market_candle": ohlc.get("latest_candle_timestamp"),
        "stale_symbol_count": int(ohlc.get("stale_symbol_count") or 0),
        "fresh_symbol_count": max(
            int(ohlc.get("symbols_checked") or 0) - int(ohlc.get("stale_symbol_count") or 0),
            0,
        ),
        "stale": bool(ohlc.get("stale_ohlc_detected")),
        "refresh_attempted": bool(refresh_info.get("refresh_attempted")),
        "refresh_success": bool(refresh_info.get("refresh_success")),
        "cache_last_updated": cache.get("cache_last_updated"),
        "cache_age_seconds": cache.get("cache_age_seconds"),
        "cache_source": cache.get("cache_source") or cache.get("source"),
        "live_fetch_available": str(cache.get("live_source_status") or "").upper() == "ACTIVE",
        "fallback_active": bool(fallback_reasons),
        "fallback_reason": "|".join(fallback_reasons) if fallback_reasons else None,
        "fallback_components": fallback_reasons,
        "scanner_data_health": {
            "scanner_status": scanner.get("scanner_status"),
            "scanner_freshness_status": scanner.get("status"),
            "ohlc_status": ohlc.get("status"),
            "cache_status": cache.get("status"),
        },
        "safety_flags": dict(SAFETY_FLAGS),
    }
    _write_json_safe(OHLC_FRESHNESS_STATUS_PATH, payload)
    return payload


def build_market_data_health(now=None):
    now_ist = as_ist_datetime(now)
    scanner = inspect_scanner_freshness(now_ist)
    ohlc = inspect_ohlc_freshness(now_ist)
    refresh_info = _refresh_stale_ohlc_if_needed(ohlc, now_ist)
    if refresh_info.get("refresh_attempted"):
        ohlc = inspect_ohlc_freshness(now_ist)
    cache = inspect_live_price_cache(now_ist)
    refresh = _ohlc_refresh_visibility()
    refresh.update(refresh_info)
    ohlc_status = _write_ohlc_freshness_status(ohlc, cache, scanner, refresh_info, now_ist)

    contradiction_flags = []
    if scanner.get("status") == "PASS" and ohlc.get("stale_ohlc_detected"):
        contradiction_flags.append("scanner_pass_but_ohlc_stale")
    if scanner.get("stale_ohlc_detected") and not ohlc.get("stale_ohlc_detected"):
        contradiction_flags.append("scanner_stale_ohlc_but_cache_scan_fresh")
    if cache.get("cache_present") and not cache.get("meta_present"):
        contradiction_flags.append("live_price_cache_present_without_meta")
    if scanner.get("scan_only") and not scanner.get("fallback_reason"):
        contradiction_flags.append("scan_only_without_fallback_reason")

    fallback_components = _fallback_components(scanner, cache, ohlc, refresh_info)
    fallback_reason = "|".join(fallback_components) if fallback_components else None
    fallback_active = bool(scanner.get("scan_only") or fallback_reason)

    stale_artifacts = []
    if ohlc.get("stale_ohlc_detected"):
        stale_artifacts.append("ohlc_cache")
    if cache.get("cache_stale"):
        stale_artifacts.append("live_price_cache")
    if scanner.get("status") != "PASS":
        stale_artifacts.append("scanner_status")
    if refresh.get("status") in {"NO_REFRESHED_SYMBOLS", "FAILED"}:
        stale_artifacts.append("ohlc_refresh_status")

    fail_flags = []
    warning_flags = []
    if scanner.get("scanner_status") == "MISSING":
        fail_flags.append("scanner_status_missing")
    if str(scanner.get("scanner_status") or "").upper() == "SCAN_ONLY_STALE_OHLC":
        fail_flags.append("scan_only_stale_ohlc")
    if ohlc.get("stale_ohlc_detected"):
        warning_flags.append("ohlc_stale")
    if cache.get("cache_stale"):
        warning_flags.append("live_price_cache_stale")
    if contradiction_flags:
        warning_flags.extend(contradiction_flags)
    if scanner.get("status") == "WARNING":
        warning_flags.append("scanner_freshness_warning")

    overall_status = _status_from_flags(fail_flags, warning_flags)
    return {
        "generated_at_ist": now_ist.isoformat(),
        "overall_status": overall_status,
        "market_data_mode": "MARKET_MODE" if is_trade_window(now_ist) else "OFF_MARKET_OR_RESEARCH",
        "scanner_mode": scanner.get("scanner_mode"),
        "scanner_status": scanner.get("scanner_status"),
        "fresh_symbol_count": ohlc_status.get("fresh_symbol_count"),
        "latest_market_candle": ohlc_status.get("latest_market_candle"),
        "scanner_data_health": ohlc_status.get("scanner_data_health"),
        "stale_ohlc_detected": bool(ohlc.get("stale_ohlc_detected") or scanner.get("stale_ohlc_detected")),
        "stale_symbol_count": max(int(ohlc.get("stale_symbol_count") or 0), int(scanner.get("stale_symbol_count") or 0)),
        "live_price_cache_present": bool(cache.get("cache_present")),
        "live_price_cache_age_seconds": cache.get("cache_age_seconds"),
        "live_price_cache_stale": bool(cache.get("cache_stale")),
        "live_price_cache_meta_present": bool(cache.get("meta_present")),
        "upstox_runtime_visible": bool(cache.get("runtime_visible")),
        "upstox_token_type_visible": bool(cache.get("token_type_visible")),
        "live_price_source": cache.get("source"),
        "fallback_active": fallback_active,
        "fallback_reason": fallback_reason,
        "fallback_components": fallback_components,
        "cache_freshness": cache,
        "ohlc_freshness": ohlc,
        "ohlc_freshness_status_path": str(OHLC_FRESHNESS_STATUS_PATH).replace("\\", "/"),
        "scanner_freshness": scanner,
        "upstox_runtime": {
            "visible": bool(cache.get("runtime_visible")),
            "token_type_visible": bool(cache.get("token_type_visible")),
            "token_type_used": cache.get("token_type_used"),
            "live_source_status": cache.get("live_source_status"),
            "last_successful_live_fetch": cache.get("last_successful_live_fetch"),
            "fallback_reason": cache.get("fallback_reason"),
            "stale_cache_detected": cache.get("stale_cache_detected"),
        },
        "ohlc_refresh_visibility": refresh,
        "contradiction_flags": contradiction_flags,
        "stale_artifacts": stale_artifacts,
        "safety_flags": dict(SAFETY_FLAGS),
        "diagnostic_flags": {
            "fail_flags": fail_flags,
            "warning_flags": warning_flags,
        },
    }


def run_market_data_health_check(path=HEALTH_PATH, now=None):
    payload = build_market_data_health(now=now)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_market_data_health_check(), indent=2, sort_keys=True))
