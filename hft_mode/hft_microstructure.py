"""Read-only HFT microstructure input from Upstox full market quotes."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.upstox_auth import UpstoxMarketDataAuthError, market_data_headers, market_data_token_info
from hft_mode.hft_candidate import MAX_PRICE, MIN_PRICE, calculate_spread_pct, reject_reason_for_tick
from hft_mode.hft_data_contracts import HFTPriceTick
from hft_mode.hft_universe import parse_dt, safe_float, safe_int


IST = timezone(timedelta(hours=5, minutes=30))
HFT_DIR = ROOT / "data" / "hft_mode"
MICROSTRUCTURE_PATH = HFT_DIR / "hft_microstructure_status.json"
FULL_QUOTE_URL = "https://api.upstox.com/v2/market-quote/quotes"
MAX_BATCH_SIZE = 50


def now_ist() -> datetime:
    return datetime.now(IST)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def chunks(items: list[dict[str, Any]], size: int = MAX_BATCH_SIZE):
    for index in range(0, len(items), max(1, int(size))):
        yield items[index : index + max(1, int(size))]


def _extract_quote(payload: dict[str, Any], instrument_key: str) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {}
    for key in (instrument_key, instrument_key.replace("|", ":"), instrument_key.replace(":", "|")):
        item = data.get(key)
        if isinstance(item, dict):
            return item
    for item in data.values():
        if not isinstance(item, dict):
            continue
        item_token = item.get("instrument_token") or item.get("instrumentKey")
        if item_token == instrument_key:
            return item
    return {}


def _first_depth_price(levels: Any) -> tuple[float | None, int | None]:
    if not isinstance(levels, list):
        return None, None
    for level in levels:
        if not isinstance(level, dict):
            continue
        price = safe_float(level.get("price"))
        qty = safe_int(level.get("quantity") or level.get("qty"))
        if price is not None and price > 0:
            return price, qty
    return None, None


def _bid_ask_from_quote(quote: dict[str, Any]) -> tuple[float | None, float | None, int | None, int | None]:
    bid = safe_float(quote.get("bid") or quote.get("best_bid") or quote.get("bid_price"))
    ask = safe_float(quote.get("ask") or quote.get("best_ask") or quote.get("ask_price"))
    bid_qty = safe_int(quote.get("bid_qty") or quote.get("bid_quantity") or quote.get("total_buy_quantity"))
    ask_qty = safe_int(quote.get("ask_qty") or quote.get("ask_quantity") or quote.get("total_sell_quantity"))

    bid_ask = quote.get("bid_ask_quote")
    if isinstance(bid_ask, dict):
        bid = bid or safe_float(bid_ask.get("bid_price") or bid_ask.get("bidPrice"))
        ask = ask or safe_float(bid_ask.get("ask_price") or bid_ask.get("askPrice"))
        bid_qty = bid_qty or safe_int(bid_ask.get("bid_qty") or bid_ask.get("bid_quantity") or bid_ask.get("bidQty"))
        ask_qty = ask_qty or safe_int(bid_ask.get("ask_qty") or bid_ask.get("ask_quantity") or bid_ask.get("askQty"))

    depth = quote.get("depth")
    if isinstance(depth, dict):
        depth_bid, depth_bid_qty = _first_depth_price(depth.get("buy"))
        depth_ask, depth_ask_qty = _first_depth_price(depth.get("sell"))
        bid = bid or depth_bid
        ask = ask or depth_ask
        bid_qty = bid_qty or depth_bid_qty
        ask_qty = ask_qty or depth_ask_qty

    return bid, ask, bid_qty, ask_qty


def _quote_ltp(quote: dict[str, Any]) -> float | None:
    return safe_float(quote.get("last_price") or quote.get("ltp") or quote.get("lastPrice"))


def _quote_volume(quote: dict[str, Any]) -> int | None:
    return safe_int(quote.get("volume") or quote.get("volume_traded") or quote.get("total_volume"))


def _row_from_quote(symbol_item: dict[str, Any], quote: dict[str, Any], timestamp: str) -> dict[str, Any]:
    symbol = str(symbol_item.get("symbol") or "").upper()
    instrument_key = symbol_item.get("instrument_key")
    ltp = _quote_ltp(quote) or safe_float(symbol_item.get("ltp"))
    volume = _quote_volume(quote) or safe_int(symbol_item.get("volume"))
    bid, ask, bid_qty, ask_qty = _bid_ask_from_quote(quote)
    spread_pct = None
    spread = None
    reason = None

    if bid is not None and ask is not None and bid > 0 and ask > 0 and bid <= ask:
        spread = round(ask - bid, 6)
        spread_pct = calculate_spread_pct(bid, ask)

    tick = HFTPriceTick(
        symbol=symbol,
        price=ltp,
        timestamp=parse_dt(timestamp) or now_ist(),
        volume=volume,
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        source="upstox_full_market_quote",
        is_fresh=True,
    )
    reason = reject_reason_for_tick(tick, spread_pct=spread_pct)
    if reason is None and (ltp is None or ltp < MIN_PRICE or ltp > MAX_PRICE):
        reason = "price_outside_15_25"

    return {
        "symbol": symbol,
        "instrument_key": instrument_key,
        "ltp": ltp,
        "volume": volume,
        "bid": bid,
        "ask": ask,
        "bid_quantity": bid_qty,
        "ask_quantity": ask_qty,
        "spread": spread,
        "spread_pct": spread_pct,
        "source": "upstox_full_market_quote",
        "endpoint": FULL_QUOTE_URL,
        "timestamp_ist": timestamp,
        "status": "VALID" if reason is None else "REJECTED",
        "reason": reason,
        "raw_quote_present": bool(quote),
    }


def collect_hft_microstructure(symbols: list[dict[str, Any]], path: Path = MICROSTRUCTURE_PATH) -> dict[str, Any]:
    timestamp = now_ist().isoformat()
    clean_symbols = [
        item for item in symbols
        if isinstance(item, dict) and item.get("symbol") and item.get("instrument_key")
    ]
    try:
        headers = market_data_headers()
        token_type = market_data_token_info().get("token_type", "ANALYTICS_TOKEN")
    except UpstoxMarketDataAuthError as exc:
        payload = {
            "status": "AUTH_REQUIRED",
            "timestamp_ist": timestamp,
            "source_endpoint": FULL_QUOTE_URL,
            "token_type_used": "MISSING_ANALYTICS_TOKEN",
            "symbols_processed": 0,
            "valid_bid_ask_count": 0,
            "records": [],
            "rejected": [],
            "reason": str(exc),
            "read_only": True,
            "trade_placement_allowed": False,
        }
        atomic_write_json(path, payload)
        return payload

    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for batch in chunks(clean_symbols):
        params = {"instrument_key": ",".join(str(item.get("instrument_key")) for item in batch)}
        try:
            response = requests.get(FULL_QUOTE_URL, headers=headers, params=params, timeout=12)
            try:
                payload = response.json()
            except Exception:
                payload = {}
            if response.status_code != 200:
                for item in batch:
                    rejected.append({
                        "symbol": item.get("symbol"),
                        "instrument_key": item.get("instrument_key"),
                        "reason": f"HTTP_{response.status_code}",
                    })
                errors.append({"status_code": response.status_code, "reason": str(payload)[:300]})
                continue
        except requests.RequestException as exc:
            for item in batch:
                rejected.append({
                    "symbol": item.get("symbol"),
                    "instrument_key": item.get("instrument_key"),
                    "reason": type(exc).__name__,
                })
            errors.append({"status_code": None, "reason": str(exc)[:300]})
            continue

        for item in batch:
            quote = _extract_quote(payload, str(item.get("instrument_key")))
            row = _row_from_quote(item, quote, timestamp)
            records.append(row)
            if row.get("status") != "VALID":
                rejected.append({
                    "symbol": row.get("symbol"),
                    "instrument_key": row.get("instrument_key"),
                    "reason": row.get("reason") or "invalid_microstructure",
                    "ltp": row.get("ltp"),
                    "bid": row.get("bid"),
                    "ask": row.get("ask"),
                    "spread_pct": row.get("spread_pct"),
                })

    valid = [row for row in records if row.get("status") == "VALID"]
    status = "BLOCKED_PENDING_LIVE_MARKET_TEST"
    payload = {
        "status": status,
        "timestamp_ist": timestamp,
        "source_endpoint": FULL_QUOTE_URL,
        "token_type_used": token_type,
        "symbols_requested": len(clean_symbols),
        "symbols_processed": len(records),
        "valid_bid_ask_count": len(valid),
        "signal_allowed": False,
        "paper_trade_allowed": False,
        "blocker_reason": "live_nse_market_hours_bid_ask_validation_required",
        "records": records,
        "rejected": rejected,
        "errors": errors,
        "read_only": True,
        "trade_placement_allowed": False,
    }
    atomic_write_json(path, payload)
    return payload


def valid_ticks_from_microstructure(payload: dict[str, Any]) -> list[HFTPriceTick]:
    ticks: list[HFTPriceTick] = []
    for row in payload.get("records") or []:
        if not isinstance(row, dict) or row.get("status") != "VALID":
            continue
        timestamp = parse_dt(row.get("timestamp_ist")) or now_ist()
        ticks.append(
            HFTPriceTick(
                symbol=str(row.get("symbol") or "").upper(),
                price=safe_float(row.get("ltp")),
                timestamp=timestamp,
                volume=safe_int(row.get("volume")),
                bid=safe_float(row.get("bid")),
                ask=safe_float(row.get("ask")),
                spread_pct=safe_float(row.get("spread_pct")),
                source=row.get("source") or "upstox_full_market_quote",
                is_fresh=True,
            )
        )
    return ticks


if __name__ == "__main__":
    from hft_mode.hft_universe import build_hft_universe_cache

    universe = build_hft_universe_cache()
    print(json.dumps(collect_hft_microstructure(universe.get("symbols") or []), indent=2, sort_keys=True))
