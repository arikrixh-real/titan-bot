import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER_STATUS_PATH = ROOT / "data" / "runtime" / "scanner_status.json"
INTEGRITY_PATH = ROOT / "data" / "runtime" / "breakout_pipeline_integrity.json"
DASHBOARD_PATH = ROOT / "dashboard.py"
RUNTIME_SCANNER_PATH = ROOT / "runtime_scanner.py"


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def first_int(payload, *keys):
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except Exception:
            continue
    return 0


def dashboard_mapping_correct():
    text = read_text(DASHBOARD_PATH)
    required = [
        "scanner_breakout_counts",
        '"raw_breakout_ready_count": breakout_counts["raw_breakout_ready_count"]',
        '"qualified_breakout_ready_count": breakout_counts["qualified_breakout_ready_count"]',
        '"breakout_ready_count": breakout_counts["breakout_ready_count"]',
        "Raw Breakout Ready",
        "Qualified Breakout",
    ]
    forbidden = [
        r'"raw_breakout_ready_count":\s*int\(first_number\([^)]*default=0\)',
        r'"breakout_ready_count":\s*int\(first_number\(preferred_payload\.get\("momentum_passed"',
        r"latest_breakout_ready\s*=\s*scan_breakdown\.get\(\"breakout_ready_count\",\s*latest_entry_passed\)",
    ]
    return all(item in text for item in required) and not any(re.search(pattern, text) for pattern in forbidden)


def runtime_payload_correct(scanner_status):
    raw = first_int(scanner_status, "raw_breakout_ready_count", "raw_breakout_ready")
    qualified = first_int(scanner_status, "qualified_breakout_ready_count")
    alias = first_int(scanner_status, "breakout_ready_count", "breakout_ready")
    text = read_text(RUNTIME_SCANNER_PATH)
    wrong_alias = bool(
        re.search(r'"breakout_ready_count":\s*momentum_passed', text)
        or re.search(r"breakout_ready_count\s*=\s*momentum_passed", text)
    )
    publishes_raw = '"raw_breakout_ready_count": raw_breakout_ready_count' in text
    publishes_qualified = '"qualified_breakout_ready_count": breakout_ready_count' in text
    return bool(raw >= qualified and alias == qualified and publishes_raw and publishes_qualified and not wrong_alias)


def main():
    scanner_status = read_json(SCANNER_STATUS_PATH)
    integrity = read_json(INTEGRITY_PATH)
    raw = first_int(scanner_status, "raw_breakout_ready_count", "raw_breakout_ready") or first_int(
        integrity,
        "raw_breakout_ready_count",
    )
    qualified = first_int(scanner_status, "qualified_breakout_ready_count") or first_int(
        integrity,
        "qualified_breakout_ready_count",
    )
    violating_symbols = integrity.get("violating_symbols") if isinstance(integrity.get("violating_symbols"), list) else []
    integrity_valid = bool(raw >= qualified and not violating_symbols and integrity.get("integrity_valid", True))

    print(f"raw_breakout_ready_count: {raw}")
    print(f"qualified_breakout_ready_count: {qualified}")
    print(f"integrity_valid {'YES' if integrity_valid else 'NO'}")
    print(f"violating_symbols: {violating_symbols}")
    print(f"dashboard_mapping_correct {'YES' if dashboard_mapping_correct() else 'NO'}")
    print(f"runtime_payload_correct {'YES' if runtime_payload_correct(scanner_status) else 'NO'}")


if __name__ == "__main__":
    main()
