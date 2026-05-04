import requests

from config.api_keys import UPSTOX_ACCESS_TOKEN
from config.upstox_symbols import get_instrument_key


def safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _extract_ltp(data, instrument_key):
    """
    Upstox LTP response keys can vary.
    This safely searches inside data["data"] for last_price / ltp.
    """

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

    # fallback: check first object inside data
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
    try:
        instrument_key = get_instrument_key(symbol)

        if not instrument_key:
            print(f"Upstox fetch skipped {symbol}: instrument key not found")
            return None

        if not UPSTOX_ACCESS_TOKEN:
            print(f"Upstox fetch skipped {symbol}: UPSTOX_ACCESS_TOKEN missing")
            return None

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
            print(f"Upstox fetch error {symbol}: non-json response {response.status_code}")
            return None

        if response.status_code != 200:
            print(f"Upstox fetch error {symbol}: HTTP {response.status_code} {data}")
            return None

        ltp = _extract_ltp(data, instrument_key)
        ltp = safe_float(ltp)

        if ltp is None:
            print(f"Upstox fetch error {symbol}: LTP not found in response")
            return None

        return ltp

    except Exception as e:
        print(f"Upstox fetch error {symbol}: {e}")
        return None


def get_live_price(symbol):
    clean_symbol = str(symbol).replace(".NS", "").upper().strip()
price = fetch_price_from_upstox(clean_symbol)
    return safe_float(price)