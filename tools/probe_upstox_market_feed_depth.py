"""Read-only probe for Upstox V3 market data feed top-of-book depth.

Subscribes to YESBANK only and prints connection/subscription/tick details.
This script does not write runtime files and does not place orders.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import upstox_client

from data.upstox_auth import configure_market_data_sdk, market_data_token_info


INSTRUMENT_KEY = "NSE_EQ|INE528G01035"
SYMBOL = "YESBANK"
DEFAULT_MODE = "full_d30"


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def safe_int(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def top_book_from_message(message: dict[str, Any]) -> dict[str, Any]:
    feeds = message.get("feeds") if isinstance(message, dict) else None
    feed = feeds.get(INSTRUMENT_KEY) if isinstance(feeds, dict) else None
    if not isinstance(feed, dict):
        return {
            "feed_present": False,
            "raw_top_of_book_keys": [],
            "bid_price": None,
            "ask_price": None,
            "spread": None,
        }

    quote = None
    path = []
    full_feed = feed.get("fullFeed")
    if isinstance(full_feed, dict):
        market_ff = full_feed.get("marketFF") or full_feed.get("indexFF")
        if isinstance(market_ff, dict):
            market_level = market_ff.get("marketLevel")
            if isinstance(market_level, dict):
                levels = market_level.get("bidAskQuote")
                if isinstance(levels, list) and levels:
                    quote = next((item for item in levels if isinstance(item, dict)), None)
                    path = ["feeds", INSTRUMENT_KEY, "fullFeed", "marketFF", "marketLevel", "bidAskQuote", "0"]
    if quote is None and isinstance(feed.get("firstLevelWithGreeks"), dict):
        flwg = feed.get("firstLevelWithGreeks")
        quote = flwg.get("firstDepth") if isinstance(flwg, dict) else None
        path = ["feeds", INSTRUMENT_KEY, "firstLevelWithGreeks", "firstDepth"]

    if not isinstance(quote, dict):
        return {
            "feed_present": True,
            "raw_top_of_book_keys": [],
            "top_of_book_path": path,
            "bid_price": None,
            "ask_price": None,
            "spread": None,
        }

    bid_price = safe_float(quote.get("bidP") or quote.get("bidPrice") or quote.get("bid_price"))
    ask_price = safe_float(quote.get("askP") or quote.get("askPrice") or quote.get("ask_price"))
    bid_qty = safe_int(quote.get("bidQ") or quote.get("bidQty") or quote.get("bid_quantity"))
    ask_qty = safe_int(quote.get("askQ") or quote.get("askQty") or quote.get("ask_quantity"))
    spread = round(ask_price - bid_price, 6) if bid_price is not None and ask_price is not None and bid_price <= ask_price else None
    return {
        "feed_present": True,
        "top_of_book_path": path,
        "raw_top_of_book_keys": sorted(quote.keys()),
        "bid_price": bid_price,
        "ask_price": ask_price,
        "bid_quantity": bid_qty,
        "ask_quantity": ask_qty,
        "spread": spread,
        "valid_bid_ask": bool(bid_price is not None and ask_price is not None and spread is not None),
    }


def get_authorize_status(api_client: upstox_client.ApiClient) -> dict[str, Any]:
    try:
        api = upstox_client.WebsocketApi(api_client)
        response = api.get_market_data_feed_authorize_v3()
        payload = response.to_dict() if hasattr(response, "to_dict") else {}
        uri = ((payload.get("data") or {}).get("authorized_redirect_uri") or "")
        return {
            "authorize_status": payload.get("status"),
            "authorized_redirect_uri_present": bool(uri),
            "authorized_redirect_uri_prefix": uri[:32] if uri else None,
        }
    except Exception as exc:
        return {
            "authorize_status": "ERROR",
            "authorize_error": f"{type(exc).__name__}:{str(exc)[:240]}",
        }


def run_probe(timeout_seconds: float = 12.0, mode: str = DEFAULT_MODE) -> dict[str, Any]:
    token_info = market_data_token_info()
    configuration = configure_market_data_sdk(upstox_client.Configuration())
    api_client = upstox_client.ApiClient(configuration)
    authorize = get_authorize_status(api_client)
    done = threading.Event()
    messages: list[dict[str, Any]] = []
    message_summaries: list[dict[str, Any]] = []
    errors: list[str] = []
    state: dict[str, Any] = {
        "symbol": SYMBOL,
        "instrument_key": INSTRUMENT_KEY,
        "mode": mode,
        "token_type_used": token_info.get("token_type"),
        "read_only": True,
        "trade_placement_allowed": False,
        "connection_status": "NOT_STARTED",
        "subscription_status": "NOT_SENT",
        **authorize,
    }

    streamer = upstox_client.MarketDataStreamerV3(
        api_client,
        instrumentKeys=[INSTRUMENT_KEY],
        mode=mode,
    )
    streamer.auto_reconnect(False)

    def on_open():
        state["connection_status"] = "OPEN"
        state["subscription_status"] = "SUBSCRIBED_ON_OPEN"

    def on_message(message):
        messages.append(message)
        if len(message_summaries) < 5:
            message_summaries.append(
                {
                    "keys": sorted(message.keys()) if isinstance(message, dict) else [],
                    "type": message.get("type") if isinstance(message, dict) else None,
                    "feed_keys": sorted((message.get("feeds") or {}).keys())[:5] if isinstance(message.get("feeds") if isinstance(message, dict) else None, dict) else [],
                    "market_info_keys": sorted((message.get("marketInfo") or {}).keys()) if isinstance(message.get("marketInfo") if isinstance(message, dict) else None, dict) else [],
                }
            )
        top = top_book_from_message(message)
        state.update(top)
        state["received_tick_count"] = len(messages)
        if top.get("valid_bid_ask"):
            done.set()

    def on_error(error):
        errors.append(str(error))
        state["connection_status"] = "ERROR"
        state["last_error"] = str(error)[:300]
        done.set()

    def on_close(code=None, reason=None):
        state["close_code"] = code
        state["close_reason"] = reason
        if state.get("connection_status") not in {"ERROR", "OPEN"}:
            state["connection_status"] = "CLOSED"

    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)

    try:
        streamer.connect()
        started = time.time()
        while time.time() - started < timeout_seconds and not done.is_set():
            time.sleep(0.25)
    finally:
        try:
            streamer.disconnect()
        except Exception:
            pass

    state.setdefault("received_tick_count", len(messages))
    state.setdefault("feed_present", False)
    state.setdefault("raw_top_of_book_keys", [])
    state.setdefault("bid_price", None)
    state.setdefault("ask_price", None)
    state.setdefault("spread", None)
    state["errors"] = errors
    state["message_summaries"] = message_summaries
    state["valid_bid_ask"] = bool(state.get("bid_price") is not None and state.get("ask_price") is not None and state.get("spread") is not None)
    state["feed_provides_valid_bid_ask"] = state["valid_bid_ask"]
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Upstox V3 market data feed depth for YESBANK only.")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--mode", default=DEFAULT_MODE, choices=["full", "full_d30", "ltpc"])
    args = parser.parse_args()
    result = run_probe(timeout_seconds=args.timeout, mode=args.mode)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("connection_status") in {"OPEN", "ERROR"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
