import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from titan_master_brain.setup_reasoning_engine import evaluate_setups


IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_STATUS_PATH = Path("data") / "runtime" / "scanner_status.json"
MASTER_BRAIN_STATUS_PATH = Path("data") / "runtime" / "master_brain_status.json"


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
        "trade_creation": False,
        "telegram_alerts": False,
        "supabase_writes": False,
        "journal_writes": False,
        "error_type": None,
        "error_message": None,
    }


def _sanitized_setups(candidate_symbols):
    setups = []
    for symbol in candidate_symbols or []:
        if not symbol:
            continue
        setups.append(
            {
                "symbol": symbol,
                "side": None,
                "score": 0.0,
                "rr": 0.0,
                "setup_context": {"confirmations": 0},
                "market_context": {"trend": "UNKNOWN"},
                "source": "scanner_status.json",
                "scan_only": True,
                "execution_allowed": False,
            }
        )
    return setups


def _write_status(payload, path=MASTER_BRAIN_STATUS_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_master_brain():
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

        candidate_symbols = scanner_status.get("candidate_symbols", [])
        if not isinstance(candidate_symbols, list):
            candidate_symbols = []

        setups = _sanitized_setups(candidate_symbols)
        context = {
            "source": "scanner_status.json",
            "scan_only": True,
            "observe_only": True,
            "execution_allowed": False,
        }
        evaluated = evaluate_setups(setups, context)

        top_symbols = []
        for item in evaluated or []:
            if isinstance(item, dict) and item.get("symbol"):
                top_symbols.append(item.get("symbol"))

        payload.update(
            {
                "input_candidates": len(setups),
                "evaluated_count": len(evaluated or []),
                "top_symbols": top_symbols[:5],
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


if __name__ == "__main__":
    print(json.dumps(run_master_brain(), indent=2, sort_keys=True))
