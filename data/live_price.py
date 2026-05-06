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
import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

try:
    from config.api_keys import UPSTOX_ACCESS_TOKEN as CONFIG_UPSTOX_ACCESS_TOKEN
except Exception:
    CONFIG_UPSTOX_ACCESS_TOKEN = None

from config.upstox_symbols import get_instrument_key, normalize_symbol


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


def fetch_price_from_upstox(symbol):
    symbol = normalize_symbol(symbol)
    instrument_key = get_instrument_key(symbol)

    # No spam. Cached data fallback will be used.
    if not instrument_key:
        return None

    access_token = get_upstox_token()

    if not access_token:
        print("Upstox skipped: UPSTOX_ACCESS_TOKEN missing")
        return None

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
            print("Upstox error: response was not valid JSON")
            return None

        if response.status_code != 200:
            message = str(data)

            if response.status_code == 401 or "Invalid token" in message or "invalid token" in message.lower():
                print("Upstox token invalid/expired. Update UPSTOX_ACCESS_TOKEN.")
            else:
                print(f"Upstox error: HTTP {response.status_code}")

            return None

        ltp = _extract_ltp(data, instrument_key)
        return safe_float(ltp)

    except Exception as e:
        print(f"Upstox live price error: {e}")
        return None


def get_live_price(symbol):
    return fetch_price_from_upstox(symbol)


if __name__ == "__main__":
    print("Testing RELIANCE live price...")
    print(get_live_price("RELIANCE"))