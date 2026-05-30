from titan_brain.supabase_client import supabase
from datetime import datetime
import json


_DB_WARNED = set()


def _db_available():
    return supabase is not None


def _log_db_error(scope, error):
    text = str(error)
    if "WinError 10013" in text:
        key = (scope, "socket")
        if key in _DB_WARNED:
            return
        _DB_WARNED.add(key)
        print(f"[DB WARN - {scope}] Supabase socket unavailable; DB write skipped.")
        return
    print(f"[DB ERROR - {scope}] {text}")


def _safe_json(data):
    """
    Converts non-serializable values safely for Supabase.
    Prevents:
    Object of type bool is not JSON serializable
    """

    try:
        return json.loads(json.dumps(data, default=str))
    except Exception:
        return {}


def insert_scan(scan_data):
    if not _db_available():
        return None
    try:
        payload = _safe_json({
            "scan_time": datetime.now().isoformat(),
            "total_symbols": scan_data.get("total_symbols", 0),
            "scanned_count": scan_data.get("scanned_count", 0),
            "setup_count": scan_data.get("setup_count", 0),
            "errors": scan_data.get("errors", 0)
        })

        response = supabase.table("scans").insert(payload).execute()

        if response.data:
            return response.data[0]["id"]

        return None

    except Exception as e:
        _log_db_error("SCAN", e)
        return None


def insert_scan_symbol(scan_id, symbol_data):
    if not _db_available():
        return None
    try:
        payload = _safe_json({
            "scan_id": scan_id,
            "symbol": symbol_data.get("symbol"),
            "price": symbol_data.get("price"),
            "trend": symbol_data.get("trend"),
            "volume_score": symbol_data.get("volume_score"),
            "strength_score": symbol_data.get("strength_score"),
            "compression_score": symbol_data.get("compression_score"),
            "final_score": symbol_data.get("final_score"),
            "passed": bool(symbol_data.get("passed", False)),
            "reason": symbol_data.get("reason"),
            "raw_data": _safe_json(symbol_data)
        })

        supabase.table("scan_symbols").insert(payload).execute()

    except Exception as e:
        _log_db_error("SYMBOL", e)


def insert_setup(setup_data):
    if not _db_available():
        return None
    try:
        payload = _safe_json(setup_data)

        supabase.table("setups").insert(payload).execute()

    except Exception as e:
        _log_db_error("SETUP", e)


def insert_trade(trade_data):
    if not _db_available():
        return None
    try:
        trade_data = trade_data or {}

        trade_id = trade_data.get("trade_id")

        # Prevent trade_id=True issue
        if isinstance(trade_id, bool) or not trade_id:
            symbol = str(trade_data.get("symbol", "UNKNOWN"))
            side = str(trade_data.get("side", "NA"))
            entry = str(trade_data.get("entry", "0"))

            trade_id = (
                f"{symbol}_{side}_{entry}_"
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )

            trade_data["trade_id"] = trade_id

        payload = _safe_json(trade_data)

        supabase.table("trades").insert(payload).execute()

    except Exception as e:
        _log_db_error("TRADE", e)


def insert_trade_result(result_data):
    """
    Deprecated compatibility helper.

    Final trade_results ownership belongs to journal.outcome_tracker. Legacy
    titan_brain callers must not insert closed result rows directly.
    """
    print("[DB] trade_results insert skipped; journal.outcome_tracker owns final outcomes.")
    return None


def insert_learning(learning_data):
    if not _db_available():
        return None
    try:
        payload = _safe_json(learning_data)

        supabase.table("learning_memory").insert(payload).execute()

    except Exception as e:
        _log_db_error("LEARNING", e)


def insert_strategy_weights(weight_data):
    if not _db_available():
        return None
    try:
        payload = _safe_json(weight_data)

        supabase.table("strategy_weights").insert(payload).execute()

    except Exception as e:
        _log_db_error("STRATEGY WEIGHTS", e)
