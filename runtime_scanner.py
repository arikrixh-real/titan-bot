import json
import hashlib
import tempfile
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from signal_path_diagnostics import add_example, build_scan_report, save_scan_report
from trend_diagnostics import apply_adaptive_trend, explain_trend, save_trend_diagnostics
from engines.setup_engine import (
    breakout_ready,
    get_last_load_debug,
    load_cached_stock_data,
    strong_momentum,
    structure_ok,
    trend_direction,
)
from engines.market_filter import market_regime_status
from engines.time_filter import current_bot_mode
from core.truth_gate import SAFE_SCANNER_PATH, UNSAFE_SCANNER_PATH, scanner_gate_status
from core.truth_gate import validate_trade_setup
from data.paper_journal import maybe_write_paper_journal
from utils.market_hours import is_trade_window
from engines.risk_engine import calculate_rr
from engines.trade_levels import calculate_trade_levels

try:
    from scanners.volume_scanner import volume_anomaly_score
    from scanners.strength_scanner import price_strength_score
    from scanners.compression_scanner import compression_score
    from engines.score_engine import final_signal_score
except Exception:
    volume_anomaly_score = None
    price_strength_score = None
    compression_score = None
    final_signal_score = None

try:
    from intelligence.dynamic_stock_selector import get_dynamic_top_stocks
except Exception:
    get_dynamic_top_stocks = None

from data.ohlc_health import ensure_fresh_ohlc


IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
SCANNER_FILTER_TRUTH_STATUS_PATH = Path("data") / "runtime" / "scanner_filter_truth_status.json"
SCANNER_PREVIOUS_SIGNATURE_PATH = Path("data") / "runtime" / "scanner_previous_signature.json"
SCANNER_RUNTIME_HEARTBEAT_PATH = Path("data") / "runtime" / "scanner_runtime_heartbeat.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
SETUP_ENGINE_STATUS_PATH = Path("data") / "runtime" / "setup_engine_status.json"
WORKER_HEALTH_PATH = Path("data") / "runtime" / "worker_health.json"
FINAL_REJECTION_DEBUG_PATH = Path("data") / "debug" / "final_rejection_breakdown.json"
LIVE_PRICE_CACHE_PATH = Path("data") / "live_price_cache.json"
OHLC_REFRESH_STATUS_PATH = Path("data") / "runtime" / "ohlc_refresh_status.json"
RUNTIME_SELECTOR_STATUS_PATH = Path("data") / "runtime" / "runtime_selector_status.json"
SCAN_SELECTION_STATE_PATH = Path("data") / "scan_selection_state.json"
FILTER_ENGINE_DIAGNOSTICS_PATH = Path("data") / "runtime" / "filter_engine_diagnostics.json"
MOMENTUM_BREAKOUT_COUNTER_AUDIT_PATH = Path("data") / "runtime" / "momentum_breakout_counter_audit.json"
BREAKOUT_PIPELINE_INTEGRITY_PATH = Path("data") / "runtime" / "breakout_pipeline_integrity.json"
NEAR_PASS_SETUPS_PATH = Path("data") / "runtime" / "near_pass_setups.json"
FINAL_VALIDATED_SETUPS_PATH = Path("data") / "runtime" / "final_validated_setups.json"
FINAL_SETUP_WRITE_DEBUG_PATH = Path("data") / "runtime" / "final_setup_write_debug.json"
FILTER_DIAGNOSTICS_HISTORY_DIR = Path("data") / "runtime" / "filter_diagnostics_history"
NEAR_PASS_HISTORY_DIR = Path("data") / "runtime" / "near_pass_history"
RUNTIME_FRESH_SECONDS = 15 * 60
MARKET_CANDLE_STALE_MINUTES = 45
PARTIAL_STALE_TOLERANCE_RATIO = 0.15
SCORED_DYNAMIC_LIMIT = 50
DIAGNOSTIC_HISTORY_RETENTION = 100


def _timestamp_ist():
    return datetime.now(IST).isoformat()


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _heartbeat_payload(
    *,
    latest_cycle=None,
    publish_status,
    scanner_runtime_mode=None,
    scanner_loop_health,
    last_publish_exception=None,
):
    previous = _read_json(SCANNER_RUNTIME_HEARTBEAT_PATH)
    publish_count = _optional_int(previous.get("publish_count")) or 0
    failed_publish_count = _optional_int(previous.get("failed_publish_count")) or 0
    previous_publish_time = previous.get("latest_publish_time")
    if publish_status in {"PUBLISHED", "PARTIAL"}:
        publish_count += 1
    if publish_status == "PUBLISHED":
        last_publish_exception = None
    elif publish_status == "FAILED":
        failed_publish_count += 1
    return {
        "latest_cycle": latest_cycle or previous.get("latest_cycle"),
        "latest_publish_time": _timestamp_ist(),
        "previous_publish_time": previous_publish_time,
        "publish_status": publish_status,
        "publish_count": publish_count,
        "failed_publish_count": failed_publish_count,
        "last_publish_exception": last_publish_exception,
        "scanner_runtime_mode": scanner_runtime_mode or previous.get("scanner_runtime_mode") or "UNKNOWN",
        "scanner_loop_health": scanner_loop_health,
        "safety_flags": {
            "advisory_only": True,
            "affects_live_ranking": False,
            "affects_execution": False,
            "broker_mutation": False,
            "telegram_mutation": False,
            "supabase_mutation": False,
            "live_order_behavior": False,
            "recommended_live_weight": 0.0,
            "rank_adjustment": 0.0,
        },
    }


def _write_scanner_heartbeat(**kwargs):
    try:
        _atomic_write_json(SCANNER_RUNTIME_HEARTBEAT_PATH, _heartbeat_payload(**kwargs))
    except Exception:
        pass


def _payload_dt(payload):
    if not isinstance(payload, dict):
        return None
    value = (
        payload.get("timestamp_ist")
        or payload.get("last_finished_at")
        or payload.get("last_started_at")
        or payload.get("timestamp")
        or payload.get("updated_at")
        or payload.get("created_at")
    )
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _payload_fresh(payload, fresh_seconds=RUNTIME_FRESH_SECONDS):
    dt = _payload_dt(payload)
    if not dt:
        return False
    return (datetime.now(IST) - dt).total_seconds() <= fresh_seconds


def _payload_active(payload):
    if not isinstance(payload, dict) or not payload:
        return False
    status = str(payload.get("status") or "").upper()
    if not status:
        return False
    inactive_markers = ("FAILED", "ERROR", "STOPPED", "INACTIVE", "TIMEOUT", "STALE")
    return not any(marker in status for marker in inactive_markers)


def _fresh_active_payload(path):
    payload = _read_json(path)
    return payload, bool(_payload_fresh(payload) and _payload_active(payload))


def _worker_health_task_ok(task):
    payload = _read_json(WORKER_HEALTH_PATH)
    task_payload = payload.get(task) if isinstance(payload, dict) else None
    return bool(_payload_fresh(task_payload) and _payload_active(task_payload))


def _task_available(task, status_path):
    payload, payload_ok = _fresh_active_payload(status_path)
    return payload, bool(payload_ok or _worker_health_task_ok(task))


def _task_availability_state(task, status_path):
    payload = _read_json(status_path)
    worker_ok = _worker_health_task_ok(task)
    fresh = _payload_fresh(payload)
    active = _payload_active(payload)
    present = bool(payload)
    truly_unavailable = bool((not present and not worker_ok) or (present and not active and not worker_ok))
    return {
        "payload": payload,
        "ok": bool((fresh and active) or worker_ok),
        "present": present,
        "fresh": fresh,
        "active": active,
        "worker_ok": worker_ok,
        "truly_unavailable": truly_unavailable,
        "advisory_stale": bool(present and active and not fresh and not worker_ok),
        "status": payload.get("status") if isinstance(payload, dict) else None,
        "timestamp": _final_count_timestamp(payload),
    }


def _fresh_int(payload, key):
    if not _payload_fresh(payload):
        return None
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _list_count(payload, key):
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return len(value) if isinstance(value, list) else None


def _nested_selected_count(payload, key):
    if not isinstance(payload, dict):
        return None
    nested = payload.get(key)
    if not isinstance(nested, dict):
        return None
    selected = nested.get("selected")
    return len(selected) if isinstance(selected, list) else None


def _first_count(payload, keys):
    if not isinstance(payload, dict):
        return None, None
    for key in keys:
        value = _optional_int(payload.get(key))
        if value is not None:
            return value, key
    return None, None


def _final_count_timestamp(payload):
    dt = _payload_dt(payload)
    return dt.isoformat() if dt else None


def _resolve_final_count(master_payload, setup_payload, final_debug):
    """
    Read-only resolver for actual final candidate counts already emitted by
    setup_engine/master_brain outputs. Zero is a valid count; None means no
    usable source exists.
    """
    count, key = _first_count(
        master_payload,
        (
            "final_passed",
            "final_selected_count",
            "selected_count",
            "selected_candidates_count",
        ),
    )
    if count is None:
        count = _nested_selected_count(master_payload, "final_decisions")
        key = "final_decisions.selected" if count is not None else None
    if count is None:
        count = _list_count(master_payload, "selected")
        key = "selected" if count is not None else None
    if count is not None:
        return {
            "entry_passed": _optional_int(master_payload.get("entry_passed")),
            "final_passed": count,
            "final_count_source": "master_brain_status",
            "final_passed_note": (
                f"Real final count read from data/runtime/master_brain_status.json field {key}."
            ),
            "entry_stage_available": _optional_int(master_payload.get("entry_passed")) is not None,
            "available": True,
            "timestamp": _final_count_timestamp(master_payload),
        }

    count, key = _first_count(
        setup_payload,
        (
            "final_passed",
            "final_selected_count",
            "selected_count",
            "selected_candidates_count",
        ),
    )
    if count is not None:
        return {
            "entry_passed": _optional_int(setup_payload.get("entry_passed")),
            "final_passed": count,
            "final_count_source": "setup_engine_status",
            "final_passed_note": (
                f"Real final count read from data/runtime/setup_engine_status.json field {key}."
            ),
            "entry_stage_available": _optional_int(setup_payload.get("entry_passed")) is not None,
            "available": True,
            "timestamp": _final_count_timestamp(setup_payload),
        }

    debug_count, debug_key = _first_count(final_debug, ("final_passed",))
    if debug_count is not None:
        return {
            "entry_passed": _optional_int(final_debug.get("entry_passed")),
            "final_passed": debug_count,
            "final_count_source": "setup_engine_status",
            "final_passed_note": (
                "Real setup_engine final count read from "
                f"data/debug/final_rejection_breakdown.json field {debug_key}."
            ),
            "entry_stage_available": _optional_int(final_debug.get("entry_passed")) is not None,
            "available": True,
            "timestamp": _final_count_timestamp(final_debug),
        }

    missing = []
    if not isinstance(setup_payload, dict) or not setup_payload:
        missing.append("data/runtime/setup_engine_status.json missing or empty")
    else:
        missing.append("setup_engine_status has no final count field")
    if not isinstance(master_payload, dict) or not master_payload:
        missing.append("data/runtime/master_brain_status.json missing or empty")
    else:
        missing.append("master_brain_status has no selected/final count field")
    if not isinstance(final_debug, dict) or not final_debug:
        missing.append("data/debug/final_rejection_breakdown.json missing or empty")
    else:
        missing.append("final_rejection_breakdown has no final_passed field")

    return {
        "entry_passed": None,
        "final_passed": None,
        "final_count_source": "unavailable",
        "final_passed_note": "Final count unavailable: " + "; ".join(missing) + ".",
        "entry_stage_available": False,
        "available": False,
        "timestamp": None,
    }


