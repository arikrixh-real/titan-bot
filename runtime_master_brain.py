import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engines.risk_engine import calculate_rr
from engines.trade_levels import calculate_trade_levels
from titan_master_brain.setup_reasoning_engine import evaluate_setups


IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"
RUNTIME_MODE_ENV = "TITAN_RUNTIME_MASTER_BRAIN_MODE"
MODE_READ_ONLY = "READ_ONLY"
MODE_HEALTH = "HEALTH"
MODE_REAL = "REAL"
SUPPORTED_RUNTIME_MODES = {MODE_READ_ONLY, MODE_HEALTH, MODE_REAL}


def _timestamp_ist():
    return datetime.now(IST).isoformat()


def _base_payload(scanner_status=None):
    scanner_status = scanner_status if isinstance(scanner_status, dict) else {}
    return {
        "timestamp_ist": _timestamp_ist(),
        "mode": scanner_status.get("mode", "READ_ONLY_MASTER_BRAIN"),
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


def _write_status(payload, path=MASTER_BRAIN_STATUS_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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

    return run_real_master_brain()


def _run_health_master_controller():
    from titan_master_brain.master_controller import (
        run_master_brain as run_real_master_brain,
    )

    return run_real_master_brain(health_check=True)


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


def _run_read_only_master_brain():
    scanner_status = None

    try:
        scanner_status = json.loads(SCANNER_STATUS_PATH.read_text(encoding="utf-8"))
        payload = _base_payload(scanner_status)

        if scanner_status.get("scan_only") is not True:
            payload.update(
                {
                    "status": "MASTER_BRAIN_READ_ONLY_SKIPPED",
                    "error_type": "ScanOnlyValidationError",
                    "error_message": "scanner_status.scan_only must be true",
                }
            )
            _write_status(payload)
            return payload

        candidate_details = scanner_status.get("candidate_details", [])
        if not isinstance(candidate_details, list):
            candidate_details = []

        setups = _sanitized_setups(candidate_details)
        context = {
            "source": "scanner_status.json",
            "scan_only": True,
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

    if mode == MODE_HEALTH:
        return _run_health_master_controller()

    if mode == MODE_REAL:
        return _run_real_master_controller()

    return _run_read_only_master_brain()


def main():
    return run_master_brain()


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
