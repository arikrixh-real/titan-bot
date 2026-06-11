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
from data.live_price import safe_float
from data.price_cache import load_cache, save_cache, save_cache_meta
from data.upstox_auth import UpstoxMarketDataAuthError, market_data_headers, market_data_token_info


IST = timezone(timedelta(hours=5, minutes=30))
RUNTIME_META_PATH = ROOT / "data" / "runtime" / "live_price_cache_meta.json"
ROOT_META_PATH = ROOT / "data" / "live_price_cache_meta.json"
STATUS_PATH = ROOT / "data" / "live_price_status.json"
UPSTOX_QUOTE_URL = "https://api.upstox.com/v2/market-quote/quotes"
HFT_UNIVERSE_PATH = ROOT / "data" / "hft_mode" / "hft_universe_cache.json"
CLASSIC_UNIVERSE_PATH = ROOT / "data" / "classic_mode" / "classic_universe_cache.json"
QUOTE_FRESH_SECONDS = 120


def now_ist() -> datetime:
    return datetime.now(IST)


def read_json(path: Path, default=None):
    try:
        if not path.exists():
            return default
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if payload is not None else default
    except Exception:
        return default


def parse_dt(value):
    if value in (None, "", "null"):
        return None
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 9999999999 else value
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(IST)
        except Exception:
            return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def age_seconds(value):
    parsed = parse_dt(value)
    if parsed is None:
        return None
    return max(0.0, (now_ist() - parsed).total_seconds())


def _universe_entries(path: Path) -> list[dict]:
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return []
    return [item for item in payload.get("symbols") or [] if isinstance(item, dict)]


def symbol_universe_entries() -> list[tuple[str, str | None, str]]:
    symbols: dict[str, dict] = {}
    for symbol, instrument_key in MANUAL_INSTRUMENT_KEYS.items():
        clean = normalize_symbol(symbol)
        if clean:
            symbols[clean] = {"instrument_key": instrument_key, "source": "manual_instrument_keys"}

    cache = load_cache()
    if isinstance(cache, dict):
        for symbol, value in cache.items():
            clean = normalize_symbol(symbol)
            if not clean:
                continue
            existing = symbols.setdefault(clean, {"instrument_key": None, "source": "live_price_cache"})
            if isinstance(value, dict) and value.get("instrument_key") and not existing.get("instrument_key"):
                existing["instrument_key"] = value.get("instrument_key")

    for path, source in ((HFT_UNIVERSE_PATH, "hft_universe"), (CLASSIC_UNIVERSE_PATH, "classic_universe")):
        for item in _universe_entries(path):
            clean = normalize_symbol(item.get("symbol"))
            if not clean:
                continue
            existing = symbols.setdefault(clean, {"instrument_key": None, "source": source})
            if item.get("instrument_key"):
                existing["instrument_key"] = item.get("instrument_key")
            if existing.get("source") == "live_price_cache":
                existing["source"] = source

    return [
        (symbol, values.get("instrument_key"), values.get("source") or "unknown")
        for symbol, values in sorted(symbols.items())
        if symbol
    ]


def symbol_universe() -> list[str]:
    return [symbol for symbol, _, _ in symbol_universe_entries()]


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


def quote_volume(quote: dict):
    if not isinstance(quote, dict):
        return None
    for key in ("volume", "total_volume", "day_volume", "last_traded_quantity", "ltq"):
        value = quote.get(key)
        if value not in [None, ""]:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
    return None


def quote_bid_ask(quote: dict):
    if not isinstance(quote, dict):
        return None, None
    bid = quote.get("bid") or quote.get("best_bid") or quote.get("bid_price")
    ask = quote.get("ask") or quote.get("best_ask") or quote.get("ask_price")
    depth = quote.get("depth")
    if isinstance(depth, dict):
        buy = depth.get("buy")
        sell = depth.get("sell")
        if bid in [None, ""] and isinstance(buy, list) and buy:
            bid = buy[0].get("price") if isinstance(buy[0], dict) else None
        if ask in [None, ""] and isinstance(sell, list) and sell:
            ask = sell[0].get("price") if isinstance(sell[0], dict) else None
    return safe_float(bid), safe_float(ask)


def quote_spread_values(bid, ask):
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        return None, None
    spread = round(ask - bid, 6)
    midpoint = (bid + ask) / 2
    spread_pct = round((spread / midpoint) * 100.0, 6) if midpoint > 0 else None
    return spread, spread_pct


def quote_timestamp(quote: dict):
    if not isinstance(quote, dict):
        return None
    for key in (
        "last_trade_time",
        "last_traded_time",
        "ltt",
        "timestamp",
        "exchange_timestamp",
        "exchangeTimestamp",
        "lastUpdateTime",
    ):
        if quote.get(key) not in [None, ""]:
            return quote.get(key)
    return None


