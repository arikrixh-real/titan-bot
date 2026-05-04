"""
TITAN - Live Price Engine
-------------------------
Safe Upstox LTP fetcher.

IMPORTANT:
- Does NOT spam Upstox search API.
- Uses only known instrument keys from config/upstox_symbols.py.
- If symbol is not mapped, returns None silently.
- setup_engine.py will fallback to cached Close price.
"""

import requests

from config.api_keys import UPSTOX_ACCESS_TOKEN
from config.upstox_symbols import get_instrument_key, normalize_symbol


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


def fetch_price_from_upstox(symbol):
    symbol = normalize_symbol(symbol)

    instrument_key = get_instrument_key(symbol)

    # No spam. Cached data fallback will be used.
    if not instrument_key:
        return None

    if not UPSTOX_ACCESS_TOKEN:
        print("Upstox skipped: UPSTOX_ACCESS_TOKEN missing")
        return None

    try:
        url = "https://api.upstox.com/v2/market-quote/ltp"

        headers = {
            "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}",
            "Accept": "application/json",
        }

        params = {
            "instrument_key": instrument_key
        }

        response = requests.get(url, headers=headers, params=params, timeout=8)

        try:
            data = response.json()
        except Exception:
            return None

        if response.status_code != 200:
            message = str(data)

            # Print token problem clearly, but don't spam every symbol
            if "Invalid token" in message or response.status_code == 401:
                print("Upstox token invalid/expired. Update UPSTOX_ACCESS_TOKEN.")
            return None

        ltp = _extract_ltp(data, instrument_key)
        return safe_float(ltp)

    except Exception:
        return None


def get_live_price(symbol):
    return fetch_price_from_upstox(symbol)