import requests

# 🔐 your Upstox access token (already in env or config)
from config.api_keys import UPSTOX_ACCESS_TOKEN
from config.upstox_symbols import get_instrument_key


def safe_float(value):
    try:
        return float(value)
    except:
        return None


def fetch_price_from_upstox(symbol):
    try:
        instrument_key = get_instrument_key(symbol)

        url = "https://api.upstox.com/v2/market-quote/ltp"

        headers = {
            "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}",
            "Accept": "application/json",
        }

        params = {
            "instrument_key": instrument_key
        }

        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        ltp = data["data"][instrument_key]["last_price"]

        return ltp

    except Exception as e:
        print(f"Upstox fetch error {symbol}: {e}")
        return None


def get_live_price(symbol):
    try:
        price = fetch_price_from_upstox(symbol)

        price = safe_float(price)

        if price is None:
            return None

        return price

    except Exception as e:
        print(f"Live price error {symbol}: {e}")
        return None