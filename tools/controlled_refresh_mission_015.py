import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.market_hours import IST, as_ist_datetime


RUNTIME_DIR = Path("data") / "runtime"
LOCK_DIR = RUNTIME_DIR / "locks"
MISSION_DIAGNOSTIC_PATH = RUNTIME_DIR / "controlled_refresh_mission_015.json"
SETUP_ENGINE_STATUS_PATH = RUNTIME_DIR / "setup_engine_status.json"

APPROVED_STALE_LOCKS = [
    LOCK_DIR / "task_heartbeat.lock",
    LOCK_DIR / "task_runtime_status.lock",
    LOCK_DIR / "titan_daemon.lock",
]


def _timestamp():
    return datetime.now(IST).isoformat()


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


def clear_approved_stale_locks():
    cleared = []
    for path in APPROVED_STALE_LOCKS:
        if path.exists():
            path.unlink()
            cleared.append(str(path).replace("\\", "/"))
    return cleared


def lock_recheck():
    from restart_readiness_gate import classify_locks

    locks = classify_locks(LOCK_DIR)
    active = [lock for lock in locks if lock.get("status") == "ACTIVE_LOCK"]
    unknown = [lock for lock in locks if lock.get("status") == "UNKNOWN_LOCK"]
    stale = [lock for lock in locks if lock.get("status") == "STALE_LOCK"]
    return {
        "active_locks": len(active),
        "unknown_locks": len(unknown),
        "stale_locks": len(stale),
        "locks": locks,
    }


def _symbols_from_ohlc_refresh(refresh_payload):
    symbols = []
    seen = set()
    for item in refresh_payload.get("symbol_results") or []:
        symbol = str((item or {}).get("symbol") or "").strip().upper().replace(".NS", "")
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols


def run_ohlc_data_only_refresh():
    from data.ohlc_health import ensure_fresh_ohlc
    from runtime_ohlc_refresh import run_ohlc_refresh

    started = time.monotonic()
    refresh_payload = run_ohlc_refresh()
    symbols = _symbols_from_ohlc_refresh(refresh_payload)
    health_payload = ensure_fresh_ohlc(symbols, max_age_hours=24) if symbols else {}
    symbol_results = health_payload.get("symbol_results") if isinstance(health_payload, dict) else []
    fresh_count = int(health_payload.get("valid_count") or 0) if isinstance(health_payload, dict) else 0
    degraded_count = sum(
        1
        for item in symbol_results or []
        if ((item.get("freshness") or {}).get("status") == "DEGRADED")
    )
    invalid_count = int(health_payload.get("invalid_count") or 0) if isinstance(health_payload, dict) else 0
    stale_count = max(degraded_count, invalid_count)
    missing_count = 0
    status = str(health_payload.get("status") or refresh_payload.get("status") or "UNKNOWN")
    return {
        "data_only": True,
        "order_api_called": False,
        "trading_api_called": False,
        "symbols_checked": len(symbols),
        "fresh_count": fresh_count,
        "stale_count": stale_count,
        "missing_count": missing_count,
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 3),
        "refresh_status": refresh_payload.get("status"),
        "ohlc_health_status": health_payload.get("status") if isinstance(health_payload, dict) else None,
        "error": refresh_payload.get("error_message"),
    }


def run_scanner_scan_only_refresh():
    import runtime_scanner

    def _journal_blocked(**_kwargs):
        return {
            "enabled": False,
            "last_write_status": "MISSION_015_SCAN_ONLY_BLOCKED",
            "attempted": 0,
            "written": 0,
            "duplicate_skipped": 0,
            "failed": 0,
            "destination": None,
            "broker_execution_disabled": True,
            "telegram_sent": False,
            "journal_mutation": False,
            "blocked_reason": "Mission 015 scan-only guard",
        }

    started = time.monotonic()
    original_journal_writer = runtime_scanner.maybe_write_paper_journal
    runtime_scanner.maybe_write_paper_journal = _journal_blocked
    try:
        payload = runtime_scanner.run_scanner()
    finally:
        runtime_scanner.maybe_write_paper_journal = original_journal_writer

    final_setups = _read_json(RUNTIME_DIR / "final_validated_setups.json")
    final_count = payload.get("final_passed")
    if final_count is None:
        final_count = final_setups.get("validated_setup_count")
    if final_count is None and isinstance(final_setups.get("setups"), list):
        final_count = len(final_setups.get("setups"))
    return {
        "scan_only": True,
        "journal_mutation": False,
        "telegram_sent": False,
        "broker_order_api_called": False,
        "symbols_scanned": int(payload.get("stocks_checked") or payload.get("symbols_scanned") or 0),
        "final_setups_count": int(final_count or 0),
        "status": payload.get("status") or payload.get("mode") or "UNKNOWN",
        "duration_seconds": round(time.monotonic() - started, 3),
        "scanner_cycle_id": payload.get("scanner_cycle_id"),
        "errors": payload.get("errors"),
        "fallback_reason": payload.get("fallback_reason"),
    }


