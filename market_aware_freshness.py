import json
import os
import tempfile
from pathlib import Path

from scanner_ohlc_setup_truth import (
    build_scanner_ohlc_setup_truth,
    classify_ohlc_status,
    classify_scanner_status,
    classify_setup_engine_status,
)
from utils.market_hours import as_ist_datetime, last_valid_market_session, market_state


RUNTIME_DIR = Path("data") / "runtime"
MARKET_AWARE_FRESHNESS_PATH = RUNTIME_DIR / "market_aware_freshness.json"
RESTART_READINESS_GATE_PATH = RUNTIME_DIR / "restart_readiness_gate.json"


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def build_market_aware_freshness(*, now=None, output_path=MARKET_AWARE_FRESHNESS_PATH, write=True):
    now_ist = as_ist_datetime(now)
    scanner_truth = build_scanner_ohlc_setup_truth(now=now_ist, write=True)
    ohlc = scanner_truth.get("ohlc_status") or classify_ohlc_status(now=now_ist)
    scanner = scanner_truth.get("scanner_status") or classify_scanner_status(now=now_ist)
    setup = scanner_truth.get("setup_engine_status") or classify_setup_engine_status(now=now_ist)
    gate = _read_json(RESTART_READINESS_GATE_PATH)
    ohlc_status = ohlc.get("status") or "UNKNOWN"
    scanner_status = scanner.get("status") or "UNKNOWN"
    setup_status = setup.get("status") or "UNKNOWN"
    refresh_needed = bool(ohlc_status in {"DEGRADED", "STALE", "UNKNOWN"} or scanner_truth.get("restart_blocker"))
    payload = {
        "generated_at": now_ist.isoformat(),
        "market_state": market_state(now_ist),
        "last_valid_session": last_valid_market_session(now_ist).isoformat(),
        "ohlc_status": ohlc_status,
        "scanner_status": scanner_status,
        "setup_status": setup_status,
        "refresh_needed": refresh_needed,
        "restart_allowed": bool(gate.get("overall_restart_allowed")),
        "reason": ";".join(scanner_truth.get("restart_blockers") or []) or "market_aware_cache_valid",
        "source_files": {
            "ohlc_health": "data/runtime/ohlc_health.json",
            "scanner_truth": "data/runtime/scanner_ohlc_setup_truth.json",
            "restart_gate": "data/runtime/restart_readiness_gate.json",
        },
    }
    if write:
        _atomic_write_json(output_path, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(build_market_aware_freshness(write=True), indent=2, sort_keys=True))
