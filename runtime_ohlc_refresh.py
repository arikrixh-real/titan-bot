import json
import time
from pathlib import Path

from config.universe import NSE_STOCKS
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
        "source": "YFINANCE",
        "symbol_source": symbol_source,
        "symbols_requested": len(symbols),
        "max_runtime_refresh_symbols": MAX_RUNTIME_REFRESH_SYMBOLS,
        "bounded_refresh": True,
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

        result = refresh_ohlc_cache(symbols=symbols, pause_seconds=0.05)
        refreshed_count = int(result.get("refreshed") or 0)
        failed_count = int(result.get("failed") or 0)
        skipped_count = int(result.get("skipped") or 0)
        payload["status"] = "COMPLETED" if refreshed_count > 0 else "NO_REFRESHED_SYMBOLS"
        payload["refreshed_count"] = refreshed_count
        payload["failed_count"] = failed_count
        payload["skipped_count"] = skipped_count
        payload["result_summary"] = result
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