def _read_previous_run_count(path):
    try:
        path = Path(path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        run_count = payload.get("run_count") if isinstance(payload, dict) else None
        if isinstance(run_count, int) and not isinstance(run_count, bool):
            return run_count
    except Exception:
        return None
    return None


def _read_previous_data_signature(path=SCANNER_PREVIOUS_SIGNATURE_PATH):
    try:
        path = Path(path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        signature = payload.get("data_signature") if isinstance(payload, dict) else None
        return signature if isinstance(signature, str) and signature else None
    except Exception:
        return None


def _write_previous_data_signature(signature, scanner_cycle_id, timestamp_ist, path=SCANNER_PREVIOUS_SIGNATURE_PATH):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "data_signature": signature,
            "scanner_cycle_id": scanner_cycle_id,
            "timestamp_ist": timestamp_ist,
        }
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)
    except Exception:
        pass


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
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(path)
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _clean_selector_symbol(symbol):
    return str(symbol or "").strip().upper().replace(".NS", "")


def _dedupe_symbols(symbols):
    selected = []
    seen = set()
    for symbol in symbols or []:
        clean = _clean_selector_symbol(symbol)
        if clean and clean not in seen:
            selected.append(clean)
            seen.add(clean)
    return selected


def _write_runtime_selector_status(
    *,
    selector_used,
    fallback_active,
    fallback_reason,
    symbols,
    selection_source,
    truth_gate_status="UNKNOWN",
):
    payload = {
        "timestamp_ist": _timestamp_ist(),
        "selector_used": selector_used,
        "fallback_active": bool(fallback_active),
        "fallback_reason": fallback_reason,
        "selected_count": len(symbols or []),
        "symbols": list(symbols or []),
        "selection_source": selection_source,
        "truth_gate_status": truth_gate_status,
    }
    try:
        _atomic_write_json(RUNTIME_SELECTOR_STATUS_PATH, payload)
    except Exception:
        pass
    return payload


def _write_scan_selection_state_from_selector(selector_payload):
    try:
        previous = _read_json(SCAN_SELECTION_STATE_PATH)
        payload = dict(previous)
        symbols = selector_payload.get("symbols") or []
        payload.update(
            {
                "timestamp": selector_payload.get("timestamp_ist"),
                "selector": selector_payload.get("selector_used"),
                "runtime_path": selector_payload.get("selector_used"),
                "fallback_active": bool(selector_payload.get("fallback_active")),
                "fallback_reason": selector_payload.get("fallback_reason"),
                "selected_symbols_count": len(symbols),
                "selected_symbols": symbols,
                "selection_source": selector_payload.get("selection_source"),
            }
        )
        _atomic_write_json(SCAN_SELECTION_STATE_PATH, payload)
    except Exception:
        pass


def _print_selector_banner(selector_payload):
    print("[TITAN SELECTOR]")
    if selector_payload.get("fallback_active"):
        print("MODE=FALLBACK")
        print(f"SELECTOR={UNSAFE_SCANNER_PATH}")
        print(f"REASON={selector_payload.get('fallback_reason')}")
        return
    print("MODE=LIVE_DYNAMIC")
    print(f"SELECTOR={SAFE_SCANNER_PATH}")
    print(f"COUNT={selector_payload.get('selected_count')}")


def _load_scored_dynamic_symbols_with_debug():
    if get_dynamic_top_stocks is None:
        raise RuntimeError("dynamic selector import unavailable")

    selected_symbols = _dedupe_symbols(get_dynamic_top_stocks(limit=SCORED_DYNAMIC_LIMIT))
    if not selected_symbols:
        raise RuntimeError("dynamic selector returned no symbols")

    ohlc_health = ensure_fresh_ohlc(selected_symbols, max_age_hours=24)
    valid_symbol_set = set(ohlc_health.get("valid_symbols") or [])
    invalid_symbols = list(ohlc_health.get("invalid_symbols") or [])

    cached_symbols = {}
    missing_symbols = []
    stale_symbols = []
    cache_debug = {}

    for symbol in selected_symbols:
        if symbol not in valid_symbol_set:
            continue
        data = load_cached_stock_data(symbol)
        if data is None or getattr(data, "empty", False):
            missing_symbols.append(symbol)
            continue
        cached_symbols[symbol] = data
        cache_debug[symbol] = {"selector": SAFE_SCANNER_PATH}

    for symbol, data in cached_symbols.items():
        if _last_candle_timestamp(data) is None:
            stale_symbols.append(symbol)

    load_debug = {
        "selector": SAFE_SCANNER_PATH,
        "runtime_path": SAFE_SCANNER_PATH,
        "selected_symbols_count": len(selected_symbols),
        "loaded_symbols_count": len(cached_symbols),
        "missing_symbols_count": len(missing_symbols),
        "missing_symbols": missing_symbols,
        "stale_cache_count": len(stale_symbols) + len(invalid_symbols),
        "stale_cache_symbols": stale_symbols + invalid_symbols,
        "invalid_ohlc_symbols_count": len(invalid_symbols),
        "invalid_ohlc_symbols": invalid_symbols,
        "ohlc_health_status": ohlc_health.get("status"),
        "ohlc_health_reason": ohlc_health.get("reason"),
        "ohlc_health_path": "data/runtime/ohlc_health.json",
        "selected_symbols": selected_symbols,
        "scan_symbols": list(cached_symbols.keys()),
        "cache_debug": cache_debug,
    }
    return cached_symbols, load_debug, selected_symbols


def _load_runtime_symbols_with_selector():
    try:
        cached_symbols, load_debug, selected_symbols = _load_scored_dynamic_symbols_with_debug()
        selector_payload = _write_runtime_selector_status(
            selector_used=SAFE_SCANNER_PATH,
            fallback_active=False,
            fallback_reason=None,
            symbols=selected_symbols,
            selection_source="intelligence.dynamic_stock_selector.get_dynamic_top_stocks",
        )
        _write_scan_selection_state_from_selector(selector_payload)
        _print_selector_banner(selector_payload)
        return cached_symbols, load_debug, selector_payload
    except Exception as exc:
        cached_symbols, load_debug = _load_cached_symbols_with_debug()
        selected_symbols = list((cached_symbols or {}).keys())
        reason = f"SELECTOR_CRASH:{type(exc).__name__}:{exc}"
        selector_payload = _write_runtime_selector_status(
            selector_used=UNSAFE_SCANNER_PATH,
            fallback_active=True,
            fallback_reason=reason,
            symbols=selected_symbols,
            selection_source="data.loader.load_cached_stock_data",
        )
        _write_scan_selection_state_from_selector(selector_payload)
        _print_selector_banner(selector_payload)
        return cached_symbols, load_debug, selector_payload


def _scan_mode(load_debug, scan_only):
    if not scan_only:
        return "FULL_RUNTIME_PIPELINE"

    if not isinstance(load_debug, dict):
        return "SCAN_ONLY"

    selected_count = load_debug.get("selected_symbols_count")
    if selected_count is None:
        return "SCAN_ONLY"

    return f"SCAN_ONLY_CACHED_{selected_count}"


def _side_from_trend(trend):
    if trend == "BULLISH":
        return "LONG"
    if trend == "BEARISH":
        return "SHORT"
    if trend == "UP":
        return "LONG"
    if trend == "DOWN":
        return "SHORT"
    return None


def _last_ohlc(data):
    try:
        if data is None or data.empty:
            return None

        for column in ["High", "Low", "Close"]:
            if column not in data.columns:
                return None

        last = data.iloc[-1]
        return {
            "High": float(last["High"]),
            "Low": float(last["Low"]),
            "Close": float(last["Close"]),
        }
    except Exception:
        return None


def _last_close(data):
    try:
        if data is None or data.empty or "Close" not in data.columns:
            return None
        return float(data["Close"].iloc[-1])
    except Exception:
        return None


