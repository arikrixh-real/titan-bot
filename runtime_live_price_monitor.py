import json
from pathlib import Path

from data.live_price import get_live_price_debug
from data.price_cache import META_CACHE_FILE
from utils.market_hours import as_ist_datetime


LIVE_PRICE_MONITOR_STATUS_PATH = (
    Path("data") / "runtime" / "live_price_monitor_status.json"
)
PAPER_TRADE_REGISTRY_PATH = Path("data") / "runtime" / "paper_trade_registry.json"
MAX_SYMBOLS_PER_RUN = 5
NETWORK_OR_TOKEN_FAILURE_STATUSES = {
    "API_ERROR",
    "DNS_ERROR",
    "HTTP_ERROR",
    "NETWORK_BLOCKED",
    "TOKEN_INVALID",
    "TOKEN_MISSING",
}


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
            "cache_meta_updated": False,
            "price_cache_meta_path": META_CACHE_FILE,
            "max_symbols_per_run": MAX_SYMBOLS_PER_RUN,
            "network_or_token_failure_count": 0,
            "price_results": [],
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    price_results = []
    successful_prices = 0
    failed_prices = 0
    cache_meta_updated = False
    network_or_token_failure_count = 0

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
            status = result.get("status")
            source = result.get("source")

            if status in NETWORK_OR_TOKEN_FAILURE_STATUSES:
                network_or_token_failure_count += 1

            if price is not None and source == "UPSTOX" and status == "ACTIVE":
                cache_meta_updated = True

            if price is None:
                failed_prices += 1
            else:
                successful_prices += 1

            price_results.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "source": source,
                    "status": status,
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
        "cache_meta_updated": cache_meta_updated,
        "price_cache_meta_path": META_CACHE_FILE,
        "max_symbols_per_run": MAX_SYMBOLS_PER_RUN,
        "network_or_token_failure_count": network_or_token_failure_count,
        "price_results": price_results,
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_live_price_monitor(), indent=2, sort_keys=True))
