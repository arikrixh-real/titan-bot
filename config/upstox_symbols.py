import requests
from config.api_keys import UPSTOX_ACCESS_TOKEN

_cached_map = {}


def get_instrument_key(stock):
    if stock in _cached_map:
        return _cached_map[stock]

    try:
        url = "https://api.upstox.com/v2/search/instruments"

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}"
        }

        params = {
            "query": stock
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()

        results = data.get("data", [])

        for item in results:
            exchange = item.get("exchange")
            segment = item.get("segment")
            symbol = item.get("trading_symbol")
            instrument_key = item.get("instrument_key")

            if exchange == "NSE" and symbol == stock and instrument_key:
                _cached_map[stock] = instrument_key
                return instrument_key

    except Exception as e:
        print(f"Instrument fetch error for {stock}: {e}")

    return None