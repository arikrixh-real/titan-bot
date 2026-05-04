import json
import os
from datetime import datetime


MEMORY_DIR = os.path.join("titan_brain", "memory")
SCAN_MEMORY_FILE = os.path.join(MEMORY_DIR, "scan_memory.json")


def _ensure_scan_memory_file():
    os.makedirs(MEMORY_DIR, exist_ok=True)

    if not os.path.exists(SCAN_MEMORY_FILE):
        with open(SCAN_MEMORY_FILE, "w") as f:
            json.dump([], f, indent=4)


def _load_scans():
    _ensure_scan_memory_file()

    with open(SCAN_MEMORY_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_scans(data):
    _ensure_scan_memory_file()

    with open(SCAN_MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)


def log_scan(
    total_symbols=0,
    scanned_symbols=None,
    setup_symbols=None,
    errors=None
):
    scanned_symbols = scanned_symbols or []
    setup_symbols = setup_symbols or []
    errors = errors or []

    scans = _load_scans()

    scan_record = {
        "timestamp": datetime.now().isoformat(),
        "total_symbols": total_symbols,
        "scanned_count": len(scanned_symbols),
        "setup_count": len(setup_symbols),
        "scanned_symbols": scanned_symbols,
        "setup_symbols": setup_symbols,
        "errors": errors
    }

    scans.append(scan_record)
    _save_scans(scans)

    return scan_record


def get_all_scans():
    return _load_scans()


def get_latest_scan():
    scans = _load_scans()

    if not scans:
        return None

    return scans[-1]