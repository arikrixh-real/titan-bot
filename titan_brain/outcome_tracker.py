from datetime import datetime

from data.live_price import get_live_price
from titan_brain.supabase_client import supabase
from titan_brain.db import insert_trade_result
from utils.market_hours import is_trade_window, trade_window_text


def get_open_trades():
    try:
        result = (
            supabase
            .table("trades")
            .select("*")
            .eq("status", "OPEN")
            .execute()
        )

        return result.data or []

    except Exception as e:
        print(f"[OUTCOME TRACKER ERROR - FETCH OPEN TRADES] {e}")
        return []


def update_trade_closed(trade_id, result, exit_price, actual_rr, pnl):
    try:
        supabase.table("trades").update({
            "status": "CLOSED"
        }).eq("trade_id", trade_id).execute()

        supabase.table("setups").update({
            "status": "CLOSED"
        }).eq("trade_id", trade_id).execute()

    except Exception as e:
        print(f"[OUTCOME TRACKER ERROR - UPDATE TRADE] {e}")


def calculate_pnl(side, entry, exit_price, position_size):
    if side == "BUY":
        return (exit_price - entry) * position_size

    if side == "SELL":
        return (entry - exit_price) * position_size

    return 0


def calculate_actual_rr(side, entry, stop_loss, exit_price):
    risk = abs(entry - stop_loss)

    if risk == 0:
        return 0

    if side == "BUY":
        return (exit_price - entry) / risk

    if side == "SELL":
        return (entry - exit_price) / risk

    return 0


def check_trade_outcome(trade):
    trade_id = trade.get("trade_id")
    symbol = trade.get("symbol")
    side = trade.get("side")

    entry = float(trade.get("entry", 0))
    stop_loss = float(trade.get("stop_loss", 0))
    target = float(trade.get("target", 0))
    position_size = float(trade.get("position_size", 0))

    live_price = get_live_price(symbol)

    if live_price is None:
        return None

    live_price = float(live_price)

    result = None

    if side == "BUY":
        if live_price >= target:
            result = "WIN"
        elif live_price <= stop_loss:
            result = "LOSS"

    elif side == "SELL":
        if live_price <= target:
            result = "WIN"
        elif live_price >= stop_loss:
            result = "LOSS"

    if result is None:
        return {
            "trade_id": trade_id,
            "symbol": symbol,
            "status": "OPEN",
            "live_price": live_price
        }

    pnl = calculate_pnl(side, entry, live_price, position_size)
    actual_rr = calculate_actual_rr(side, entry, stop_loss, live_price)

    result_data = {
        "trade_id": trade_id,
        "symbol": symbol,
        "result": result,
        "exit_price": live_price,
        "actual_rr": round(actual_rr, 2),
        "pnl": round(pnl, 2),
        "mistake_tags": [],
        "learning_notes": [
            f"Trade closed automatically by TITAN at {datetime.now().isoformat()}"
        ]
    }

    insert_trade_result(result_data)

    update_trade_closed(
        trade_id=trade_id,
        result=result,
        exit_price=live_price,
        actual_rr=actual_rr,
        pnl=pnl
    )

    print(f"✅ Trade closed: {symbol} | {result} | Exit: {live_price}")

    return result_data


def run_outcome_tracker():
    print("🎯 TITAN Outcome Tracker Started")

    if not is_trade_window():
        print(f"[OutcomeTracker] Skipped outside trade window ({trade_window_text()}).")
        return {
            "open_trades": 0,
            "closed_trades": 0,
            "skipped": "OUTSIDE_TRADE_WINDOW",
        }

    open_trades = get_open_trades()

    if not open_trades:
        print("No open trades to track.")
        return {
            "open_trades": 0,
            "closed_trades": 0
        }

    closed_count = 0

    for trade in open_trades:
        outcome = check_trade_outcome(trade)

        if outcome and outcome.get("result") in ["WIN", "LOSS"]:
            closed_count += 1

    print(f"📌 Open trades checked: {len(open_trades)}")
    print(f"✅ Trades closed: {closed_count}")

    return {
        "open_trades": len(open_trades),
        "closed_trades": closed_count
    }
