import json
import time
from pathlib import Path

from config.universe import NSE_STOCKS
from data.upstox_ohlc import refresh_symbol_from_upstox
from scripts.refresh_ohlc_cache import refresh_ohlc_cache
from utils.market_hours import as_ist_datetime, is_trade_window


STATUS_PATH = Path("data") / "runtime" / "ohlc_refresh_status.json"
SCAN_SELECTION_STATE_PATH = Path("data") / "scan_selection_state.json"
MAX_RUNTIME_REFRESH_SYMBOLS = 50


def _normalize_yfinance_symbol(symbol):
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    if clean.startswith("^") or clean.endswith(".NS"):
        return clean
    return f"{clean}.NS"


def _read_current_scanner_symbols(limit=MAX_RUNTIME_REFRESH_SYMBOLS):
    try:
        if not SCAN_SELECTION_STATE_PATH.exists():
            return []
        payload = json.loads(SCAN_SELECTION_STATE_PATH.read_text(encoding="utf-8"))
        symbols = payload.get("selected_symbols")
        if not isinstance(symbols, list):
            return []
        normalized = []
        seen = set()
        for symbol in symbols:
            normalized_symbol = _normalize_yfinance_symbol(symbol)
            if normalized_symbol and normalized_symbol not in seen:
                normalized.append(normalized_symbol)
                seen.add(normalized_symbol)
            if len(normalized) >= limit:
                break
        return normalized
    except Exception:
        return []


def _fallback_symbols(limit=MAX_RUNTIME_REFRESH_SYMBOLS):
    normalized = []
    seen = set()
    for symbol in NSE_STOCKS:
        normalized_symbol = _normalize_yfinance_symbol(symbol)
        if normalized_symbol and normalized_symbol not in seen:
            normalized.append(normalized_symbol)
            seen.add(normalized_symbol)
        if len(normalized) >= limit:
            break
    return normalized


def _write_status(payload):
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _yfinance_result_by_symbol(result):
    by_symbol = {}
    for item in result.get("symbol_results") or []:
        if not isinstance(item, dict):
            continue
        symbol = _normalize_yfinance_symbol(item.get("symbol"))
        if symbol:
            by_symbol[symbol] = item
    return by_symbol


def _cache_unchanged_result(symbol, upstox_result, fallback_result=None):
    fallback_reason = None
    fallback_status = None
    if isinstance(fallback_result, dict):
        fallback_reason = fallback_result.get("reason")
        fallback_status = fallback_result.get("status")

    return {
        "symbol": symbol,
        "status": "CACHE_UNCHANGED",
        "source": "CACHE_UNCHANGED",
        "reason": fallback_reason or "Upstox and yfinance did not refresh cache",
        "upstox_status": upstox_result.get("status"),
        "upstox_reason": upstox_result.get("reason"),
        "fallback_status": fallback_status,
        "fallback_reason": fallback_reason,
    }


