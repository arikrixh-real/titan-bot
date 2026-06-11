"""
TITAN - Live Price Engine
-------------------------
Safe Upstox LTP fetcher.

Fix included:
- Loads read-only UPSTOX_ANALYTICS_TOKEN from D:\\TITAN\\.env using python-dotenv for market data.
- Uses explicit AUTH_REQUIRED status if analytics auth is missing.
- Does NOT spam Upstox search API.
- Uses known instrument keys from config/upstox_symbols.py.
- If symbol is not mapped, returns None silently.
- setup_engine.py will fallback to cached Close price.
"""

import os
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

from config.upstox_symbols import get_instrument_key, normalize_symbol
from data.price_cache import get_cached_price_debug


STATUS_FILE = "data/live_price_status.json"
_STATUS_LOGGED = set()
IST = timezone(timedelta(hours=5, minutes=30))


def _cache_visibility(symbol, max_age_seconds=120):
    try:
        cache_result = get_cached_price_debug(normalize_symbol(symbol), max_age_seconds=max_age_seconds)
    except Exception as exc:
        return {
            "cache_age_seconds": None,
            "stale_cache_detected": True,
            "cache_timestamp": None,
            "cache_status": "CACHE_ERROR",
            "cache_reason": str(exc),
        }

    age_seconds = cache_result.get("age_seconds")
    return {
        "cache_age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "stale_cache_detected": not bool(cache_result.get("fresh")),
        "cache_timestamp": cache_result.get("timestamp"),
        "cache_status": cache_result.get("status"),
        "cache_reason": cache_result.get("reason"),
    }


def _log_status_once(symbol, status, message="", source="UNKNOWN"):
    key = (status, source, str(message)[:120])
    if key in _STATUS_LOGGED:
        return
    _STATUS_LOGGED.add(key)
    print(
        f"[UpstoxStatus] symbol={normalize_symbol(symbol)} | "
        f"status={status} | source={source} | reason={message}"
    )


def _write_status(
    symbol,
    status,
    message="",
    price=None,
    source="UNKNOWN",
    token_type_used="MISSING",
    cache_age_seconds=None,
    fallback_reason=None,
    live_source_status=None,
    last_successful_live_fetch=None,
    stale_cache_detected=None,
):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        normalized = normalize_symbol(symbol)
        cache_visibility = _cache_visibility(normalized)
        if cache_age_seconds is None:
            cache_age_seconds = cache_visibility.get("cache_age_seconds")
        if stale_cache_detected is None:
            stale_cache_detected = cache_visibility.get("stale_cache_detected")
        if fallback_reason is None and str(source).upper() in {"CACHE", "LIVE_PRICE_CACHE", "UNKNOWN", "NONE"}:
            fallback_reason = message or None
        if live_source_status is None:
            live_source_status = status
        if last_successful_live_fetch is None and str(source).upper() == "UPSTOX" and str(status).upper() == "ACTIVE":
            last_successful_live_fetch = datetime.now(IST).isoformat()
        payload = {
            "symbol": normalized,
            "status": status,
            "last_price": price,
            "source": source,
            "token_type_used": token_type_used,
            "timestamp": datetime.now().isoformat(),
            "timestamp_ist": datetime.now(IST).isoformat(),
            "reason": message,
            "cache_age_seconds": cache_age_seconds,
            "fallback_reason": fallback_reason,
            "live_source_status": live_source_status,
            "last_successful_live_fetch": last_successful_live_fetch,
            "stale_cache_detected": bool(stale_cache_detected),
            "cache_status": cache_visibility.get("cache_status"),
            "cache_timestamp": cache_visibility.get("cache_timestamp"),
        }
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _shared_market_state_price(symbol, max_age_seconds=120):
    try:
        from runtime_market_state import get_symbol_state
    except Exception:
        return None
    state = get_symbol_state(symbol)
    if not isinstance(state, dict):
        return None
    price = safe_float(state.get("ltp"))
    age = safe_float(state.get("ltp_age_seconds"))
    if price is None:
        return None
    fresh = age is not None and age <= max_age_seconds
    return {
        "price": price if fresh else None,
        "stale_price": price if not fresh else None,
        "source": "SHARED_MARKET_STATE",
        "status": "ACTIVE" if fresh else "STALE",
        "reason": "Fresh shared market state" if fresh else "Shared market state stale or untimestamped",
        "token_type_used": state.get("token_type_used") or "UNKNOWN",
        "cache_age_seconds": age,
        "fallback_reason": None if fresh else "shared_market_state_stale",
        "live_source_status": "ACTIVE" if fresh else "STALE",
        "last_successful_live_fetch": state.get("ltp_timestamp_ist") if fresh else None,
        "stale_cache_detected": not fresh,
    }