def _quote_failure_reason(batch_status: str, batch_reason: str | None, quote: dict | None, price, quote_age) -> str | None:
    if batch_status != "OK":
        return batch_reason or batch_status
    if not isinstance(quote, dict):
        return "quote_missing"
    if price is None:
        return "missing_ltp"
    if quote_age is not None and quote_age > QUOTE_FRESH_SECONDS:
        return "stale_ltp"
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
    try:
        headers = market_data_headers()
        token_type = market_data_token_info().get("token_type", "ANALYTICS_TOKEN")
    except UpstoxMarketDataAuthError as exc:
        headers = None
        token_type = "MISSING_ANALYTICS_TOKEN"
        auth_error = str(exc)
    else:
        auth_error = None
    symbol_entries = symbol_universe_entries()
    symbols = [symbol for symbol, _, _ in symbol_entries]
    mapped: list[tuple[str, str, str]] = []
    unmapped: list[str] = []

    for symbol, explicit_key, symbol_source in symbol_entries:
        instrument_key = explicit_key or get_instrument_key(symbol)
        if instrument_key:
            mapped.append((symbol, instrument_key, symbol_source))
        else:
            unmapped.append(symbol)

    results = []
    successful = 0
    failed = 0
    failed_symbols = set(unmapped)
    duplicate_keys = duplicate_instrument_keys()
    hft_universe_symbols = {
        normalize_symbol(item.get("symbol"))
        for item in _universe_entries(HFT_UNIVERSE_PATH)
        if normalize_symbol(item.get("symbol"))
    }

    if auth_error:
        failed = len(mapped)
        payload = {
            "generated_at_ist": started.isoformat(),
            "timestamp_ist": started.isoformat(),
            "timestamp": started.isoformat(),
            "status": "AUTH_REQUIRED",
            "source": "Upstox",
            "token_type_used": token_type,
            "symbols_requested": len(symbols),
            "symbols_mapped": len(mapped),
            "symbols_refreshed": 0,
            "symbols_failed": failed,
            "symbols_unmapped": unmapped,
            "cache_status": "STALE",
            "reason": auth_error,
            "read_only": True,
            "orders_placed": False,
        }
        write_json(RUNTIME_META_PATH, payload)
        write_json(ROOT_META_PATH, payload)
        write_status(payload)
        return payload

    for batch in chunks(mapped, max(1, int(batch_size))):
        instrument_keys = [instrument_key for _, instrument_key, _ in batch]
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

        for symbol, instrument_key, symbol_source in batch:
            quote, response_key = (
                extract_quote_for_instrument(data, instrument_key, symbol)
                if batch_status == "OK"
                else (None, None)
            )
            price = safe_float(quote_ltp(quote))
            raw_quote_timestamp = quote_timestamp(quote)
            quote_age = age_seconds(raw_quote_timestamp)
            open_price = safe_float(quote_open(quote))
            change, change_source = quote_change(quote, price, open_price)
            change_percent = quote_change_percent(change, price, open_price, change_source)
            volume = quote_volume(quote)
            bid, ask = quote_bid_ask(quote)
            spread, spread_pct = quote_spread_values(bid, ask)
            symbol_timestamp = now_ist().isoformat()
            failure_reason = _quote_failure_reason(batch_status, batch_reason, quote, price, quote_age)
            quote_status = "ACTIVE" if failure_reason is None else "STALE" if failure_reason == "stale_ltp" else "NO_PRICE" if failure_reason == "missing_ltp" else batch_status
            if failure_reason is None:
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
                        "volume": volume,
                        "bid": bid,
                        "ask": ask,
                        "spread": spread,
                        "spread_pct": spread_pct,
                        "change_source": change_source,
                        "status": "ACTIVE",
                        "source": "UPSTOX",
                        "symbol_source": symbol_source,
                        "quote_timestamp_raw": raw_quote_timestamp,
                        "quote_age_seconds": round(quote_age, 3) if quote_age is not None else None,
                        "raw_quote_keys": sorted(quote.keys()) if isinstance(quote, dict) else [],
                        "top_of_book_keys": {
                            "bid_present": bid is not None and bid > 0,
                            "ask_present": ask is not None and ask > 0,
                            "depth_present": isinstance((quote or {}).get("depth"), dict),
                        },
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
                        "volume": volume,
                        "bid": bid,
                        "ask": ask,
                        "spread": spread,
                        "spread_pct": spread_pct,
                        "change_source": "UNAVAILABLE",
                        "status": quote_status,
                        "source": "UPSTOX" if isinstance(quote, dict) else "UNKNOWN",
                        "symbol_source": symbol_source,
                        "quote_timestamp_raw": raw_quote_timestamp,
                        "quote_age_seconds": round(quote_age, 3) if quote_age is not None else None,
                        "raw_quote_keys": sorted(quote.keys()) if isinstance(quote, dict) else [],
                        "top_of_book_keys": {
                            "bid_present": bid is not None and bid > 0,
                            "ask_present": ask is not None and ask > 0,
                            "depth_present": isinstance((quote or {}).get("depth"), dict),
                        },
                        "reason": failure_reason or batch_reason or "Upstox response had no LTP for symbol",
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
            "volume": result.get("volume"),
            "bid": result.get("bid"),
            "ask": result.get("ask"),
            "spread": result.get("spread"),
            "spread_pct": result.get("spread_pct"),
            "quote_timestamp_raw": result.get("quote_timestamp_raw"),
            "quote_age_seconds": result.get("quote_age_seconds"),
            "instrument_key": result.get("instrument_key"),
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
            "volume": result.get("volume"),
            "bid": result.get("bid"),
            "ask": result.get("ask"),
            "spread": result.get("spread"),
            "spread_pct": result.get("spread_pct"),
            "quote_timestamp_raw": result.get("quote_timestamp_raw"),
            "quote_age_seconds": result.get("quote_age_seconds"),
            "instrument_key": result.get("instrument_key"),
            "updated_at_ist": result.get("timestamp_ist"),
            "source": result.get("source"),
            "status": result.get("status"),
        }
        result["written_ltp"] = entry.get("ltp")
    save_cache(cache)
    save_cache_meta(cache_meta)

    finished = now_ist()
    status = "FRESH" if successful > 0 and failed == 0 else "PARTIAL" if successful > 0 else "FAILED"
    hft_results = [item for item in results if normalize_symbol(item.get("symbol")) in hft_universe_symbols]
    hft_failed = [item for item in hft_results if item.get("status") != "ACTIVE"]
    stale_ltp_count = sum(1 for item in results if item.get("reason") == "stale_ltp" or item.get("status") == "STALE")
    missing_ltp_count = sum(1 for item in results if item.get("reason") in {"missing_ltp", "quote_missing"} or item.get("ltp") in [None, 0])
    missing_bid_ask_count = sum(
        1
        for item in results
        if item.get("ltp") not in [None, 0]
        and not (
            safe_float(item.get("bid")) is not None
            and safe_float(item.get("ask")) is not None
            and safe_float(item.get("bid")) > 0
            and safe_float(item.get("ask")) > 0
        )
    )
    payload = {
        "generated_at_ist": finished.isoformat(),
        "timestamp_ist": finished.isoformat(),
        "timestamp": finished.isoformat(),
        "started_at_ist": started.isoformat(),
        "status": status,
        "source": "Upstox",
        "token_type_used": token_type,
        "symbols_requested": len(symbols),
        "symbols_mapped": len(mapped),
        "symbols_refreshed": successful,
        "symbols_failed": failed,
        "universe_count": len(hft_universe_symbols),
        "quote_requested_count": len(mapped),
        "quote_success_count": successful,
        "quote_failed_count": failed,
        "hft_quote_requested_count": len(hft_results),
        "hft_quote_success_count": len(hft_results) - len(hft_failed),
        "hft_quote_failed_count": len(hft_failed),
        "stale_ltp_count": stale_ltp_count,
        "missing_ltp_count": missing_ltp_count,
        "missing_bid_ask_count": missing_bid_ask_count,
        "per_symbol_failure_reason": [
            {
                "symbol": item.get("symbol"),
                "instrument_key": item.get("instrument_key"),
                "symbol_source": item.get("symbol_source"),
                "status": item.get("status"),
                "reason": item.get("reason") or ("missing_bid_ask" if item.get("ltp") not in [None, 0] and (not item.get("bid") or not item.get("ask")) else None),
                "ltp": item.get("ltp"),
                "bid": item.get("bid"),
                "ask": item.get("ask"),
                "quote_age_seconds": item.get("quote_age_seconds"),
            }
            for item in results
            if item.get("status") != "ACTIVE" or (item.get("ltp") not in [None, 0] and (not item.get("bid") or not item.get("ask")))
        ],
        "symbols_unmapped": unmapped,
        "duplicate_instrument_keys": duplicate_keys,
        "cache_status": "FRESH" if successful > 0 else "STALE",
        "cache_last_updated": finished.isoformat() if successful > 0 else None,
        "read_only": True,
        "orders_placed": False,
        "results": results,
    }
    root_meta_payload = dict(cache_meta)
    root_meta_payload.update(
        {
            "generated_at_ist": payload["generated_at_ist"],
            "timestamp_ist": payload["timestamp_ist"],
            "timestamp": payload["timestamp"],
            "started_at_ist": payload["started_at_ist"],
            "status": payload["status"],
            "source": payload["source"],
            "token_type_used": payload["token_type_used"],
            "symbols_requested": payload["symbols_requested"],
            "symbols_refreshed": payload["symbols_refreshed"],
            "symbols_failed": payload["symbols_failed"],
            "cache_status": payload["cache_status"],
            "cache_last_updated": payload["cache_last_updated"],
            "read_only": True,
            "orders_placed": False,
        }
    )
    write_json(RUNTIME_META_PATH, payload)
    write_json(ROOT_META_PATH, root_meta_payload)
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
