import json
import os

CACHE_FILE = "data/live_price_cache.json"


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}

    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4)


def get_cached_price(symbol):
    cache = load_cache()
    return cache.get(symbol)


def update_cached_price(symbol, price):
    if price is None:
        return

    cache = load_cache()
    cache[symbol] = price
    save_cache(cache)
