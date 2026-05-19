import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from engines.setup_engine import (
    breakout_ready,
    get_last_load_debug,
    load_cached_stock_data,
    strong_momentum,
    structure_ok,
    trend_direction,
)
from engines.time_filter import current_bot_mode


IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"


def _timestamp_ist():
    return datetime.now(IST).isoformat()


def _read_previous_run_count(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        run_count = payload.get("run_count") if isinstance(payload, dict) else None
        if isinstance(run_count, int) and not isinstance(run_count, bool):
            return run_count
    except Exception:
        return None
    return None


def _scan_mode(load_debug):
    if not isinstance(load_debug, dict):
        return "SCAN_ONLY"

    selected_count = load_debug.get("selected_symbols_count")
    if selected_count is None:
        return "SCAN_ONLY"

    return f"SCAN_ONLY_CACHED_{selected_count}"


def _side_from_trend(trend):
    if trend == "BULLISH":
        return "LONG"
    if trend == "BEARISH":
        return "SHORT"
    if trend == "UP":
        return "LONG"
    if trend == "DOWN":
        return "SHORT"
    return None


def _last_ohlc(data):
    try:
        if data is None or data.empty:
            return None

        for column in ["High", "Low", "Close"]:
            if column not in data.columns:
                return None

        last = data.iloc[-1]
        return {
            "High": float(last["High"]),
            "Low": float(last["Low"]),
            "Close": float(last["Close"]),
        }
    except Exception:
        return None


def _parse_candle_timestamp(value):
    try:
        if value is None:
            return None
        parsed = __import__("pandas").to_datetime(value, errors="coerce")
        if parsed is None or parsed is __import__("pandas").NaT:
            return None
        if getattr(parsed, "tzinfo", None) is None:
            parsed = parsed.tz_localize(timezone.utc)
        return parsed.to_pydatetime().astimezone(IST)
    except Exception:
        return None


def _last_candle_timestamp(data):
    try:
        if data is None or data.empty:
            return None

        for column in ["Datetime", "Date", "timestamp", "time"]:
            if column in data.columns:
                dt = _parse_candle_timestamp(data[column].iloc[-1])
                if dt:
                    return dt

        index = getattr(data, "index", None)
        if index is not None and len(index) > 0:
            return _parse_candle_timestamp(index[-1])
    except Exception:
        return None
    return None


def _latest_timestamp(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def _status_payload(
    *,
    mode,
    stocks_checked,
    trend_passed,
    structure_passed,
    momentum_passed,
    breakout_ready_count,
    passed_setups,
    candidate_symbols,
    candidate_details,
    errors,
    latest_candle_timestamp,
    stale_symbol_count,
    stale_symbols,
    stale_data_warning,
    scanner_cycle_id,
    scan_started_at_ist,
    scan_finished_at_ist,
    scan_duration_seconds,
    run_count=None,
):
    payload = {
        "timestamp_ist": scan_finished_at_ist,
        "scanner_cycle_id": scanner_cycle_id,
        "scan_started_at_ist": scan_started_at_ist,
        "scan_finished_at_ist": scan_finished_at_ist,
        "scan_duration_seconds": scan_duration_seconds,
        "mode": mode,
        "status": "SCAN_ONLY_STALE_OHLC" if stale_data_warning else "SCAN_ONLY_COMPLETE",
        "source": "VPS_RUNTIME_SCANNER",
        "scan_only": True,
        "real_scanner_called": True,
        "trade_creation": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": False,
        "stocks_checked": stocks_checked,
        "trend_passed": trend_passed,
        "momentum_passed": momentum_passed,
        "structure_passed": structure_passed,
        "entry_passed": breakout_ready_count,
        "final_passed": 0,
        "alerts_sent": 0,
        "breakout_ready_count": breakout_ready_count,
        "passed_setups": passed_setups,
        "missing_fields": ["final_passed"],
        "candidate_symbols": candidate_symbols[:5],
        "candidate_details": candidate_details[:5],
        "latest_candle_timestamp": latest_candle_timestamp,
        "stale_symbol_count": stale_symbol_count,
        "stale_symbols": stale_symbols[:20],
        "stale_data_warning": stale_data_warning,
        "errors": errors,
    }
    if run_count is not None:
        payload["run_count"] = run_count
    return payload


def run_scanner(path=SCANNER_STATUS_PATH):
    path = Path(path)
    started_monotonic = time.monotonic()
    scan_started_at_ist = _timestamp_ist()
    scanner_cycle_id = f"{scan_started_at_ist}-{uuid4()}"
    previous_run_count = _read_previous_run_count(path)
    run_count = previous_run_count + 1 if previous_run_count is not None else None

    stocks_checked = 0
    trend_passed = 0
    structure_passed = 0
    momentum_passed = 0
    breakout_ready_count = 0
    passed_setups = 0
    candidate_symbols = []
    candidate_details = []
    errors = 0
    mode = "SCAN_ONLY"
    bot_mode = current_bot_mode(datetime.now(IST))
    market_mode = bot_mode == "MARKET_MODE"
    today_ist = datetime.now(IST).date()
    latest_candle_dt = None
    stale_symbols = []

    try:
        cached_symbols = load_cached_stock_data() or {}
        load_debug = get_last_load_debug() or {}
        mode = _scan_mode(load_debug)
    except Exception:
        cached_symbols = {}
        errors += 1

    for symbol, data in cached_symbols.items():
        stocks_checked += 1
        candle_dt = _last_candle_timestamp(data)
        latest_candle_dt = _latest_timestamp(latest_candle_dt, candle_dt)
        if market_mode and (candle_dt is None or candle_dt.date() < today_ist):
            stale_symbols.append(symbol)

        try:
            trend = trend_direction(data)
            side = _side_from_trend(trend)
            if side is None:
                continue
            trend_passed += 1

            if not structure_ok(data, side=side):
                continue
            structure_passed += 1

            if not strong_momentum(data, side=side):
                continue
            momentum_passed += 1

            if not breakout_ready(data, side=side):
                continue
            breakout_ready_count += 1

            passed_setups += 1
            if len(candidate_symbols) < 5:
                candidate_symbols.append(symbol)
            if len(candidate_details) < 5:
                last_ohlc = _last_ohlc(data)
                if last_ohlc is not None:
                    candidate_details.append(
                        {
                            "symbol": symbol,
                            "side": side,
                            "last_ohlc": last_ohlc,
                        }
                    )

        except Exception:
            errors += 1
            continue

    scan_finished_at_ist = _timestamp_ist()
    scan_duration_seconds = round(time.monotonic() - started_monotonic, 3)
    stale_symbol_count = len(stale_symbols)
    stale_data_warning = bool(market_mode and stale_symbol_count > 0)
    payload = _status_payload(
        mode=mode,
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        structure_passed=structure_passed,
        momentum_passed=momentum_passed,
        breakout_ready_count=breakout_ready_count,
        passed_setups=passed_setups,
        candidate_symbols=candidate_symbols,
        candidate_details=candidate_details,
        errors=errors,
        latest_candle_timestamp=latest_candle_dt.isoformat() if latest_candle_dt else None,
        stale_symbol_count=stale_symbol_count,
        stale_symbols=stale_symbols,
        stale_data_warning=stale_data_warning,
        scanner_cycle_id=scanner_cycle_id,
        scan_started_at_ist=scan_started_at_ist,
        scan_finished_at_ist=scan_finished_at_ist,
        scan_duration_seconds=scan_duration_seconds,
        run_count=run_count,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_scanner(), indent=2, sort_keys=True))
