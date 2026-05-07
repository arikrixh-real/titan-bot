from datetime import datetime, timezone
from titan_brain.memory.supabase_client import get_supabase


def save_trade_result(
    symbol,
    side,
    entry,
    sl,
    tp,
    status="LIVE",
    result=None,
    pnl=0,
    exit_price=None,
):
    try:
        supabase = get_supabase()

        data = {
            "symbol": symbol,
            "side": side,
            "entry": float(entry) if entry else None,
            "sl": float(sl) if sl else None,
            "tp": float(tp) if tp else None,
            "status": status,
            "result": result,
            "pnl": pnl,
            "exit_price": exit_price,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        supabase.table("trade_results").insert(data).execute()

        print(f"✅ Trade stored: {symbol}")
        return True

    except Exception as e:
        print(f"❌ Trade save failed: {e}")
        return False