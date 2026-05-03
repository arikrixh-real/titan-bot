from titan_brain.supabase_client import supabase
from datetime import datetime


def insert_scan(scan_data):
    try:
        response = supabase.table("scans").insert({
            "scan_time": datetime.now().isoformat(),
            "total_symbols": scan_data["total_symbols"],
            "scanned_count": scan_data["scanned_count"],
            "setup_count": scan_data["setup_count"],
            "errors": scan_data["errors"]
        }).execute()

        return response.data[0]["id"]

    except Exception as e:
        print(f"[DB ERROR - SCAN] {e}")
        return None


def insert_scan_symbol(scan_id, symbol_data):
    try:
        supabase.table("scan_symbols").insert({
            "scan_id": scan_id,
            "symbol": symbol_data["symbol"],
            "price": symbol_data["price"],
            "trend": symbol_data["trend"],
            "volume_score": symbol_data["volume_score"],
            "strength_score": symbol_data["strength_score"],
            "compression_score": symbol_data["compression_score"],
            "final_score": symbol_data["final_score"],
            "passed": symbol_data["passed"],
            "reason": symbol_data.get("reason"),
            "raw_data": symbol_data
        }).execute()

    except Exception as e:
        print(f"[DB ERROR - SYMBOL] {e}")


def insert_setup(setup_data):
    try:
        supabase.table("setups").insert(setup_data).execute()

    except Exception as e:
        print(f"[DB ERROR - SETUP] {e}")


def insert_trade(trade_data):
    try:
        supabase.table("trades").insert(trade_data).execute()

    except Exception as e:
        print(f"[DB ERROR - TRADE] {e}")


def insert_trade_result(result_data):
    try:
        supabase.table("trade_results").insert(result_data).execute()

    except Exception as e:
        print(f"[DB ERROR - TRADE RESULT] {e}")


def insert_learning(learning_data):
    try:
        supabase.table("learning_memory").insert(learning_data).execute()

    except Exception as e:
        print(f"[DB ERROR - LEARNING] {e}")


def insert_strategy_weights(weight_data):
    try:
        supabase.table("strategy_weights").insert(weight_data).execute()

    except Exception as e:
        print(f"[DB ERROR - STRATEGY WEIGHTS] {e}")