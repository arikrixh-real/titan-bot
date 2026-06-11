from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from titan_alpha_math import alpha_config
from titan_alpha_math.lane_classifier import classify_input
from runtime_market_state import LTP_FRESH_SECONDS, OHLC_FRESH_SECONDS, read_json, safe_float, safe_int
from runtime_mode_switch import signal_allowed as mode_signal_allowed, switch_in_progress
from runtime_signal_manager import approve_signals


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "data" / "runtime"
CLASSIC_RUNTIME_GUARD_PATH = RUNTIME_DIR / "classic_engine_guard.json"
CLASSIC_UNIVERSE_PATH = ROOT / "data" / "classic_mode" / "classic_universe_cache.json"
SHARED_MARKET_STATE_PATH = RUNTIME_DIR / "shared_market_state.json"

IST = timezone(timedelta(hours=5, minutes=30))
CLASSIC_ENGINE = os.getenv("CLASSIC_ENGINE", "TOIF").strip().upper() or "TOIF"
LEGACY_CLASSIC_FILTERS = os.getenv("LEGACY_CLASSIC_FILTERS", "false").strip().lower() in {"1", "true", "yes", "on"}
TOIF_MIN_PROBABILITY = 0.56
REQUIRED_TOIF_INPUTS = {
    "ltp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "avg_volume",
    "atr",
    "vwap",
    "stock_return",
    "sector_return",
    "index_return",
    "relative_volatility",
    "spread",
    "bid_depth",
    "ask_depth",
    "hold",
    "retest",
    "rejection",
    "similar_wins",
    "similar_losses",
}


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


def classic_config_snapshot() -> dict[str, Any]:
    return {
        "classic_engine": CLASSIC_ENGINE,
        "legacy_classic_filters": LEGACY_CLASSIC_FILTERS,
        "toif_formula_version": alpha_config.FORMULA_VERSION,
        "classic_engine_source": "env:CLASSIC_ENGINE default TOIF",
        "legacy_filters_source": "env:LEGACY_CLASSIC_FILTERS default false",
    }


def write_classic_engine_guard(*, active_mode: str, toif_active: bool, legacy_active: bool, hft_active: bool, reason: str = "") -> dict[str, Any]:
    payload = {
        "timestamp_ist": now_ist().isoformat(),
        "active_mode": active_mode,
        "classic_engine": CLASSIC_ENGINE,
        "legacy_classic_filters": LEGACY_CLASSIC_FILTERS,
        "toif_runner_active": bool(toif_active),
        "legacy_classic_runner_active": bool(legacy_active),
        "hft_runner_active": bool(hft_active),
        "no_duplicate_classic_runners": not (toif_active and legacy_active),
        "toif_direct_upstox_calls": False,
        "toif_input_source": "runtime_market_state.shared_market_state + data/classic_mode/classic_universe_cache.json",
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
        "reason": reason,
        **classic_config_snapshot(),
    }
    atomic_write_json(CLASSIC_RUNTIME_GUARD_PATH, payload)
    return payload


def _universe_symbols() -> list[dict[str, Any]]:
    payload = read_json(CLASSIC_UNIVERSE_PATH, {})
    if not isinstance(payload, dict):
        return []
    return [item for item in payload.get("symbols") or [] if isinstance(item, dict)]


def _state_for_symbol(symbols: dict[str, dict[str, Any]], item: dict[str, Any]) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "").upper().replace(".NS", "")
    state = symbols.get(symbol)
    return state if isinstance(state, dict) else {}


def _fresh_ltp(state: dict[str, Any]) -> tuple[bool, str | None]:
    ltp = safe_float(state.get("ltp"))
    age = safe_float(state.get("ltp_age_seconds"))
    if ltp is None:
        return False, "missing_ltp"
    if age is None:
        return False, "missing_ltp_timestamp"
    if age > LTP_FRESH_SECONDS:
        return False, "stale_ltp"
    return True, None


def _fresh_ohlc(state: dict[str, Any]) -> tuple[bool, str | None]:
    ohlc = state.get("ohlc_snapshot") if isinstance(state.get("ohlc_snapshot"), dict) else {}
    age = safe_float(state.get("ohlc_age_seconds"))
    if str(ohlc.get("status") or "").upper() not in {"FRESH", "LIVE", "ACTIVE"}:
        return False, "ohlc_not_fresh"
    if age is None:
        return False, "missing_ohlc_timestamp"
    if age > OHLC_FRESH_SECONDS:
        return False, "stale_ohlc"
    rows = safe_int(ohlc.get("rows"))
    if rows is None or rows <= 0:
        return False, "missing_ohlc_rows"
    for field in ("open", "high", "low", "close", "volume"):
        if safe_float(ohlc.get(field)) is None:
            return False, "missing_ohlc_price_fields"
    return True, None