def run_ohlc_refresh():
    started_monotonic = time.monotonic()
    now_ist = as_ist_datetime()
    trade_window = is_trade_window(now_ist)
    symbols = _read_current_scanner_symbols()
    symbol_source = "scan_selection_state"
    if not symbols:
        symbols = _fallback_symbols()
        symbol_source = "nse_stocks_fallback"

    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "status": "PENDING",
        "trade_window": trade_window,
        "source": "UPSTOX_FIRST_YFINANCE_FALLBACK",
        "symbol_source": symbol_source,
        "symbols_requested": len(symbols),
        "max_runtime_refresh_symbols": MAX_RUNTIME_REFRESH_SYMBOLS,
        "bounded_refresh": True,
        "upstox_success_count": 0,
        "yfinance_fallback_count": 0,
        "refreshed_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "skipped_reason": None,
        "duration_seconds": None,
        "result_summary": None,
        "error_type": None,
        "error_message": None,
    }

    try:
        if not symbols:
            payload["status"] = "SKIPPED"
            payload["skipped_reason"] = "NO_SYMBOLS_AVAILABLE"
            return payload

        symbol_results = []
        fallback_symbols = []
        upstox_results = {}
        upstox_success_count = 0

        for symbol in symbols:
            try:
                upstox_result = refresh_symbol_from_upstox(symbol)
            except Exception as exc:
                upstox_result = {
                    "symbol": symbol,
                    "status": "UPSTOX_EXCEPTION",
                    "reason": str(exc),
                    "source": "UPSTOX",
                }
            upstox_results[symbol] = upstox_result
            if upstox_result.get("status") == "OK":
                upstox_success_count += 1
                symbol_results.append(
                    {
                        "symbol": symbol,
                        "status": "REFRESHED",
                        "source": "UPSTOX",
                        "reason": None,
                        "latest_candle_timestamp": upstox_result.get("latest_candle_timestamp"),
                        "candle_count": upstox_result.get("candle_count"),
                        "instrument_key": upstox_result.get("instrument_key"),
                        "token_type_used": upstox_result.get("token_type_used"),
                    }
                )
            else:
                fallback_symbols.append(symbol)

        yfinance_result = {}
        yfinance_by_symbol = {}
        if fallback_symbols:
            try:
                yfinance_result = refresh_ohlc_cache(symbols=fallback_symbols, pause_seconds=0.05)
            except Exception as exc:
                yfinance_result = {
                    "requested": len(fallback_symbols),
                    "refreshed": 0,
                    "skipped": 0,
                    "failed": len(fallback_symbols),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "symbol_results": [
                        {
                            "symbol": symbol,
                            "status": "FAILED",
                            "reason": str(exc),
                        }
                        for symbol in fallback_symbols
                    ],
                }
            yfinance_by_symbol = _yfinance_result_by_symbol(yfinance_result)

        yfinance_fallback_count = 0
        failed_count = 0
        skipped_count = 0

        for symbol in fallback_symbols:
            fallback_result = yfinance_by_symbol.get(symbol)
            upstox_result = upstox_results.get(symbol, {})
            if isinstance(fallback_result, dict) and fallback_result.get("status") == "REFRESHED":
                yfinance_fallback_count += 1
                symbol_results.append(
                    {
                        "symbol": symbol,
                        "status": "REFRESHED",
                        "source": "YFINANCE_FALLBACK",
                        "reason": None,
                        "latest_candle_timestamp": fallback_result.get("latest_candle_timestamp"),
                        "upstox_status": upstox_result.get("status"),
                        "upstox_reason": upstox_result.get("reason"),
                    }
                )
                continue

            failed_count += 1
            skipped_count += 1
            symbol_results.append(
                _cache_unchanged_result(symbol, upstox_result, fallback_result)
            )

        refreshed_count = upstox_success_count + yfinance_fallback_count
        payload["status"] = "COMPLETED" if refreshed_count > 0 else "NO_REFRESHED_SYMBOLS"
        payload["upstox_success_count"] = upstox_success_count
        payload["yfinance_fallback_count"] = yfinance_fallback_count
        payload["fallback_count"] = yfinance_fallback_count
        payload["refreshed_count"] = refreshed_count
        payload["failed_count"] = failed_count
        payload["skipped_count"] = skipped_count
        payload["symbol_results"] = symbol_results
        payload["skip_reasons"] = {}
        for item in payload["symbol_results"]:
            if not isinstance(item, dict) or item.get("status") not in {"SKIPPED", "CACHE_UNCHANGED"}:
                continue
            reason = item.get("reason") or "UNKNOWN"
            payload["skip_reasons"][reason] = payload["skip_reasons"].get(reason, 0) + 1
        if refreshed_count == 0 and skipped_count == len(symbols):
            payload["skipped_reason"] = "ALL_SYMBOLS_FAILED_UPSTOX_AND_YFINANCE_CACHE_UNCHANGED"
        payload["result_summary"] = {
            "requested": len(symbols),
            "refreshed": refreshed_count,
            "upstox_refreshed": upstox_success_count,
            "yfinance_fallback_refreshed": yfinance_fallback_count,
            "cache_unchanged": skipped_count,
            "failed": failed_count,
            "yfinance_result": yfinance_result,
        }
        return payload
    except Exception as exc:
        payload["status"] = "FAILED"
        payload["failed_count"] = len(symbols)
        payload["error_type"] = type(exc).__name__
        payload["error_message"] = str(exc)
        return payload
    finally:
        payload["duration_seconds"] = round(time.monotonic() - started_monotonic, 3)
        payload["timestamp_ist"] = as_ist_datetime().isoformat()
        _write_status(payload)


if __name__ == "__main__":
    print(json.dumps(run_ohlc_refresh(), indent=2, sort_keys=True))
