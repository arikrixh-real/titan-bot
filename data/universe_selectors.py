"""Common market universe and mode-specific selector artifacts."""

from __future__ import annotations

import json
import math
import os
import tempfile
import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from config.upstox_symbols import normalize_symbol
from data.price_cache import load_cache


ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
UNIVERSE_MASTER_PATH = ROOT / "data" / "universe_master.json"
COMMON_SNAPSHOT_PATH = ROOT / "data" / "common_market_snapshot.json"
UPSTOX_NSE_INSTRUMENT_CACHE_PATH = ROOT / "data" / "upstox_nse_eq_instruments.json"
HFT_UNIVERSE_PATH = ROOT / "data" / "hft_mode" / "hft_universe_cache.json"
CLASSIC_UNIVERSE_PATH = ROOT / "data" / "classic_mode" / "classic_universe_cache.json"
PAPER_ACCOUNT_PATH = ROOT / "data" / "paper_trading" / "paper_account.json"
CACHE_DIR = ROOT / "data" / "cache"
UPSTOX_NSE_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

HFT_TARGET_COUNT = 80
CLASSIC_TARGET_COUNT = 50
MIN_HFT_VOLUME = 250_000
MIN_HFT_PRICE = 15.0
MAX_HFT_SPREAD_PCT = 0.75
FRESH_SECONDS = 15 * 60
QUOTE_BATCH_SIZE = 50
HFT_EXCLUDED_SYMBOLS = {
    "BANK10ADD",
    "BANKBEES",
    "GOLDBEES",
    "LIQUIDBEES",
    "NIFTYBEES",
    "PHARMABEES",
    "PVTBANIETF",
    "SILVER1",
    "SILVERBEES",
    "SILVERCASE",
    "TATAGOLD",
    "TATSILV",
}
HFT_EXCLUDED_SYMBOL_FRAGMENTS = (
    "BEES",
    "ETF",
    "GOLD",
    "SILVER",
    "LIQUID",
)
HFT_EXCLUDED_NAME_FRAGMENTS = (
    "ETF",
    "EXCHANGE TRADED",
    "FUND",
    "GOLD",
    "SILVER",
    "LIQUID",
    "NIFTY",
    "SENSEX",
    "GILT",
    "G-SEC",
    "GSEC",
    "GOVT",
    "GOVERNMENT",
    "TREASURY",
)


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


def age_seconds(value: Any) -> float | None:
    parsed = parse_dt(value)
    if parsed is None:
        return None
    return max(0.0, (now_ist() - parsed).total_seconds())


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number <= 0:
        return None
    return number