def run_setup_diagnostic_proof(scanner_result):
    final_setups = _read_json(RUNTIME_DIR / "final_validated_setups.json")
    final_count = final_setups.get("validated_setup_count")
    if final_count is None and isinstance(final_setups.get("setups"), list):
        final_count = len(final_setups["setups"])
    scanner_called = int(scanner_result.get("symbols_scanned") or 0) > 0
    now_ist = as_ist_datetime()
    status_payload = {
        "generated_at": now_ist.isoformat(),
        "timestamp_ist": now_ist.isoformat(),
        "status": "OK" if scanner_called else "DIAGNOSTIC_SKIPPED",
        "diagnostic_only": True,
        "setup_engine_status": "DIAGNOSTIC_PROOF",
        "reason": (
            "runtime_scanner invoked real setup filter functions in scan-only mission"
            if scanner_called
            else "scanner did not scan symbols"
        ),
        "real_setup_engine_called": bool(scanner_called),
        "actual_setup_generation": bool(scanner_called),
        "active_trades_created": 0,
        "trade_creation": False,
        "journal_writes": False,
        "supabase_writes": False,
        "telegram_alerts": False,
        "broker_orders": False,
        "live_execution_enabled": False,
        "affects_execution": False,
        "affects_live_ranking": False,
        "scanner_cycle_id": scanner_result.get("scanner_cycle_id"),
        "symbols_scanned": scanner_result.get("symbols_scanned"),
        "final_setups_count": int(final_count or 0),
        "final_setups_file": "data/runtime/final_validated_setups.json",
    }
    _atomic_write_json(SETUP_ENGINE_STATUS_PATH, status_payload)
    return {
        "diagnostic_only": True,
        "active_trades_created": 0,
        "journal_mutation": False,
        "real_setup_engine_called": bool(scanner_called),
        "status": "OK" if scanner_called else "DIAGNOSTIC_SKIPPED",
        "setup_engine_status_written": "data/runtime/setup_engine_status.json",
        "final_setups_count": int(final_count or 0),
    }


def build_truth_and_gate():
    from restart_readiness_gate import build_restart_readiness_gate
    from runtime_truth import build_authoritative_runtime_truth
    from scanner_ohlc_setup_truth import build_scanner_ohlc_setup_truth

    scanner_truth = build_scanner_ohlc_setup_truth(write=True)
    runtime_truth = build_authoritative_runtime_truth(write=True)
    gate = build_restart_readiness_gate(
        runtime_truth=runtime_truth,
        scanner_truth=scanner_truth,
        write=True,
    )
    gate.setdefault("controlled_refresh_plan", {})["actual_refresh_executed"] = True
    gate["controlled_refresh_plan"]["actual_refresh_diagnostic"] = str(
        MISSION_DIAGNOSTIC_PATH
    ).replace("\\", "/")
    _atomic_write_json(RUNTIME_DIR / "restart_readiness_gate.json", gate)
    return scanner_truth, runtime_truth, gate


def run_mission():
    diagnostic = {
        "generated_at": _timestamp(),
        "mission": "015",
        "mode": "controlled_data_diagnostic_only",
        "stale_locks_cleared": [],
        "lock_recheck": {},
        "ohlc_refresh_result": {},
        "scanner_refresh_result": {},
        "setup_diagnostic_result": {},
        "scanner_ohlc_setup_truth_after": {},
        "authoritative_runtime_truth_after": {},
        "restart_readiness_gate_after": {},
        "safe_to_start_daemon": False,
        "safe_to_start_workers": False,
        "blockers": [],
        "warnings": [],
        "next_required_action": None,
        "safety": {
            "daemon_start": False,
            "worker_start": False,
            "broker_order_api_called": False,
            "trading_api_called": False,
            "live_trading": False,
            "telegram_sent": False,
            "journal_mutation": False,
            "hft_built": False,
        },
    }
    try:
        diagnostic["stale_locks_cleared"] = clear_approved_stale_locks()
        diagnostic["lock_recheck"] = lock_recheck()
        diagnostic["ohlc_refresh_result"] = run_ohlc_data_only_refresh()
        diagnostic["scanner_refresh_result"] = run_scanner_scan_only_refresh()
        diagnostic["setup_diagnostic_result"] = run_setup_diagnostic_proof(
            diagnostic["scanner_refresh_result"]
        )
        scanner_truth, runtime_truth, gate = build_truth_and_gate()
        diagnostic["scanner_ohlc_setup_truth_after"] = scanner_truth
        diagnostic["authoritative_runtime_truth_after"] = runtime_truth
        diagnostic["restart_readiness_gate_after"] = gate
        diagnostic["safe_to_start_daemon"] = bool(gate.get("safe_to_start_daemon"))
        diagnostic["safe_to_start_workers"] = bool(gate.get("safe_to_start_workers"))
        diagnostic["blockers"] = list(gate.get("blockers") or [])
        diagnostic["warnings"] = list(gate.get("warnings") or [])
        if diagnostic["blockers"]:
            diagnostic["next_required_action"] = (
                "Mission 016: resolve restart readiness blockers; do not start daemon/workers yet."
            )
        elif diagnostic["safe_to_start_daemon"] and not diagnostic["safe_to_start_workers"]:
            diagnostic["next_required_action"] = (
                "Mission 016: perform daemon start proof only; keep workers stopped until daemon proof passes."
            )
        elif diagnostic["safe_to_start_daemon"]:
            diagnostic["next_required_action"] = (
                "Mission 016: operator may approve daemon start proof; do not start workers in Mission 015."
            )
        else:
            diagnostic["next_required_action"] = (
                "Mission 016: reassess gate after blockers are cleared."
            )
    except Exception as exc:
        diagnostic["error"] = f"{type(exc).__name__}:{exc}"
        diagnostic["blockers"] = list(diagnostic.get("blockers") or []) + ["controlled_refresh_failed"]
        diagnostic["safe_to_start_daemon"] = False
        diagnostic["safe_to_start_workers"] = False
        diagnostic["next_required_action"] = (
            "Mission 016: fix controlled refresh error, then rerun readiness diagnostics without starting services."
        )
    finally:
        diagnostic["generated_at"] = _timestamp()
        _atomic_write_json(MISSION_DIAGNOSTIC_PATH, diagnostic)
    return diagnostic


if __name__ == "__main__":
    print(json.dumps(run_mission(), indent=2, sort_keys=True, default=str))