def _cache_price_result(symbol, max_age_seconds=120):
    try:
        cache_result = get_cached_price_debug(symbol, max_age_seconds=max_age_seconds)
    except Exception as exc:
        return {
            "price": None,
            "source": "LIVE_PRICE_CACHE",
            "status": "CACHE_ERROR",
            "reason": str(exc),
            "token_type_used": "UNKNOWN",
            "cache_age_seconds": None,
            "fallback_reason": str(exc),
            "live_source_status": "CACHE_ERROR",
            "last_successful_live_fetch": None,
            "stale_cache_detected": True,
        }
    price = safe_float(cache_result.get("price"))
    fresh = bool(cache_result.get("fresh") and price is not None)
    return {
        "price": price if fresh else None,
        "source": "LIVE_PRICE_CACHE",
        "raw_cache_source": cache_result.get("source"),
        "status": "CACHE_FRESH" if fresh else "STALE",
        "reason": cache_result.get("reason") or ("Fresh timestamped cache" if fresh else "Cache missing, stale, or untimestamped"),
        "token_type_used": "UNKNOWN",
        "cache_age_seconds": cache_result.get("age_seconds"),
        "fallback_reason": None if fresh else cache_result.get("reason"),
        "live_source_status": "CACHE_FRESH" if fresh else "STALE",
        "last_successful_live_fetch": cache_result.get("timestamp") if fresh else None,
        "stale_cache_detected": not fresh,
    }


def fetch_price_from_upstox(symbol, use_cache=True, debug=False):
    result = fetch_price_from_upstox_debug(symbol, use_cache=use_cache, debug=debug)
    return result.get("price")


def fetch_price_from_upstox_debug(symbol, use_cache=True, debug=False):
    symbol = normalize_symbol(symbol)
    instrument_key = get_instrument_key(symbol)
    token_type_used = "UNKNOWN"

    if not instrument_key:
        reason = "Instrument key missing"
        _write_status(symbol, "UNMAPPED", reason, None, "NONE", token_type_used, live_source_status="UNMAPPED")
        _log_status_once(symbol, "UNMAPPED", reason, "UNKNOWN")
        return {
            "price": None,
            "source": "UNKNOWN",
            "status": "UNMAPPED",
            "reason": reason,
            "token_type_used": token_type_used,
            "cache_age_seconds": _cache_visibility(symbol).get("cache_age_seconds"),
            "fallback_reason": reason,
            "live_source_status": "UNMAPPED",
            "last_successful_live_fetch": None,
            "stale_cache_detected": _cache_visibility(symbol).get("stale_cache_detected"),
        }

    shared_result = _shared_market_state_price(symbol)
    if shared_result and shared_result.get("price") is not None and shared_result.get("status") == "ACTIVE":
        result = shared_result
    elif use_cache:
        result = _cache_price_result(symbol)
        if result.get("price") is None and shared_result is not None:
            result = shared_result
    else:
        result = shared_result
    if result is None:
        result = {
            "price": None,
            "source": "UNKNOWN",
            "status": "UNKNOWN",
            "reason": "Canonical cache/shared market state unavailable",
            "token_type_used": "UNKNOWN",
            "cache_age_seconds": None,
            "fallback_reason": "canonical_market_data_unavailable",
            "live_source_status": "UNKNOWN",
            "last_successful_live_fetch": None,
            "stale_cache_detected": True,
        }
    status = result.get("status") or "UNKNOWN"
    reason = result.get("reason") or status
    source = result.get("source") or "UNKNOWN"
    _write_status(
        symbol,
        status,
        reason,
        result.get("price"),
        source,
        result.get("token_type_used") or "UNKNOWN",
        cache_age_seconds=result.get("cache_age_seconds"),
        fallback_reason=result.get("fallback_reason"),
        live_source_status=result.get("live_source_status") or status,
        last_successful_live_fetch=result.get("last_successful_live_fetch"),
        stale_cache_detected=result.get("stale_cache_detected"),
    )
    _log_status_once(symbol, status, reason, source)
    if debug:
        print(f"[LivePriceCompat] {symbol}: source={source} status={status} reason={reason}")
    return result


