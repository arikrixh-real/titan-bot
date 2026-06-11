"""Real cached HFT universe built from TITAN live price cache evidence."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.universe_selectors import select_hft_universe
from hft_mode.hft_candidate import MAX_PRICE, MIN_PRICE, PREFERRED_MAX_PRICE, PREFERRED_MIN_PRICE
from hft_mode.hft_data_contracts import HFTSymbolState

HFT_DIR = ROOT / "data" / "hft_mode"
UNIVERSE_CACHE_PATH = HFT_DIR / "hft_universe_cache.json"
LIVE_PRICE_CACHE_PATH = ROOT / "data" / "live_price_cache.json"
RUNTIME_META_PATH = ROOT / "data" / "runtime" / "live_price_cache_meta.json"
ROOT_META_PATH = ROOT / "data" / "live_price_cache_meta.json"
IST = timezone(timedelta(hours=5, minutes=30))
MIN_UNIVERSE_SIZE = 60
MAX_UNIVERSE_SIZE = 80
FRESH_SECONDS = 180


def now_ist() -> datetime:
    return datetime.now(IST)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
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


def parse_dt(value: Any) -> datetime | None:
    if value in (None, "", "null"):
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def payload_time(payload: dict[str, Any]) -> datetime | None:
    for key in ("timestamp_ist", "generated_at_ist", "cache_last_updated", "updated_at_ist", "timestamp", "updated_at"):
        parsed = parse_dt(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def age_seconds(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return max(0.0, (now_ist() - dt.astimezone(IST)).total_seconds())


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


def latest_live_price_meta() -> tuple[dict[str, Any], float | None]:
    runtime_meta = read_json(RUNTIME_META_PATH, {})
    root_meta = read_json(ROOT_META_PATH, {})
    candidates = [item for item in (runtime_meta, root_meta) if isinstance(item, dict) and item]
    if not candidates:
        return {}, None
    candidates.sort(key=lambda item: payload_time(item) or datetime.fromtimestamp(0, tz=IST), reverse=True)
    chosen = candidates[0]
    return chosen, age_seconds(payload_time(chosen))


def _entry_from_cache(symbol: str, raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        ltp = safe_float(raw.get("ltp") or raw.get("price") or raw.get("last_price"))
        timestamp = raw.get("timestamp_ist") or raw.get("updated_at_ist") or raw.get("timestamp")
        return {
            "symbol": str(raw.get("symbol") or symbol).upper(),
            "instrument_key": raw.get("instrument_key"),
            "ltp": ltp,
            "volume": safe_int(raw.get("volume")),
            "spread": safe_float(raw.get("spread")),
            "source": raw.get("source") or "upstox/live_price_cache",
            "timestamp_ist": timestamp,
        }
    ltp = safe_float(raw)
    return {
        "symbol": str(symbol).upper(),
        "instrument_key": None,
        "ltp": ltp,
        "volume": None,
        "spread": None,
        "source": "upstox/live_price_cache",
        "timestamp_ist": None,
    }


def _eligible_symbols(cache: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for symbol, raw in cache.items():
        entry = _entry_from_cache(symbol, raw)
        if not entry or entry.get("ltp") is None:
            continue
        price = float(entry["ltp"])
        if MIN_PRICE <= price <= MAX_PRICE:
            entries.append(entry)
    entries.sort(
        key=lambda item: (
            not (PREFERRED_MIN_PRICE <= float(item["ltp"]) <= PREFERRED_MAX_PRICE),
            -(item.get("volume") or 0),
            item["symbol"],
        )
    )
    return entries[:MAX_UNIVERSE_SIZE]


def build_hft_universe_cache(path: Path = UNIVERSE_CACHE_PATH) -> dict[str, Any]:
    if path == UNIVERSE_CACHE_PATH:
        return select_hft_universe(path=path)

    generated_at = now_ist().isoformat()
    meta, meta_age = latest_live_price_meta()
    cache = read_json(LIVE_PRICE_CACHE_PATH, {})
    meta_status = str(meta.get("status") or meta.get("cache_status") or "").upper() if isinstance(meta, dict) else ""
    auth_required = meta_status in {"AUTH_REQUIRED", "TOKEN_MISSING", "INACTIVE"}
    cache_fresh = bool(meta_age is not None and meta_age <= FRESH_SECONDS)

    if not isinstance(cache, dict) or not cache:
        status = "AUTH_REQUIRED" if auth_required else "MISSING"
        payload = {
            "status": status,
            "timestamp_ist": generated_at,
            "price_range": "20-25",
            "fallback_range": "15-25",
            "count": 0,
            "symbols": [],
            "source": "upstox/live_price_cache",
            "reason": "live_price_cache_missing",
            "live_price_cache_age_seconds": meta_age,
        }
        atomic_write_json(path, payload)
        return payload

    symbols = _eligible_symbols(cache) if cache_fresh else []
    preferred_count = sum(1 for item in symbols if PREFERRED_MIN_PRICE <= float(item["ltp"]) <= PREFERRED_MAX_PRICE)
    if auth_required:
        status = "AUTH_REQUIRED"
    elif not cache_fresh:
        status = "STALE"
    elif not symbols:
        status = "MISSING"
    elif len(symbols) < MIN_UNIVERSE_SIZE:
        status = "PARTIAL"
    else:
        status = "ACTIVE"

    payload = {
        "status": status,
        "timestamp_ist": generated_at,
        "price_range": "20-25",
        "fallback_range": "15-25",
        "count": len(symbols),
        "preferred_count": preferred_count,
        "target_count": MIN_UNIVERSE_SIZE,
        "max_count": MAX_UNIVERSE_SIZE,
        "symbols": symbols,
        "source": "upstox/live_price_cache",
        "live_price_cache_age_seconds": round(meta_age, 3) if meta_age is not None else None,
        "live_price_status": meta_status or None,
        "reason": "" if status in {"ACTIVE", "PARTIAL"} else "live_price_cache_stale_or_unavailable",
    }
    atomic_write_json(path, payload)
    return payload


def read_hft_universe_cache(path: Path = UNIVERSE_CACHE_PATH, max_age_seconds: int = FRESH_SECONDS) -> dict[str, Any]:
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return {}
    dt = payload_time(payload)
    if age_seconds(dt) is None or age_seconds(dt) > max_age_seconds:
        stale = dict(payload)
        stale["status"] = "STALE"
        stale["reason"] = stale.get("reason") or "hft_universe_cache_stale"
        return stale
    return payload


def cached_hft_symbol_states(limit: int = MAX_UNIVERSE_SIZE) -> list[HFTSymbolState]:
    payload = read_hft_universe_cache()
    if str(payload.get("status") or "").upper() not in {"ACTIVE", "PARTIAL"}:
        return []
    states = []
    for item in (payload.get("symbols") or [])[: max(0, min(limit, MAX_UNIVERSE_SIZE))]:
        if not isinstance(item, dict):
            continue
        price = safe_float(item.get("ltp"))
        if price is None:
            continue
        spread = safe_float(item.get("spread"))
        states.append(
            HFTSymbolState(
                symbol=str(item.get("symbol") or "").upper(),
                price=price,
                timestamp=parse_dt(item.get("timestamp_ist")) or payload_time(payload),
                volume=safe_int(item.get("volume")),
                bid=None,
                ask=None,
                spread_pct=spread,
                source=item.get("source") or "upstox/live_price_cache",
                is_fresh=True,
                is_liquid=item.get("volume") is not None,
                is_circuit_prone=False,
            )
        )
    return states


def get_static_hft_universe(limit: int = MAX_UNIVERSE_SIZE) -> list[HFTSymbolState]:
    return cached_hft_symbol_states(limit)


if __name__ == "__main__":
    print(json.dumps(build_hft_universe_cache(), indent=2, sort_keys=True))
