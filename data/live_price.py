import os
import requests

from config.upstox_symbols import get_instrument_key
from data.price_cache import get_cached_price, update_cached_price


UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")


def get_live_price_upstox(stock):
    if not UPSTOX_ACCESS_TOKEN:
        return None

    instrument_key = get_instrument_key(stock)

    if not instrument_key:
        return None

    try:
        url = "https://api.upstox.com/v2/market-quote/ltp"

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}"
        }

        params = {
            "instrument_key": instrument_key
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()

        quote_data = data.get("data", {})

        for _, value in quote_data.items():
            price = value.get("last_price")
            if price:
                return round(float(price), 2)

    except Exception:
        return None

    return None


def get_live_price(symbol):
    stock = symbol.replace(".NS", "")
    cached = get_cached_price(stock)

    upstox_price = get_live_price_upstox(stock)

    if upstox_price is not None:
        update_cached_price(stock, upstox_price)
        return upstox_price

    if cached is not None:
        return cached

    return None