import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engines.setup_engine import (
    breakout_ready,
    get_last_load_debug,
    load_cached_stock_data,
    strong_momentum,
    structure_ok,
    trend_direction,
)


IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"


def _timestamp_ist():
    return datetime.now(IST).isoformat()


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
    return None


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
    errors,
):
    return {
        "timestamp_ist": _timestamp_ist(),
        "mode": mode,
        "status": "SCAN_ONLY_COMPLETE",
        "scan_only": True,
        "real_scanner_called": True,
        "trade_creation": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": False,
        "stocks_checked": stocks_checked,
        "trend_passed": trend_passed,
        "structure_passed": structure_passed,
        "momentum_passed": momentum_passed,
        "breakout_ready_count": breakout_ready_count,
        "passed_setups": passed_setups,
        "candidate_symbols": candidate_symbols[:5],
        "errors": errors,
    }


def run_scanner(path=SCANNER_STATUS_PATH):
    stocks_checked = 0
    trend_passed = 0
    structure_passed = 0
    momentum_passed = 0
    breakout_ready_count = 0
    passed_setups = 0
    candidate_symbols = []
    errors = 0
    mode = "SCAN_ONLY"

    try:
        cached_symbols = load_cached_stock_data() or {}
        load_debug = get_last_load_debug() or {}
        mode = _scan_mode(load_debug)
    except Exception:
        cached_symbols = {}
        errors += 1

    for symbol, data in cached_symbols.items():
        stocks_checked += 1

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

        except Exception:
            errors += 1
            continue

    payload = _status_payload(
        mode=mode,
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        structure_passed=structure_passed,
        momentum_passed=momentum_passed,
        breakout_ready_count=breakout_ready_count,
        passed_setups=passed_setups,
        candidate_symbols=candidate_symbols,
        errors=errors,
    )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_scanner(), indent=2, sort_keys=True))
