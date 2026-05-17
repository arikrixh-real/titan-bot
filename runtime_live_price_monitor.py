import json
from pathlib import Path

from data.live_price import get_live_price_debug
from utils.market_hours import as_ist_datetime


LIVE_PRICE_MONITOR_STATUS_PATH = (
    Path("data") / "runtime" / "live_price_monitor_status.json"
)
PAPER_TRADE_REGISTRY_PATH = Path("data") / "runtime" / "paper_trade_registry.json"
MAX_SYMBOLS_PER_RUN = 5


def _read_json(path):
    path = Path(path)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _open_paper_symbols(registry):
    symbols = []
    seen = set()

    open_positions = registry.get("open_positions")
    if not isinstance(open_positions, list):
        return symbols

    for position in open_positions:
        if not isinstance(position, dict):
            continue

        symbol = str(position.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue

        seen.add(symbol)
        symbols.append(symbol)

    return symbols


def run_live_price_monitor(path=LIVE_PRICE_MONITOR_STATUS_PATH):
    now_ist = as_ist_datetime()
    registry = _read_json(PAPER_TRADE_REGISTRY_PATH)
    symbols = _open_paper_symbols(registry)[:MAX_SYMBOLS_PER_RUN]

    if not symbols:
        payload = {
            "timestamp_ist": now_ist.isoformat(),
            "status": "NO_OPEN_PAPER_POSITIONS",
            "symbols_checked": 0,
            "successful_prices": 0,
            "failed_prices": 0,
            "price_results": [],
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    price_results = []
    successful_prices = 0
    failed_prices = 0

    for symbol in symbols:
        try:
            result = get_live_price_debug(symbol, use_cache=True, debug=False)
            if not isinstance(result, dict):
                result = {
                    "price": None,
                    "source": "UNKNOWN",
                    "status": "BAD_RESULT",
                    "reason": "get_live_price_debug returned non-dict result",
                }

            price = result.get("price")
            if price is None:
                failed_prices += 1
            else:
                successful_prices += 1

            price_results.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "source": result.get("source"),
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                }
            )
        except Exception as exc:
            failed_prices += 1
            price_results.append(
                {
                    "symbol": symbol,
                    "price": None,
                    "source": "UNKNOWN",
                    "status": "ERROR",
                    "reason": str(exc),
                }
            )

    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "status": "LIVE_PRICE_CACHE_REFRESHED",
        "symbols_checked": len(symbols),
        "successful_prices": successful_prices,
        "failed_prices": failed_prices,
        "price_results": price_results,
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_live_price_monitor(), indent=2, sort_keys=True))
