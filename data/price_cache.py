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


def _parse_cache_timestamp(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 9999999999 else value
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)

    return parsed


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def get_cached_price(symbol):
    cache = load_cache()
    return cache.get(symbol)


def get_cached_price_debug(symbol, max_age_seconds=120):
    """
    Timestamp-aware cache read for strict TP/SL validation.
    Flat legacy cache values are returned as stale because they do not carry
    enough provenance for closure decisions.
    """
    cache = load_cache()
    cache_meta = load_cache_meta()

    price = _safe_float(cache.get(symbol))
    meta = cache_meta.get(symbol)

    if price is None and isinstance(meta, dict):
        price = _safe_float(meta.get("price"))

    timestamp = None
    source = "LIVE_PRICE_CACHE"
    if isinstance(meta, dict):
        timestamp = _parse_cache_timestamp(
            meta.get("updated_at_ist")
            or meta.get("updated_at")
            or meta.get("timestamp")
            or meta.get("timestamp_ist")
        )
        source = meta.get("source") or source

    now = datetime.now(timezone.utc)
    age_seconds = None
    is_fresh = False

    if timestamp is not None:
        age_seconds = max(0.0, (now - timestamp.astimezone(timezone.utc)).total_seconds())
        is_fresh = age_seconds <= max_age_seconds

    return {
        "price": price,
        "source": source,
        "status": "CACHE_FRESH" if price is not None and is_fresh else "CACHE_STALE",
        "timestamp": timestamp.isoformat() if timestamp is not None else None,
        "fresh": bool(price is not None and is_fresh),
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
        "reason": "Fresh timestamped cache" if price is not None and is_fresh else "Cache missing, stale, or untimestamped",
    }


def update_cached_price(symbol, price, source="upstox_or_runtime"):
    if price is None:
        return

    cache = load_cache()
    cache[symbol] = price
    save_cache(cache)
    update_cached_price_meta(symbol, price, source=source)
