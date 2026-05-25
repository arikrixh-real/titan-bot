import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime_engine_health import (
    atomic_write_json,
    build_master_brain_runtime_health,
    enrich_master_brain_payload,
)
from engines.risk_engine import calculate_rr
from engines.phase38_test_mode_guard import evaluate_phase38_runtime_guard, write_phase38_runtime_status
from engines.trade_levels import calculate_trade_levels
from titan_master_brain.setup_reasoning_engine import evaluate_setups


IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
RUNTIME_MODE_ENV = "TITAN_RUNTIME_MASTER_BRAIN_MODE"
MODE_READ_ONLY = "READ_ONLY"
MODE_HEALTH = "HEALTH"
MODE_REAL = "REAL"
MODE_LIVE = "LIVE"
MODE_TEST = "TEST"
MODE_RESEARCH_ONLY = "RESEARCH_ONLY"
MODE_SHADOW = "SHADOW"
MODE_PAPER = "PAPER"
SUPPORTED_RUNTIME_MODES = {
    MODE_READ_ONLY,
    MODE_HEALTH,
    MODE_REAL,
    MODE_LIVE,
    MODE_TEST,
    MODE_RESEARCH_ONLY,
    MODE_SHADOW,
    MODE_PAPER,
}
EXECUTION_OWNER_NONE = "NONE"
EXECUTION_OWNER_GITHUB_HEALTH = "GITHUB_HEALTH_ONLY"
EXECUTION_OWNER_VPS_REAL = "VPS_REAL_SOLE_LIVE_OWNER"


def _timestamp_ist():
    return datetime.now(IST).isoformat()


def _base_payload(scanner_status=None):
    scanner_status = scanner_status if isinstance(scanner_status, dict) else {}
    runtime_contract = _runtime_contract(MODE_READ_ONLY)
    phase38_guard = evaluate_phase38_runtime_guard(runtime_contract)
    return {
        "timestamp_ist": _timestamp_ist(),
        "mode": scanner_status.get("mode", "READ_ONLY_MASTER_BRAIN"),
        "runtime_mode": runtime_contract["runtime_mode"],
        "execution_owner": runtime_contract["execution_owner"],
        "execution_contract": runtime_contract["execution_contract"],
        "live_execution_enabled": runtime_contract["live_execution_enabled"],
        "telegram_enabled": runtime_contract["telegram_enabled"],
        "lifecycle_mutation_enabled": runtime_contract["lifecycle_mutation_enabled"],
        "journal_writes_enabled": runtime_contract["journal_writes_enabled"],
        "outcome_tracking_enabled": runtime_contract["outcome_tracking_enabled"],
        "phase38_runtime_guard": phase38_guard,
        "status": "MASTER_BRAIN_READ_ONLY_COMPLETE",
        "scan_only": bool(scanner_status.get("scan_only")),
        "observe_only": True,
        "input_candidates": 0,
        "evaluated_count": 0,
        "top_symbols": [],
        "trade_levels_generated": 0,
        "evaluated_trade_setups": [],
        "trade_creation": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": False,
        "error_type": None,
        "error_message": None,
    }


def _runtime_contract(mode):
    if mode in {MODE_LIVE, MODE_TEST, MODE_RESEARCH_ONLY, MODE_SHADOW, MODE_PAPER}:
        return {
            "runtime_mode": mode,
            "execution_owner": EXECUTION_OWNER_NONE,
            "execution_contract": (
                f"{mode} mode is validated by Phase 38 and held read-only; "
                "no live execution, Telegram, journaling, outcomes, or lifecycle mutation."
            ),
            "live_execution_enabled": False,
            "telegram_enabled": False,
            "lifecycle_mutation_enabled": False,
            "journal_writes_enabled": False,
            "outcome_tracking_enabled": False,
        }

    if mode == MODE_HEALTH:
        return {
            "runtime_mode": "HEALTH_ONLY",
            "execution_owner": EXECUTION_OWNER_GITHUB_HEALTH,
            "execution_contract": (
                "Health check only; no live execution, no Telegram, "
                "no journaling, no outcomes, no lifecycle mutation."
            ),
            "live_execution_enabled": False,
            "telegram_enabled": False,
            "lifecycle_mutation_enabled": False,
            "journal_writes_enabled": False,
            "outcome_tracking_enabled": False,
        }

    if mode == MODE_REAL:
        return {
            "runtime_mode": MODE_REAL,
            "execution_owner": EXECUTION_OWNER_VPS_REAL,
            "execution_contract": (
                "VPS REAL mode is the sole live execution owner; Telegram and "
                "lifecycle mutation are enabled only through the real master controller."
            ),
            "live_execution_enabled": True,
            "telegram_enabled": True,
            "lifecycle_mutation_enabled": True,
            "journal_writes_enabled": True,
            "outcome_tracking_enabled": True,
        }

    return {
        "runtime_mode": MODE_READ_ONLY,
        "execution_owner": EXECUTION_OWNER_NONE,
        "execution_contract": (
            "Marker/observation mode only; no live execution, no Telegram, "
            "no journaling, no outcomes."
        ),
        "live_execution_enabled": False,
        "telegram_enabled": False,
        "lifecycle_mutation_enabled": False,
        "journal_writes_enabled": False,
        "outcome_tracking_enabled": False,
    }


