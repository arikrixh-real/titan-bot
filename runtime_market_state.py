from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "data" / "runtime"
LIVE_PRICE_CACHE_PATH = ROOT / "data" / "live_price_cache.json"
LIVE_PRICE_STATUS_PATH = ROOT / "data" / "live_price_status.json"
LIVE_PRICE_META_PATH = RUNTIME_DIR / "live_price_cache_meta.json"
COMMON_SNAPSHOT_PATH = ROOT / "data" / "common_market_snapshot.json"
UNIVERSE_QUALITY_PATH = ROOT / "data" / "universe_quality_snapshot.json"
MARKET_STATE_PATH = RUNTIME_DIR / "shared_market_state.json"

IST = timezone(timedelta(hours=5, minutes=30))
LTP_FRESH_SECONDS = 120
MICROSTRUCTURE_FRESH_SECONDS = 120
OHLC_FRESH_SECONDS = 24 * 3600
MARKET_REFRESH_SECONDS = 5
UNIVERSE_REFRESH_SECONDS = 300

_STATE_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "symbols": {},
    "last_market_refresh_monotonic": 0.0,
    "last_universe_refresh_monotonic": 0.0,
}


def now_ist() -> datetime:
    return datetime.now(IST)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if payload is not None else default
    except Exception:
        return default


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


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def safe_int(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def parse_dt(value: Any) -> datetime | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        timestamp = value / 1000 if value > 9999999999 else value
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(IST)
        except Exception:
            return None
    text = str(value).strip()
    if text.replace(".", "", 1).isdigit():
        try:
            timestamp = float(text)
        except ValueError:
            timestamp = None
        if timestamp is not None and math.isfinite(timestamp):
            timestamp = timestamp / 1000 if timestamp > 9999999999 else timestamp
            try:
                return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(IST)
            except Exception:
                return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def age_seconds(value: Any) -> float | None:
    parsed = parse_dt(value)
    if parsed is None:
        return None
    return max(0.0, (now_ist() - parsed).total_seconds())


def payload_timestamp(payload: dict[str, Any]) -> Any:
    for key in (
        "timestamp_ist",
        "updated_at_ist",
        "timestamp",
        "updated_at",
        "generated_at_ist",
        "market_timestamp_ist",
        "cache_last_updated",
    ):
        if payload.get(key) not in (None, ""):
            return payload.get(key)
    return None


def canonical_ltp_timestamp(cache: dict[str, Any], common: dict[str, Any]) -> tuple[str | None, str | None, Any]:
    candidates = (
        ("quote_timestamp_raw", cache.get("quote_timestamp_raw")),
        ("exchange_timestamp", cache.get("exchange_timestamp") or cache.get("exchangeTimestamp")),
        ("timestamp_ist", cache.get("timestamp_ist")),
        ("updated_at_ist", cache.get("updated_at_ist")),
        ("timestamp", cache.get("timestamp")),
        ("updated_at", cache.get("updated_at")),
        ("market_timestamp_ist", common.get("market_timestamp_ist")),
    )
    for source_key, value in candidates:
        parsed = parse_dt(value)
        if parsed is not None:
            return parsed.isoformat(), source_key, value
    return None, None, None


def _cache_symbol_rows(cache: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(cache, dict):
        return {}
    rows = cache.get("prices") if isinstance(cache.get("prices"), dict) else cache
    result: dict[str, dict[str, Any]] = {}
    cache_timestamp = payload_timestamp(cache)
    for key, value in rows.items():
        symbol = str(key or "").upper().replace(".NS", "")
        if not symbol:
            continue
        if isinstance(value, dict):
            row = dict(value)
        else:
            row = {"ltp": value}
        row.setdefault("symbol", symbol)
        if cache_timestamp and not payload_timestamp(row):
            row["timestamp_ist"] = cache_timestamp
        result[symbol] = row
    return result


def _common_snapshot_rows(snapshot: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return {}
    rows = {}
    for item in snapshot.get("symbols") or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper().replace(".NS", "")
        if symbol:
            rows[symbol] = item
    return rows


def _spread_from_bid_ask(bid: float | None, ask: float | None) -> tuple[float | None, float | None]:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        return None, None
    spread = round(ask - bid, 6)
    midpoint = (bid + ask) / 2
    spread_pct = round((spread / midpoint) * 100, 6) if midpoint > 0 else None
    return spread, spread_pct


def _freshness_status(ltp_age: float | None, ohlc_age: float | None) -> str:
    if ltp_age is None:
        return "UNKNOWN"
    if ltp_age > LTP_FRESH_SECONDS:
        return "STALE"
    if ohlc_age is not None and ohlc_age > OHLC_FRESH_SECONDS:
        return "DEGRADED"
    return "LIVE"


def refresh_market_data_owner(*, force: bool = False) -> dict[str, Any]:
    import time

    with _STATE_LOCK:
        elapsed = time.monotonic() - float(_STATE.get("last_market_refresh_monotonic") or 0)
        if not force and elapsed < MARKET_REFRESH_SECONDS:
            return {"status": "SKIPPED_RECENT", "elapsed_seconds": round(elapsed, 3)}
        _STATE["last_market_refresh_monotonic"] = time.monotonic()

    try:
        from tools.refresh_live_price_cache import refresh_once

        result = refresh_once()
        return result if isinstance(result, dict) else {"status": "OK"}
    except Exception as exc:
        return {"status": "DEGRADED", "reason": f"{type(exc).__name__}:{exc}"}


def refresh_universe_owner(*, force: bool = False) -> dict[str, Any]:
    import time

    with _STATE_LOCK:
        elapsed = time.monotonic() - float(_STATE.get("last_universe_refresh_monotonic") or 0)
        if not force and elapsed < UNIVERSE_REFRESH_SECONDS:
            return {"status": "SKIPPED_RECENT", "elapsed_seconds": round(elapsed, 3)}
        _STATE["last_universe_refresh_monotonic"] = time.monotonic()

    try:
        from tools.refresh_universe_selectors import refresh_once

        result = refresh_once()
        return result if isinstance(result, dict) else {"status": "OK"}
    except Exception as exc:
        return {"status": "DEGRADED", "reason": f"{type(exc).__name__}:{exc}"}


def build_shared_market_state(*, refresh_market: bool = False, refresh_universe: bool = False) -> dict[str, Any]:
    market_refresh = refresh_market_data_owner(force=refresh_market) if refresh_market else {"status": "NOT_REQUESTED"}
    universe_refresh = refresh_universe_owner(force=refresh_universe) if refresh_universe else {"status": "NOT_REQUESTED"}

    live_status = read_json(LIVE_PRICE_STATUS_PATH, {})
    live_meta = read_json(LIVE_PRICE_META_PATH, {})
    cache_rows = _cache_symbol_rows(read_json(LIVE_PRICE_CACHE_PATH, {}))
    common_rows = _common_snapshot_rows(read_json(COMMON_SNAPSHOT_PATH, {}))
    all_symbols = sorted(set(cache_rows) | set(common_rows))

    symbols: dict[str, dict[str, Any]] = {}
    live_count = 0
    freshness_counts: dict[str, int] = {}
    ltp_ages = []
    ohlc_ages = []
    micro_ages = []
    blockers: list[str] = []
    token_type = (
        (live_status or {}).get("token_type_used")
        or (live_meta or {}).get("token_type_used")
        or "UPSTOX_ANALYTICS_TOKEN"
    )
    for symbol in all_symbols:
        cache = cache_rows.get(symbol, {})
        common = common_rows.get(symbol, {})
        timestamp, timestamp_source, source_timestamp_raw = canonical_ltp_timestamp(cache, common)
        ltp = safe_float(cache.get("ltp") or cache.get("price") or cache.get("last_price") or common.get("ltp"))
        volume = safe_int(cache.get("volume") or common.get("volume"))
        bid = safe_float(cache.get("bid") or common.get("bid"))
        ask = safe_float(cache.get("ask") or common.get("ask"))
        spread = safe_float(cache.get("spread") or common.get("spread"))
        spread_pct = safe_float(cache.get("spread_pct") or common.get("spread_pct"))
        if spread is None or spread_pct is None:
            spread, spread_pct = _spread_from_bid_ask(bid, ask)
        ltp_age = age_seconds(timestamp)
        micro_age = ltp_age if bid is not None and ask is not None and spread is not None else None
        ohlc_age = safe_float(common.get("ohlc_age_seconds"))
        freshness = _freshness_status(ltp_age, ohlc_age)
        freshness_counts[freshness] = freshness_counts.get(freshness, 0) + 1
        if freshness == "LIVE":
            live_count += 1
        if ltp_age is not None:
            ltp_ages.append(ltp_age)
        if micro_age is not None:
            micro_ages.append(micro_age)
        if ohlc_age is not None:
            ohlc_ages.append(ohlc_age)
        symbols[symbol] = {
            "symbol": symbol,
            "instrument_key": cache.get("instrument_key") or common.get("instrument_key"),
            "ltp": ltp,
            "volume": volume,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "spread_pct": spread_pct,
            "quote_status": cache.get("status") or common.get("market_data_status"),
            "quote_failure_reason": cache.get("reason"),
            "quote_age_seconds": safe_float(cache.get("quote_age_seconds")),
            "ltp_timestamp_ist": timestamp,
            "ltp_timestamp_source": timestamp_source,
            "source_timestamp_raw": source_timestamp_raw,
            "latest_tick_timestamp": timestamp,
            "ltp_age_seconds": round(ltp_age, 3) if ltp_age is not None else None,
            "microstructure_age_seconds": round(micro_age, 3) if micro_age is not None else None,
            "ohlc_snapshot": {
                "status": common.get("ohlc_status"),
                "rows": common.get("ohlc_rows"),
                "latest_timestamp": common.get("ohlc_latest_timestamp"),
                "open": common.get("ohlc_open") or common.get("open"),
                "high": common.get("ohlc_high") or common.get("high"),
                "low": common.get("ohlc_low") or common.get("low"),
                "close": common.get("ohlc_close") or common.get("close"),
                "volume": common.get("ohlc_volume") or common.get("volume"),
                "volatility_pct": common.get("volatility_pct"),
                "movement_pct": common.get("movement_pct"),
            },
            "ohlc_age_seconds": round(ohlc_age, 3) if ohlc_age is not None else None,
            "feed_status": freshness,
            "freshness_status": freshness,
            "token_type_used": token_type,
            "source_owner": "runtime_market_state",
        }
    if not symbols:
        blockers.append("shared_market_state_empty")
    if str((live_status or {}).get("status") or "").upper() in {"AUTH_REQUIRED", "FAILED", "ERROR"}:
        blockers.append(str((live_status or {}).get("reason") or (live_status or {}).get("status")))
    stale_or_degraded_count = len(symbols) - live_count
    if symbols and stale_or_degraded_count > 0:
        blockers.append(f"stale_or_degraded_symbols:{stale_or_degraded_count}")
    if symbols and not micro_ages:
        blockers.append("missing_real_microstructure")
    if ohlc_ages and max(ohlc_ages) > OHLC_FRESH_SECONDS:
        blockers.append(f"stale_ohlc_age_seconds:{round(max(ohlc_ages), 3)}")

    feed_status = "LIVE"
    if not symbols or live_count == 0:
        feed_status = "STALE"
    elif live_count < len(symbols):
        feed_status = "DEGRADED"

    payload = {
        "status": "ACTIVE" if symbols else "MISSING",
        "timestamp_ist": now_ist().isoformat(),
        "source_owner": "runtime_market_state",
        "token_type_used": token_type,
        "feed_status": feed_status,
        "freshness_status": feed_status,
        "symbol_count": len(symbols),
        "live_feed_count": live_count,
        "freshness_counts": freshness_counts,
        "ltp_age_seconds": round(max(ltp_ages), 3) if ltp_ages else None,
        "ohlc_age_seconds": round(max(ohlc_ages), 3) if ohlc_ages else None,
        "microstructure_age_seconds": round(max(micro_ages), 3) if micro_ages else None,
        "market_refresh": market_refresh,
        "universe_refresh": universe_refresh,
        "blockers": blockers,
        "symbols": symbols,
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
    }
    with _STATE_LOCK:
        _STATE["symbols"] = symbols
        _STATE["snapshot"] = payload
    atomic_write_json(MARKET_STATE_PATH, payload)
    return payload


def get_symbol_state(symbol: str) -> dict[str, Any] | None:
    key = str(symbol or "").upper().replace(".NS", "")
    with _STATE_LOCK:
        row = (_STATE.get("symbols") or {}).get(key)
    if row:
        return dict(row)
    snapshot = read_json(MARKET_STATE_PATH, {})
    symbols = snapshot.get("symbols") if isinstance(snapshot, dict) else {}
    row = symbols.get(key) if isinstance(symbols, dict) else None
    return dict(row) if isinstance(row, dict) else None
