"""
TITAN - Live Price Engine
-------------------------
Safe Upstox LTP fetcher.

Fix included:
- Loads UPSTOX_ACCESS_TOKEN from D:\\TITAN\\.env using python-dotenv.
- Falls back safely if config.api_keys token is empty.
- Does NOT spam Upstox search API.
- Uses known instrument keys from config/upstox_symbols.py.
- If symbol is not mapped, returns None silently.
- setup_engine.py will fallback to cached Close price.
"""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

try:
    from config.api_keys import UPSTOX_ACCESS_TOKEN as CONFIG_UPSTOX_ACCESS_TOKEN
except Exception:
    CONFIG_UPSTOX_ACCESS_TOKEN = None

from config.upstox_symbols import get_instrument_key, normalize_symbol
from data.price_cache import get_cached_price, get_cached_price_debug, update_cached_price
from utils.market_hours import is_trade_window


STATUS_FILE = "data/live_price_status.json"
_STATUS_LOGGED = set()


def _log_status_once(symbol, status, message="", source="UNKNOWN"):
    key = (status, source, str(message)[:120])
    if key in _STATUS_LOGGED:
        return
    _STATUS_LOGGED.add(key)
    print(
        f"[UpstoxStatus] symbol={normalize_symbol(symbol)} | "
        f"status={status} | source={source} | reason={message}"
    )


def _write_status(symbol, status, message="", price=None, source="UNKNOWN", token_type_used="MISSING"):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        payload = {
            "symbol": normalize_symbol(symbol),
            "status": status,
            "last_price": price,
            "source": source,
            "token_type_used": token_type_used,
            "timestamp": datetime.now().isoformat(),
            "reason": message,
        }
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def get_upstox_token():
    """
    Priority:
    1. UPSTOX_ANALYTICS_TOKEN
    2. UPSTOX_EXTENDED_TOKEN
    3. UPSTOX_ACCESS_TOKEN
    4. config.api_keys.UPSTOX_ACCESS_TOKEN
    """
    token_sources = [
        ("UPSTOX_ANALYTICS_TOKEN", "ANALYTICS_TOKEN"),
        ("UPSTOX_EXTENDED_TOKEN", "EXTENDED_TOKEN"),
        ("UPSTOX_ACCESS_TOKEN", "ACCESS_TOKEN"),
    ]

    for env_key, token_type in token_sources:
        token = os.getenv(env_key)
        if token and str(token).strip():
            return str(token).strip(), token_type


    if CONFIG_UPSTOX_ACCESS_TOKEN and str(CONFIG_UPSTOX_ACCESS_TOKEN).strip():
        return str(CONFIG_UPSTOX_ACCESS_TOKEN).strip(), "ACCESS_TOKEN"

    return None, "MISSING"


def safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _extract_ltp(data, instrument_key):
    if not isinstance(data, dict):
        return None

    payload = data.get("data")

    if not isinstance(payload, dict):
        return None

    possible_keys = [
        instrument_key,
        str(instrument_key).replace("|", ":"),
        str(instrument_key).replace(":", "|"),
    ]

    for key in possible_keys:
        item = payload.get(key)
        if isinstance(item, dict):
            return (
                item.get("last_price")
                or item.get("ltp")
                or item.get("lastPrice")
            )

    for item in payload.values():
        if isinstance(item, dict):
            price = (
                item.get("last_price")
                or item.get("ltp")
                or item.get("lastPrice")
            )
            if price is not None:
                return price

    return None


def fetch_price_from_upstox(symbol, use_cache=True, debug=False):
    result = fetch_price_from_upstox_debug(symbol, use_cache=use_cache, debug=debug)
    return result.get("price")


