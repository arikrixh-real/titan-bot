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
AUTH_TOKEN_FAILURE_STATUSES = {
    "TOKEN_INVALID",
    "TOKEN_MISSING",
    "UNAUTHORIZED",
    "AUTH_ERROR",
    "AUTH_TOKEN_EXPIRED",
    "TOKEN_EXPIRED",
}
AUTH_TOKEN_FAILURE_MARKERS = (
    "token",
    "unauthorized",
    "401",
    "403",
    "auth",
    "expired",
    "invalid access",
    "invalid_token",
)


def _is_auth_token_failure(status, reason):
    status_text = str(status or "").strip().upper()
    if status_text in AUTH_TOKEN_FAILURE_STATUSES:
        return True

    reason_text = str(reason or "").strip().lower()
    if not reason_text:
        return False

    return any(marker in reason_text for marker in AUTH_TOKEN_FAILURE_MARKERS)


def _health_check_token_status(price, source, status, reason):
    source_text = str(source or "").strip().upper()

    if price is not None and source_text == "UPSTOX" and status == "ACTIVE":
        return "VALID"

    if _is_auth_token_failure(status, reason):
        return "INVALID_OR_EXPIRED"

    if price is not None and source_text != "UPSTOX":
        return "CACHE_OR_FALLBACK"

    return "UNKNOWN"


def _read_json(path):
    path = Path(path)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _meta_cache_exists():
    return Path(META_CACHE_FILE).exists()


def _meta_cache_updated_for_symbol(symbol, before_meta, after_meta):
    before_entry = before_meta.get(symbol)
    after_entry = after_meta.get(symbol)

    if not isinstance(after_entry, dict):
        return False

    before_timestamp = before_entry.get("updated_at_ist") if isinstance(before_entry, dict) else None
    after_timestamp = after_entry.get("updated_at_ist")

    return bool(after_timestamp and after_timestamp != before_timestamp)


def _readiness_status(meta_cache_exists, meta_cache_updated, token_status):
    if not meta_cache_exists:
        return "FAIL_META_CACHE_MISSING"

    if token_status == "INVALID_OR_EXPIRED":
        return "FAIL_TOKEN_INVALID_OR_EXPIRED"

    if meta_cache_updated:
        return "READY"

    return "WARNING_META_CACHE_NOT_UPDATED"


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
        health_check_symbol = "RELIANCE"
        before_meta = _read_json(META_CACHE_FILE)
        try:
            result = get_live_price_debug(
                health_check_symbol, use_cache=True, debug=False
            )
            if not isinstance(result, dict):
                result = {
                    "price": None,
                    "source": "UNKNOWN",
                    "status": "BAD_RESULT",
                    "reason": "get_live_price_debug returned non-dict result",
                }
        except Exception as exc:
            result = {
                "price": None,
                "source": "UNKNOWN",
                "status": "ERROR",
                "reason": str(exc),
            }

        health_check_price = result.get("price")
        health_check_source = result.get("source")
        health_check_status = result.get("status")
        health_check_reason = result.get("reason")
        token_status = _health_check_token_status(
            health_check_price,
            health_check_source,
            health_check_status,
            health_check_reason,
        )
        after_meta = _read_json(META_CACHE_FILE)
        meta_cache_exists = _meta_cache_exists()
        meta_cache_updated = (
            health_check_price is not None
            and health_check_source == "UPSTOX"
            and health_check_status == "ACTIVE"
            and _meta_cache_updated_for_symbol(
                health_check_symbol,
                before_meta,
                after_meta,
            )
        )
        readiness_status = _readiness_status(
            meta_cache_exists,
            meta_cache_updated,
            token_status,
        )
        payload = {
            "timestamp_ist": now_ist.isoformat(),
            "status": "NO_OPEN_POSITIONS_HEALTH_CHECK_COMPLETE",
            "symbols_checked": 1,
            "successful_prices": 1 if health_check_price is not None else 0,
            "failed_prices": 0 if health_check_price is not None else 1,
            "meta_cache_exists": meta_cache_exists,
            "meta_cache_updated": meta_cache_updated,
            "cache_meta_updated": meta_cache_updated,
            "readiness_status": readiness_status,
            "price_cache_meta_path": META_CACHE_FILE,
            "max_symbols_per_run": MAX_SYMBOLS_PER_RUN,
            "network_or_token_failure_count": (
                1 if health_check_status in NETWORK_OR_TOKEN_FAILURE_STATUSES else 0
            ),
            "health_check_symbol": health_check_symbol,
            "health_check_price": health_check_price,
            "health_check_source": health_check_source,
            "health_check_status": health_check_status,
            "token_status": token_status,
            "token_action_required": token_status == "INVALID_OR_EXPIRED",
            "upstox_extended_token_recommended": True,
            "price_results": [
                {
                    "symbol": health_check_symbol,
                    "price": health_check_price,
                    "source": health_check_source,
                    "status": health_check_status,
                    "reason": health_check_reason,
                }
            ],
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
    token_status = "UNKNOWN"

    for symbol in symbols:
        before_meta = _read_json(META_CACHE_FILE)
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
            reason = result.get("reason")

            if status in NETWORK_OR_TOKEN_FAILURE_STATUSES:
                network_or_token_failure_count += 1

            if price is not None and source == "UPSTOX" and status == "ACTIVE":
                after_meta = _read_json(META_CACHE_FILE)
                cache_meta_updated = (
                    cache_meta_updated
                    or _meta_cache_updated_for_symbol(symbol, before_meta, after_meta)
                )
                token_status = "VALID"
            elif _is_auth_token_failure(status, reason):
                token_status = "INVALID_OR_EXPIRED"

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
                    "reason": reason,
                }
            )
        except Exception as exc:
            failed_prices += 1
            if _is_auth_token_failure("ERROR", str(exc)):
                token_status = "INVALID_OR_EXPIRED"
            price_results.append(
                {
                    "symbol": symbol,
                    "price": None,
                    "source": "UNKNOWN",
                    "status": "ERROR",
                    "reason": str(exc),
                }
            )

    meta_cache_exists = _meta_cache_exists()
    readiness_status = _readiness_status(
        meta_cache_exists,
        cache_meta_updated,
        token_status,
    )
    payload = {
        "timestamp_ist": now_ist.isoformat(),
        "status": "LIVE_PRICE_CACHE_REFRESHED",
        "symbols_checked": len(symbols),
        "successful_prices": successful_prices,
        "failed_prices": failed_prices,
        "meta_cache_exists": meta_cache_exists,
        "meta_cache_updated": cache_meta_updated,
        "cache_meta_updated": cache_meta_updated,
        "readiness_status": readiness_status,
        "price_cache_meta_path": META_CACHE_FILE,
        "max_symbols_per_run": MAX_SYMBOLS_PER_RUN,
        "network_or_token_failure_count": network_or_token_failure_count,
        "token_status": token_status,
        "token_action_required": token_status == "INVALID_OR_EXPIRED",
        "upstox_extended_token_recommended": True,
        "price_results": price_results,
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_live_price_monitor(), indent=2, sort_keys=True))