def _print_runtime_contract(mode):
    contract = _runtime_contract(mode)
    print(
        "[RuntimeMasterBrain] "
        f"runtime_mode={contract['runtime_mode']} "
        f"execution_owner={contract['execution_owner']} "
        f"live_execution_enabled={contract['live_execution_enabled']} "
        f"telegram_enabled={contract['telegram_enabled']} "
        f"lifecycle_mutation_enabled={contract['lifecycle_mutation_enabled']}",
        flush=True,
    )
    print(f"[RuntimeMasterBrain] {contract['execution_contract']}", flush=True)


def _ohlc_dataframe(last_ohlc):
    if not isinstance(last_ohlc, dict):
        return None

    try:
        row = {
            "High": float(last_ohlc["High"]),
            "Low": float(last_ohlc["Low"]),
            "Close": float(last_ohlc["Close"]),
        }
    except (KeyError, TypeError, ValueError):
        return None

    pandas = __import__("pandas")
    return pandas.DataFrame([row], columns=["High", "Low", "Close"])


def _sanitized_setups(candidate_details):
    setups = []
    for candidate in candidate_details or []:
        if not isinstance(candidate, dict):
            continue

        symbol = candidate.get("symbol")
        side = candidate.get("side")
        if not symbol:
            continue

        entry, sl, target = calculate_trade_levels(
            _ohlc_dataframe(candidate.get("last_ohlc")),
            side,
        )
        rr = calculate_rr(entry, sl, target, side)

        setups.append(
            {
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "sl": sl,
                "target": target,
                "score": 0.0,
                "rr": rr,
                "setup_context": {"confirmations": 0},
                "market_context": {"trend": "UNKNOWN"},
                "source": "scanner_status.json",
                "scan_only": True,
                "observe_only": True,
                "execution_allowed": False,
            }
        )
    return setups


def _write_status(payload, path=None):
    if isinstance(payload, dict):
        payload = enrich_master_brain_payload(payload)
        phase38_guard = evaluate_phase38_runtime_guard(payload)
        payload["phase38_runtime_guard"] = phase38_guard
        write_phase38_runtime_status(payload)
    path = Path(path or MASTER_BRAIN_STATUS_PATH)
    atomic_write_json(path, payload)
    if path == MASTER_BRAIN_STATUS_PATH and isinstance(payload, dict):
        build_master_brain_runtime_health(status_payload=payload)


def _runtime_mode():
    raw_mode = os.getenv(RUNTIME_MODE_ENV, MODE_READ_ONLY)
    mode = str(raw_mode or MODE_READ_ONLY).strip().upper()

    if mode not in SUPPORTED_RUNTIME_MODES:
        print(
            "[RuntimeMasterBrain] "
            f"Unsupported {RUNTIME_MODE_ENV}={raw_mode!r}; using {MODE_READ_ONLY}"
        )
        return MODE_READ_ONLY

    return mode


def _run_real_master_controller(*, health_check=False):
    from titan_master_brain.master_controller import (
        run_master_brain as run_real_master_brain,
    )

    if health_check:
        return run_real_master_brain(health_check=True)

    runtime_contract = _runtime_contract(MODE_REAL)
    phase38_guard = evaluate_phase38_runtime_guard(runtime_contract)
    write_phase38_runtime_status(runtime_contract)
    if not phase38_guard.get("phase38_runtime_allowed"):
        payload = {
            "timestamp_ist": _timestamp_ist(),
            "mode": "REAL_MASTER_CONTROLLER_BLOCKED_PHASE38",
            "status": "BLOCKED_PHASE38_FAIL_CLOSED",
            **_runtime_contract(MODE_READ_ONLY),
            "phase38_runtime_guard": phase38_guard,
            "observe_only": True,
            "scan_only": True,
            "trade_creation": False,
            "telegram_alerts": False,
            "supabase_writes": False,
            "journal_writes": False,
            "error_type": None,
            "error_message": None,
        }
        _write_status(payload)
        return payload

    _write_status(
        {
            "timestamp_ist": _timestamp_ist(),
            "mode": "REAL_MASTER_BRAIN_HANDOFF",
            "status": "REAL_MASTER_CONTROLLER_HANDOFF",
            **runtime_contract,
            "phase38_runtime_guard": phase38_guard,
            "observe_only": False,
            "scan_only": False,
            "trade_creation": True,
            "telegram_alerts": True,
            "supabase_writes": True,
            "journal_writes": True,
            "error_type": None,
            "error_message": None,
        }
    )
    return run_real_master_brain()


