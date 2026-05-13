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
from data.price_cache import get_cached_price, update_cached_price
from utils.market_hours import is_trade_window


STATUS_FILE = "data/live_price_status.json"


def _write_status(symbol, status, message="", price=None, source="UNKNOWN"):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        payload = {
            "symbol": normalize_symbol(symbol),
            "status": status,
            "last_price": price,
            "source": source,
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
    1. Environment variable from .env
    2. config.api_keys.UPSTOX_ACCESS_TOKEN
    """
    token = os.getenv("UPSTOX_ACCESS_TOKEN")

    if token and str(token).strip():
        return str(token).strip()

    if CONFIG_UPSTOX_ACCESS_TOKEN and str(CONFIG_UPSTOX_ACCESS_TOKEN).strip():
        return str(CONFIG_UPSTOX_ACCESS_TOKEN).strip()

    return None


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
    symbol = normalize_symbol(symbol)
    instrument_key = get_instrument_key(symbol)

    # No spam. Cached data fallback will be used.
    if not instrument_key:
        _write_status(symbol, "UNMAPPED", "Instrument key missing", None, "NONE")
        return None

    cached_price = safe_float(get_cached_price(symbol)) if use_cache else None

    if not is_trade_window():
        _write_status(symbol, "MARKET_CLOSED", "Market closed; using cache if available", cached_price, "CACHE" if cached_price is not None else "NONE")
        return cached_price

    access_token = get_upstox_token()

    if not access_token:
        if debug:
            print("Upstox skipped: UPSTOX_ACCESS_TOKEN missing")
        _write_status(symbol, "TOKEN_MISSING", "UPSTOX_ACCESS_TOKEN missing; using cache if available", cached_price, "CACHE" if cached_price is not None else "NONE")
        return cached_price

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
            _write_status(symbol, "BAD_RESPONSE", "Response was not valid JSON; using cache if available", cached_price, "CACHE" if cached_price is not None else "NONE")
            return cached_price

        if response.status_code != 200:
            message = str(data)

            if response.status_code == 401 or "Invalid token" in message or "invalid token" in message.lower():
                if debug:
                    print("Upstox token invalid/expired. Update UPSTOX_ACCESS_TOKEN.")
                _write_status(symbol, "TOKEN_INVALID", "Upstox token invalid/expired; using cache if available", cached_price, "CACHE" if cached_price is not None else "NONE")
            else:
                if debug:
                    print(f"Upstox error: HTTP {response.status_code}")
                _write_status(symbol, "HTTP_ERROR", f"HTTP {response.status_code}; using cache if available", cached_price, "CACHE" if cached_price is not None else "NONE")

            return cached_price

        ltp = _extract_ltp(data, instrument_key)
        price = safe_float(ltp)
        if price is not None:
            update_cached_price(symbol, price)
            _write_status(symbol, "ACTIVE", "Live price fetched", price, "UPSTOX")
            return price
        _write_status(symbol, "NO_PRICE", "Upstox response had no price; using cache if available", cached_price, "CACHE" if cached_price is not None else "NONE")
        return cached_price

    except Exception as e:
        if debug:
            print(f"Upstox live price error: {e}")
        reason = "API/socket failure; using cache if available" if "WinError 10013" in str(e) else f"{e}; using cache if available"
        _write_status(symbol, "ERROR", reason, cached_price, "CACHE" if cached_price is not None else "NONE")
        return cached_price


def get_live_price(symbol, use_cache=True, debug=False):
    return fetch_price_from_upstox(symbol, use_cache=use_cache, debug=debug)


if __name__ == "__main__":
    print("Testing RELIANCE live price...")
    print(get_live_price("RELIANCE"))
