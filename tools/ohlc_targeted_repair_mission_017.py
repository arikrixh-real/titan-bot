import json
import os
import tempfile
import time
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.ohlc_health import get_cache_file, get_ohlc_freshness, publish_ohlc_health, refresh_ohlc_cache
from market_aware_freshness import build_market_aware_freshness
from restart_readiness_gate import build_restart_readiness_gate
from runtime_truth import build_authoritative_runtime_truth
from scanner_ohlc_setup_truth import build_scanner_ohlc_setup_truth
from utils.market_hours import as_ist_datetime, last_valid_market_session, market_state


RUNTIME_DIR = Path("data") / "runtime"
MISSION_DIAGNOSTIC_PATH = RUNTIME_DIR / "ohlc_targeted_repair_mission_017.json"
OHLC_HEALTH_PATH = RUNTIME_DIR / "ohlc_health.json"
SCAN_SELECTION_STATE_PATH = Path("data") / "scan_selection_state.json"


def _timestamp():
    return as_ist_datetime().isoformat()


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}:{exc}"}
    return payload if isinstance(payload, dict) else {"_read_error": "json_root_not_object"}


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def _selected_symbols(limit=50):
    payload = _read_json(SCAN_SELECTION_STATE_PATH)
    selected = []
    seen = set()
    for symbol in payload.get("selected_symbols") or []:
        clean = str(symbol or "").strip().upper().replace(".NS", "")
        if clean and clean not in seen:
            selected.append(clean)
            seen.add(clean)
        if len(selected) >= limit:
            break
    return selected


def _stale_symbols_from_health():
    payload = _read_json(OHLC_HEALTH_PATH)
    stale = []
    for symbol in payload.get("invalid_symbols") or []:
        clean = str(symbol or "").strip().upper().replace(".NS", "")
        if clean:
            stale.append(clean)
    return stale


def _cache_snapshot(symbols):
    snapshot = {}
    for symbol in symbols:
        path = get_cache_file(symbol)
        snapshot[symbol] = {
            "path": str(path).replace("\\", "/"),
            "exists": path.exists(),
            "mtime_ns": path.stat().st_mtime_ns if path.exists() else None,
            "size_bytes": path.stat().st_size if path.exists() else None,
            "freshness": get_ohlc_freshness(symbol),
        }
    return snapshot


def _updated_cache_files(before, symbols):
    updated = []
    for symbol in symbols:
        path = get_cache_file(symbol)
        previous = before.get(symbol) or {}
        current_mtime = path.stat().st_mtime_ns if path.exists() else None
        current_size = path.stat().st_size if path.exists() else None
        if current_mtime != previous.get("mtime_ns") or current_size != previous.get("size_bytes"):
            updated.append(str(path).replace("\\", "/"))
    return updated


def _refresh_selected_ohlc_health(symbols):
    results = []
    valid = []
    invalid = []
    for symbol in symbols:
        freshness = get_ohlc_freshness(symbol)
        ok = freshness.get("status") in {"PASS", "DEGRADED"}
        if ok:
            valid.append(symbol)
        else:
            invalid.append(symbol)
        results.append(
            {
                "symbol": symbol,
                "valid": ok,
                "freshness": freshness,
                "refresh_attempted": False,
                "refresh_result": None,
            }
        )
    requested = len(symbols)
    invalid_count = len(invalid)
    invalid_ratio = round(invalid_count / requested, 4) if requested else 1.0
    degraded_count = sum(
        1
        for item in results
        if (item.get("freshness") or {}).get("status") == "DEGRADED"
    )
    if requested and invalid_count == 0 and degraded_count == 0:
        status = "PASS"
    elif requested and invalid_ratio <= 0.15:
        status = "DEGRADED"
    else:
        status = "FAIL"
    reason = None
    if not requested:
        reason = "NO_SYMBOLS_REQUESTED"
    elif invalid_count:
        reason = f"OHLC_INVALID_SYMBOLS:{invalid_count}/{requested}"
    elif degraded_count:
        reason = f"OHLC_DEGRADED_HISTORY:{degraded_count}/{requested}"
    return publish_ohlc_health(
        {
            "status": status,
            "reason": reason,
            "max_age_hours": 24,
            "requested_count": requested,
            "valid_count": len(valid),
            "invalid_count": invalid_count,
            "degraded_count": degraded_count,
            "invalid_ratio": invalid_ratio,
            "too_many_invalid": bool(requested and invalid_ratio > 0.15),
            "refresh_attempted_count": 0,
            "refreshed_count": 0,
            "valid_symbols": valid,
            "invalid_symbols": invalid,
            "symbol_results": results,
            "market_state": market_state(),
            "last_valid_session": last_valid_market_session().isoformat(),
            "ohlc_status": "VALID_MARKET_CACHE" if status == "PASS" else status,
        }
    )


