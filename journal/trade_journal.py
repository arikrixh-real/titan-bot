import json
import os
from datetime import datetime
from typing import Dict, Any, Optional


MEMORY_DIR = os.path.join("titan_brain", "memory")
TRADE_MEMORY_FILE = os.path.join(MEMORY_DIR, "trade_memory.json")


def _ensure_trade_memory_file():
    os.makedirs(MEMORY_DIR, exist_ok=True)

    if not os.path.exists(TRADE_MEMORY_FILE):
        with open(TRADE_MEMORY_FILE, "w") as f:
            json.dump([], f, indent=4)


def _load_trades():
    _ensure_trade_memory_file()

    with open(TRADE_MEMORY_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_trades(data):
    _ensure_trade_memory_file()

    with open(TRADE_MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)


def generate_trade_id(symbol: str) -> str:
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{symbol}_{now}"


def is_duplicate_open_trade(symbol: str, side: str, entry: float, tolerance: float = 0.15):
    trades = _load_trades()

    for trade in trades:
        if trade.get("status") != "OPEN":
            continue

        if trade.get("symbol") != symbol:
            continue

        if trade.get("side") != side:
            continue

        old_entry = trade.get("entry")

        if old_entry is None:
            continue

        if abs(float(old_entry) - float(entry)) <= tolerance:
            return True, trade.get("trade_id")

    return False, None


def log_trade(
    symbol: str,
    side: str,
    entry: float,
    stop_loss: float,
    target: float,
    position_size: float,
    risk_amount: float,
    rr: float,
    scores: Dict[str, Any],
    market_context: Dict[str, Any],
    setup_context: Dict[str, Any],
    reason: str,
    trigger_status: str,
    extra_notes: Optional[str] = None
) -> str:

    duplicate, existing_trade_id = is_duplicate_open_trade(
        symbol=symbol,
        side=side,
        entry=entry
    )

    if duplicate:
        return existing_trade_id

    trades = _load_trades()
    trade_id = generate_trade_id(symbol)

    trade = {
        "trade_id": trade_id,
        "timestamp": datetime.now().isoformat(),

        "symbol": symbol,
        "side": side,

        "entry": entry,
        "stop_loss": stop_loss,
        "target": target,
        "rr": rr,

        "position_size": position_size,
        "risk_amount": risk_amount,

        "scores": scores,
        "market_context": market_context,
        "setup_context": setup_context,

        "reason": reason,
        "trigger_status": trigger_status,

        "status": "OPEN",
        "result": None,
        "exit_price": None,
        "exit_time": None,
        "actual_rr": None,
        "pnl": None,

        "mistake_tags": [],
        "learning_notes": [],
        "extra_notes": extra_notes
    }

    trades.append(trade)
    _save_trades(trades)

    return trade_id


def update_trade_result(
    trade_id: str,
    result: str,
    exit_price: float,
    actual_rr: float,
    pnl: float,
    mistake_tags: Optional[list] = None,
    learning_notes: Optional[list] = None
) -> bool:

    trades = _load_trades()

    for trade in trades:
        if trade.get("trade_id") == trade_id:
            trade["status"] = "CLOSED"
            trade["result"] = result
            trade["exit_price"] = exit_price
            trade["exit_time"] = datetime.now().isoformat()
            trade["actual_rr"] = actual_rr
            trade["pnl"] = pnl
            trade["mistake_tags"] = mistake_tags or []
            trade["learning_notes"] = learning_notes or []

            _save_trades(trades)
            return True

    return False


def get_all_trades():
    return _load_trades()


def get_open_trades():
    return [trade for trade in _load_trades() if trade.get("status") == "OPEN"]


def get_closed_trades():
    return [trade for trade in _load_trades() if trade.get("status") == "CLOSED"]


def get_trades_by_symbol(symbol: str):
    return [trade for trade in _load_trades() if trade.get("symbol") == symbol]


def basic_performance_summary():
    closed = get_closed_trades()

    if not closed:
        return {
            "total_closed_trades": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "average_rr": 0,
            "message": "No closed trades yet."
        }

    total = len(closed)
    wins = len([t for t in closed if t.get("result") == "WIN"])
    losses = len([t for t in closed if t.get("result") == "LOSS"])

    total_pnl = sum(t.get("pnl", 0) for t in closed if t.get("pnl") is not None)
    rr_values = [t.get("actual_rr") for t in closed if t.get("actual_rr") is not None]

    average_rr = sum(rr_values) / len(rr_values) if rr_values else 0
    win_rate = (wins / total) * 100

    return {
        "total_closed_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2),
        "average_rr": round(average_rr, 2)
    }