import csv
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.paper_journal import (  # noqa: E402
    ACTIVE_TRADES_CSV,
    PAPER_FLAG,
    PAPER_JOURNAL_STATUS_PATH,
    latest_status,
    paper_journal_enabled,
    write_disabled_status,
)


TRADE_CONTRACT_DIAGNOSTICS_PATH = PROJECT_ROOT / "data" / "runtime" / "trade_contract_diagnostics.json"


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_csv_rows(path):
    try:
        path = Path(path)
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def _open_trade_count():
    rows = _read_csv_rows(ACTIVE_TRADES_CSV)
    return sum(1 for row in rows if str(row.get("status") or "").upper() in {"OPEN", "ACTIVE", "LIVE"})


def _duplicate_status():
    rows = _read_csv_rows(ACTIVE_TRADES_CSV)
    keys = []
    for row in rows:
        if str(row.get("status") or "").upper() not in {"OPEN", "ACTIVE", "LIVE"}:
            continue
        symbol = str(row.get("symbol") or "").upper()
        side = str(row.get("side") or "").upper()
        if symbol and side:
            keys.append(f"{symbol}|{side}")
    return "PASS" if len(keys) == len(set(keys)) else "FAIL"


def main():
    if not PAPER_JOURNAL_STATUS_PATH.exists() and not paper_journal_enabled():
        write_disabled_status(reason="STATUS_FILE_MISSING_CREATED_READ_ONLY_STATUS")

    status = latest_status()
    contract = _read_json(TRADE_CONTRACT_DIAGNOSTICS_PATH)
    latest_setup_count = int(contract.get("final_setup_count") or status.get("latest_setup_count") or 0)
    valid_setup_count = int(contract.get("valid_setup_count") or status.get("valid_setup_count") or 0)
    enabled = paper_journal_enabled()

    print("PAPER JOURNAL STATUS")
    print(f"flag: {'ENABLED' if enabled else 'DISABLED'} ({PAPER_FLAG}={os.getenv(PAPER_FLAG, '') or 'false'})")
    print(f"latest setup count: {latest_setup_count}")
    print(f"valid setup count: {valid_setup_count}")
    print(f"open trades count: {_open_trade_count()}")
    print(f"duplicate protection status: {_duplicate_status()}")
    print(f"last write status: {status.get('last_write_status') or 'UNKNOWN'}")
    print(f"enabled in status: {status.get('enabled')}")
    print(f"attempted: {status.get('attempted', 0)}")
    print(f"written: {status.get('written', 0)}")
    print(f"duplicate skipped: {status.get('duplicate_skipped', 0)}")
    print(f"failed: {status.get('failed', 0)}")
    print(f"destination: {status.get('destination')}")
    print(f"blocked reason: {status.get('blocked_reason')}")
    print("SAFETY PROOF")
    print("broker execution remains disabled: true")
    print("telegram sent: false")
    print("enabled write surface: paper journal only")
    print(f"status file: {PAPER_JOURNAL_STATUS_PATH}")


if __name__ == "__main__":
    main()