def _live_price_for_symbol(live_price_cache, symbol):
    if not isinstance(live_price_cache, dict):
        return None
    candidates = [
        live_price_cache.get(symbol),
        live_price_cache.get(str(symbol).upper()),
        live_price_cache.get(str(symbol).lower()),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("ltp", "last_price", "price", "close"):
                value = _optional_float(candidate.get(key))
                if value is not None:
                    return value
        value = _optional_float(candidate)
        if value is not None:
            return value
    nested = live_price_cache.get("prices")
    if isinstance(nested, dict):
        return _live_price_for_symbol(nested, symbol)
    return None


def _optional_float(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _live_price_check(live_price_cache, symbol, close):
    live_price = _live_price_for_symbol(live_price_cache, symbol)
    if live_price is None or close in (None, 0):
        return {
            "available": live_price is not None,
            "live_price": live_price,
            "cached_close": close,
            "mismatch_pct": None,
            "mismatch_warning": False,
        }
    mismatch_pct = round(abs(live_price - close) / abs(close) * 100.0, 4)
    return {
        "available": True,
        "live_price": live_price,
        "cached_close": close,
        "mismatch_pct": mismatch_pct,
        "mismatch_warning": mismatch_pct >= 1.0,
    }


def _safe_history_name(timestamp_ist, scanner_cycle_id):
    timestamp = str(timestamp_ist or _timestamp_ist()).replace(":", "-")
    timestamp = timestamp.replace("+", "_").replace("/", "-").replace("\\", "-")
    cycle = str(scanner_cycle_id or "unknown").replace(":", "-")
    cycle = cycle.replace("+", "_").replace("/", "-").replace("\\", "-")
    cycle = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in cycle)
    return f"{timestamp}_{cycle}.json"


def _retain_latest_history_files(directory, keep=DIAGNOSTIC_HISTORY_RETENTION):
    try:
        directory = Path(directory)
        if not directory.exists():
            return
        files = sorted(
            [path for path in directory.glob("*.json") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old_path in files[int(keep):]:
            old_path.unlink()
    except Exception as exc:
        print(f"[FILTER DIAGNOSTICS] history retention skipped: {exc}")


def _write_filter_history_snapshot(payload, near_pass_payload):
    try:
        FILTER_DIAGNOSTICS_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        NEAR_PASS_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        filename = _safe_history_name(payload.get("timestamp_ist"), payload.get("scanner_cycle_id"))
        filter_history_path = FILTER_DIAGNOSTICS_HISTORY_DIR / filename
        near_pass_history_path = NEAR_PASS_HISTORY_DIR / filename
        _atomic_write_json(filter_history_path, payload)
        _atomic_write_json(near_pass_history_path, near_pass_payload)
        _retain_latest_history_files(FILTER_DIAGNOSTICS_HISTORY_DIR)
        _retain_latest_history_files(NEAR_PASS_HISTORY_DIR)
        payload["history_snapshot_path"] = str(filter_history_path)
        payload["near_pass_history_snapshot_path"] = str(near_pass_history_path)
    except Exception as exc:
        payload["history_snapshot_error"] = str(exc)


def _contract_side(side):
    side = str(side or "").upper().strip()
    if side == "LONG":
        return "BUY"
    if side == "SHORT":
        return "SELL"
    if side in {"BUY", "SELL"}:
        return side
    return side


def _final_setup_reason(symbol_diag):
    trend_values = (symbol_diag.get("trend_engine") or {}).get("values") or {}
    return (
        f"trend={trend_values.get('direction')}; "
        f"momentum={(symbol_diag.get('momentum_engine') or {}).get('status')}; "
        f"structure={(symbol_diag.get('structure_engine') or {}).get('status')}; "
        f"entry={(symbol_diag.get('entry_engine') or {}).get('status')}"
    )


def _build_final_validated_setup(symbol, data, side, symbol_diag, scanner_cycle_id, truth_gate_payload, selector_payload):
    entry, stop_loss, target = calculate_trade_levels(data, side=side)
    rr = calculate_rr(entry, stop_loss, target, side=side)
    final_score = ((symbol_diag.get("final_score_engine") or {}).get("values") or {}).get("final_score")
    setup = {
        "symbol": str(symbol).upper(),
        "side": _contract_side(side),
        "entry": entry,
        "stop_loss": stop_loss,
        "target": target,
        "rr": rr,
        "final_score": final_score,
        "reason": _final_setup_reason(symbol_diag),
        "scanner_cycle_id": scanner_cycle_id,
        "timestamp_ist": _timestamp_ist(),
        "truth_gate_status": (truth_gate_payload or {}).get("overall_status"),
        "selector_used": (selector_payload or {}).get("selector_used"),
    }
    setup["contract_validation"] = validate_trade_setup(setup)
    return setup


def _write_final_validated_setups(setups, scanner_cycle_id, reason=None):
    required_fields = ["symbol", "side", "entry", "stop_loss", "target", "rr", "final_score", "reason"]
    validation_failures = []
    for setup in setups or []:
        missing = [field for field in required_fields if setup.get(field) in (None, "")]
        if missing:
            validation_failures.append({"symbol": setup.get("symbol"), "missing_fields": missing})
    payload = {
        "timestamp_ist": _timestamp_ist(),
        "scanner_cycle_id": scanner_cycle_id,
        "validated_setup_count": len(setups or []),
        "setups": setups or [],
        "reason": reason if not setups else None,
        "source": "runtime_scanner.canonical_final_validated_setups",
        "schema_version": 1,
    }
    _atomic_write_json(FINAL_VALIDATED_SETUPS_PATH, payload)
    file_size = FINAL_VALIDATED_SETUPS_PATH.stat().st_size if FINAL_VALIDATED_SETUPS_PATH.exists() else 0
    write_timestamp = _timestamp_ist()
    debug_payload = {
        "timestamp_ist": write_timestamp,
        "scanner_write_timestamp_ist": write_timestamp,
        "scanner_validated_count": len(setups or []),
        "scanner_symbols": [item.get("symbol") for item in setups or []],
        "file_written": FINAL_VALIDATED_SETUPS_PATH.exists(),
        "file_size_bytes": file_size,
        "paper_journal_loaded_count": None,
        "paper_journal_symbols": [],
        "validation_failures": validation_failures,
        "path": str(FINAL_VALIDATED_SETUPS_PATH),
        "scanner_cycle_id": scanner_cycle_id,
        "sequence": ["scanner_write_complete"],
    }
    _atomic_write_json(FINAL_SETUP_WRITE_DEBUG_PATH, debug_payload)
    print("[FINAL SETUPS]")
    print(f"validated_count={debug_payload['scanner_validated_count']}")
    print(f"path={FINAL_VALIDATED_SETUPS_PATH}")
    print(f"symbols={debug_payload['scanner_symbols']}")
    if validation_failures:
        print(f"validation_failures={validation_failures}")
    return payload


def _series(data, column):
    try:
        if data is None or column not in data.columns:
            return None
        return data[column].astype(float).dropna()
    except Exception:
        return None


def _round(value, places=4):
    try:
        if value is None:
            return None
        return round(float(value), places)
    except Exception:
        return None


def _rsi(close, period=14):
    try:
        if close is None or len(close) < period + 1:
            return None
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs = gain / loss.replace(0, float("nan"))
        return _round(100 - (100 / (1 + rs.iloc[-1])))
    except Exception:
        return None


def _atr(data, period=14):
    try:
        high = _series(data, "High")
        low = _series(data, "Low")
        close = _series(data, "Close")
        if high is None or low is None or close is None or len(close) < period + 1:
            return None
        previous_close = close.shift(1)
        true_range = (high - low).to_frame("hl")
        true_range["hc"] = (high - previous_close).abs()
        true_range["lc"] = (low - previous_close).abs()
        return _round(true_range.max(axis=1).rolling(period).mean().iloc[-1])
    except Exception:
        return None


def _support_resistance(data, lookback=8):
    try:
        if data is None or len(data) < lookback:
            return None, None
        recent = data.iloc[-lookback:]
        support = float(recent["Low"].iloc[:-1].min())
        resistance = float(recent["High"].iloc[:-1].max())
        return support, resistance
    except Exception:
        return None, None


def _engine_error(name, exc):
    return {
        "status": "ERROR",
        "reason": f"{name}_EXCEPTION:{type(exc).__name__}:{exc}",
        "values": {},
        "exception": traceback.format_exc(),
    }


def _diagnose_trend_engine(data):
    try:
        close = _series(data, "Close")
        if close is None or len(close) == 0:
            return {"status": "FAIL", "reason": "CLOSE_SERIES_MISSING", "values": {}}
        ema20 = close.ewm(span=20, adjust=False).mean() if len(close) >= 20 else None
        ema50 = close.ewm(span=50, adjust=False).mean() if len(close) >= 50 else None
        direction = trend_direction(data)
        side = _side_from_trend(direction)
        slope = None
        if ema20 is not None and len(ema20) >= 5:
            slope = float(ema20.iloc[-1]) - float(ema20.iloc[-5])
        values = {
            "EMA20": _round(ema20.iloc[-1]) if ema20 is not None else None,
            "EMA50": _round(ema50.iloc[-1]) if ema50 is not None else None,
            "ema20_available": ema20 is not None,
            "ema50_available": ema50 is not None,
            "direction": direction,
            "slope": _round(slope),
            "close": _round(close.iloc[-1]),
            "rows": len(close),
            "row_count": len(close),
            "history_depth_status": (
                "PASS" if len(close) >= 100 else (
                    "DEGRADED" if len(close) >= 60 else "FAIL"
                )
            ),
            "side": side,
        }
        return {
            "status": "PASS" if side else "FAIL",
            "reason": None if side else str(direction or "NO_VALID_TREND"),
            "values": values,
        }
    except Exception as exc:
        return _engine_error("TREND_ENGINE", exc)


def _diagnose_momentum_engine(data, side):
    try:
        close = _series(data, "Close")
        volume = _series(data, "Volume")
        last = data.iloc[-1] if data is not None and len(data) else None
        previous = data.iloc[-2] if data is not None and len(data) > 1 else None
        body_ratio = None
        breakout_strength = None
        if last is not None:
            candle_range = float(last["High"] - last["Low"])
            body_ratio = abs(float(last["Close"] - last["Open"])) / candle_range if candle_range else None
        support, resistance = _support_resistance(data)
        last_close = float(close.iloc[-1]) if close is not None and len(close) else None
        if last_close and resistance and side == "LONG":
            breakout_strength = (last_close / resistance) - 1
        elif last_close and support and side == "SHORT":
            breakout_strength = (support / last_close) - 1
        volume_ratio = None
        if volume is not None and len(volume) >= 2:
            avg_volume = float(volume.tail(min(20, len(volume))).mean())
            volume_ratio = float(volume.iloc[-1]) / avg_volume if avg_volume else None
        passed = bool(side and strong_momentum(data, side=side))
        values = {
            "RSI": _rsi(close),
            "volume_ratio": _round(volume_ratio),
            "breakout_strength": _round(breakout_strength),
            "ATR": _atr(data),
            "momentum_score": _round((body_ratio or 0) * 100),
            "body_ratio": _round(body_ratio),
            "last_close": _round(last_close),
            "previous_close": _round(previous["Close"]) if previous is not None else None,
        }
        return {"status": "PASS" if passed else "FAIL", "reason": None if passed else "MOMENTUM_FAIL", "values": values}
    except Exception as exc:
        return _engine_error("MOMENTUM_ENGINE", exc)


def _diagnose_structure_engine(data, side):
    try:
        support, resistance = _support_resistance(data)
        close = _series(data, "Close")
        last_close = float(close.iloc[-1]) if close is not None and len(close) else None
        passed = bool(side and structure_ok(data, side=side))
        breakout_status = None
        if last_close is not None and support is not None and resistance is not None:
            if side == "LONG":
                breakout_status = last_close > resistance
            elif side == "SHORT":
                breakout_status = last_close < support
        compression_status = None
        if last_close and support is not None and resistance is not None:
            compression_status = ((resistance - support) / last_close) <= 0.02
        values = {
            "support": _round(support),
            "resistance": _round(resistance),
            "breakout_status": breakout_status,
            "compression_status": compression_status,
            "close": _round(last_close),
        }
        return {"status": "PASS" if passed else "FAIL", "reason": None if passed else "STRUCTURE_FAIL", "values": values}
    except Exception as exc:
        return _engine_error("STRUCTURE_ENGINE", exc)


def _diagnose_entry_engine(data, side):
    try:
        close = _series(data, "Close")
        entry_price = float(close.iloc[-1]) if close is not None and len(close) else None
        support, resistance = _support_resistance(data)
        passed = bool(side and breakout_ready(data, side=side))
        sl_distance = None
        rr = None
        reward = None
        if entry_price is not None and support is not None and resistance is not None:
            if side == "LONG":
                sl_distance = max(entry_price - support, 0)
                reward = max(resistance - entry_price, 0)
            elif side == "SHORT":
                sl_distance = max(resistance - entry_price, 0)
                reward = max(entry_price - support, 0)
            rr = reward / sl_distance if sl_distance and reward is not None else None
        values = {
            "entry_price": _round(entry_price),
            "trigger_state": "READY" if passed else "NOT_READY",
            "RR": _round(rr),
            "SL_distance": _round(sl_distance),
        }
        return {"status": "PASS" if passed else "FAIL", "reason": None if passed else "NOT_READY", "values": values}
    except Exception as exc:
        return _engine_error("ENTRY_ENGINE", exc)


def _diagnose_market_filter():
    try:
        status = market_regime_status()
        return {"status": "PASS", "reason": None, "values": {"market_status": status}}
    except Exception as exc:
        return _engine_error("MARKET_FILTER", exc)


def _diagnose_final_score_engine(data, momentum_diag, structure_diag, entry_diag):
    try:
        if final_signal_score is None:
            return {"status": "ERROR", "reason": "FINAL_SCORE_ENGINE_IMPORT_FAILED", "values": {}}
        volume_value = volume_anomaly_score(data) if volume_anomaly_score else 0
        strength_value = price_strength_score(data) if price_strength_score else 0
        compression_value = compression_score(data) if compression_score else 0
        score = final_signal_score(
            volume_score=volume_value,
            strength_score=strength_value,
            compression_score=compression_value,
            momentum_ok=momentum_diag.get("status") == "PASS",
            structure_ok=structure_diag.get("status") == "PASS",
            entry_ok=entry_diag.get("status") == "PASS",
        )
        return {
            "status": "PASS",
            "reason": None,
            "values": {
                "volume_score": _round(volume_value),
                "strength_score": _round(strength_value),
                "compression_score": _round(compression_value),
                "final_score": _round(score),
            },
        }
    except Exception as exc:
        return _engine_error("FINAL_SCORE_ENGINE", exc)


def _symbol_filter_diagnostics(symbol, data):
    trend_diag = _diagnose_trend_engine(data)
    side = (trend_diag.get("values") or {}).get("side")
    momentum_diag = _diagnose_momentum_engine(data, side)
    structure_diag = _diagnose_structure_engine(data, side)
    entry_diag = _diagnose_entry_engine(data, side)
    market_diag = _diagnose_market_filter()
    final_score_diag = _diagnose_final_score_engine(data, momentum_diag, structure_diag, entry_diag)
    return {
        "symbol": str(symbol),
        "trend_engine": trend_diag,
        "momentum_engine": momentum_diag,
        "structure_engine": structure_diag,
        "entry_engine": entry_diag,
        "market_filter": market_diag,
        "final_score_engine": final_score_diag,
    }


def _momentum_breakout_audit_record(symbol, diagnostic):
    momentum_diag = diagnostic.get("momentum_engine") if isinstance(diagnostic, dict) else {}
    entry_diag = diagnostic.get("entry_engine") if isinstance(diagnostic, dict) else {}
    trend_diag = diagnostic.get("trend_engine") if isinstance(diagnostic, dict) else {}
    structure_diag = diagnostic.get("structure_engine") if isinstance(diagnostic, dict) else {}
    return {
        "symbol": str(symbol),
        "momentum_passed": momentum_diag.get("status") == "PASS",
        "breakout_ready": entry_diag.get("status") == "PASS",
        "momentum_reason": momentum_diag.get("reason"),
        "breakout_reason": entry_diag.get("reason"),
        "momentum_values": momentum_diag.get("values") or {},
        "breakout_values": entry_diag.get("values") or {},
        "side": (trend_diag.get("values") or {}).get("side"),
        "trend_passed": trend_diag.get("status") == "PASS",
        "structure_passed": structure_diag.get("status") == "PASS",
        "counted_momentum_passed": False,
        "counted_breakout_ready": False,
        "pipeline_stop_reason": None,
    }


def _write_momentum_breakout_counter_audit(
    records,
    *,
    scanner_cycle_id,
    timestamp_ist,
    momentum_passed_count,
    breakout_ready_count,
    data_signature,
):
    records = [record for record in records if isinstance(record, dict)]
    raw_overlap = sum(1 for row in records if row.get("momentum_passed") and row.get("breakout_ready"))
    raw_momentum_only = sum(1 for row in records if row.get("momentum_passed") and not row.get("breakout_ready"))
    raw_breakout_only = sum(1 for row in records if row.get("breakout_ready") and not row.get("momentum_passed"))
    raw_neither = sum(1 for row in records if not row.get("momentum_passed") and not row.get("breakout_ready"))
    raw_breakout_ready_count = raw_overlap + raw_breakout_only
    counted_overlap = sum(1 for row in records if row.get("counted_momentum_passed") and row.get("counted_breakout_ready"))
    counted_momentum_only = sum(1 for row in records if row.get("counted_momentum_passed") and not row.get("counted_breakout_ready"))
    counted_breakout_only = sum(1 for row in records if row.get("counted_breakout_ready") and not row.get("counted_momentum_passed"))
    counted_neither = sum(1 for row in records if not row.get("counted_momentum_passed") and not row.get("counted_breakout_ready"))
    counted_sets_identical = bool(
        momentum_passed_count == breakout_ready_count
        and counted_momentum_only == 0
        and counted_breakout_only == 0
    )
    suspicious_reasons = []
    if momentum_passed_count == breakout_ready_count:
        suspicious_reasons.append("COUNTS_IDENTICAL")
    if counted_breakout_only > 0:
        suspicious_reasons.append("PIPELINE_COUNT_INCONSISTENCY_BREAKOUT_WITHOUT_MOMENTUM")
    if raw_breakout_only > 0:
        suspicious_reasons.append("RAW_BREAKOUT_CAN_PASS_WITHOUT_MOMENTUM")
    if counted_sets_identical:
        suspicious_reasons.append("ALL_COUNTED_MOMENTUM_SYMBOLS_ARE_COUNTED_BREAKOUT_SYMBOLS")

    payload = {
        "timestamp_ist": timestamp_ist,
        "scanner_cycle_id": scanner_cycle_id,
        "data_signature": data_signature,
        "source": "runtime_scanner.independent_momentum_breakout_audit",
        "counter_sources": {
            "momentum_passed": "runtime_scanner.loop.strong_momentum",
            "breakout_ready": "runtime_scanner.loop.breakout_ready",
        },
        "momentum_passed_count": int(momentum_passed_count or 0),
        "raw_breakout_ready_count": raw_breakout_ready_count,
        "qualified_breakout_ready_count": int(breakout_ready_count or 0),
        "breakout_ready_count": int(breakout_ready_count or 0),
        "raw_overlap_count": raw_overlap,
        "raw_momentum_only_count": raw_momentum_only,
        "raw_breakout_only_count": raw_breakout_only,
        "raw_neither_count": raw_neither,
        "overlap_count": raw_overlap,
        "momentum_only_count": raw_momentum_only,
        "breakout_only_count": raw_breakout_only,
        "neither_count": raw_neither,
        "counted_overlap_count": counted_overlap,
        "counted_momentum_only_count": counted_momentum_only,
        "counted_breakout_only_count": counted_breakout_only,
        "counted_neither_count": counted_neither,
        "qualified_breakout_only_count": counted_breakout_only,
        "exact_same_source": False,
        "counted_sets_identical": counted_sets_identical,
        "suspicious_identical_reason": ";".join(suspicious_reasons) if suspicious_reasons else "NOT_IDENTICAL_OR_NATURAL_DIVERGENCE",
        "records": records,
    }
    _atomic_write_json(MOMENTUM_BREAKOUT_COUNTER_AUDIT_PATH, payload)
    return payload


def _write_breakout_pipeline_integrity(
    records,
    *,
    scanner_cycle_id,
    timestamp_ist,
    raw_breakout_ready_count,
    qualified_breakout_ready_count,
):
    records = [record for record in records if isinstance(record, dict)]
    proof_records = []
    violating_symbols = []
    for record in records:
        raw_breakout_ready = bool(record.get("breakout_ready"))
        qualified_breakout_ready = bool(record.get("counted_breakout_ready"))
        if qualified_breakout_ready and not raw_breakout_ready:
            violating_symbols.append(record.get("symbol"))
        if qualified_breakout_ready:
            qualification_reason = "QUALIFIED_AFTER_TREND_STRUCTURE_MOMENTUM_AND_BREAKOUT"
        else:
            qualification_reason = record.get("pipeline_stop_reason") or (
                "RAW_BREAKOUT_ONLY_NOT_PIPELINE_QUALIFIED"
                if raw_breakout_ready
                else "RAW_BREAKOUT_FALSE"
            )
        proof_records.append(
            {
                "symbol": record.get("symbol"),
                "raw_breakout_ready": raw_breakout_ready,
                "qualified_breakout_ready": qualified_breakout_ready,
                "momentum_passed": bool(record.get("momentum_passed")),
                "structure_passed": bool(record.get("structure_passed")),
                "trend_passed": bool(record.get("trend_passed")),
                "qualification_reason": qualification_reason,
            }
        )

    raw_count = int(raw_breakout_ready_count or 0)
    qualified_count = int(qualified_breakout_ready_count or 0)
    integrity_errors = []
    if qualified_count > raw_count:
        integrity_errors.append("QUALIFIED_BREAKOUT_EXCEEDS_RAW_BREAKOUT")
    if violating_symbols:
        integrity_errors.append("QUALIFIED_SYMBOL_WITHOUT_RAW_BREAKOUT")

    payload = {
        "timestamp_ist": timestamp_ist,
        "scanner_cycle_id": scanner_cycle_id,
        "raw_breakout_ready_count": raw_count,
        "qualified_breakout_ready_count": qualified_count,
        "breakout_ready_count": qualified_count,
        "alias_valid": qualified_count == int(qualified_breakout_ready_count or 0),
        "integrity_valid": not integrity_errors,
        "integrity_errors": integrity_errors,
        "violating_symbols": [symbol for symbol in violating_symbols if symbol],
        "records": proof_records,
        "source": "runtime_scanner.breakout_pipeline_integrity",
        "rule": "qualified_breakout_ready_count <= raw_breakout_ready_count",
    }
    _atomic_write_json(BREAKOUT_PIPELINE_INTEGRITY_PATH, payload)
    return payload


def _near_pass_candidate(diag):
    engines = ["trend_engine", "momentum_engine", "structure_engine", "entry_engine"]
    passed = sum(1 for engine in engines if diag.get(engine, {}).get("status") == "PASS")
    failed_conditions = [
        f"{engine}:{diag.get(engine, {}).get('reason') or diag.get(engine, {}).get('status')}"
        for engine in engines
        if diag.get(engine, {}).get("status") != "PASS"
    ]
    final_values = diag.get("final_score_engine", {}).get("values") or {}
    score = passed * 25 + float(final_values.get("final_score") or 0)
    return {
        "symbol": diag.get("symbol"),
        "score": _round(score),
        "passed_filter_count": passed,
        "failed_conditions": failed_conditions,
        "missing_confirmations": failed_conditions,
        "final_score": final_values.get("final_score"),
    }


def _write_filter_diagnostics(symbol_diagnostics, scanner_cycle_id, final_validated_setups=None):
    engine_names = [
        "trend_engine",
        "momentum_engine",
        "structure_engine",
        "entry_engine",
        "market_filter",
        "final_score_engine",
    ]
    engine_counts = {}
    rejection_reasons = {}
    exceptions = []
    for engine in engine_names:
        counts = Counter()
        reasons = Counter()
        for item in symbol_diagnostics:
            result = item.get(engine, {})
            status = result.get("status") or "UNKNOWN"
            counts[status] += 1
            reason = result.get("reason")
            if reason:
                reasons[reason] += 1
            if status == "ERROR":
                exceptions.append(
                    {
                        "symbol": item.get("symbol"),
                        "engine": engine,
                        "reason": reason,
                        "exception": result.get("exception"),
                    }
                )
        engine_counts[engine] = dict(counts)
        rejection_reasons[engine] = dict(reasons.most_common(10))

    near_pass = sorted(
        (_near_pass_candidate(item) for item in symbol_diagnostics),
        key=lambda item: item.get("score") or 0,
        reverse=True,
    )[:10]
    if final_validated_setups is not None:
        final_setup_count = len(final_validated_setups)
    else:
        final_setup_count = sum(
            1
            for item in symbol_diagnostics
            if all(item.get(engine, {}).get("status") == "PASS" for engine in ["trend_engine", "momentum_engine", "structure_engine", "entry_engine"])
        )
    payload = {
        "timestamp_ist": _timestamp_ist(),
        "scanner_cycle_id": scanner_cycle_id,
        "symbols_scanned": len(symbol_diagnostics),
        "engine_counts": engine_counts,
        "rejection_reasons": rejection_reasons,
        "exceptions": exceptions,
        "near_pass_setups": near_pass,
        "final_setup_count": final_setup_count,
        "symbols": symbol_diagnostics,
    }
    near_pass_payload = {
        "timestamp_ist": payload["timestamp_ist"],
        "scanner_cycle_id": scanner_cycle_id,
        "near_pass_setups": near_pass,
    }
    _write_filter_history_snapshot(payload, near_pass_payload)
    _atomic_write_json(FILTER_ENGINE_DIAGNOSTICS_PATH, payload)
    _atomic_write_json(NEAR_PASS_SETUPS_PATH, near_pass_payload)
    return payload


def _print_filter_diagnostics_summary(payload):
    print("[FILTER DIAGNOSTICS]")
    for engine, counts in (payload.get("engine_counts") or {}).items():
        print(f"{engine}: {counts}")
    print(f"final_setup_count={payload.get('final_setup_count')}")
    for engine, engine_reasons in (payload.get("rejection_reasons") or {}).items():
        if engine_reasons:
            print(f"{engine} top_rejections={engine_reasons}")
    exceptions = payload.get("exceptions") or []
    if exceptions:
        print(f"engine_exceptions={len(exceptions)}")


def _parse_candle_timestamp(value):
    try:
        if value is None:
            return None
        parsed = __import__("pandas").to_datetime(value, errors="coerce")
        if parsed is None or parsed is __import__("pandas").NaT:
            return None
        if getattr(parsed, "tzinfo", None) is None:
            parsed = parsed.tz_localize(timezone.utc)
        return parsed.to_pydatetime().astimezone(IST)
    except Exception:
        return None


def _last_candle_timestamp(data):
    try:
        if data is None or data.empty:
            return None

        for column in ["Datetime", "Date", "timestamp", "time"]:
            if column in data.columns:
                dt = _parse_candle_timestamp(data[column].iloc[-1])
                if dt:
                    return dt

        index = getattr(data, "index", None)
        if index is not None and len(index) > 0:
            return _parse_candle_timestamp(index[-1])
    except Exception:
        return None
    return None


def _latest_timestamp(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def _data_signature(signature_rows):
    normalized_rows = []
    for row in sorted(signature_rows, key=lambda item: item["symbol"]):
        normalized_rows.append(
            {
                "symbol": row["symbol"],
                "latest_candle_timestamp": row["latest_candle_timestamp"],
                "close": row["close"],
            }
        )
    raw = json.dumps(normalized_rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candle_age_minutes(latest_candle_dt, now_ist):
    if latest_candle_dt is None:
        return None
    try:
        return round(max((now_ist - latest_candle_dt).total_seconds(), 0) / 60, 2)
    except Exception:
        return None


def _stale_policy(stale_symbol_count, stocks_checked, latest_candle_age_minutes, market_mode):
    stale_symbol_ratio = (
        round(stale_symbol_count / stocks_checked, 4)
        if stocks_checked > 0
        else 0.0
    )
    global_stale = bool(
        market_mode
        and (
            latest_candle_age_minutes is None
            or latest_candle_age_minutes > MARKET_CANDLE_STALE_MINUTES
        )
    )
    partial_stale_tolerated = bool(
        market_mode
        and stale_symbol_count > 0
        and not global_stale
        and stale_symbol_ratio <= PARTIAL_STALE_TOLERANCE_RATIO
    )
    stale_ratio_fallback = bool(
        market_mode
        and stale_symbol_count > 0
        and stale_symbol_ratio > PARTIAL_STALE_TOLERANCE_RATIO
    )
    fallback_required = bool(global_stale or stale_ratio_fallback)

    if fallback_required and global_stale:
        policy = "GLOBAL_LATEST_CANDLE_STALE_FALLBACK"
    elif fallback_required:
        policy = "STALE_SYMBOL_RATIO_FALLBACK"
    elif partial_stale_tolerated:
        policy = "PARTIAL_STALE_TOLERATED_15_PERCENT"
    else:
        policy = "OHLC_FRESH"

    return {
        "fallback_required": fallback_required,
        "partial_stale_tolerated": partial_stale_tolerated,
        "stale_symbol_ratio": stale_symbol_ratio,
        "stale_policy": policy,
        "global_stale": global_stale,
    }


def _load_cached_symbols_with_debug():
    cached_symbols = load_cached_stock_data() or {}
    return cached_symbols, (get_last_load_debug() or {})


def _reload_cached_symbol_frames(symbols):
    reloaded = {}
    for symbol in symbols or []:
        data = load_cached_stock_data(symbol)
        if data is not None and not getattr(data, "empty", False):
            reloaded[str(symbol)] = data
    return reloaded


def _market_mode_stale_symbols(cached_symbols, now_ist):
    today_ist = now_ist.date()
    stale = []
    latest_candle_dt = None
    for symbol, data in (cached_symbols or {}).items():
        candle_dt = _last_candle_timestamp(data)
        latest_candle_dt = _latest_timestamp(latest_candle_dt, candle_dt)
        if candle_dt is None or candle_dt.date() < today_ist:
            stale.append(str(symbol))
    latest_candle_age_minutes = _candle_age_minutes(latest_candle_dt, now_ist)
    return stale, latest_candle_dt, latest_candle_age_minutes


def _refresh_ohlc_for_market_scan(cached_symbols, load_debug, market_mode):
    diagnostics = {
        "attempted": False,
        "reason": None,
        "status": "NOT_REQUIRED",
        "refresh_status_path": str(OHLC_REFRESH_STATUS_PATH).replace("\\", "/"),
        "before_stale_cache_count": int((load_debug or {}).get("stale_cache_count") or 0),
        "before_market_stale_symbol_count": 0,
        "before_latest_candle_timestamp": None,
        "before_latest_candle_age_minutes": None,
        "after_stale_cache_count": None,
        "after_market_stale_symbol_count": None,
        "after_latest_candle_timestamp": None,
        "after_latest_candle_age_minutes": None,
        "refresh_result_status": None,
        "refreshed_count": None,
        "failed_count": None,
        "skipped_count": None,
        "error": None,
        "fake_trend_forced": False,
    }
    if not market_mode:
        diagnostics["status"] = "SKIPPED_NOT_MARKET_MODE"
        return cached_symbols, load_debug, diagnostics

    before_stale, before_latest_dt, before_age = _market_mode_stale_symbols(
        cached_symbols,
        datetime.now(IST),
    )
    diagnostics.update(
        {
            "before_market_stale_symbol_count": len(before_stale),
            "before_latest_candle_timestamp": before_latest_dt.isoformat() if before_latest_dt else None,
            "before_latest_candle_age_minutes": before_age,
        }
    )

    refresh_required = bool(
        diagnostics["before_stale_cache_count"] > 0
        or before_stale
        or before_latest_dt is None
        or (before_age is not None and before_age > MARKET_CANDLE_STALE_MINUTES)
    )
    if not refresh_required:
        diagnostics["status"] = "FRESH"
        return cached_symbols, load_debug, diagnostics

    diagnostics["attempted"] = True
    diagnostics["reason"] = "MARKET_MODE_STALE_OHLC_REFRESH_REQUIRED"
    try:
        from runtime_ohlc_refresh import run_ohlc_refresh

        refresh_result = run_ohlc_refresh()
        diagnostics["refresh_result_status"] = refresh_result.get("status") if isinstance(refresh_result, dict) else None
        diagnostics["refreshed_count"] = refresh_result.get("refreshed_count") if isinstance(refresh_result, dict) else None
        diagnostics["failed_count"] = refresh_result.get("failed_count") if isinstance(refresh_result, dict) else None
        diagnostics["skipped_count"] = refresh_result.get("skipped_count") if isinstance(refresh_result, dict) else None
        same_symbols = list((cached_symbols or {}).keys())
        cached_symbols = _reload_cached_symbol_frames(same_symbols)
        after_stale, after_latest_dt, after_age = _market_mode_stale_symbols(
            cached_symbols,
            datetime.now(IST),
        )
        diagnostics.update(
            {
                "after_stale_cache_count": int((load_debug or {}).get("stale_cache_count") or 0),
                "after_market_stale_symbol_count": len(after_stale),
                "after_latest_candle_timestamp": after_latest_dt.isoformat() if after_latest_dt else None,
                "after_latest_candle_age_minutes": after_age,
                "status": "REFRESHED_RELOADED" if not after_stale else "REFRESH_ATTEMPTED_STALE_REMAINS",
            }
        )
    except Exception as exc:
        diagnostics["status"] = "REFRESH_FAILED_USING_EXISTING_CACHE"
        diagnostics["error"] = f"{type(exc).__name__}:{exc}"
    return cached_symbols, load_debug, diagnostics


def _status_payload(
    *,
    mode,
    stocks_checked,
    trend_passed,
    strict_trend_passed,
    adaptive_trend_passed,
    structure_passed,
    momentum_passed,
    raw_breakout_ready_count,
    breakout_ready_count,
    breakout_integrity_payload,
    passed_setups,
    candidate_symbols,
    candidate_details,
    errors,
    latest_candle_timestamp,
    latest_candle_age_minutes,
    data_signature,
    repeated_data_signature,
    repeated_data_warning,
    stale_symbol_count,
    stale_symbols,
    stale_data_warning,
    ohlc_fallback_required,
    partial_stale_tolerated,
    stale_symbol_ratio,
    stale_policy,
    scanner_cycle_id,
    scan_started_at_ist,
    scan_finished_at_ist,
    scan_duration_seconds,
    scan_only,
    entry_stage_available,
    entry_passed,
    final_passed,
    final_passed_note,
    fallback_reason,
    fallback_components,
    pipeline_health,
    final_count_source,
    ohlc_refresh_diagnostics,
    degraded_but_operational=False,
    advisory_reason=None,
    advisory_components=None,
    run_count=None,
):
    status = "FULL_RUNTIME_PIPELINE_COMPLETE"
    if ohlc_fallback_required:
        status = "SCAN_ONLY_STALE_OHLC"
    elif scan_only:
        status = "SCAN_ONLY_FALLBACK"
    if isinstance(breakout_integrity_payload, dict) and not breakout_integrity_payload.get("integrity_valid", True):
        status = "BREAKOUT_PIPELINE_INTEGRITY_ERROR"

    if ohlc_fallback_required:
        dashboard_status_message = "True stale OHLC fallback active"
    elif partial_stale_tolerated:
        dashboard_status_message = "Partial stale symbols tolerated; warning only"
    elif final_passed is None:
        dashboard_status_message = "Final count unavailable from current runtime output"
    elif scan_only:
        dashboard_status_message = "Scanner-only fallback active"
    elif final_passed == 0:
        dashboard_status_message = "No setups found"
    else:
        dashboard_status_message = "Full runtime pipeline active"

    missing_fields = []
    if entry_passed is None:
        missing_fields.append("entry_passed")
    if final_passed is None:
        missing_fields.append("final_passed")

    payload = {
        "timestamp_ist": scan_finished_at_ist,
        "scanner_timestamp": scan_finished_at_ist,
        "scanner_cycle_id": scanner_cycle_id,
        "scan_started_at_ist": scan_started_at_ist,
        "scan_finished_at_ist": scan_finished_at_ist,
        "scan_duration_seconds": scan_duration_seconds,
        "mode": mode,
        "status": status,
        "source": "VPS_RUNTIME_SCANNER",
        "scan_only": scan_only,
        "fallback_reason": fallback_reason,
        "fallback_components": fallback_components,
        "advisory_reason": advisory_reason,
        "advisory_components": advisory_components or [],
        "degraded_but_operational": bool(degraded_but_operational),
        "pipeline_health": pipeline_health,
        "ohlc_refresh_diagnostics": ohlc_refresh_diagnostics,
        "partial_stale_tolerated": partial_stale_tolerated,
        "stale_symbol_ratio": stale_symbol_ratio,
        "stale_policy": stale_policy,
        "final_count_source": final_count_source,
        "dashboard_status_message": dashboard_status_message,
        "real_scanner_called": True,
        "trade_creation": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": False,
        "stocks_checked": stocks_checked,
        "trend_passed": trend_passed,
        "trend_passed_count": trend_passed,
        "strict_trend_passed": strict_trend_passed,
        "adaptive_trend_passed": adaptive_trend_passed,
        "momentum_passed": momentum_passed,
        "momentum_passed_count": momentum_passed,
        "structure_passed": structure_passed,
        "structure_passed_count": structure_passed,
        "entry_passed": entry_passed,
        "entry_passed_count": entry_passed,
        "entry_stage_available": entry_stage_available,
        "entry_passed_note": (
            "Full setup engine entry count unavailable."
            if entry_passed is None and not scan_only
            else (
                "No independent entry-stage engine runs in scanner-only mode; use breakout_ready_count for this scanner gate."
                if scan_only
                else None
            )
        ),
        "final_passed": final_passed,
        "final_passed_count": final_passed,
        "final_passed_note": (
            final_passed_note
            or (
                "Final count unavailable from current runtime output."
                if final_passed is None
                else None
            )
        ),
        "alerts_sent": 0,
        "alerts_this_scan": 0,
        "raw_breakout_ready": raw_breakout_ready_count,
        "raw_breakout_ready_count": raw_breakout_ready_count,
        "qualified_breakout_ready": breakout_ready_count,
        "qualified_breakout_ready_count": breakout_ready_count,
        "breakout_ready": breakout_ready_count,
        "breakout_ready_count": breakout_ready_count,
        "breakout_pipeline_integrity": {
            "status_path": "data/runtime/breakout_pipeline_integrity.json",
            "integrity_valid": bool((breakout_integrity_payload or {}).get("integrity_valid", False)),
            "integrity_errors": (breakout_integrity_payload or {}).get("integrity_errors") or [],
            "violating_symbols": (breakout_integrity_payload or {}).get("violating_symbols") or [],
        },
        "selected_symbols_count": stocks_checked,
        "counter_confidence": "LOW" if scan_only or final_passed is None else "HIGH",
        "counter_source": "runtime_scanner_independent_stage_counters",
        "counter_sources": {
            "stocks_checked": "runtime_scanner.loop.stocks_checked",
            "trend_passed": "runtime_scanner.loop.trend_direction",
            "momentum_passed": "runtime_scanner.loop.strong_momentum",
            "structure_passed": "runtime_scanner.loop.structure_ok",
            "breakout_ready": "runtime_scanner.loop.breakout_ready",
            "final_passed": final_count_source,
            "alerts_this_scan": "runtime_scanner.alerts_disabled_readonly_status",
        },
        "passed_setups": passed_setups,
        "missing_fields": missing_fields,
        "candidate_symbols": candidate_symbols[:5],
        "candidate_details": candidate_details[:5],
        "latest_candle_timestamp": latest_candle_timestamp,
        "latest_market_candle": latest_candle_timestamp,
        "latest_candle_age_minutes": latest_candle_age_minutes,
        "data_signature": data_signature,
        "repeated_data_signature": repeated_data_signature,
        "repeated_data_warning": repeated_data_warning,
        "fresh_symbol_count": max(int(stocks_checked or 0) - int(stale_symbol_count or 0), 0),
        "stale_symbol_count": stale_symbol_count,
        "stale_symbols": stale_symbols[:20],
        "stale_data_warning": stale_data_warning,
        "ohlc_fallback_required": ohlc_fallback_required,
        "scanner_data_health": {
            "stocks_checked": stocks_checked,
            "fresh_symbol_count": max(int(stocks_checked or 0) - int(stale_symbol_count or 0), 0),
            "stale_symbol_count": stale_symbol_count,
            "latest_market_candle": latest_candle_timestamp,
            "latest_candle_age_minutes": latest_candle_age_minutes,
            "stale_policy": stale_policy,
            "refresh_attempted": bool((ohlc_refresh_diagnostics or {}).get("attempted")),
            "refresh_status": (ohlc_refresh_diagnostics or {}).get("status"),
            "degraded_but_operational": bool(degraded_but_operational),
        },
        "errors": errors,
    }
    if run_count is not None:
        payload["run_count"] = run_count
    return payload


def _full_pipeline_health(ohlc_fallback_required, partial_stale_tolerated, stale_symbol_ratio, stale_policy):
    master_state = _task_availability_state("master_brain", MASTER_BRAIN_STATUS_PATH)
    setup_state = _task_availability_state("setup_engine", SETUP_ENGINE_STATUS_PATH)
    master_payload = master_state["payload"]
    setup_payload = setup_state["payload"]
    master_ok = master_state["ok"]
    setup_ok = setup_state["ok"]

    final_debug = _read_json(FINAL_REJECTION_DEBUG_PATH)
    final_count = _resolve_final_count(master_payload, setup_payload, final_debug)

    fallback_reasons = []
    advisory_reasons = []
    if ohlc_fallback_required:
        fallback_reasons.append("OHLC_STALE")
    if master_state["truly_unavailable"] and not final_count["available"]:
        fallback_reasons.append("MASTER_BRAIN_UNAVAILABLE")
    elif not master_ok:
        advisory_reasons.append("MASTER_BRAIN_STALE_ADVISORY")
    if setup_state["truly_unavailable"] and not final_count["available"]:
        fallback_reasons.append("SETUP_ENGINE_UNAVAILABLE")
    elif not setup_ok:
        advisory_reasons.append("SETUP_ENGINE_STALE_ADVISORY")

    scan_only = bool(fallback_reasons)
    return {
        "scan_only": scan_only,
        "fallback_reason": "|".join(fallback_reasons) if fallback_reasons else None,
        "fallback_components": fallback_reasons,
        "advisory_reason": "|".join(advisory_reasons) if advisory_reasons else None,
        "advisory_components": advisory_reasons,
        "degraded_but_operational": bool(partial_stale_tolerated or advisory_reasons),
        "pipeline_health": {
            "scanner_ok": True,
            "master_brain_ok": master_ok,
            "setup_engine_ok": setup_ok,
            "master_brain_truly_unavailable": master_state["truly_unavailable"],
            "setup_engine_truly_unavailable": setup_state["truly_unavailable"],
            "master_brain_advisory_stale": master_state["advisory_stale"],
            "setup_engine_advisory_stale": setup_state["advisory_stale"],
            "ohlc_refresh_ok": not ohlc_fallback_required,
            "ohlc_stale": ohlc_fallback_required,
            "partial_stale_tolerated": partial_stale_tolerated,
            "stale_symbol_ratio": stale_symbol_ratio,
            "stale_policy": stale_policy,
            "final_counts_available": final_count["available"],
            "final_count_timestamp": final_count["timestamp"],
        },
        "entry_passed": final_count["entry_passed"],
        "final_passed": final_count["final_passed"],
        "final_passed_note": final_count["final_passed_note"],
        "final_count_source": final_count["final_count_source"],
        "entry_stage_available": final_count["entry_stage_available"],
        "master_status": master_payload.get("status"),
        "setup_status": setup_payload.get("status"),
        "master_brain_state": {k: v for k, v in master_state.items() if k != "payload"},
        "setup_engine_state": {k: v for k, v in setup_state.items() if k != "payload"},
        "final_debug": final_debug,
    }


def _market_filter_diagnostics(pipeline, stale_policy_result):
    health = pipeline.get("pipeline_health") if isinstance(pipeline, dict) else {}
    final_debug = pipeline.get("final_debug") if isinstance(pipeline, dict) else {}
    return {
        "market_regime": final_debug.get("market_status") if isinstance(final_debug, dict) else None,
        "volatility_filter": {
            "ohlc_stale": bool(health.get("ohlc_stale")),
            "stale_policy": stale_policy_result.get("stale_policy"),
            "stale_symbol_ratio": stale_policy_result.get("stale_symbol_ratio"),
            "partial_stale_tolerated": stale_policy_result.get("partial_stale_tolerated"),
        },
        "news_filter": None,
        "risk_filter": None,
        "runtime_filters": {
            "scan_only": bool(pipeline.get("scan_only")),
            "fallback_reason": pipeline.get("fallback_reason"),
            "advisory_reason": pipeline.get("advisory_reason"),
            "degraded_but_operational": bool(pipeline.get("degraded_but_operational")),
            "master_brain_ok": bool(health.get("master_brain_ok")),
            "setup_engine_ok": bool(health.get("setup_engine_ok")),
        },
    }


def _setup_engine_rejections_from_debug(final_debug, entry_passed, final_passed):
    if not isinstance(final_debug, dict) or not _payload_fresh(final_debug):
        return Counter(), {}, None

    reasons = Counter()
    for reason, count in (final_debug.get("breakdown") or {}).items():
        try:
            reasons[str(reason)] += int(count)
        except Exception:
            continue

    examples = {}
    symbols_by_reason = final_debug.get("symbols_by_reason") or {}
    if isinstance(symbols_by_reason, dict):
        for reason, symbols in symbols_by_reason.items():
            if isinstance(symbols, list):
                examples[str(reason)] = [str(symbol) for symbol in symbols[:8]]

    rejected = final_debug.get("total_final_rejections_after_entry")
    if rejected is None and final_passed is not None and entry_passed is not None:
        rejected = max(int(entry_passed) - int(final_passed), 0)
    return reasons, examples, rejected


def _regime_diagnostics():
    try:
        status = market_regime_status()
    except Exception as exc:
        status = {
            "market_ok": True,
            "reason": f"regime diagnostics unavailable: {exc}",
            "regime": "UNKNOWN",
            "status": "UNKNOWN",
        }

    if not isinstance(status, dict):
        status = {"market_ok": True, "regime": str(status or "UNKNOWN")}

    current_regime = (
        status.get("regime")
        or status.get("status")
        or status.get("direction")
        or "UNKNOWN"
    )
    blocked = "market_ok" in status and not bool(status.get("market_ok"))
    return {
        "current_regime": current_regime,
        "allowed_regimes": "fail-open market_regime_status",
        "rejected_regimes": [current_regime] if blocked else [],
        "candidates_blocked_by_regime_mismatch": 0,
        "market_status": status,
    }


def _publish_scanner_outputs(path, payload, data_signature, scanner_cycle_id, scan_finished_at_ist):
    publish_errors = []
    scanner_status_published = False
    scanner_truth_published = False

    try:
        _atomic_write_json(path, payload)
        scanner_status_published = True
    except Exception as exc:
        publish_errors.append(f"scanner_status:{type(exc).__name__}:{exc}")

    if scanner_status_published:
        try:
            from scanner_filter_truth import build_scanner_filter_truth_status

            build_scanner_filter_truth_status(
                scanner_status_path=path,
                output_path=SCANNER_FILTER_TRUTH_STATUS_PATH,
            )
            scanner_truth_published = True
        except Exception as exc:
            publish_errors.append(f"scanner_filter_truth:{type(exc).__name__}:{exc}")

    if scanner_status_published:
        try:
            _write_previous_data_signature(data_signature, scanner_cycle_id, scan_finished_at_ist)
        except Exception as exc:
            publish_errors.append(f"previous_signature:{type(exc).__name__}:{exc}")

    if publish_errors:
        status = "PARTIAL" if scanner_status_published else "FAILED"
        _write_scanner_heartbeat(
            latest_cycle=scanner_cycle_id,
            publish_status=status,
            scanner_runtime_mode=payload.get("mode"),
            scanner_loop_health="DEGRADED" if scanner_status_published else "PUBLISH_FAILED",
            last_publish_exception="|".join(publish_errors),
        )
        payload["publish_status"] = status
        payload["publish_errors"] = publish_errors
        payload["scanner_status_published"] = scanner_status_published
        payload["scanner_truth_published"] = scanner_truth_published
        return payload

    _write_scanner_heartbeat(
        latest_cycle=scanner_cycle_id,
        publish_status="PUBLISHED",
        scanner_runtime_mode=payload.get("mode"),
        scanner_loop_health="ACTIVE",
    )
    payload["publish_status"] = "PUBLISHED"
    payload["scanner_status_published"] = True
    payload["scanner_truth_published"] = True
    return payload


def run_scanner(path=SCANNER_STATUS_PATH):
    path = Path(path)
    started_monotonic = time.monotonic()
    scan_started_at_ist = _timestamp_ist()
    scanner_cycle_id = f"{scan_started_at_ist}-{uuid4()}"
    _write_scanner_heartbeat(
        latest_cycle=scanner_cycle_id,
        publish_status="STARTED",
        scanner_runtime_mode="SCANNING",
        scanner_loop_health="RUNNING",
    )
    previous_run_count = _read_previous_run_count(path)
    run_count = previous_run_count + 1 if previous_run_count is not None else None
    previous_data_signature = _read_previous_data_signature()

    stocks_checked = 0
    trend_passed = 0
    strict_trend_passed = 0
    adaptive_trend_passed = 0
    structure_passed = 0
    momentum_passed = 0
    breakout_ready_count = 0
    passed_setups = 0
    candidate_symbols = []
    candidate_details = []
    errors = 0
    mode = "SCAN_ONLY"
    bot_mode = current_bot_mode(datetime.now(IST))
    market_mode = bot_mode == "MARKET_MODE"
    today_ist = datetime.now(IST).date()
    latest_candle_dt = None
    stale_symbols = []
    signature_rows = []
    load_debug = {}
    ohlc_refresh_diagnostics = {}
    trend_reasons = Counter()
    structure_reasons = Counter()
    momentum_reasons = Counter()
    entry_reasons = Counter()
    trend_examples = {}
    structure_examples = {}
    momentum_examples = {}
    entry_examples = {}
    trend_diagnostic_symbols = []
    filter_symbol_diagnostics = []
    momentum_breakout_audit_records = []
    final_validated_setups = []
    regime_diagnostics = _regime_diagnostics()
    live_price_cache = _read_json(LIVE_PRICE_CACHE_PATH)
    selector_payload = _write_runtime_selector_status(
        selector_used=SAFE_SCANNER_PATH,
        fallback_active=False,
        fallback_reason=None,
        symbols=[],
        selection_source="runtime_scanner.starting",
        truth_gate_status="UNKNOWN",
    )

    try:
        cached_symbols, load_debug, selector_payload = _load_runtime_symbols_with_selector()
        cached_symbols, load_debug, ohlc_refresh_diagnostics = _refresh_ohlc_for_market_scan(
            cached_symbols,
            load_debug,
            market_mode,
        )
    except Exception:
        cached_symbols = {}
        errors += 1
        ohlc_refresh_diagnostics = {
            "status": "LOAD_OR_REFRESH_EXCEPTION",
            "attempted": False,
            "fake_trend_forced": False,
        }

    ohlc_market_status = None
    if load_debug.get("ohlc_health_status") == "FAIL":
        ohlc_market_status = {
            "status": "FAIL",
            "ok": False,
            "reason": load_debug.get("ohlc_health_reason") or "OHLC_CACHE_INVALID",
            "stale_data_detected": True,
            "unsafe_sources_detected": [],
        }
    elif load_debug.get("ohlc_health_status") == "DEGRADED":
        ohlc_market_status = {
            "status": "DEGRADED",
            "ok": False,
            "reason": load_debug.get("ohlc_health_reason") or "BELOW_IDEAL_HISTORY_ROWS",
            "stale_data_detected": False,
            "unsafe_sources_detected": [],
        }
    truth_gate_payload = scanner_gate_status(
        runtime_path=selector_payload.get("selector_used") or UNSAFE_SCANNER_PATH,
        market_status=ohlc_market_status,
    )
    truth_gate_blocked = truth_gate_payload.get("overall_status") == "FAIL"
    selector_payload = _write_runtime_selector_status(
        selector_used=selector_payload.get("selector_used") or UNSAFE_SCANNER_PATH,
        fallback_active=selector_payload.get("fallback_active"),
        fallback_reason=selector_payload.get("fallback_reason"),
        symbols=selector_payload.get("symbols") or list((cached_symbols or {}).keys()),
        selection_source=selector_payload.get("selection_source") or "UNKNOWN",
        truth_gate_status=truth_gate_payload.get("overall_status") or "UNKNOWN",
    )
    if truth_gate_blocked:
        print(f"[TruthGate] Scanner real setup generation blocked: {truth_gate_payload.get('blocked_reason')}")

    for symbol, data in cached_symbols.items():
        stocks_checked += 1
        symbol_filter_diagnostic = _symbol_filter_diagnostics(symbol, data)
        filter_symbol_diagnostics.append(symbol_filter_diagnostic)
        momentum_breakout_audit_record = _momentum_breakout_audit_record(symbol, symbol_filter_diagnostic)
        momentum_breakout_audit_records.append(momentum_breakout_audit_record)
        candle_dt = _last_candle_timestamp(data)
        latest_candle_dt = _latest_timestamp(latest_candle_dt, candle_dt)
        signature_rows.append(
            {
                "symbol": str(symbol),
                "latest_candle_timestamp": candle_dt.isoformat() if candle_dt else None,
                "close": _last_close(data),
            }
        )
        if market_mode and (candle_dt is None or candle_dt.date() < today_ist):
            stale_symbols.append(symbol)

        try:
            trend = trend_direction(data)
            trend_diagnostic = apply_adaptive_trend(
                explain_trend(symbol, data, trend),
                regime_diagnostics,
            )
            close = _last_close(data)
            candle_age = _candle_age_minutes(candle_dt, datetime.now(IST))
            data_stale = bool(market_mode and (candle_dt is None or candle_dt.date() < today_ist))
            trend_diagnostic.update(
                {
                    "latest_candle_timestamp": candle_dt.isoformat() if candle_dt else None,
                    "latest_candle_age_minutes": candle_age,
                    "data_stale": data_stale,
                    "stale_reason": (
                        "missing_latest_candle_timestamp"
                        if market_mode and candle_dt is None
                        else (
                            "latest_candle_before_today"
                            if data_stale
                            else None
                        )
                    ),
                    "live_price_check": _live_price_check(live_price_cache, symbol, close),
                }
            )
            trend_diagnostic_symbols.append(trend_diagnostic)
            strict_side = _side_from_trend(trend)
            side = strict_side
            if side is None and trend_diagnostic.get("adaptive_accepted"):
                side = trend_diagnostic.get("adaptive_side")
            if side is None:
                reason = str(trend or "NO_VALID_TREND")
                trend_reasons[reason] += 1
                add_example(trend_examples, reason, symbol)
                momentum_breakout_audit_record["pipeline_stop_reason"] = f"TREND:{reason}"
                continue
            trend_passed += 1
            if strict_side is None:
                adaptive_trend_passed += 1
            else:
                strict_trend_passed += 1

            if not structure_ok(data, side=side):
                structure_reasons["STRUCTURE_FAIL"] += 1
                add_example(structure_examples, "STRUCTURE_FAIL", symbol)
                momentum_breakout_audit_record["pipeline_stop_reason"] = "STRUCTURE_FAIL"
                continue
            structure_passed += 1

            if not strong_momentum(data, side=side):
                momentum_reasons["MOMENTUM_FAIL"] += 1
                add_example(momentum_examples, "MOMENTUM_FAIL", symbol)
                momentum_breakout_audit_record["pipeline_stop_reason"] = "MOMENTUM_FAIL"
                continue
            momentum_passed += 1
            momentum_breakout_audit_record["counted_momentum_passed"] = True

            if not breakout_ready(data, side=side):
                entry_reasons["NOT_READY"] += 1
                add_example(entry_examples, "NOT_READY", symbol)
                momentum_breakout_audit_record["pipeline_stop_reason"] = "NOT_READY"
                continue
            breakout_ready_count += 1
            momentum_breakout_audit_record["counted_breakout_ready"] = True
            momentum_breakout_audit_record["pipeline_stop_reason"] = "PASSED_BREAKOUT_READY"

            final_setup = _build_final_validated_setup(
                symbol,
                data,
                side,
                symbol_filter_diagnostic,
                scanner_cycle_id,
                truth_gate_payload,
                selector_payload,
            )
            if (final_setup.get("contract_validation") or {}).get("status") != "PASS":
                entry_reasons[f"CONTRACT_INVALID:{(final_setup.get('contract_validation') or {}).get('reason')}"] += 1
                momentum_breakout_audit_record["pipeline_stop_reason"] = (
                    f"CONTRACT_INVALID:{(final_setup.get('contract_validation') or {}).get('reason')}"
                )
                continue

            final_validated_setups.append(final_setup)
            passed_setups = len(final_validated_setups)
            if len(candidate_symbols) < 5:
                candidate_symbols.append(symbol)
            if len(candidate_details) < 5:
                last_ohlc = _last_ohlc(data)
                if last_ohlc is not None:
                    candidate_details.append(
                        {
                            "symbol": symbol,
                            "side": side,
                            "last_ohlc": last_ohlc,
                        }
                    )

        except Exception:
            errors += 1
            if "momentum_breakout_audit_record" in locals():
                momentum_breakout_audit_record["pipeline_stop_reason"] = "SCANNER_EXCEPTION"
            continue

    final_validated_payload = _write_final_validated_setups(
        final_validated_setups,
        scanner_cycle_id,
        reason=None if final_validated_setups else "NO_VALIDATED_FINAL_SETUPS",
    )
    filter_diagnostics_payload = _write_filter_diagnostics(
        filter_symbol_diagnostics,
        scanner_cycle_id,
        final_validated_setups=final_validated_setups,
    )
    _print_filter_diagnostics_summary(filter_diagnostics_payload)
    paper_journal_payload = maybe_write_paper_journal(
        truth_gate_payload=truth_gate_payload,
        selector_payload=selector_payload,
        ohlc_status=load_debug.get("ohlc_health_status"),
        scan_id=scanner_cycle_id,
        within_trading_window=is_trade_window(),
        refresh_contract=True,
    )
    print(
        "[PaperJournal] "
        f"enabled={paper_journal_payload.get('enabled')} "
        f"status={paper_journal_payload.get('last_write_status')} "
        f"written={paper_journal_payload.get('written')} "
        f"duplicates={paper_journal_payload.get('duplicate_skipped')}"
    )

    scan_finished_at_ist = _timestamp_ist()
    finished_dt = datetime.now(IST)
    scan_duration_seconds = round(time.monotonic() - started_monotonic, 3)
    stale_symbol_count = len(stale_symbols)
    latest_candle_age_minutes = _candle_age_minutes(latest_candle_dt, finished_dt)
    stale_policy_result = _stale_policy(
        stale_symbol_count,
        stocks_checked,
        latest_candle_age_minutes,
        market_mode,
    )
    stale_data_warning = bool(
        market_mode
        and (
            stale_symbol_count > 0
            or stale_policy_result["fallback_required"]
        )
    )
    pipeline = _full_pipeline_health(
        stale_policy_result["fallback_required"],
        stale_policy_result["partial_stale_tolerated"],
        stale_policy_result["stale_symbol_ratio"],
        stale_policy_result["stale_policy"],
    )
    scan_only = pipeline["scan_only"]
    mode = _scan_mode(load_debug, scan_only)
    data_signature = _data_signature(signature_rows)
    repeated_data_signature = bool(previous_data_signature and previous_data_signature == data_signature)
    repeated_data_warning = (
        "Scanner input data unchanged from previous cycle"
        if repeated_data_signature
        else None
    )
    for item in trend_diagnostic_symbols:
        item["repeated_data_signature"] = repeated_data_signature
        if repeated_data_warning:
            item["stale_reason"] = item.get("stale_reason") or repeated_data_warning
    momentum_breakout_audit_payload = _write_momentum_breakout_counter_audit(
        momentum_breakout_audit_records,
        scanner_cycle_id=scanner_cycle_id,
        timestamp_ist=scan_finished_at_ist,
        momentum_passed_count=momentum_passed,
        breakout_ready_count=breakout_ready_count,
        data_signature=data_signature,
    )
    breakout_integrity_payload = _write_breakout_pipeline_integrity(
        momentum_breakout_audit_records,
        scanner_cycle_id=scanner_cycle_id,
        timestamp_ist=scan_finished_at_ist,
        raw_breakout_ready_count=momentum_breakout_audit_payload.get("raw_breakout_ready_count"),
        qualified_breakout_ready_count=momentum_breakout_audit_payload.get("qualified_breakout_ready_count"),
    )
    payload = _status_payload(
        mode=mode,
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        strict_trend_passed=strict_trend_passed,
        adaptive_trend_passed=adaptive_trend_passed,
        structure_passed=structure_passed,
        momentum_passed=momentum_passed,
        raw_breakout_ready_count=momentum_breakout_audit_payload.get("raw_breakout_ready_count"),
        breakout_ready_count=breakout_ready_count,
        breakout_integrity_payload=breakout_integrity_payload,
        passed_setups=passed_setups,
        candidate_symbols=candidate_symbols,
        candidate_details=candidate_details,
        errors=errors,
        latest_candle_timestamp=latest_candle_dt.isoformat() if latest_candle_dt else None,
        latest_candle_age_minutes=latest_candle_age_minutes,
        data_signature=data_signature,
        repeated_data_signature=repeated_data_signature,
        repeated_data_warning=repeated_data_warning,
        stale_symbol_count=stale_symbol_count,
        stale_symbols=stale_symbols,
        stale_data_warning=stale_data_warning,
        ohlc_fallback_required=stale_policy_result["fallback_required"],
        partial_stale_tolerated=stale_policy_result["partial_stale_tolerated"],
        stale_symbol_ratio=stale_policy_result["stale_symbol_ratio"],
        stale_policy=stale_policy_result["stale_policy"],
        scanner_cycle_id=scanner_cycle_id,
        scan_started_at_ist=scan_started_at_ist,
        scan_finished_at_ist=scan_finished_at_ist,
        scan_duration_seconds=scan_duration_seconds,
        scan_only=scan_only,
        entry_stage_available=pipeline["entry_stage_available"],
        entry_passed=pipeline["entry_passed"],
        final_passed=pipeline["final_passed"],
        final_passed_note=pipeline["final_passed_note"],
        fallback_reason=pipeline["fallback_reason"],
        fallback_components=pipeline["fallback_components"],
        pipeline_health=pipeline["pipeline_health"],
        final_count_source=pipeline["final_count_source"],
        ohlc_refresh_diagnostics=ohlc_refresh_diagnostics,
        degraded_but_operational=pipeline["degraded_but_operational"],
        advisory_reason=pipeline["advisory_reason"],
        advisory_components=pipeline["advisory_components"],
        run_count=run_count,
    )
    payload["truth_gate"] = {
        "overall_status": truth_gate_payload.get("overall_status"),
        "blocked_reason": truth_gate_payload.get("blocked_reason"),
        "runtime_path": selector_payload.get("selector_used") or UNSAFE_SCANNER_PATH,
        "real_setup_generation_allowed": not truth_gate_blocked,
        "status_path": "data/runtime/truth_gate_status.json",
    }
    payload["runtime_selector"] = {
        "selector_used": selector_payload.get("selector_used"),
        "fallback_active": selector_payload.get("fallback_active"),
        "fallback_reason": selector_payload.get("fallback_reason"),
        "selected_count": selector_payload.get("selected_count"),
        "status_path": "data/runtime/runtime_selector_status.json",
    }
    payload["momentum_breakout_counter_audit"] = {
        "status_path": "data/runtime/momentum_breakout_counter_audit.json",
        "momentum_passed_count": momentum_breakout_audit_payload.get("momentum_passed_count"),
        "raw_breakout_ready_count": momentum_breakout_audit_payload.get("raw_breakout_ready_count"),
        "qualified_breakout_ready_count": momentum_breakout_audit_payload.get("qualified_breakout_ready_count"),
        "breakout_ready_count": momentum_breakout_audit_payload.get("breakout_ready_count"),
        "overlap_count": momentum_breakout_audit_payload.get("overlap_count"),
        "raw_breakout_only_count": momentum_breakout_audit_payload.get("raw_breakout_only_count"),
        "qualified_breakout_only_count": momentum_breakout_audit_payload.get("qualified_breakout_only_count"),
        "neither_count": momentum_breakout_audit_payload.get("neither_count"),
        "suspicious_identical_reason": momentum_breakout_audit_payload.get("suspicious_identical_reason"),
    }
    payload["final_validated_setups"] = {
        "validated_setup_count": final_validated_payload.get("validated_setup_count"),
        "status_path": "data/runtime/final_validated_setups.json",
        "symbols": [item.get("symbol") for item in final_validated_payload.get("setups") or []],
    }
    payload["paper_journal"] = {
        "enabled": paper_journal_payload.get("enabled"),
        "last_write_status": paper_journal_payload.get("last_write_status"),
        "attempted": paper_journal_payload.get("attempted"),
        "written": paper_journal_payload.get("written"),
        "duplicate_skipped": paper_journal_payload.get("duplicate_skipped"),
        "failed": paper_journal_payload.get("failed"),
        "destination": paper_journal_payload.get("destination"),
        "broker_execution_disabled": True,
        "telegram_sent": False,
        "status_path": "data/runtime/paper_journal_status.json",
    }
    try:
        from learning_evolution_truth import refresh_learning_evolution_truth

        learning_truth = refresh_learning_evolution_truth(write_files=True)
        payload["learning_evolution_truth"] = {
            "status": "UPDATED",
            "evolution_memory_path": "data/runtime/evolution_memory.json",
            "closed_outcome_count": learning_truth.get("closed_outcome_count"),
            "learning_confidence": learning_truth.get("learning_confidence"),
            "top_performing_setup_type": (learning_truth.get("top_performing_setup_type") or {}).get("name"),
            "weakest_setup_type": (learning_truth.get("weakest_setup_type") or {}).get("name"),
            "evolution_changes_today": (learning_truth.get("strategy_weight_change_log") or {}).get("changes_today"),
        }
    except Exception as exc:
        payload["learning_evolution_truth"] = {
            "status": "ERROR",
            "error": f"{type(exc).__name__}:{exc}",
            "evolution_memory_path": "data/runtime/evolution_memory.json",
        }

    setup_reasons, setup_examples, setup_rejected = _setup_engine_rejections_from_debug(
        pipeline.get("final_debug"),
        pipeline.get("entry_passed"),
        pipeline.get("final_passed"),
    )
    diagnostics_final_passed = None if scan_only else pipeline["final_passed"]
    diagnostics_report = build_scan_report(
        scan_cycle_id=scanner_cycle_id,
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        momentum_passed=momentum_passed,
        structure_passed=structure_passed,
        entry_passed=breakout_ready_count,
        final_passed=diagnostics_final_passed,
        alerts_sent=0,
        trend_reasons=trend_reasons,
        trend_examples=trend_examples,
        momentum_reasons=momentum_reasons,
        momentum_examples=momentum_examples,
        structure_reasons=structure_reasons,
        structure_examples=structure_examples,
        entry_reasons=entry_reasons,
        entry_examples=entry_examples,
        setup_reasons=setup_reasons,
        setup_examples=setup_examples,
        setup_received=0 if scan_only else breakout_ready_count,
        setup_rejected=0 if scan_only else setup_rejected,
        market_filters=_market_filter_diagnostics(pipeline, stale_policy_result),
        breakout_ready=breakout_ready_count,
    )
    save_scan_report(diagnostics_report)
    save_trend_diagnostics(
        scanner_cycle_id,
        trend_diagnostic_symbols,
        regime_diagnostics=regime_diagnostics,
    )

    return _publish_scanner_outputs(path, payload, data_signature, scanner_cycle_id, scan_finished_at_ist)


if __name__ == "__main__":
    print(json.dumps(run_scanner(), indent=2, sort_keys=True))