def safe_int(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def account_size() -> float | None:
    account = read_json(PAPER_ACCOUNT_PATH, {})
    if not isinstance(account, dict):
        return None
    value = safe_float(account.get("current_balance") or account.get("equity") or account.get("balance"))
    return value


def chunks(items: list[Any], size: int):
    for index in range(0, len(items), max(1, int(size))):
        yield items[index : index + max(1, int(size))]


def _valid_nse_eq_instrument(row: dict[str, Any]) -> bool:
    return (
        isinstance(row, dict)
        and row.get("segment") == "NSE_EQ"
        and row.get("instrument_type") == "EQ"
        and str(row.get("instrument_key") or "").startswith("NSE_EQ|")
        and bool(str(row.get("trading_symbol") or "").strip())
    )


def load_upstox_nse_eq_instruments() -> tuple[list[dict[str, Any]], str]:
    try:
        response = requests.request("GET", UPSTOX_NSE_INSTRUMENTS_URL, timeout=30)
        response.raise_for_status()
        raw_rows = json.loads(gzip.decompress(response.content).decode("utf-8"))
        source = UPSTOX_NSE_INSTRUMENTS_URL
    except Exception:
        cached = read_json(UPSTOX_NSE_INSTRUMENT_CACHE_PATH, {})
        raw_rows = cached.get("symbols") if isinstance(cached, dict) else []
        source = str(UPSTOX_NSE_INSTRUMENT_CACHE_PATH.relative_to(ROOT))

    seen = set()
    symbols = []
    for row in raw_rows or []:
        if not _valid_nse_eq_instrument(row):
            continue
        symbol = normalize_symbol(row.get("trading_symbol"))
        instrument_key = str(row.get("instrument_key") or "").strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(
            {
                "symbol": symbol,
                "instrument_key": instrument_key,
                "exchange": row.get("exchange") or "NSE",
                "segment": row.get("segment"),
                "instrument_type": row.get("instrument_type"),
                "name": row.get("name") or row.get("short_name") or symbol,
                "short_name": row.get("short_name"),
                "isin": row.get("isin"),
                "lot_size": safe_int(row.get("lot_size")),
                "minimum_lot": safe_int(row.get("minimum_lot")),
                "tick_size": safe_float(row.get("tick_size")),
                "freeze_quantity": row.get("freeze_quantity"),
                "exchange_token": row.get("exchange_token"),
                "security_type": row.get("security_type"),
                "source": source,
            }
        )
    symbols.sort(key=lambda item: item["symbol"])
    cache_payload = {
        "status": "ACTIVE" if symbols else "MISSING",
        "timestamp_ist": now_ist().isoformat(),
        "count": len(symbols),
        "source": source,
        "symbols": symbols,
    }
    atomic_write_json(UPSTOX_NSE_INSTRUMENT_CACHE_PATH, cache_payload)
    return symbols, source


def build_universe_master(path: Path = UNIVERSE_MASTER_PATH) -> dict[str, Any]:
    symbols, source = load_upstox_nse_eq_instruments()
    payload = {
        "status": "ACTIVE" if symbols else "MISSING",
        "timestamp_ist": now_ist().isoformat(),
        "count": len(symbols),
        "source": source,
        "source_url": UPSTOX_NSE_INSTRUMENTS_URL,
        "filter": "segment=NSE_EQ,instrument_type=EQ",
        "symbols": symbols,
    }
    atomic_write_json(path, payload)
    return payload


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
        if item.get("instrument_token") == instrument_key or item.get("instrumentKey") == instrument_key:
            return item
    return {}


def _quote_ltp(quote: dict[str, Any]) -> float | None:
    return safe_float(quote.get("last_price") or quote.get("ltp") or quote.get("lastPrice"))


def _quote_volume(quote: dict[str, Any]) -> int | None:
    for key in ("volume", "total_volume", "day_volume", "last_traded_quantity", "ltq"):
        value = safe_int(quote.get(key))
        if value is not None:
            return value
    return None


def _quote_open(quote: dict[str, Any]) -> float | None:
    for key in ("open", "open_price", "day_open"):
        value = safe_float(quote.get(key))
        if value is not None:
            return value
    ohlc = quote.get("ohlc")
    if isinstance(ohlc, dict):
        return safe_float(ohlc.get("open") or ohlc.get("o"))
    return None


def _quote_change_percent(quote: dict[str, Any], ltp: float | None, open_price: float | None) -> float | None:
    for key in ("net_change_percent", "change_percent", "pct_change", "day_change_percent"):
        value = safe_float(quote.get(key))
        if value is not None:
            return value
    change = None
    for key in ("net_change", "change", "chg", "day_change", "absolute_change"):
        change = safe_float(quote.get(key))
        if change is not None:
            break
    if change is not None and open_price:
        return round((change / open_price) * 100.0, 4)
    if ltp is not None and open_price:
        return round(((ltp - open_price) / open_price) * 100.0, 4)
    return None


def _item_symbol(item: Any) -> str:
    if isinstance(item, dict):
        return normalize_symbol(item.get("symbol") or item.get("trading_symbol"))
    return normalize_symbol(item)


def fetch_quote_map(items: list[Any]) -> dict[str, dict[str, Any]]:
    quote_map: dict[str, dict[str, Any]] = {}
    cache = load_cache()
    rows = cache.get("prices") if isinstance(cache, dict) and isinstance(cache.get("prices"), dict) else cache
    rows = rows if isinstance(rows, dict) else {}
    for item in items or []:
        symbol = _item_symbol(item)
        if not symbol:
            continue
        raw = rows.get(symbol)
        if not isinstance(raw, dict):
            raw = {"ltp": raw} if raw not in (None, "") else {}
        ltp = safe_float(raw.get("ltp") or raw.get("price") or raw.get("last_price"))
        timestamp = raw.get("timestamp_ist") or raw.get("updated_at_ist") or raw.get("timestamp")
        market_age = age_seconds(timestamp) if timestamp else None
        status = raw.get("status") or ("ACTIVE" if ltp is not None else "MISSING_LTP")
        if ltp is not None and (market_age is None or market_age > FRESH_SECONDS):
            status = "STALE"
        quote_map[symbol] = {
            "symbol": symbol,
            "instrument_key": raw.get("instrument_key") or (item.get("instrument_key") if isinstance(item, dict) else None),
            "ltp": ltp,
            "open": safe_float(raw.get("open")),
            "change_percent": safe_float(raw.get("change_percent")),
            "volume": safe_int(raw.get("volume")),
            "bid": safe_float(raw.get("bid")),
            "ask": safe_float(raw.get("ask")),
            "spread": safe_float(raw.get("spread")),
            "spread_pct": safe_float(raw.get("spread_pct")),
            "timestamp_ist": timestamp,
            "source": raw.get("source") or "data/live_price_cache.json",
            "status": status,
        }
    return quote_map


def _cache_metrics(symbol: str) -> dict[str, Any]:
    path = CACHE_DIR / f"{symbol}.csv"
    if not path.exists():
        return {
            "ohlc_status": "MISSING",
            "ohlc_rows": 0,
            "ohlc_latest_timestamp": None,
            "ohlc_age_seconds": None,
            "volatility_pct": None,
            "movement_pct": None,
            "avg_volume_20": None,
        }
    try:
        df = pd.read_csv(path)
    except Exception:
        return {"ohlc_status": "READ_ERROR", "ohlc_rows": 0}
    if df is None or df.empty or "Close" not in df.columns:
        return {"ohlc_status": "EMPTY", "ohlc_rows": 0}
    df = df.copy()
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    rows = len(df)
    latest_ts = None
    if "Datetime" in df.columns and rows:
        latest_ts = str(df["Datetime"].iloc[-1])
    age = age_seconds(latest_ts)
    close = pd.to_numeric(df.get("Close"), errors="coerce").dropna()
    volume = pd.to_numeric(df.get("Volume"), errors="coerce").dropna() if "Volume" in df.columns else pd.Series(dtype=float)
    volatility = None
    movement = None
    if len(close) >= 20:
        returns = close.pct_change().dropna().tail(20)
        volatility = round(float(returns.std()) * 100.0, 4) if not returns.empty else None
        base = float(close.iloc[-20])
        if base:
            movement = round(((float(close.iloc[-1]) - base) / base) * 100.0, 4)
    return {
        "ohlc_status": "FRESH" if rows >= 60 and age is not None and age <= 24 * 3600 else "STALE",
        "ohlc_rows": rows,
        "ohlc_latest_timestamp": latest_ts,
        "ohlc_age_seconds": round(age, 3) if age is not None else None,
        "volatility_pct": volatility,
        "movement_pct": movement,
        "avg_volume_20": round(float(volume.tail(20).mean()), 2) if not volume.empty else None,
    }


def build_common_market_snapshot(master: dict[str, Any] | None = None, path: Path = COMMON_SNAPSHOT_PATH) -> dict[str, Any]:
    master = master if isinstance(master, dict) else build_universe_master()
    live_cache = load_cache()
    master_symbols = master.get("symbols") or []
    quote_map = fetch_quote_map(master_symbols)
    symbols = []
    for item in master_symbols:
        symbol = item.get("symbol")
        raw = quote_map.get(symbol) or (live_cache.get(symbol) if isinstance(live_cache, dict) else None)
        raw = raw if isinstance(raw, dict) else {}
        ltp = safe_float(raw.get("ltp") or raw.get("price") or raw.get("last_price"))
        timestamp = raw.get("timestamp_ist") or raw.get("updated_at_ist") or raw.get("timestamp")
        bid = safe_float(raw.get("bid"))
        ask = safe_float(raw.get("ask"))
        spread = safe_float(raw.get("spread"))
        spread_pct = round((spread / ltp) * 100.0, 6) if spread is not None and ltp else None
        record = {
            **item,
            "ltp": ltp,
            "volume": safe_int(raw.get("volume")),
            "open": safe_float(raw.get("open")),
            "change_percent": safe_float(raw.get("change_percent")),
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "spread_pct": spread_pct,
            "market_data_status": raw.get("status") or ("MISSING_LTP" if ltp is None else "ACTIVE"),
            "market_data_source": raw.get("source") or "data/live_price_cache.json",
            "market_timestamp_ist": timestamp,
            "market_age_seconds": round(age_seconds(timestamp), 3) if timestamp else None,
            **_cache_metrics(symbol),
        }
        symbols.append(record)
    enriched = [item for item in symbols if item.get("ltp") is not None]
    payload = {
        "status": "ACTIVE" if enriched else "MISSING",
        "timestamp_ist": now_ist().isoformat(),
        "source": "data/live_price_cache.json + data/cache/*.csv",
        "count": len(symbols),
        "enriched_count": len(enriched),
        "quote_enriched_count": len(quote_map),
        "symbols": symbols,
    }
    atomic_write_json(path, payload)
    return payload


def _hft_affordability_score(price: float, capital: float) -> float:
    if price <= 0 or capital <= 0:
        return 0.0
    max_qty = int(capital // price)
    if max_qty <= 0:
        return 0.0
    qty_score = min(max_qty / 20.0, 1.0)
    price_score = max(0.0, min((capital * 0.25 - price) / max(capital * 0.25, 1.0), 1.0))
    return round((qty_score * 0.65 + price_score * 0.35) * 100.0, 3)


def _is_hft_excluded_security(item: dict[str, Any]) -> bool:
    symbol = str(item.get("symbol") or "").upper()
    name = str(item.get("name") or item.get("short_name") or "").upper()
    if symbol in HFT_EXCLUDED_SYMBOLS:
        return True
    if any(fragment in symbol for fragment in HFT_EXCLUDED_SYMBOL_FRAGMENTS):
        return True
    return any(fragment in name for fragment in HFT_EXCLUDED_NAME_FRAGMENTS)


def select_hft_universe(snapshot: dict[str, Any] | None = None, path: Path = HFT_UNIVERSE_PATH) -> dict[str, Any]:
    snapshot = snapshot if isinstance(snapshot, dict) else build_common_market_snapshot()
    capital = account_size()
    selected = []
    rejected = []
    if capital is None:
        for item in snapshot.get("symbols") or []:
            rejected.append(
                {
                    "symbol": item.get("symbol"),
                    "reasons": ["missing_account_size"],
                    "ltp": item.get("ltp"),
                    "volume": item.get("volume"),
                }
            )
        payload = {
            "status": "DEGRADED",
            "timestamp_ist": now_ist().isoformat(),
            "source": "data/common_market_snapshot.json",
            "price_range": "dynamic_account_aware",
            "account_size": None,
            "account_size_status": "UNKNOWN",
            "blocker_reason": "MISSING_ACCOUNT_SIZE",
            "min_price": MIN_HFT_PRICE,
            "min_volume": MIN_HFT_VOLUME,
            "count": 0,
            "quality_filtered_count": 0,
            "target_count": HFT_TARGET_COUNT,
            "symbols": [],
            "rejected": rejected[:200],
            "rejected_count": len(rejected),
            "rejected_reason_counts": {"missing_account_size": len(rejected)},
            "candidate_generation_requires": "real_account_size_and_real_bid_ask_spread_from_microstructure_feed",
            "trade_placement_allowed": False,
        }
        atomic_write_json(path, payload)
        return payload
    for item in snapshot.get("symbols") or []:
        symbol = item.get("symbol")
        ltp = safe_float(item.get("ltp"))
        volume = safe_int(item.get("volume"))
        reasons = []
        if _is_hft_excluded_security(item):
            reasons.append("etf_fund_or_security_like")
        if ltp is None:
            reasons.append("missing_ltp")
        elif ltp < MIN_HFT_PRICE:
            reasons.append("penny_below_min_price")
        if volume is None or volume < MIN_HFT_VOLUME:
            reasons.append("low_or_missing_volume")
        if item.get("market_age_seconds") is None or float(item.get("market_age_seconds") or 999999) > FRESH_SECONDS:
            reasons.append("stale_market_data")
        if ltp is not None and int(capital // ltp) < 1:
            reasons.append("not_affordable_for_account")
        if item.get("spread_pct") is not None and float(item["spread_pct"]) > MAX_HFT_SPREAD_PCT:
            reasons.append("bad_spread")
        if item.get("movement_pct") in (None, "") and item.get("volatility_pct") in (None, "") and item.get("change_percent") in (None, ""):
            reasons.append("no_movement_evidence")
        if reasons:
            rejected.append({"symbol": symbol, "reasons": reasons, "ltp": ltp, "volume": volume})
            continue
        affordability = _hft_affordability_score(float(ltp), capital)
        liquidity_score = min((volume or 0) / 5_000_000, 1.0) * 100
        movement_value = item.get("movement_pct") if item.get("movement_pct") not in (None, "") else item.get("change_percent")
        movement_score = min(abs(float(movement_value or 0.0)) * 12.0, 100.0)
        volatility_score = min(float(item.get("volatility_pct") or 0.0) * 35.0, 100.0)
        score = round(affordability * 0.45 + liquidity_score * 0.25 + movement_score * 0.15 + volatility_score * 0.15, 3)
        selected.append(
            {
                **item,
                "account_size": capital,
                "affordable_quantity": int(capital // float(ltp)),
                "affordability_score": affordability,
                "selector_score": score,
                "reason": "low_price_liquid_mover_account_affordable",
                "requires_real_bid_ask_for_candidate_generation": True,
            }
        )
    selected.sort(key=lambda item: item.get("selector_score") or 0, reverse=True)
    prelimit_count = len(selected)
    selected = selected[:HFT_TARGET_COUNT]
    rejected_reason_counts: dict[str, int] = {}
    for item in rejected:
        for reason in item.get("reasons") or []:
            rejected_reason_counts[reason] = rejected_reason_counts.get(reason, 0) + 1
    payload = {
        "status": "ACTIVE" if len(selected) >= 10 else "PARTIAL" if selected else "MISSING",
        "timestamp_ist": now_ist().isoformat(),
        "source": "data/common_market_snapshot.json",
        "price_range": "dynamic_account_aware",
        "fallback_range": "account_affordable_low_price_liquid_movers",
        "account_size": capital,
        "min_price": MIN_HFT_PRICE,
        "min_volume": MIN_HFT_VOLUME,
        "count": len(selected),
        "quality_filtered_count": prelimit_count,
        "target_count": HFT_TARGET_COUNT,
        "symbols": selected,
        "rejected": rejected[:200],
        "rejected_count": len(rejected),
        "rejected_reason_counts": rejected_reason_counts,
        "excluded_etf_fund_count": rejected_reason_counts.get("etf_fund_or_security_like", 0),
        "excluded_penny_count": rejected_reason_counts.get("penny_below_min_price", 0),
        "candidate_generation_requires": "real_bid_ask_spread_from_microstructure_feed",
        "trade_placement_allowed": False,
    }
    atomic_write_json(path, payload)
    return payload


def select_classic_universe(snapshot: dict[str, Any] | None = None, path: Path = CLASSIC_UNIVERSE_PATH) -> dict[str, Any]:
    snapshot = snapshot if isinstance(snapshot, dict) else build_common_market_snapshot()
    selected = []
    rejected = []
    for item in snapshot.get("symbols") or []:
        symbol = item.get("symbol")
        reasons = []
        if item.get("ltp") is None:
            reasons.append("missing_ltp")
        if item.get("ohlc_status") != "FRESH":
            reasons.append("ohlc_not_fresh")
        if (item.get("ohlc_rows") or 0) < 100:
            reasons.append("insufficient_ohlc_history")
        if item.get("volume") is None or int(item.get("volume") or 0) < 100_000:
            reasons.append("low_or_missing_volume")
        if item.get("volatility_pct") is None:
            reasons.append("missing_volatility")
        if reasons:
            rejected.append({"symbol": symbol, "reasons": reasons, "ltp": item.get("ltp"), "rows": item.get("ohlc_rows")})
            continue
        liquidity_score = min((int(item.get("volume") or 0) / 5_000_000) * 100.0, 100.0)
        ohlc_score = min((int(item.get("ohlc_rows") or 0) / 1000) * 100.0, 100.0)
        movement_score = min(abs(float(item.get("movement_pct") or 0.0)) * 10.0, 100.0)
        volatility_score = min(float(item.get("volatility_pct") or 0.0) * 30.0, 100.0)
        score = round(ohlc_score * 0.35 + liquidity_score * 0.25 + movement_score * 0.20 + volatility_score * 0.20, 3)
        selected.append({**item, "selector_score": score, "reason": "fresh_ohlc_liquid_structural_candidate"})
    selected.sort(key=lambda item: item.get("selector_score") or 0, reverse=True)
    prelimit_count = len(selected)
    selected = selected[:CLASSIC_TARGET_COUNT]
    payload = {
        "status": "ACTIVE" if selected else "MISSING",
        "timestamp_ist": now_ist().isoformat(),
        "source": "data/common_market_snapshot.json",
        "count": len(selected),
        "quality_filtered_count": prelimit_count,
        "target_count": CLASSIC_TARGET_COUNT,
        "symbols": selected,
        "rejected": rejected[:200],
        "rejected_count": len(rejected),
        "trade_placement_allowed": False,
    }
    atomic_write_json(path, payload)
    return payload


def refresh_all_universes() -> dict[str, Any]:
    master = build_universe_master()
    snapshot = build_common_market_snapshot(master)
    hft = select_hft_universe(snapshot)
    classic = select_classic_universe(snapshot)
    return {
        "timestamp_ist": now_ist().isoformat(),
        "common_universe_count": master.get("count"),
        "common_snapshot_count": snapshot.get("count"),
        "common_snapshot_enriched_count": snapshot.get("enriched_count"),
        "hft_universe_count": hft.get("count"),
        "classic_universe_count": classic.get("count"),
        "paths": {
            "universe_master": str(UNIVERSE_MASTER_PATH.relative_to(ROOT)),
            "common_market_snapshot": str(COMMON_SNAPSHOT_PATH.relative_to(ROOT)),
            "hft_universe": str(HFT_UNIVERSE_PATH.relative_to(ROOT)),
            "classic_universe": str(CLASSIC_UNIVERSE_PATH.relative_to(ROOT)),
        },
    }
