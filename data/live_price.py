import os
import requests
from dotenv import load_dotenv

from config.upstox_symbols import get_instrument_key
from data.price_cache import get_cached_price, update_cached_price

load_dotenv()

UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")


def get_live_price_upstox(stock, debug=False):
    if not UPSTOX_ACCESS_TOKEN:
        if debug:
            print("❌ UPSTOX_ACCESS_TOKEN missing")
        return None

    instrument_key = get_instrument_key(stock)

    if not instrument_key:
        if debug:
            print(f"❌ No instrument key for {stock}")
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

        if debug:
            print(f"\n🔍 {stock}")
            print(f"Instrument Key: {instrument_key}")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text[:1000]}")

        if response.status_code != 200:
            return None

        data = response.json()
        quote_data = data.get("data", {})

        if not quote_data:
            return None

        for _, value in quote_data.items():
            price = value.get("last_price") or value.get("ltp")

            if price is not None:
                return round(float(price), 2)

    except Exception as e:
        if debug:
            print(f"❌ Upstox live price error for {stock}: {e}")
        return None

    return None


def get_live_price(symbol, use_cache=True, debug=False):
    stock = str(symbol).replace(".NS", "").upper().strip()

    upstox_price = get_live_price_upstox(stock, debug=debug)

    if upstox_price is not None:
        update_cached_price(stock, upstox_price)
        return upstox_price

    if use_cache:
        cached = get_cached_price(stock)
        if cached is not None:
            if debug:
                print(f"⚠️ Using cached price for {stock}: {cached}")
            return cached

    return None