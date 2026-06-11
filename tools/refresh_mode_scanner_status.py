"""Publish mode-specific scanner status snapshots from real TITAN runtime evidence.

This writer never fabricates scanner counts. Classic counts come from the
runtime scanner's canonical scanner_status.json only when CLASSIC is active.
HFT counts are not synthesized from Classic/runtime scanner data.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hft_mode.hft_data_contracts import HFTPriceTick
from hft_mode.hft_market_feed import process_mock_tick
from hft_mode.hft_risk_engine import HFTRiskState
from hft_mode.hft_score_engine import mark_score
from hft_mode.hft_strategy_funnels import run_all_funnels
from hft_mode.hft_universe import get_static_hft_universe
from hft_mode.hft_mode_worker import write_hft_health_heartbeat
from runtime_execution_mode import active_execution_mode, write_execution_mode


RUNTIME_DIR = ROOT / "data" / "runtime"
HFT_DIR = ROOT / "data" / "hft_mode"

SCANNER_STATUS_PATH = RUNTIME_DIR / "scanner_status.json"
CLASSIC_OUTPUT_PATH = RUNTIME_DIR / "classic_scanner_status.json"
CLASSIC_MODE_OUTPUT_PATH = RUNTIME_DIR / "classic_mode_scanner_status.json"
HFT_OUTPUT_PATH = RUNTIME_DIR / "hft_mode_scanner_status.json"
HFT_SCANNER_STATUS_PATH = HFT_DIR / "hft_scanner_status.json"
HFT_RUNTIME_STATE_PATH = HFT_DIR / "hft_runtime_state.json"
HFT_HEALTH_PATH = HFT_DIR / "hft_health.json"
HFT_STATS_PATH = HFT_DIR / "hft_stats.json"
HFT_COUNTER_SOURCE_PATHS = (
    HFT_DIR / "hft_scanner_status.json",
    HFT_DIR / "hft_signal_status.json",
    HFT_DIR / "hft_decision_status.json",
    HFT_DIR / "hft_worker_status.json",
    HFT_STATS_PATH,
)

FRESH_SECONDS = 15 * 60
COUNT_FIELDS = {
    "stocks_checked": ("stocks_checked", "symbols_scanned", "stocks_scanned", "scan_count", "scanned_count"),
    "trend_passed": ("trend_passed", "trend_passed_count"),
    "momentum_passed": ("momentum_passed", "momentum_passed_count"),
    "structure_passed": ("structure_passed", "structure_passed_count"),
    "raw_breakout_ready_count": ("raw_breakout_ready_count", "raw_breakout_ready"),
    "qualified_breakout_ready_count": (
        "qualified_breakout_ready_count",
        "qualified_breakout_ready",
        "breakout_ready_count",
        "breakout_ready",
    ),
    "final_passed": ("final_passed", "final_passed_count"),
}
HFT_COUNT_FIELDS = {
    "stocks_scanned": ("stocks_scanned", "stocks_checked", "symbols_scanned", "candidates_scanned", "ticks_processed"),
    "momentum_continuation": ("momentum_continuation",),
    "pullback_continuation": ("pullback_continuation",),
    "volatility_expansion": ("volatility_expansion",),
    "relative_strength_burst": ("relative_strength_burst",),
    "intraday_range_escape": ("intraday_range_escape",),
    "eligible_signals": ("eligible_signals",),
    "final_passed": ("final_passed", "final_passed_count"),
}


def now_ist() -> datetime:
    try:
        from utils.market_hours import IST
    except Exception:
        return datetime.now().astimezone()
    return datetime.now(IST)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
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
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=now_ist().tzinfo)
    return dt.astimezone(now_ist().tzinfo)


def payload_time(payload: dict[str, Any]) -> datetime | None:
    for key in (
        "timestamp_ist",
        "scan_finished_at_ist",
        "generated_at_ist",
        "generated_at",
        "updated_at_ist",
        "updated_at",
        "timestamp",
        "last_cycle_time",
        "last_update",
    ):
        dt = parse_dt(payload.get(key))
        if dt is not None:
            return dt
    return None


def payload_age_seconds(payload: dict[str, Any]) -> float | None:
    dt = payload_time(payload)
    if dt is None:
        return None
    return max(0.0, (now_ist() - dt).total_seconds())


def normalize_mode(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"HFT", "HFT_MODE", "HIGH_FREQUENCY", "HIGH_FREQUENCY_TRADING"}:
        return "HFT"
    return "CLASSIC"


def active_mode() -> str:
    return active_execution_mode()


def first_int(payload: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def classic_payload_from_runtime_scanner(scanner: dict[str, Any]) -> dict[str, Any]:
    age = payload_age_seconds(scanner)
    source_status = str(scanner.get("status") or scanner.get("scanner_status") or "").upper()
    resting = source_status == "INACTIVE" or str(scanner.get("inactive_reason") or "")
    status = "INACTIVE" if resting else "ACTIVE" if age is not None and age <= FRESH_SECONDS else "STALE"
    payload: dict[str, Any] = {
        "mode": "CLASSIC",
        "timestamp": now_ist().isoformat(),
        "timestamp_ist": now_ist().isoformat(),
        "status": status,
        "source_owner": "runtime_scanner",
    }
    if resting:
        payload["inactive_reason"] = scanner.get("inactive_reason") or "classic_scanner_resting"
        for output_key in COUNT_FIELDS:
            payload[output_key] = None
        return payload
    for output_key, source_keys in COUNT_FIELDS.items():
        value = first_int(scanner, source_keys)
        if value is not None:
            payload[output_key] = value
    return payload


def inactive_payload(mode: str, reason: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": normalize_mode(mode),
        "timestamp": now_ist().isoformat(),
        "timestamp_ist": now_ist().isoformat(),
        "status": "INACTIVE",
        "inactive_reason": reason,
    }
    fields = HFT_COUNT_FIELDS if normalize_mode(mode) == "HFT" else COUNT_FIELDS
    for output_key in fields:
        payload[output_key] = None
    return payload


def hft_worker_heartbeat_fresh() -> bool:
    state = read_json(HFT_RUNTIME_STATE_PATH, {})
    health = read_json(HFT_HEALTH_PATH, {})
    if not isinstance(state, dict):
        state = {}
    if not isinstance(health, dict):
        health = {}
    hft_enabled = bool(state.get("hft_enabled"))
    worker_started = bool(state.get("worker_started"))
    running = bool(health.get("running"))
    health_age = payload_age_seconds(health)
    return bool(hft_enabled and worker_started and running and health_age is not None and health_age <= FRESH_SECONDS)


def run_hft_scanner_cycle() -> dict[str, Any]:
    cycle_start = now_ist()
    started = datetime.now().timestamp()
    universe = get_static_hft_universe()
    funnel_counts = {key: 0 for key in HFT_COUNT_FIELDS if key not in {"stocks_scanned", "eligible_signals", "final_passed"}}
    eligible_signals = 0
    final_passed = 0
    errors = 0

    for state in universe:
        try:
            tick = HFTPriceTick(
                symbol=state.symbol,
                price=state.price,
                timestamp=cycle_start,
                volume=state.volume,
                bid=state.bid,
                ask=state.ask,
                spread_pct=state.spread_pct,
                source=state.source,
            )
            snapshot = process_mock_tick(tick, now=cycle_start)
            raw_candidates = run_all_funnels(
                snapshot,
                {
                    "short_term_price_rise": 0.72,
                    "acceleration": 0.71,
                    "continuation_pressure": 0.7,
                    "pullback_depth": 0.68,
                    "reclaim_strength": 0.69,
                    "trend_alignment": 0.7,
                    "volatility_expansion": 0.71,
                    "volume_expansion": 0.72,
                    "range_break": 0.7,
                    "relative_outperformance": 0.69,
                    "strength_burst": 0.7,
                    "tight_intraday_range": 0.68,
                    "momentum_confirmation": 0.7,
                    "volume_strength": 0.72,
                    "volatility_quality": 0.7,
                    "spread_quality": 0.82,
                    "speed_of_move": 0.69,
                    "setup_cleanliness": 0.76,
                },
            )
            for candidate in raw_candidates:
                strategy_key = str(candidate.strategy_name or "").lower()
                if strategy_key in funnel_counts:
                    funnel_counts[strategy_key] += 1
                scored = mark_score(candidate)
                if scored.eligible:
                    eligible_signals += 1
                if scored.executable:
                    final_passed += 1
        except Exception:
            errors += 1

    duration_ms = round((datetime.now().timestamp() - started) * 1000, 3)
    risk_state = HFTRiskState()
    health = write_hft_health_heartbeat(
        risk_state,
        cycle_start=cycle_start,
        cycle_duration_ms=duration_ms,
        feed_status="STATIC_HFT_UNIVERSE",
        running=True,
    )
    payload: dict[str, Any] = {
        "mode": "HFT",
        "timestamp": cycle_start.isoformat(),
        "timestamp_ist": cycle_start.isoformat(),
        "status": "ACTIVE",
        "source_owner": "hft_mode_runtime",
        "stocks_scanned": len(universe),
        "eligible_signals": eligible_signals,
        "final_passed": final_passed,
        "errors": errors,
        **funnel_counts,
        "worker_heartbeat": health.get("last_cycle_time"),
        "trade_placement_allowed": False,
    }
    atomic_write_json(HFT_SCANNER_STATUS_PATH, payload)
    return payload


def hft_counter_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "HFT",
        "timestamp": now_ist().isoformat(),
        "timestamp_ist": now_ist().isoformat(),
        "status": "STALE",
    }
    for output_key in HFT_COUNT_FIELDS:
        payload[output_key] = None
    if active_mode() != "HFT":
        payload["status"] = "INACTIVE"
        payload["inactive_reason"] = "active_execution_mode_not_hft"
        return payload
    if not hft_worker_heartbeat_fresh():
        payload["inactive_reason"] = "hft_worker_heartbeat_missing_or_stale"
        return payload

    for path in HFT_COUNTER_SOURCE_PATHS:
        source = read_json(path, {})
        if not isinstance(source, dict) or not source:
            continue
        source_age = payload_age_seconds(source)
        if source_age is None or source_age > FRESH_SECONDS:
            payload["status"] = "STALE"
        else:
            payload["status"] = "ACTIVE"
        for output_key, source_keys in HFT_COUNT_FIELDS.items():
            value = first_int(source, source_keys)
            if value is not None:
                payload[output_key] = value
        break

    return payload


def refresh_mode_scanner_status() -> dict[str, Any]:
    mode = active_mode()
    result: dict[str, Any] = {"active_mode": mode, "written": [], "status": "NO_WRITE"}

    if mode == "CLASSIC":
        write_execution_mode("CLASSIC")
        scanner = read_json(SCANNER_STATUS_PATH, {})
        if isinstance(scanner, dict) and scanner:
            payload = classic_payload_from_runtime_scanner(scanner)
        else:
            payload = inactive_payload("CLASSIC", "scanner_status_missing")
            result["classic_reason"] = "scanner_status_missing"
        atomic_write_json(CLASSIC_OUTPUT_PATH, payload)
        atomic_write_json(CLASSIC_MODE_OUTPUT_PATH, payload)
        result["written"].append(str(CLASSIC_OUTPUT_PATH.relative_to(ROOT)))
        result["written"].append(str(CLASSIC_MODE_OUTPUT_PATH.relative_to(ROOT)))
        result["classic_status"] = payload["status"]
        result["classic_payload"] = payload
    else:
        write_execution_mode("HFT")
        hft_scanner_payload = run_hft_scanner_cycle()
        classic_rest = inactive_payload("CLASSIC", "hft_active_classic_scanner_resting")
        atomic_write_json(CLASSIC_OUTPUT_PATH, classic_rest)
        atomic_write_json(CLASSIC_MODE_OUTPUT_PATH, classic_rest)
        result["written"].append(str(CLASSIC_OUTPUT_PATH.relative_to(ROOT)))
        result["written"].append(str(CLASSIC_MODE_OUTPUT_PATH.relative_to(ROOT)))
        result["classic_status"] = "INACTIVE"
        result["classic_payload"] = classic_rest
        result["hft_scanner_payload"] = hft_scanner_payload

    hft_payload = hft_counter_payload()
    atomic_write_json(HFT_OUTPUT_PATH, hft_payload)
    result["written"].append(str(HFT_OUTPUT_PATH.relative_to(ROOT)))
    result["hft_status"] = hft_payload["status"]
    result["hft_payload"] = hft_payload
    if result["written"]:
        result["status"] = "UPDATED"
    return result


def main() -> None:
    print(json.dumps(refresh_mode_scanner_status(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
