import json
from pathlib import Path

from config.universe import NSE_STOCKS
from scripts.refresh_ohlc_cache import refresh_ohlc_cache
from utils.market_hours import as_ist_datetime, is_trade_window


STATUS_PATH = Path("data") / "runtime" / "ohlc_refresh_status.json"


def _write_status(payload):
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_ohlc_refresh():
    now_ist = as_ist_datetime()
    trade_window = is_trade_window(now_ist)
    symbols_requested = len(NSE_STOCKS)
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "status": "PENDING",
        "trade_window": trade_window,
        "symbols_requested": symbols_requested,
        "result_summary": None,
        "error_type": None,
        "error_message": None,
    }

    try:
        if trade_window:
            payload["status"] = "SKIPPED_TRADE_WINDOW"
            return payload

        result = refresh_ohlc_cache(symbols=NSE_STOCKS, pause_seconds=0.2)
        payload["status"] = "COMPLETED"
        payload["result_summary"] = result
        return payload
    except Exception as exc:
        payload["status"] = "FAILED"
        payload["error_type"] = type(exc).__name__
        payload["error_message"] = str(exc)
        return payload
    finally:
        _write_status(payload)


if __name__ == "__main__":
    print(json.dumps(run_ohlc_refresh(), indent=2, sort_keys=True))