def fetch_price_from_upstox_debug(symbol, use_cache=True, debug=False):
    symbol = normalize_symbol(symbol)
    instrument_key = get_instrument_key(symbol)
    access_token, token_type_used = get_upstox_token()

    # No spam. Cached data fallback will be used.
    if not instrument_key:
        reason = "Instrument key missing"
        _write_status(symbol, "UNMAPPED", reason, None, "NONE", token_type_used)
        _log_status_once(symbol, "UNMAPPED", reason, "UNKNOWN")
        return {
            "price": None,
            "source": "UNKNOWN",
            "status": "UNMAPPED",
            "reason": reason,
            "token_type_used": token_type_used,
        }

    cached_price = safe_float(get_cached_price(symbol)) if use_cache else None

    if not is_trade_window():
        reason = "Market closed; using cache if available"
        source = "LIVE_PRICE_CACHE" if cached_price is not None else "UNKNOWN"
        _write_status(symbol, "MARKET_CLOSED", reason, cached_price, "CACHE" if cached_price is not None else "NONE", token_type_used)
        _log_status_once(symbol, "MARKET_CLOSED", reason, source)
        return {
            "price": cached_price,
            "source": source,
            "status": "MARKET_CLOSED",
            "reason": reason,
            "token_type_used": token_type_used,
        }

    if not access_token:
        if debug:
            print("Upstox skipped: Upstox token missing")
        reason = "Upstox token missing; using cache if available"
        source = "LIVE_PRICE_CACHE" if cached_price is not None else "UNKNOWN"
        _write_status(symbol, "TOKEN_MISSING", reason, cached_price, "CACHE" if cached_price is not None else "NONE", token_type_used)
        _log_status_once(symbol, "TOKEN_MISSING", reason, source)
        return {
            "price": cached_price,
            "source": source,
            "status": "TOKEN_MISSING",
            "reason": reason,
            "token_type_used": token_type_used,
        }

    try:
        url = "https://api.upstox.com/v2/market-quote/ltp"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        params = {
            "instrument_key": instrument_key
        }

        response = requests.get(url, headers=headers, params=params, timeout=8)

        try:
            data = response.json()
        except Exception:
            if debug:
                print("Upstox error: response was not valid JSON")
            reason = "Response was not valid JSON; using cache if available"
            source = "LIVE_PRICE_CACHE" if cached_price is not None else "UNKNOWN"
            _write_status(symbol, "BAD_RESPONSE", reason, cached_price, "CACHE" if cached_price is not None else "NONE", token_type_used)
            _log_status_once(symbol, "BAD_RESPONSE", reason, source)
            return {
                "price": cached_price,
                "source": source,
                "status": "BAD_RESPONSE",
                "reason": reason,
                "token_type_used": token_type_used,
            }

        if response.status_code != 200:
            message = str(data)

            if response.status_code == 401 or "Invalid token" in message or "invalid token" in message.lower():
                if debug:
                    print("Upstox token invalid/expired. Update UPSTOX_ACCESS_TOKEN.")
                status = "TOKEN_INVALID"
                reason = "Upstox token invalid/expired; using cache if available"
            else:
                if debug:
                    print(f"Upstox error: HTTP {response.status_code}")
                status = "HTTP_ERROR"
                reason = f"HTTP {response.status_code}; using cache if available"

            source = "LIVE_PRICE_CACHE" if cached_price is not None else "UNKNOWN"
            _write_status(symbol, status, reason, cached_price, "CACHE" if cached_price is not None else "NONE", token_type_used)
            _log_status_once(symbol, status, reason, source)

            return {
                "price": cached_price,
                "source": source,
                "status": status,
                "reason": reason,
                "token_type_used": token_type_used,
            }

        ltp = _extract_ltp(data, instrument_key)
        price = safe_float(ltp)
        if price is not None:
            update_cached_price(symbol, price, source="UPSTOX")
            _write_status(symbol, "ACTIVE", "Live price fetched", price, "UPSTOX", token_type_used)
            return {
                "price": price,
                "source": "UPSTOX",
                "status": "ACTIVE",
                "reason": "Live price fetched",
                "token_type_used": token_type_used,
            }
        reason = "Upstox response had no price; using cache if available"
        source = "LIVE_PRICE_CACHE" if cached_price is not None else "UNKNOWN"
        _write_status(symbol, "NO_PRICE", reason, cached_price, "CACHE" if cached_price is not None else "NONE", token_type_used)
        _log_status_once(symbol, "NO_PRICE", reason, source)
        return {
            "price": cached_price,
            "source": source,
            "status": "NO_PRICE",
            "reason": reason,
            "token_type_used": token_type_used,
        }

    except Exception as e:
        if debug:
            print(f"Upstox live price error: {e}")
        error_text = str(e)
        if "WinError 10013" in error_text:
            status = "NETWORK_BLOCKED"
            reason = "Socket blocked while calling Upstox; using cache if available"
        elif "getaddrinfo failed" in error_text or "NameResolutionError" in error_text:
            status = "DNS_ERROR"
            reason = "DNS resolution failed while calling Upstox; using cache if available"
        else:
            status = "API_ERROR"
            reason = f"{error_text}; using cache if available"
        source = "LIVE_PRICE_CACHE" if cached_price is not None else "UNKNOWN"
        _write_status(symbol, status, reason, cached_price, "CACHE" if cached_price is not None else "NONE", token_type_used)
        _log_status_once(symbol, status, reason, source)
        return {
            "price": cached_price,
            "source": source,
            "status": status,
            "reason": reason,
            "token_type_used": token_type_used,
        }


def get_live_price(symbol, use_cache=True, debug=False):
    return fetch_price_from_upstox(symbol, use_cache=use_cache, debug=debug)


def get_live_price_debug(symbol, use_cache=True, debug=False):
    return fetch_price_from_upstox_debug(symbol, use_cache=use_cache, debug=debug)


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

    if price is not None and source == "UPSTOX" and status == "ACTIVE":
        return {
            "price": price,
            "source": "UPSTOX",
            "status": "ACTIVE",
            "timestamp": datetime.now().isoformat(),
            "fresh": True,
            "age_seconds": 0,
            "max_age_seconds": max_age_seconds,
            "reason": live_result.get("reason") or "Live Upstox price fetched",
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
