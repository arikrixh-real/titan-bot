import json
import os
from datetime import datetime, timedelta, timezone

CACHE_FILE = "data/live_price_cache.json"
META_CACHE_FILE = "data/live_price_cache_meta.json"
IST = timezone(timedelta(hours=5, minutes=30))


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


def load_cache_meta():
    if not os.path.exists(META_CACHE_FILE):
        return {}

    try:
        with open(META_CACHE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}

    return payload if isinstance(payload, dict) else {}


def save_cache_meta(cache_meta):
    os.makedirs(os.path.dirname(META_CACHE_FILE), exist_ok=True)
    with open(META_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_meta, f, indent=4, sort_keys=True)


def update_cached_price_meta(symbol, price, source="upstox_or_runtime"):
    if price is None:
        return False

    cache_meta = load_cache_meta()
    cache_meta[symbol] = {
        "price": price,
        "updated_at_ist": datetime.now(IST).isoformat(),
        "source": source,
        "status": "UPDATED",
    }
    save_cache_meta(cache_meta)
    return True


def get_cached_price(symbol):
    cache = load_cache()
    return cache.get(symbol)


def update_cached_price(symbol, price, source="upstox_or_runtime"):
    if price is None:
        return

    cache = load_cache()
    cache[symbol] = price
    save_cache(cache)
    update_cached_price_meta(symbol, price, source=source)
