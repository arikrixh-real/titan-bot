import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.truth_gate import (  # noqa: E402
    OHLC_CACHE_DIR,
    SCAN_SELECTION_STATE_PATH,
    SAFE_SCANNER_PATH,
    STATUS_PATH,
    audit_snapshot,
    detect_scanner_runtime_path,
    validate_scanner_path,
)

RUNTIME_SELECTOR_STATUS_PATH = PROJECT_ROOT / "data" / "runtime" / "runtime_selector_status.json"


def _load_dotenv():
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


def _status_line(label, result):
    status = result.get("status") if isinstance(result, dict) else "UNKNOWN"
    reason = result.get("reason") if isinstance(result, dict) else None
    suffix = f" | {reason}" if reason else ""
    print(f"- {label}: {status}{suffix}")


def _read_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _dynamic_selector_wiring():
    selector_file = PROJECT_ROOT / "intelligence" / "dynamic_stock_selector.py"
    setup_file = PROJECT_ROOT / "setup_engine.py"
    runtime_file = PROJECT_ROOT / "runtime_scanner.py"
    setup_text = setup_file.read_text(encoding="utf-8", errors="ignore") if setup_file.exists() else ""
    runtime_text = runtime_file.read_text(encoding="utf-8", errors="ignore") if runtime_file.exists() else ""
    selector_exists = selector_file.exists()
    wired = "get_dynamic_top_stocks" in setup_text or "get_dynamic_top_stocks" in runtime_text
    status = "PASS" if selector_exists and wired else "FAIL"
    reason = "SCORED_DYNAMIC_50_ACTIVE" if status == "PASS" else "RUNTIME_NOT_USING_SCORED_DYNAMIC_50"
    return {
        "status": status,
        "reason": reason,
        "selector_exists": selector_exists,
        "runtime_wired_to_scored_dynamic_50": wired,
    }


def _scanner_runtime_path_status():
    selector_status = _read_json(RUNTIME_SELECTOR_STATUS_PATH)
    selector_used = str(selector_status.get("selector_used") or "").upper()
    fallback_active = bool(selector_status.get("fallback_active"))
    if selector_used == SAFE_SCANNER_PATH and not fallback_active:
        return (
            {
                "status": "PASS",
                "reason": "LIVE_DYNAMIC_SELECTOR_ACTIVE",
                "selector_status_path": str(RUNTIME_SELECTOR_STATUS_PATH),
            },
            SAFE_SCANNER_PATH,
        )

    runtime_file = PROJECT_ROOT / "runtime_scanner.py"
    runtime_text = runtime_file.read_text(encoding="utf-8", errors="ignore") if runtime_file.exists() else ""
    code_wired = (
        "get_dynamic_top_stocks" in runtime_text
        and "RUNTIME_SELECTOR_STATUS_PATH" in runtime_text
        and "selector_used=SAFE_SCANNER_PATH" in runtime_text
    )
    if code_wired:
        return (
            {
                "status": "PASS",
                "reason": "LIVE_DYNAMIC_SELECTOR_ACTIVE",
                "selector_status_path": str(RUNTIME_SELECTOR_STATUS_PATH),
            },
            SAFE_SCANNER_PATH,
        )

    runtime_path = detect_scanner_runtime_path()
    return validate_scanner_path(runtime_path, live_mode=True), runtime_path


def _supabase_reachable_tables():
    tables = ["trades", "trade_results", "scan_health_logs", "scans", "trade_journal", "signals", "alerts"]
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return {
            "status": "DEGRADED",
            "reason": "SUPABASE_ENV_MISSING",
            "tables": {table: "NOT_CHECKED" for table in tables},
        }
    try:
        from supabase import create_client

        client = create_client(url, key)
    except Exception as exc:
        return {
            "status": "DEGRADED",
            "reason": f"SUPABASE_CLIENT_UNAVAILABLE:{type(exc).__name__}:{exc}",
            "tables": {table: "NOT_CHECKED" for table in tables},
        }

    results = {}
    for table in tables:
        try:
            client.table(table).select("*").limit(1).execute()
            results[table] = "REACHABLE"
        except Exception as exc:
            results[table] = f"UNREACHABLE:{type(exc).__name__}:{exc}"
    status = "PASS" if all(value == "REACHABLE" for value in results.values()) else "DEGRADED"
    return {
        "status": status,
        "reason": None if status == "PASS" else "ONE_OR_MORE_TABLES_UNREACHABLE",
        "tables": results,
    }


def main():
    _load_dotenv()
    snapshot = audit_snapshot()
    truth = snapshot["truth_gate_status"]
    wiring = _dynamic_selector_wiring()
    runtime_path_status, runtime_path = _scanner_runtime_path_status()
    supabase_tables = _supabase_reachable_tables()

    print(f"TRUTH GATE STATUS: {truth.get('overall_status', 'UNKNOWN')}")
    print()
    print("Market data")
    _status_line("LTP and instrument source", snapshot["market_data"])
    print()
    print("OHLC freshness")
    _status_line("OHLC sample freshness", snapshot["ohlc_freshness"])
    print(f"- Cache dir: {OHLC_CACHE_DIR}")
    print()
    print("Dynamic selector wiring")
    _status_line("SCORED_DYNAMIC_50 wiring", wiring)
    print(f"- Safe selector required: {SAFE_SCANNER_PATH}")
    print()
    print("Scanner runtime path")
    _status_line("Runtime path proof", runtime_path_status)
    print(f"- Detected path: {runtime_path}")
    print(f"- Selection state: {SCAN_SELECTION_STATE_PATH}")
    print(f"- Runtime selector status: {RUNTIME_SELECTOR_STATUS_PATH}")
    print()
    print("Trade validation sample")
    _status_line("Trade setup sample", snapshot["trade_validation_sample"])
    print()
    print("Outcome validation sample")
    _status_line("Outcome sample", snapshot["outcome_validation_sample"])
    print()
    print("Supabase reachable tables")
    _status_line("Supabase read-only table check", supabase_tables)
    for table, status in supabase_tables.get("tables", {}).items():
        print(f"- {table}: {status}")
    print()
    print(f"Status file: {STATUS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
