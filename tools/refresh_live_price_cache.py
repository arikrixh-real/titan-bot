"""
Read-only Upstox LTP cache refresher for TITAN dashboards.

This tool only reads market data and writes cache/evidence files. It does not
import execution modules and does not place orders.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.upstox_symbols import MANUAL_INSTRUMENT_KEYS, get_instrument_key, normalize_symbol
from data.live_price import get_upstox_token, safe_float
from data.price_cache import load_cache, save_cache, save_cache_meta


IST = timezone(timedelta(hours=5, minutes=30))
RUNTIME_META_PATH = ROOT / "data" / "runtime" / "live_price_cache_meta.json"
STATUS_PATH = ROOT / "data" / "live_price_status.json"
UPSTOX_QUOTE_URL = "https://api.upstox.com/v2/market-quote/quotes"


def now_ist() -> datetime:
    return datetime.now(IST)


def symbol_universe() -> list[str]:
    symbols = {normalize_symbol(symbol) for symbol in MANUAL_INSTRUMENT_KEYS}
    cache = load_cache()
    if isinstance(cache, dict):
        symbols.update(normalize_symbol(symbol) for symbol in cache.keys())
    return sorted(symbol for symbol in symbols if symbol)


def chunks(items: list[tuple[str, str]], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def extract_quote_for_instrument(data: dict, instrument_key: str, symbol: str):
    if not isinstance(data, dict):
        return None, None

    payload = data.get("data")
    if not isinstance(payload, dict):
        return None, None

    possible_keys = (
        instrument_key,
        str(instrument_key).replace("|", ":"),
        str(instrument_key).replace(":", "|"),
        f"NSE_EQ:{normalize_symbol(symbol)}",
    )
    for key in possible_keys:
        item = payload.get(key)
        if isinstance(item, dict):
            return item, key

    for key, item in payload.items():
        if not isinstance(item, dict):
            continue
        item_token = item.get("instrument_token") or item.get("instrumentKey")
        if item_token == instrument_key:
            return item, key

    return None, None


def quote_ltp(quote: dict):
    if not isinstance(quote, dict):
        return None
    return quote.get("last_price") or quote.get("ltp") or quote.get("lastPrice")


def quote_open(quote: dict):
    if not isinstance(quote, dict):
        return None
    for key in ("open", "open_price", "day_open"):
        if quote.get(key) not in [None, ""]:
            return quote.get(key)
    ohlc = quote.get("ohlc")
    if isinstance(ohlc, dict):
        for key in ("open", "o"):
            if ohlc.get(key) not in [None, ""]:
                return ohlc.get(key)
    return None


def quote_change(quote: dict, ltp, open_price):
    if isinstance(quote, dict):
        for key in ("net_change", "change", "chg", "day_change", "absolute_change"):
            if quote.get(key) not in [None, ""]:
                return safe_float(quote.get(key)), "QUOTE"
    ltp_number = safe_float(ltp)
    open_number = safe_float(open_price)
    if ltp_number is not None and open_number is not None:
        return round(ltp_number - open_number, 4), "LTP_MINUS_OPEN"
    return None, "UNAVAILABLE"


def quote_change_percent(change, ltp, open_price, source):
    change_number = safe_float(change)
    if change_number is None:
        return None
    open_number = safe_float(open_price)
    if open_number not in [None, 0]:
        return round((change_number / open_number) * 100, 4)
    if source == "QUOTE":
        ltp_number = safe_float(ltp)
        previous_close = ltp_number - change_number if ltp_number is not None else None
        if previous_close not in [None, 0]:
            return round((change_number / previous_close) * 100, 4)
    return None


def duplicate_instrument_keys() -> dict[str, list[str]]:
    grouped = {}
    for symbol, key in MANUAL_INSTRUMENT_KEYS.items():
        grouped.setdefault(key, []).append(normalize_symbol(symbol))
    return {
        key: sorted(set(symbols))
        for key, symbols in grouped.items()
        if key and len(set(symbols)) > 1
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_status(payload: dict) -> None:
    write_json(STATUS_PATH, payload)


def refresh_once(batch_size: int = 50, pause_seconds: float = 0.2) -> dict:
    started = now_ist()
    token, token_type = get_upstox_token()
    symbols = symbol_universe()
    mapped: list[tuple[str, str]] = []
    unmapped: list[str] = []

    for symbol in symbols:
        instrument_key = get_instrument_key(symbol)
        if instrument_key:
            mapped.append((symbol, instrument_key))
        else:
            unmapped.append(symbol)

    results = []
    successful = 0
    failed = 0
    failed_symbols = set(unmapped)
    duplicate_keys = duplicate_instrument_keys()

    if not token:
        failed = len(mapped)
        payload = {
            "generated_at_ist": started.isoformat(),
            "status": "TOKEN_MISSING",
            "source": "Upstox",
            "token_type_used": token_type,
            "symbols_requested": len(symbols),
            "symbols_mapped": len(mapped),
            "symbols_refreshed": 0,
            "symbols_failed": failed,
            "symbols_unmapped": unmapped,
            "cache_status": "STALE",
            "reason": "Upstox token missing",
            "read_only": True,
        }
        write_json(RUNTIME_META_PATH, payload)
        write_status(payload)
        return payload

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    for batch in chunks(mapped, max(1, int(batch_size))):
        instrument_keys = [instrument_key for _, instrument_key in batch]
        params = {"instrument_key": ",".join(instrument_keys)}
        batch_status = "UNKNOWN"
        batch_reason = None
        data = {}

        try:
            response = requests.get(UPSTOX_QUOTE_URL, headers=headers, params=params, timeout=12)
            try:
                data = response.json()
            except Exception:
                data = {}

            if response.status_code == 401:
                batch_status = "TOKEN_INVALID"
                batch_reason = "Upstox token invalid or expired"
            elif response.status_code != 200:
                batch_status = "HTTP_ERROR"
                batch_reason = f"HTTP {response.status_code}"
            else:
                batch_status = "OK"
        except requests.RequestException as exc:
            batch_status = "NETWORK_ERROR"
            batch_reason = str(exc)

        for symbol, instrument_key in batch:
            quote, response_key = (
                extract_quote_for_instrument(data, instrument_key, symbol)
                if batch_status == "OK"
                else (None, None)
            )
            price = safe_float(quote_ltp(quote))
            open_price = safe_float(quote_open(quote))
            change, change_source = quote_change(quote, price, open_price)
            change_percent = quote_change_percent(change, price, open_price, change_source)
            symbol_timestamp = now_ist().isoformat()
            if price is not None:
                successful += 1
                results.append(
                    {
                        "symbol": symbol,
                        "instrument_key": instrument_key,
                        "response_key": response_key,
                        "ltp": price,
                        "open": open_price,
                        "change": change,
                        "change_percent": change_percent,
                        "change_source": change_source,
                        "status": "ACTIVE",
                        "source": "UPSTOX",
                        "timestamp": symbol_timestamp,
                        "timestamp_ist": symbol_timestamp,
                    }
                )
            else:
                failed += 1
                failed_symbols.add(symbol)
                results.append(
                    {
                        "symbol": symbol,
                        "instrument_key": instrument_key,
                        "response_key": response_key,
                        "ltp": None,
                        "open": open_price,
                        "change": None,
                        "change_percent": None,
                        "change_source": "UNAVAILABLE",
                        "status": batch_status if batch_status != "OK" else "NO_PRICE",
                        "source": "UNKNOWN",
                        "reason": batch_reason or "Upstox response had no LTP for symbol",
                        "timestamp": symbol_timestamp,
                        "timestamp_ist": symbol_timestamp,
                    }
                )

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    cache = {}
    cache_meta = {}
    for result in results:
        symbol = result.get("symbol")
        if not symbol:
            continue
        entry = {
            "symbol": symbol,
            "ltp": result.get("ltp"),
            "open": result.get("open"),
            "change": result.get("change"),
            "change_percent": result.get("change_percent"),
            "timestamp": result.get("timestamp"),
            "timestamp_ist": result.get("timestamp_ist"),
            "source": result.get("source"),
            "status": result.get("status"),
        }
        cache[symbol] = entry
        cache_meta[symbol] = {
            "price": result.get("ltp"),
            "ltp": result.get("ltp"),
            "open": result.get("open"),
            "change": result.get("change"),
            "change_percent": result.get("change_percent"),
            "updated_at_ist": result.get("timestamp_ist"),
            "source": result.get("source"),
            "status": result.get("status"),
        }
        result["written_ltp"] = entry.get("ltp")
    save_cache(cache)
    save_cache_meta(cache_meta)

    finished = now_ist()
    status = "FRESH" if successful > 0 and failed == 0 else "PARTIAL" if successful > 0 else "FAILED"
    payload = {
        "generated_at_ist": finished.isoformat(),
        "started_at_ist": started.isoformat(),
        "status": status,
        "source": "Upstox",
        "token_type_used": token_type,
        "symbols_requested": len(symbols),
        "symbols_mapped": len(mapped),
        "symbols_refreshed": successful,
        "symbols_failed": failed,
        "symbols_unmapped": unmapped,
        "duplicate_instrument_keys": duplicate_keys,
        "cache_status": "FRESH" if successful > 0 else "STALE",
        "cache_last_updated": finished.isoformat() if successful > 0 else None,
        "read_only": True,
        "orders_placed": False,
        "results": results,
    }
    write_json(RUNTIME_META_PATH, payload)
    write_status(
        {
            "timestamp_ist": finished.isoformat(),
            "status": status,
            "source": "UPSTOX_FULL_REFRESH",
            "token_type_used": token_type,
            "symbols_requested": len(symbols),
            "symbols_refreshed": successful,
            "symbols_failed": failed,
            "read_only": True,
        }
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh TITAN live LTP cache from Upstox.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--interval", type=float, default=5.0, help="Loop interval in seconds.")
    parser.add_argument("--batch-size", type=int, default=50, help="Upstox instruments per request.")
    parser.add_argument("--pause", type=float, default=0.2, help="Pause between request batches.")
    args = parser.parse_args()

    while True:
        result = refresh_once(batch_size=args.batch_size, pause_seconds=args.pause)
        diagnostics = [
                {
                    "symbol": item.get("symbol"),
                    "instrument_key": item.get("instrument_key"),
                    "ltp": item.get("ltp"),
                    "open": item.get("open"),
                    "change": item.get("change"),
                    "change_percent": item.get("change_percent"),
                }
            for item in (result.get("results") or [])[:10]
        ]
        print(
            json.dumps(
                {
                    "timestamp_ist": result.get("generated_at_ist"),
                    "status": result.get("status"),
                    "cache_status": result.get("cache_status"),
                    "symbols_requested": result.get("symbols_requested"),
                    "symbols_refreshed": result.get("symbols_refreshed"),
                    "symbols_failed": result.get("symbols_failed"),
                    "symbols_unmapped": len(result.get("symbols_unmapped") or []),
                    "duplicate_instrument_keys": result.get("duplicate_instrument_keys") or {},
                    "diagnostic_10": diagnostics,
                    "source": result.get("source"),
                    "read_only": result.get("read_only"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if not args.loop:
            return 0 if result.get("symbols_refreshed", 0) > 0 else 1
        time.sleep(max(1.0, float(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())