def get_live_price(symbol, use_cache=True, debug=False):
    return fetch_price_from_upstox(symbol, use_cache=use_cache, debug=debug)


def _debug_source(raw_result):
    source = str(raw_result.get("source") or "").strip().upper()
    status = str(raw_result.get("status") or raw_result.get("live_source_status") or "").strip().upper()
    price = safe_float(raw_result.get("price"))

    if source == "SHARED_MARKET_STATE" and status == "ACTIVE" and price is not None:
        return "SHARED_MARKET_STATE"
    if status == "MARKET_CLOSED":
        return "MARKET_CLOSED"
    if source in {"LIVE_PRICE_CACHE", "CACHE"} and price is not None:
        return "LIVE_PRICE_CACHE"
    if price is not None:
        return "FALLBACK"
    return "ERROR"


def _normalize_debug_result(original_symbol, raw_result):
    normalized = normalize_symbol(original_symbol)
    raw_result = raw_result if isinstance(raw_result, dict) else {}
    ltp = safe_float(raw_result.get("price"))
    source = _debug_source(raw_result)
    error = raw_result.get("reason") or raw_result.get("error")
    fetch_status = "OK" if ltp is not None and source != "ERROR" else "FAILED"
    status = str(raw_result.get("status") or raw_result.get("live_source_status") or "").strip().upper()
    legacy_source = raw_result.get("source")
    legacy_status = status
    if source == "MARKET_CLOSED" and ltp is None:
        fetch_status = "FAILED"

    proof = {
        "symbol": original_symbol,
        "normalized_symbol": normalized,
        "instrument_key": get_instrument_key(normalized),
        "ltp": ltp,
        "source": source,
        "fetch_status": fetch_status,
        "token_type_used": raw_result.get("token_type_used") or "UNKNOWN",
        "timestamp_ist": datetime.now(IST).isoformat(),
        "error": None if fetch_status == "OK" and source in {"SHARED_MARKET_STATE", "LIVE_PRICE_CACHE"} else error,
        # Backward-compatible aliases for existing debug callers.
        "price": ltp,
        "status": "ACTIVE" if source in {"SHARED_MARKET_STATE", "LIVE_PRICE_CACHE"} and fetch_status == "OK" else status,
        "reason": raw_result.get("reason"),
        "legacy_source": legacy_source,
        "legacy_status": legacy_status,
        "live_source_status": raw_result.get("live_source_status") or status,
        "cache_age_seconds": raw_result.get("cache_age_seconds"),
        "fallback_reason": raw_result.get("fallback_reason"),
        "last_successful_live_fetch": raw_result.get("last_successful_live_fetch"),
        "stale_cache_detected": raw_result.get("stale_cache_detected"),
    }
    return proof


def get_live_price_debug(symbol, use_cache=True, debug=False):
    try:
        raw_result = fetch_price_from_upstox_debug(symbol, use_cache=use_cache, debug=debug)
        return _normalize_debug_result(symbol, raw_result)
    except Exception as exc:
        normalized = normalize_symbol(symbol)
        return {
            "symbol": symbol,
            "normalized_symbol": normalized,
            "instrument_key": get_instrument_key(normalized),
            "ltp": None,
            "source": "ERROR",
            "fetch_status": "FAILED",
            "token_type_used": "UNKNOWN",
            "timestamp_ist": datetime.now(IST).isoformat(),
            "error": str(exc),
            "price": None,
            "status": "ERROR",
            "reason": str(exc),
            "legacy_source": "UNKNOWN",
            "legacy_status": "ERROR",
            "live_source_status": "ERROR",
        }