def _run_health_master_controller():
    from titan_master_brain.master_controller import (
        run_master_brain as run_real_master_brain,
    )

    result = run_real_master_brain(health_check=True)
    if isinstance(result, dict):
        payload = dict(result)
        payload.update(_runtime_contract(MODE_HEALTH))
        payload.setdefault("status", "HEALTH_CHECK_COMPLETE")
        payload["timestamp_ist"] = _timestamp_ist()
        _write_status(payload)
        return payload

    return result


def _evaluated_trade_setups(evaluated):
    trade_setups = []
    for item in evaluated or []:
        if not isinstance(item, dict):
            continue

        trade_setups.append(
            {
                "symbol": item.get("symbol"),
                "side": item.get("side"),
                "entry": item.get("entry"),
                "sl": item.get("sl"),
                "target": item.get("target"),
                "rr": item.get("rr"),
            }
        )
    return trade_setups


def _read_scanner_status():
    if not SCANNER_STATUS_PATH.exists():
        return {}, {
            "scanner_status_available": False,
            "scanner_status_error": "missing_scanner_status",
        }

    scanner_status = json.loads(SCANNER_STATUS_PATH.read_text(encoding="utf-8"))
    if not isinstance(scanner_status, dict):
        raise ValueError("scanner_status.json must contain a JSON object")

    return scanner_status, {
        "scanner_status_available": True,
        "scanner_status_error": None,
    }


def _run_read_only_master_brain():
    scanner_status = None

    try:
        scanner_status, scanner_status_metadata = _read_scanner_status()
        payload = _base_payload(scanner_status)
        payload.update(_runtime_contract(_runtime_mode()))
        payload.update(scanner_status_metadata)
        if not scanner_status_metadata["scanner_status_available"]:
            payload.update(
                {
                    "status": "MASTER_BRAIN_READ_ONLY_NO_CANDIDATES",
                    "input_candidates": 0,
                    "evaluated_count": 0,
                }
            )
            _write_status(payload)
            return payload

        scanner_scan_only = bool(scanner_status.get("scan_only"))

        candidate_details = scanner_status.get("candidate_details", [])
        if not isinstance(candidate_details, list):
            candidate_details = []

        setups = _sanitized_setups(candidate_details)
        for setup in setups:
            setup["scan_only"] = scanner_scan_only
        context = {
            "source": "scanner_status.json",
            "scan_only": scanner_scan_only,
            "observe_only": True,
            "execution_allowed": False,
        }
        evaluated = evaluate_setups(setups, context)
        evaluated_trade_setups = _evaluated_trade_setups(evaluated)

        top_symbols = []
        for item in evaluated or []:
            if isinstance(item, dict) and item.get("symbol"):
                top_symbols.append(item.get("symbol"))

        payload.update(
            {
                "input_candidates": len(setups),
                "evaluated_count": len(evaluated or []),
                "top_symbols": top_symbols[:5],
                "trade_levels_generated": sum(
                    1
                    for setup in setups
                    if setup.get("entry") is not None
                    and setup.get("sl") is not None
                    and setup.get("target") is not None
                ),
                "evaluated_trade_setups": evaluated_trade_setups,
            }
        )
        _write_status(payload)
        return payload

    except Exception as exc:
        payload = _base_payload(scanner_status)
        payload.update(_runtime_contract(_runtime_mode()))
        payload.update(
            {
                "scanner_status_available": SCANNER_STATUS_PATH.exists(),
                "scanner_status_error": (
                    "invalid_scanner_status"
                    if SCANNER_STATUS_PATH.exists()
                    else "missing_scanner_status"
                ),
            }
        )
        payload.update(
            {
                "status": "MASTER_BRAIN_READ_ONLY_ERROR",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
        _write_status(payload)
        return payload


def run_master_brain():
    mode = _runtime_mode()
    print(f"[RuntimeMasterBrain] mode={mode}", flush=True)
    _print_runtime_contract(mode)

    if mode == MODE_HEALTH:
        return _run_health_master_controller()

    if mode == MODE_REAL:
        return _run_real_master_controller()

    return _run_read_only_master_brain()


def main():
    return run_master_brain()


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
