import os
import requests
from dotenv import load_dotenv

load_dotenv()

UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

_cached_map = {}


MANUAL_INSTRUMENT_KEYS = {
    "RELIANCE": "NSE_EQ|INE002A01018",
    "TCS": "NSE_EQ|INE467B01029",
    "INFY": "NSE_EQ|INE009A01021",
    "HDFCBANK": "NSE_EQ|INE040A01034",
    "ICICIBANK": "NSE_EQ|INE090A01021",
    "SBIN": "NSE_EQ|INE062A01020",
    "AXISBANK": "NSE_EQ|INE238A01034",
    "KOTAKBANK": "NSE_EQ|INE237A01028",
    "LT": "NSE_EQ|INE018A01030",
    "ITC": "NSE_EQ|INE154A01025",
    "BHARTIARTL": "NSE_EQ|INE397D01024",
    "HINDUNILVR": "NSE_EQ|INE030A01027",
    "MARUTI": "NSE_EQ|INE585B01010",
    "TATAMOTORS": "NSE_EQ|INE155A01022",
    "TATASTEEL": "NSE_EQ|INE081A01020",
    "ADANIENT": "NSE_EQ|INE423A01024",
    "ADANIPORTS": "NSE_EQ|INE742F01042",
    "GRASIM": "NSE_EQ|INE047A01021",
    "NTPC": "NSE_EQ|INE733E01010",
    "ONGC": "NSE_EQ|INE213A01029",
    "PFC": "NSE_EQ|INE134E01011",
}


def normalize_symbol(stock):
    stock = str(stock).upper().strip()

    # yfinance NSE format cleanup
    if stock.endswith(".NS"):
        stock = stock[:-3]

    # general cleanup
    stock = stock.replace("NSE:", "").replace("NSE_EQ:", "").replace("NSE_EQ|", "")
    stock = stock.strip()

    return stock


def get_instrument_key(stock):
    stock = normalize_symbol(stock)

    if stock in _cached_map:
        return _cached_map[stock]

    if stock in MANUAL_INSTRUMENT_KEYS:
        _cached_map[stock] = MANUAL_INSTRUMENT_KEYS[stock]
        return MANUAL_INSTRUMENT_KEYS[stock]

    if not UPSTOX_ACCESS_TOKEN:
        return None

    try:
        url = "https://api.upstox.com/v2/search/instruments"

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}",
        }

        params = {
            "query": stock
        }

        response = requests.get(url, headers=headers, params=params, timeout=8)

        try:
            data = response.json()
        except Exception:
            print(f"Upstox instrument search error for {stock}: non-json response")
            return None

        if response.status_code != 200:
            print(f"Upstox instrument search error for {stock}: HTTP {response.status_code} {data}")
            return None

        results = data.get("data", [])

        if isinstance(results, dict):
            results = list(results.values())

        for item in results:
            if not isinstance(item, dict):
                continue

            exchange = str(item.get("exchange", "")).upper()
            trading_symbol = str(item.get("trading_symbol", "")).upper().strip()
            instrument_key = item.get("instrument_key")

            if exchange in ["NSE", "NSE_EQ"] and trading_symbol == stock and instrument_key:
                _cached_map[stock] = instrument_key
                return instrument_key

    except Exception as e:
        print(f"Upstox instrument search error for {stock}: {e}")
        return None

    return None