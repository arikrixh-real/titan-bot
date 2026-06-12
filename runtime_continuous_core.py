from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from runtime_execution_mode import active_execution_mode
from runtime_market_state import (
    LTP_FRESH_SECONDS,
    MICROSTRUCTURE_FRESH_SECONDS,
    OHLC_FRESH_SECONDS,
    build_shared_market_state,
    read_json,
    safe_float,
    safe_int,
)
from runtime_mode_switch import read_mode_switch_status, signal_allowed as mode_signal_allowed, switch_in_progress
from runtime_signal_manager import approve_signals
from runtime_classic_engine import run_toif_classic_engine, write_classic_engine_guard


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "data" / "runtime"
ACTIVE_RUNTIME_SNAPSHOT_PATH = RUNTIME_DIR / "active_runtime_snapshot.json"
ACTIVE_SCANNER_SNAPSHOT_PATH = RUNTIME_DIR / "active_scanner_snapshot.json"
FEED_HEALTH_SNAPSHOT_PATH = RUNTIME_DIR / "feed_health_snapshot.json"
HFT_SCANNER_STATUS_PATH = ROOT / "data" / "hft_mode" / "hft_scanner_status.json"
HFT_MODE_SCANNER_STATUS_PATH = RUNTIME_DIR / "hft_mode_scanner_status.json"
CLASSIC_SCANNER_STATUS_PATH = RUNTIME_DIR / "classic_scanner_status.json"
CLASSIC_MODE_SCANNER_STATUS_PATH = RUNTIME_DIR / "classic_mode_scanner_status.json"
HFT_UNIVERSE_PATH = ROOT / "data" / "hft_mode" / "hft_universe_cache.json"
CLASSIC_UNIVERSE_PATH = ROOT / "data" / "classic_mode" / "classic_universe_cache.json"
PAPER_ENGINE_STATUS_PATH = RUNTIME_DIR / "paper_engine_status.json"
PAPER_REGISTRY_PATH = RUNTIME_DIR / "paper_trade_registry.json"
OUTCOME_TRACKER_STATUS_PATH = RUNTIME_DIR / "outcome_tracker_status.json"

IST = timezone(timedelta(hours=5, minutes=30))


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


def normalize_mode(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"HFT", "HFT_MODE"}:
        return "HFT"
    if text in {"CLASSICAL_TOIF", "TOIF", "CLASSIC"}:
        return "CLASSIC"
    if text in {"OFF", "NONE", "DISABLED"}:
        return "OFF"
    return "CLASSIC"