def _failed_after_repair(symbols):
    failed = []
    for symbol in symbols:
        freshness = get_ohlc_freshness(symbol)
        if freshness.get("status") not in {"PASS", "DEGRADED"}:
            failed.append(
                {
                    "symbol": symbol,
                    "reason": freshness.get("reason") or freshness.get("market_cache_reason") or "UNKNOWN",
                    "latest_candle_timestamp": freshness.get("latest_candle_timestamp"),
                    "market_cache_status": freshness.get("market_cache_status"),
                    "cache_file": freshness.get("cache_file"),
                }
            )
    return failed


def run_mission():
    stale_before = _stale_symbols_from_health()
    selected = _selected_symbols()
    before_snapshot = _cache_snapshot(stale_before)
    refresh_results = []
    refresh_source_used = []
    started = time.monotonic()

    for symbol in stale_before:
        result = refresh_ohlc_cache(symbol, force=True)
        refresh_results.append(result)
        source = result.get("source")
        if source and source not in refresh_source_used:
            refresh_source_used.append(source)

    health_after = _refresh_selected_ohlc_health(selected)
    scanner_truth = build_scanner_ohlc_setup_truth(write=True)
    runtime_truth = build_authoritative_runtime_truth(write=True)
    gate = build_restart_readiness_gate(runtime_truth=runtime_truth, scanner_truth=scanner_truth, write=True)
    market_freshness = build_market_aware_freshness(write=True)
    stale_after = list(health_after.get("invalid_symbols") or [])
    failed_symbols = _failed_after_repair(stale_before)
    cache_files_updated = _updated_cache_files(before_snapshot, stale_before)

    diagnostic = {
        "generated_at": _timestamp(),
        "mission": "017",
        "mode": "controlled_market_data_repair_only",
        "stale_symbols_before": stale_before,
        "stale_count_before": len(stale_before),
        "refresh_attempted_symbols": stale_before,
        "refresh_source_used": refresh_source_used,
        "broker_order_api_called": False,
        "trading_api_called": False,
        "cache_files_updated": cache_files_updated,
        "failed_symbols": failed_symbols,
        "stale_symbols_after": stale_after,
        "fresh_count_after": int(health_after.get("fresh_count") or health_after.get("valid_count") or 0),
        "stale_count_after": int(health_after.get("stale_count") or len(stale_after)),
        "missing_count_after": int(health_after.get("missing_count") or 0),
        "ohlc_status_after": health_after.get("ohlc_status") or health_after.get("status"),
        "market_aware_freshness_after": market_freshness,
        "restart_readiness_after": gate,
        "safe_to_start_daemon": bool(gate.get("safe_to_start_daemon")),
        "safe_to_start_workers": bool(gate.get("safe_to_start_workers")),
        "blockers": list(gate.get("blockers") or []),
        "warnings": list(gate.get("warnings") or []),
        "duration_seconds": round(time.monotonic() - started, 3),
        "refresh_results": refresh_results,
        "safety": {
            "daemon_start": False,
            "worker_start": False,
            "broker_order_api_called": False,
            "trading_api_called": False,
            "live_trading": False,
            "telegram_sent": False,
            "journal_mutation": False,
            "supabase_trade_order_state": False,
            "hft_built": False,
        },
    }
    _atomic_write_json(MISSION_DIAGNOSTIC_PATH, diagnostic)
    return diagnostic


if __name__ == "__main__":
    print(json.dumps(run_mission(), indent=2, sort_keys=True, default=str))