def get_strict_fresh_price_debug(symbol, max_age_seconds=120, debug=False):
    """
    Strict price helper for TP/SL closure.
    Accepts only a real active Upstox price, or an explicitly timestamped fresh
    cache price. It never returns entry/last_price fallbacks.
    """
    normalized = normalize_symbol(symbol)

    try:
        live_result = fetch_price_from_upstox_debug(
            normalized,
            use_cache=False,
            debug=debug,
        )
    except Exception as e:
        live_result = {
            "price": None,
            "source": "UNKNOWN",
            "status": "API_ERROR",
            "reason": str(e),
            "token_type_used": "UNKNOWN",
        }

    price = safe_float(live_result.get("price"))
    source = str(live_result.get("source") or "").upper()
    status = str(live_result.get("status") or "").upper()

    if price is not None and source == "SHARED_MARKET_STATE" and status == "ACTIVE":
        age = live_result.get("cache_age_seconds")
        return {
            "price": price,
            "source": "SHARED_MARKET_STATE",
            "status": "ACTIVE",
            "timestamp": live_result.get("last_successful_live_fetch") or datetime.now().isoformat(),
            "fresh": True,
            "age_seconds": age,
            "max_age_seconds": max_age_seconds,
            "reason": live_result.get("reason") or "Fresh shared market state",
            "token_type_used": live_result.get("token_type_used"),
        }

    try:
        cache_result = get_cached_price_debug(normalized, max_age_seconds=max_age_seconds)
    except Exception as e:
        cache_result = {
            "price": None,
            "source": "LIVE_PRICE_CACHE",
            "status": "CACHE_ERROR",
            "timestamp": None,
            "fresh": False,
            "age_seconds": None,
            "max_age_seconds": max_age_seconds,
            "reason": str(e),
        }
    cache_price = safe_float(cache_result.get("price"))

    if cache_price is not None and cache_result.get("fresh"):
        if debug:
            print(
                f"[StrictPrice] {normalized}: using fresh timestamped cache "
                f"age={cache_result.get('age_seconds')}s"
            )
        return {
            "price": cache_price,
            "source": cache_result.get("source") or "LIVE_PRICE_CACHE",
            "status": "CACHE_FRESH",
            "timestamp": cache_result.get("timestamp"),
            "fresh": True,
            "age_seconds": cache_result.get("age_seconds"),
            "max_age_seconds": max_age_seconds,
            "reason": cache_result.get("reason"),
            "live_status": live_result.get("status"),
            "live_source": live_result.get("source"),
            "live_reason": live_result.get("reason"),
            "token_type_used": live_result.get("token_type_used"),
        }

    reason = (
        f"PRICE_STALE: live source={live_result.get('source')} "
        f"status={live_result.get('status')} reason={live_result.get('reason')}; "
        f"cache status={cache_result.get('status')} reason={cache_result.get('reason')}"
    )
    if debug:
        print(f"[StrictPrice] {normalized}: {reason}")

    return {
        "price": None,
        "source": "UNKNOWN",
        "status": "PRICE_STALE",
        "timestamp": cache_result.get("timestamp"),
        "fresh": False,
        "age_seconds": cache_result.get("age_seconds"),
        "max_age_seconds": max_age_seconds,
        "reason": reason,
        "live_status": live_result.get("status"),
        "live_source": live_result.get("source"),
        "live_reason": live_result.get("reason"),
        "cache_price": cache_result.get("price"),
        "cache_status": cache_result.get("status"),
        "token_type_used": live_result.get("token_type_used"),
    }


if __name__ == "__main__":
    print("Testing RELIANCE live price...")
    print(get_live_price("RELIANCE"))