def _symbols_from_market_state(market_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    symbols = market_state.get("symbols") if isinstance(market_state, dict) else {}
    return symbols if isinstance(symbols, dict) else {}


def _universe_symbols(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path, {})
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


def _fresh_microstructure(state: dict[str, Any]) -> tuple[bool, str | None]:
    ok_ltp, reason = _fresh_ltp(state)
    if not ok_ltp:
        return False, reason
    bid = safe_float(state.get("bid"))
    ask = safe_float(state.get("ask"))
    spread = safe_float(state.get("spread"))
    age = safe_float(state.get("microstructure_age_seconds"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        return False, "missing_bid_ask"
    if spread is None:
        return False, "missing_spread"
    if age is None:
        return False, "missing_microstructure_timestamp"
    if age > MICROSTRUCTURE_FRESH_SECONDS:
        return False, "stale_microstructure"
    return True, None


def _fresh_ohlc(state: dict[str, Any]) -> tuple[bool, str | None]:
    ok_ltp, reason = _fresh_ltp(state)
    if not ok_ltp:
        return False, reason
    ohlc = state.get("ohlc_snapshot") if isinstance(state.get("ohlc_snapshot"), dict) else {}
    age = safe_float(state.get("ohlc_age_seconds"))
    if str(ohlc.get("status") or "").upper() not in {"FRESH", "LIVE", "ACTIVE"}:
        return False, "ohlc_not_fresh"
    if age is None:
        return False, "missing_ohlc_timestamp"
    if age > OHLC_FRESH_SECONDS:
        return False, "stale_ohlc"
    if safe_int(ohlc.get("rows")) is None or int(ohlc.get("rows") or 0) <= 0:
        return False, "missing_ohlc_rows"
    return True, None


def _count_open_trades(mode: str) -> int:
    registry = read_json(PAPER_REGISTRY_PATH, {})
    if not isinstance(registry, dict):
        return 0
    count = 0
    for item in registry.get("open_positions") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "OPEN").upper() == "OPEN" and normalize_mode(item.get("mode")) == mode:
            count += 1
    return count


def _inactive_payload(mode: str, reason: str) -> dict[str, Any]:
    timestamp = now_ist().isoformat()
    return {
        "mode": normalize_mode(mode),
        "status": "INACTIVE",
        "timestamp": timestamp,
        "timestamp_ist": timestamp,
        "inactive_reason": reason,
        "signal_allowed": False,
        "trade_placement_allowed": False,
        "paper_trade_candidates": [],
        "source_owner": "runtime_continuous_core",
    }


def _reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _evaluate_hft(market_state: dict[str, Any], switch_status: dict[str, Any]) -> dict[str, Any]:
    symbols = _symbols_from_market_state(market_state)
    universe = _universe_symbols(HFT_UNIVERSE_PATH)
    live_feed_count = 0
    liquid_active_count = 0
    activity_passed = 0
    momentum_passed = 0
    volatility_passed = 0
    spread_passed = 0
    stale_ltp_count = 0
    missing_ltp_count = 0
    missing_bid_ask_count = 0
    shortlist: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    rejected = []
    blockers: list[str] = []
    health_warnings: list[str] = []
    for item in universe:
        state = _state_for_symbol(symbols, item)
        symbol = str(item.get("symbol") or "").upper()
        bid = safe_float(state.get("bid"))
        ask = safe_float(state.get("ask"))
        ltp_value = safe_float(state.get("ltp"))
        if ltp_value is not None and (bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask):
            missing_bid_ask_count += 1
        ltp_ok, ltp_reason = _fresh_ltp(state)
        if ltp_ok:
            live_feed_count += 1
        else:
            if ltp_reason == "stale_ltp":
                stale_ltp_count += 1
            elif ltp_reason in {"missing_ltp", "missing_ltp_timestamp"}:
                missing_ltp_count += 1
            rejected.append({"symbol": symbol, "reason": ltp_reason})
            continue
        volume = safe_int(state.get("volume") or item.get("volume"))
        if volume is None or volume < 250_000:
            rejected.append({"symbol": symbol, "reason": "low_or_missing_volume"})
            continue
        liquid_active_count += 1
        activity_passed += 1
        change = safe_float(item.get("change_percent"))
        movement = safe_float((state.get("ohlc_snapshot") or {}).get("movement_pct"))
        volatility = safe_float((state.get("ohlc_snapshot") or {}).get("volatility_pct"))
        if change is not None and abs(change) > 0:
            momentum_passed += 1
        if volatility is not None and volatility > 0:
            volatility_passed += 1
        if (change is None or abs(change) <= 0) and (movement is None or abs(movement) <= 0) and (volatility is None or volatility <= 0):
            rejected.append({"symbol": symbol, "reason": "no_real_movement_evidence"})
            continue
        ltp = safe_float(state.get("ltp"))
        if ltp is None:
            rejected.append({"symbol": symbol, "reason": "missing_ltp"})
            continue
        shortlist.append(
            {
                "symbol": symbol,
                "mode": "HFT",
                "ltp": ltp,
                "volume": volume,
                "change_percent": change,
                "movement_pct": movement,
                "volatility_pct": volatility,
                "source": "runtime_continuous_core",
                "shortlist_basis": "real_ltp_volume_movement",
                "paper_only": True,
                "broker_orders": False,
                "live_order_placement": False,
            }
        )
        micro_ok, micro_reason = _fresh_microstructure(state)
        if not micro_ok:
            if (
                micro_reason in {"missing_bid_ask", "missing_spread", "missing_microstructure_timestamp"}
                and not (ltp_value is not None and (bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask))
            ):
                missing_bid_ask_count += 1
            rejected.append({"symbol": symbol, "reason": micro_reason, "stage": "final_candidate"})
            continue
        spread_pct = safe_float(state.get("spread_pct"))
        if spread_pct is None or spread_pct > 0.75:
            rejected.append({"symbol": symbol, "reason": "bad_or_missing_spread", "stage": "final_candidate"})
            continue
        spread_passed += 1
        candidates.append(
            {
                "symbol": symbol,
                "mode": "HFT",
                "side": "LONG",
                "entry": ltp,
                "sl": round(ltp * 0.995, 4),
                "target": round(ltp * 1.01, 4),
                "signal_type": "HFT_REAL_MICROSTRUCTURE",
                "strategy": "hft_shared_market_state",
                "source": "runtime_continuous_core",
                "latest_tick_timestamp": state.get("latest_tick_timestamp"),
                "ltp": ltp,
                "volume": volume,
                "bid": state.get("bid"),
                "ask": state.get("ask"),
                "spread": state.get("spread"),
                "spread_pct": state.get("spread_pct"),
                "paper_only": True,
                "broker_orders": False,
                "live_order_placement": False,
            }
        )

    if not universe:
        blockers.append("hft_universe_missing")
    if market_state.get("token_type_used") != "ANALYTICS_TOKEN":
        blockers.append("market_data_source_not_upstox_analytics_token")
    active_feed_status = "LIVE"
    if not universe or live_feed_count == 0:
        active_feed_status = "STALE"
    elif live_feed_count < len(universe) or missing_bid_ask_count > 0 or spread_passed < live_feed_count:
        active_feed_status = "DEGRADED"
    if active_feed_status == "STALE":
        blockers.append("feed_status_STALE")
    elif active_feed_status == "DEGRADED":
        health_warnings.append("feed_status_DEGRADED")
    if spread_passed == 0:
        blockers.append("missing_real_hft_microstructure")
    if switch_in_progress():
        blockers.append(f"mode_switch_{switch_status.get('state') or 'LOCKED'}")
    elif not mode_signal_allowed():
        blockers.append("mode_signal_not_allowed")
    signal_ok = bool(candidates) and not blockers
    approved = approve_signals(candidates, mode="HFT", signal_allowed=signal_ok, blockers=blockers)
    approved_count = int(approved.get("approved_count") or 0)
    approval_rejected = approved.get("rejected") if isinstance(approved.get("rejected"), list) else []
    timestamp = now_ist().isoformat()
    payload = {
        "mode": "HFT",
        "status": "ACTIVE" if universe else "MISSING",
        "feed_status": active_feed_status,
        "timestamp": timestamp,
        "timestamp_ist": timestamp,
        "universe_count": len(universe),
        "live_feed_count": live_feed_count,
        "quote_requested_count": (market_state.get("market_refresh") or {}).get("hft_quote_requested_count"),
        "quote_success_count": (market_state.get("market_refresh") or {}).get("hft_quote_success_count"),
        "quote_failed_count": (market_state.get("market_refresh") or {}).get("hft_quote_failed_count"),
        "stale_ltp_count": stale_ltp_count,
        "missing_ltp_count": missing_ltp_count,
        "missing_bid_ask_count": missing_bid_ask_count,
        "liquid_active_count": liquid_active_count,
        "activity_passed": activity_passed,
        "momentum_passed": momentum_passed,
        "volatility_passed": volatility_passed,
        "spread_passed": spread_passed,
        "shortlist_count": len(shortlist),
        "hft_shortlist": shortlist[:200],
        "microstructure_candidate_count": len(candidates),
        "final_candidate_count": approved_count,
        "eligible_signals": approved_count,
        "final_passed": approved_count,
        "stocks_scanned": len(universe),
        "paper_trade_candidates": approved.get("approved_signals") or [],
        "signal_allowed": bool(approved_count) and signal_ok,
        "approval_status": approved.get("status") or ("ACTIVE" if signal_ok else "BLOCKED"),
        "approval_blockers": blockers,
        "approval_rejected_count": int(approved.get("rejected_count") or 0),
        "approval_reject_reason_counts": approved.get("reject_reason_counts") or _reason_counts(approval_rejected),
        "preapproval_reject_reason_counts": _reason_counts(rejected),
        "trade_placement_allowed": False,
        "blockers": blockers,
        "health_warnings": health_warnings,
        "rejected": rejected[:200],
        "source_owner": "runtime_continuous_core",
        "switch_status": switch_status,
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
    }
    atomic_write_json(HFT_SCANNER_STATUS_PATH, payload)
    atomic_write_json(HFT_MODE_SCANNER_STATUS_PATH, payload)
    return payload


def _evaluate_classic(market_state: dict[str, Any], switch_status: dict[str, Any]) -> dict[str, Any]:
    symbols = _symbols_from_market_state(market_state)
    universe = _universe_symbols(CLASSIC_UNIVERSE_PATH)
    live_feed_count = 0
    eligible_count = 0
    ohlc_valid_count = 0
    alpha_checked_count = 0
    alpha_passed = 0
    high_alpha_count = 0
    candidates: list[dict[str, Any]] = []
    rejected = []
    blockers: list[str] = []
    for item in universe:
        state = _state_for_symbol(symbols, item)
        symbol = str(item.get("symbol") or "").upper()
        ltp_ok, ltp_reason = _fresh_ltp(state)
        if ltp_ok:
            live_feed_count += 1
        else:
            rejected.append({"symbol": symbol, "reason": ltp_reason})
            continue
        volume = safe_int(state.get("volume") or item.get("volume"))
        if volume is None or volume <= 0:
            rejected.append({"symbol": symbol, "reason": "missing_volume"})
            continue
        eligible_count += 1
        ohlc_ok, ohlc_reason = _fresh_ohlc(state)
        if not ohlc_ok:
            rejected.append({"symbol": symbol, "reason": ohlc_reason})
            continue
        ohlc_valid_count += 1
        alpha_checked_count += 1
        score = safe_float(item.get("selector_score"))
        if score is None:
            rejected.append({"symbol": symbol, "reason": "missing_real_alpha_score"})
            continue
        if score >= 50:
            alpha_passed += 1
        if score >= 75:
            high_alpha_count += 1
        if score < 50:
            rejected.append({"symbol": symbol, "reason": "alpha_below_threshold"})
            continue
        ltp = safe_float(state.get("ltp"))
        candidates.append(
            {
                "symbol": symbol,
                "mode": "CLASSIC",
                "side": "LONG",
                "entry": ltp,
                "sl": round(float(ltp) * 0.98, 4) if ltp else None,
                "target": round(float(ltp) * 1.04, 4) if ltp else None,
                "signal_type": "CLASSICAL_TOIF_REAL_OHLC",
                "strategy": "classic_shared_market_state",
                "source": "runtime_continuous_core",
                "candle_time": (state.get("ohlc_snapshot") or {}).get("latest_timestamp"),
                "paper_only": True,
                "broker_orders": False,
                "live_order_placement": False,
            }
        )

    if not universe:
        blockers.append("classic_universe_missing")
    active_feed_status = "LIVE" if universe and live_feed_count == len(universe) else "DEGRADED" if live_feed_count else "STALE"
    if active_feed_status in {"STALE", "DEGRADED"}:
        blockers.append(f"feed_status_{active_feed_status}")
    if ohlc_valid_count == 0:
        blockers.append("missing_fresh_ohlc")
    signal_ok = bool(candidates) and not blockers and mode_signal_allowed() and not switch_in_progress()
    approved = approve_signals(candidates, mode="CLASSIC", signal_allowed=signal_ok, blockers=blockers)
    timestamp = now_ist().isoformat()
    payload = {
        "mode": "CLASSIC",
        "status": "ACTIVE" if universe else "MISSING",
        "feed_status": active_feed_status,
        "timestamp": timestamp,
        "timestamp_ist": timestamp,
        "universe_count": len(universe),
        "live_feed_count": live_feed_count,
        "eligible_count": eligible_count,
        "ohlc_valid_count": ohlc_valid_count,
        "alpha_checked_count": alpha_checked_count,
        "alpha_passed": alpha_passed,
        "high_alpha_count": high_alpha_count,
        "shortlist_count": len(candidates),
        "final_candidate_count": int(approved.get("approved_count") or 0),
        "stocks_checked": len(universe),
        "trend_passed": alpha_passed,
        "momentum_passed": alpha_passed,
        "structure_passed": ohlc_valid_count,
        "raw_breakout_ready_count": len(candidates),
        "qualified_breakout_ready_count": int(approved.get("approved_count") or 0),
        "final_passed": int(approved.get("approved_count") or 0),
        "paper_trade_candidates": approved.get("approved_signals") or [],
        "signal_allowed": signal_ok,
        "trade_placement_allowed": False,
        "blockers": blockers,
        "rejected": rejected[:200],
        "source_owner": "runtime_continuous_core",
        "switch_status": switch_status,
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
    }
    atomic_write_json(CLASSIC_SCANNER_STATUS_PATH, payload)
    atomic_write_json(CLASSIC_MODE_SCANNER_STATUS_PATH, payload)
    return payload


def _active_snapshot(mode: str, scanner_payload: dict[str, Any], market_state: dict[str, Any], switch_status: dict[str, Any]) -> dict[str, Any]:
    paper = read_json(PAPER_ENGINE_STATUS_PATH, {})
    outcome = read_json(OUTCOME_TRACKER_STATUS_PATH, {})
    timestamp = now_ist().isoformat()
    filter_counts = {
        key: scanner_payload.get(key)
        for key in (
            "activity_passed",
            "momentum_passed",
            "volatility_passed",
            "spread_passed",
            "eligible_count",
            "ohlc_valid_count",
            "alpha_checked_count",
            "alpha_passed",
            "high_alpha_count",
        )
        if key in scanner_payload
    }
    blockers = list(scanner_payload.get("blockers") or [])
    if market_state.get("blockers"):
        blockers.extend(str(item) for item in market_state.get("blockers") or [])
    signal_ok = bool(scanner_payload.get("signal_allowed")) and mode_signal_allowed() and not switch_in_progress()
    payload = {
        "active_mode": mode,
        "scanner_loop_status": scanner_payload.get("status") or "UNKNOWN",
        "feed_status": scanner_payload.get("feed_status") or market_state.get("feed_status") or "UNKNOWN",
        "signal_allowed": signal_ok,
        "trade_placement_allowed": False,
        "stale_blockers": blockers,
        "universe_count": scanner_payload.get("universe_count"),
        "live_feed_count": scanner_payload.get("live_feed_count"),
        "quote_requested_count": scanner_payload.get("quote_requested_count"),
        "quote_success_count": scanner_payload.get("quote_success_count"),
        "quote_failed_count": scanner_payload.get("quote_failed_count"),
        "stale_ltp_count": scanner_payload.get("stale_ltp_count"),
        "missing_ltp_count": scanner_payload.get("missing_ltp_count"),
        "missing_bid_ask_count": scanner_payload.get("missing_bid_ask_count"),
        "spread_passed": scanner_payload.get("spread_passed"),
        "momentum_passed": scanner_payload.get("momentum_passed"),
        "volatility_passed": scanner_payload.get("volatility_passed"),
        "filter_pass_counts": filter_counts,
        "shortlist_count": scanner_payload.get("shortlist_count"),
        "final_candidate_count": scanner_payload.get("final_candidate_count"),
        "open_trade_count": _count_open_trades(mode),
        "outcome_tracker_status": outcome.get("status") or outcome.get("result") or "UNKNOWN",
        "ltp_age_seconds": market_state.get("ltp_age_seconds"),
        "ohlc_age_seconds": market_state.get("ohlc_age_seconds"),
        "microstructure_age_seconds": market_state.get("microstructure_age_seconds"),
        "token_type_used": market_state.get("token_type_used"),
        "last_valid_update": timestamp if (scanner_payload.get("feed_status") or market_state.get("feed_status")) == "LIVE" else None,
        "source_owner": "runtime_continuous_core",
        "switch_status": switch_status,
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
        "paper_status": paper.get("status") or "UNKNOWN",
        "timestamp_ist": timestamp,
    }
    return payload


def run_continuous_runtime_core(*, refresh_market: bool = True, refresh_universe: bool = False) -> dict[str, Any]:
    mode = normalize_mode(active_execution_mode())
    switch_status = read_mode_switch_status()
    market_state = build_shared_market_state(refresh_market=refresh_market, refresh_universe=refresh_universe)
    if switch_in_progress() or not mode_signal_allowed():
        scanner_payload = _inactive_payload(mode, f"mode_switch_{switch_status.get('state') or 'LOCKED'}")
    elif mode == "HFT":
        scanner_payload = _evaluate_hft(market_state, switch_status)
        classic_rest = _inactive_payload("CLASSIC", "hft_active_classic_scanner_resting")
        atomic_write_json(CLASSIC_SCANNER_STATUS_PATH, classic_rest)
        atomic_write_json(CLASSIC_MODE_SCANNER_STATUS_PATH, classic_rest)
        write_classic_engine_guard(active_mode="HFT", toif_active=False, legacy_active=False, hft_active=True, reason="hft_active_classic_resting")
    elif mode == "OFF":
        scanner_payload = _inactive_payload("OFF", "execution_mode_off")
        atomic_write_json(HFT_MODE_SCANNER_STATUS_PATH, _inactive_payload("HFT", "execution_mode_off"))
        atomic_write_json(CLASSIC_SCANNER_STATUS_PATH, _inactive_payload("CLASSIC", "execution_mode_off"))
        atomic_write_json(CLASSIC_MODE_SCANNER_STATUS_PATH, _inactive_payload("CLASSIC", "execution_mode_off"))
        write_classic_engine_guard(active_mode="OFF", toif_active=False, legacy_active=False, hft_active=False, reason="execution_mode_off")
    else:
        scanner_payload = run_toif_classic_engine(market_state)
        scanner_payload["switch_status"] = switch_status
        atomic_write_json(CLASSIC_SCANNER_STATUS_PATH, scanner_payload)
        atomic_write_json(CLASSIC_MODE_SCANNER_STATUS_PATH, scanner_payload)
        hft_rest = _inactive_payload("HFT", "classic_active_hft_scanner_resting")
        atomic_write_json(HFT_SCANNER_STATUS_PATH, hft_rest)
        atomic_write_json(HFT_MODE_SCANNER_STATUS_PATH, hft_rest)

    active_snapshot = _active_snapshot(mode, scanner_payload, market_state, switch_status)
    feed_snapshot = {
        "timestamp_ist": active_snapshot["timestamp_ist"],
        "status": active_snapshot.get("feed_status") or "UNKNOWN",
        "feed_status": active_snapshot.get("feed_status") or "UNKNOWN",
        "active_mode": mode,
        "universe_count": scanner_payload.get("universe_count"),
        "live_feed_count": scanner_payload.get("live_feed_count"),
        "quote_requested_count": scanner_payload.get("quote_requested_count"),
        "quote_success_count": scanner_payload.get("quote_success_count"),
        "quote_failed_count": scanner_payload.get("quote_failed_count"),
        "stale_ltp_count": scanner_payload.get("stale_ltp_count"),
        "missing_ltp_count": scanner_payload.get("missing_ltp_count"),
        "missing_bid_ask_count": scanner_payload.get("missing_bid_ask_count"),
        "spread_passed": scanner_payload.get("spread_passed"),
        "momentum_passed": scanner_payload.get("momentum_passed"),
        "volatility_passed": scanner_payload.get("volatility_passed"),
        "shortlist_count": scanner_payload.get("shortlist_count"),
        "final_candidate_count": scanner_payload.get("final_candidate_count"),
        "signal_allowed": active_snapshot.get("signal_allowed"),
        "trade_placement_allowed": False,
        "global_live_feed_count": market_state.get("live_feed_count"),
        "symbol_count": market_state.get("symbol_count"),
        "ltp_age_seconds": market_state.get("ltp_age_seconds"),
        "ohlc_age_seconds": market_state.get("ohlc_age_seconds"),
        "microstructure_age_seconds": market_state.get("microstructure_age_seconds"),
        "token_type_used": market_state.get("token_type_used"),
        "blockers": active_snapshot.get("stale_blockers") or market_state.get("blockers") or [],
        "recovery": {
            "market_refresh": market_state.get("market_refresh"),
            "universe_refresh": market_state.get("universe_refresh"),
        },
        "source_owner": "runtime_market_state",
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
    }
    atomic_write_json(ACTIVE_SCANNER_SNAPSHOT_PATH, scanner_payload)
    atomic_write_json(ACTIVE_RUNTIME_SNAPSHOT_PATH, active_snapshot)
    atomic_write_json(FEED_HEALTH_SNAPSHOT_PATH, feed_snapshot)
    return {
        "status": "UPDATED",
        "active_mode": mode,
        "scanner_status": scanner_payload.get("status"),
        "feed_status": market_state.get("feed_status"),
        "signal_allowed": active_snapshot.get("signal_allowed"),
        "final_candidate_count": active_snapshot.get("final_candidate_count"),
        "snapshot_path": str(ACTIVE_RUNTIME_SNAPSHOT_PATH.relative_to(ROOT)),
        "paper_only": True,
        "broker_orders": False,
        "live_order_placement": False,
    }


if __name__ == "__main__":
    print(json.dumps(run_continuous_runtime_core(), indent=2, sort_keys=True))