def _toif_record(symbol: str, state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    ohlc = state.get("ohlc_snapshot") if isinstance(state.get("ohlc_snapshot"), dict) else {}
    ltp = safe_float(state.get("ltp"))
    volume = safe_float(ohlc.get("volume"))
    volatility_pct = safe_float(ohlc.get("volatility_pct"))
    movement_pct = safe_float(ohlc.get("movement_pct"))
    open_price = safe_float(ohlc.get("open"))
    high = safe_float(ohlc.get("high"))
    low = safe_float(ohlc.get("low"))
    close = safe_float(ohlc.get("close"))
    atr = (high - low) if high is not None and low is not None else None
    avg_volume = safe_float(item.get("avg_volume_20"))
    vwap = safe_float(ohlc.get("vwap"))
    spread = safe_float(state.get("spread"))
    stock_return = movement_pct / 100.0 if movement_pct is not None else None
    relative_volatility = volatility_pct / 100.0 if volatility_pct is not None else None
    missing = []
    field_sources = {
        "ltp": "real_shared_market_state" if ltp is not None else "missing",
        "open": "real_shared_ohlc_state" if open_price is not None else "missing",
        "high": "real_shared_ohlc_state" if high is not None else "missing",
        "low": "real_shared_ohlc_state" if low is not None else "missing",
        "close": "real_shared_ohlc_state" if close is not None else "missing",
        "volume": "real_shared_ohlc_state" if volume is not None else "missing",
        "avg_volume": "real_shared_ohlc_state" if avg_volume is not None else "missing",
        "atr": "derived_from_shared_ohlc_high_low" if atr is not None else "missing",
        "vwap": "real_shared_ohlc_state" if vwap is not None else "missing",
        "stock_return": "derived_from_real_shared_ohlc_movement" if stock_return is not None else "missing",
        "relative_volatility": "derived_from_real_shared_ohlc_volatility" if relative_volatility is not None else "missing",
        "spread": "real_shared_market_state" if spread is not None else "missing",
        "bid_depth": "missing",
        "ask_depth": "missing",
        "sector_return": "missing",
        "index_return": "missing",
        "hold": "missing",
        "retest": "missing",
        "rejection": "missing",
        "similar_wins": "missing",
        "similar_losses": "missing",
    }
    for field, source in field_sources.items():
        if source == "missing":
            missing.append(field)
    return {
        "symbol": symbol,
        "ltp": ltp,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "avg_volume": avg_volume,
        "atr": atr,
        "vwap": vwap,
        "stock_return": stock_return,
        "sector_return": None,
        "index_return": None,
        "relative_volatility": relative_volatility,
        "spread": spread,
        "bid_depth": None,
        "ask_depth": None,
        "hold": None,
        "retest": None,
        "rejection": None,
        "similar_wins": None,
        "similar_losses": None,
        "timestamps": state.get("latest_tick_timestamp"),
        "missing_inputs": sorted(set(missing)),
        "field_sources": field_sources,
    }


def _missing_required_toif_inputs(record: dict[str, Any]) -> list[str]:
    missing = set(record.get("missing_inputs") or [])
    missing.update(field for field in REQUIRED_TOIF_INPUTS if record.get(field) is None)
    return sorted(missing & REQUIRED_TOIF_INPUTS)


def run_toif_classic_engine(market_state: dict[str, Any] | None = None) -> dict[str, Any]:
    timestamp = now_ist().isoformat()
    if market_state is None:
        market_state = read_json(SHARED_MARKET_STATE_PATH, {})
    if not isinstance(market_state, dict):
        market_state = {}
    symbols = market_state.get("symbols") if isinstance(market_state.get("symbols"), dict) else {}
    universe = _universe_symbols()
    live_feed_count = 0
    ohlc_valid_count = 0
    alpha_checked_count = 0
    alpha_passed = 0
    high_alpha_count = 0
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    blockers: list[str] = []
    errors: list[str] = []

    for item in universe:
        symbol = str(item.get("symbol") or "").upper().replace(".NS", "")
        state = _state_for_symbol(symbols, item)
        ltp_ok, ltp_reason = _fresh_ltp(state)
        if not ltp_ok:
            rejected.append({"symbol": symbol, "reason": ltp_reason, "alpha": None, "reject_reason": ltp_reason})
            continue
        live_feed_count += 1
        ohlc_ok, ohlc_reason = _fresh_ohlc(state)
        if not ohlc_ok:
            rejected.append({"symbol": symbol, "reason": ohlc_reason, "alpha": None, "reject_reason": ohlc_reason})
            continue
        ohlc_valid_count += 1
        try:
            record = _toif_record(symbol, state, item)
            missing_required = _missing_required_toif_inputs(record)
            if missing_required:
                rejected.append(
                    {
                        "symbol": symbol,
                        "reason": "INSUFFICIENT_TOIF_INPUTS",
                        "alpha": None,
                        "reject_reason": "MISSING_TOIF_INPUT",
                        "missing_inputs": missing_required,
                    }
                )
                continue
            alpha_checked_count += 1
            lane, score = classify_input(record, "LONG")
        except Exception as exc:
            reason = f"toif_error:{type(exc).__name__}"
            errors.append(f"{symbol}:{type(exc).__name__}:{exc}")
            rejected.append({"symbol": symbol, "reason": reason, "alpha": None, "reject_reason": reason})
            continue
        alpha = safe_float(score.get("trade_power"))
        probability = safe_float(score.get("probability"))
        if alpha is None or probability is None:
            rejected.append({"symbol": symbol, "reason": "toif_alpha_null", "alpha": None, "reject_reason": "toif_alpha_null"})
            continue
        if lane != "NO_TRADE" and probability >= TOIF_MIN_PROBABILITY:
            alpha_passed += 1
        if lane in {"ELITE", "STRONG"}:
            high_alpha_count += 1
        if lane == "NO_TRADE" or probability < TOIF_MIN_PROBABILITY:
            rejected.append(
                {
                    "symbol": symbol,
                    "reason": "toif_rejected",
                    "reject_reason": "toif_rejected",
                    "alpha": alpha,
                    "probability": probability,
                    "lane": lane,
                    "missing_inputs": score.get("missing_inputs") or [],
                }
            )
            continue
        ltp = safe_float(state.get("ltp"))
        if ltp is None:
            rejected.append({"symbol": symbol, "reason": "missing_ltp", "alpha": None, "reject_reason": "missing_ltp"})
            continue
        candidates.append(
            {
                "symbol": symbol,
                "mode": "CLASSIC",
                "engine": "TOIF",
                "formula_version": alpha_config.FORMULA_VERSION,
                "side": "LONG",
                "entry": ltp,
                "sl": round(ltp * 0.98, 4),
                "target": round(ltp * 1.04, 4),
                "signal_type": "CLASSIC_TOIF_REAL_OHLC",
                "strategy": "classic_toif_shared_market_state",
                "source": "runtime_classic_engine",
                "alpha": alpha,
                "probability": probability,
                "trade_power": score.get("trade_power"),
                "lane": lane,
                "missing_inputs": score.get("missing_inputs") or [],
                "signal_allowed": True,
                "paper_only": True,
                "broker_orders": False,
                "live_order_placement": False,
            }
        )

    if CLASSIC_ENGINE != "TOIF":
        blockers.append(f"classic_engine_not_toif:{CLASSIC_ENGINE}")
    if LEGACY_CLASSIC_FILTERS:
        blockers.append("legacy_classic_filters_enabled")
    if not universe:
        blockers.append("classic_universe_missing")
    if live_feed_count < len(universe):
        blockers.append("classic_feed_incomplete")
    if ohlc_valid_count < live_feed_count:
        blockers.append("classic_ohlc_incomplete")
    if errors:
        blockers.append("toif_runtime_errors")

    feed_status = "LIVE" if universe and live_feed_count == len(universe) and ohlc_valid_count == len(universe) else "DEGRADED" if live_feed_count else "STALE"
    if ohlc_valid_count and alpha_checked_count == 0:
        blockers.append("INSUFFICIENT_TOIF_INPUTS")
    signal_ok = bool(candidates) and not blockers and mode_signal_allowed() and not switch_in_progress()
    approved = approve_signals(candidates, mode="CLASSIC", signal_allowed=signal_ok, blockers=blockers)
    approved_count = int(approved.get("approved_count") or 0)
    payload = {
        "mode": "CLASSIC",
        "engine": "TOIF",
        "classic_engine": CLASSIC_ENGINE,
        "legacy_classic_filters": LEGACY_CLASSIC_FILTERS,
        "formula_version": alpha_config.FORMULA_VERSION,
        "status": "ACTIVE" if universe and not blockers else "DEGRADED" if universe else "MISSING",
        "feed_status": feed_status,
        "timestamp": timestamp,
        "timestamp_ist": timestamp,
        "universe_count": len(universe),
        "live_feed_count": live_feed_count,
        "eligible_count": live_feed_count,
        "ohlc_valid_count": ohlc_valid_count,
        "alpha_checked_count": alpha_checked_count,
        "alpha_passed": alpha_passed,
        "high_alpha_count": high_alpha_count,
        "shortlist_count": len(candidates),
        "final_candidate_count": approved_count,
        "stocks_checked": len(universe),
        "trend_passed": alpha_passed,
        "momentum_passed": alpha_passed,
        "structure_passed": ohlc_valid_count,
        "raw_breakout_ready_count": len(candidates),
        "qualified_breakout_ready_count": approved_count,
        "final_passed": approved_count,
        "paper_trade_candidates": approved.get("approved_signals") or [],
        "signal_allowed": signal_ok,
        "trade_placement_allowed": False,
        "blockers": blockers,
        "rejected": rejected[:200],
        "errors": errors[:50],
        "source_owner": "runtime_classic_engine",
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
    }
    write_classic_engine_guard(
        active_mode="CLASSIC",
        toif_active=True,
        legacy_active=LEGACY_CLASSIC_FILTERS,
        hft_active=False,
        reason="classic_mode_routes_to_toif",
    )
    return payload
