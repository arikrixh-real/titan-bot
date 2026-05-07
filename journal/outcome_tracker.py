"""
TITAN - Outcome Tracker Safe Engine
STEP 9A - SUPABASE DASHBOARD RESULT FIX

Purpose:
- Reads OPEN trades from data/journals/active_trades.csv
- Gets latest price
- Checks TP/SL hit
- Updates active_trades.csv status
- Writes completed outcomes to:
    data/journals/trade_outcomes.csv
    data/journals/trade_outcomes.jsonl
- Saves every CLOSED TP/SL result to Supabase trade_results
  so deployed dashboard updates without Git memory push.

Safe:
- Does not send alerts
- Does not place broker orders
- Does not delete trades
"""

import csv
import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from data.live_price import get_live_price


IST = ZoneInfo("Asia/Kolkata")

JOURNAL_DIR = Path("data/journals")
ACTIVE_TRADES_CSV = JOURNAL_DIR / "active_trades.csv"
OUTCOMES_CSV = JOURNAL_DIR / "trade_outcomes.csv"
OUTCOMES_JSONL = JOURNAL_DIR / "trade_outcomes.jsonl"

OUTCOME_FIELDS = [
    "closed_at",
    "trade_id",
    "opened_at",
    "symbol",
    "side",
    "entry",
    "sl",
    "target",
    "rr",
    "score",
    "rank_score",
    "alert_sent",
    "market_status",
    "outcome",
    "exit_price",
    "pnl_points",
    "result_reason",
]


# ---------------------------------------------------------
# SUPABASE CLIENT
# ---------------------------------------------------------

def _get_supabase_client():
    """
    Robust Supabase connection for GitHub + local.
    Tries:
    1. titan_master_brain.supabase_client.supabase
    2. SUPABASE_URL + SUPABASE_KEY from env/secrets
    """
    try:
        from titan_master_brain.supabase_client import supabase
        if supabase is not None:
            return supabase
    except Exception:
        pass

    try:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            print("[OutcomeTracker DB] Supabase secrets missing. Dashboard DB result not saved.")
            return None

        return create_client(url, key)

    except Exception as e:
        print(f"[OutcomeTracker DB] Supabase client unavailable: {e}")
        return None


SUPABASE = _get_supabase_client()


# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def _now():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value):
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y"}


def _json_safe(value):
    try:
        if hasattr(value, "item"):
            value = value.item()
    except Exception:
        pass

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)


def _ensure_files():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    if not ACTIVE_TRADES_CSV.exists():
        with open(ACTIVE_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "trade_id", "opened_at", "scan_id", "symbol", "side", "entry", "sl",
                "target", "rr", "score", "rank_score", "alert_sent", "market_status",
                "status", "last_checked_at", "last_price", "pnl_points", "result_reason"
            ])
            writer.writeheader()

    if not OUTCOMES_CSV.exists():
        with open(OUTCOMES_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
            writer.writeheader()

    if not OUTCOMES_JSONL.exists():
        OUTCOMES_JSONL.touch()


# ---------------------------------------------------------
# OUTCOME LOGIC
# ---------------------------------------------------------

def _check_outcome(row, live_price):
    side = str(row.get("side", "")).upper().strip()

    entry = _safe_float(row.get("entry"))
    sl = _safe_float(row.get("sl"))
    target = _safe_float(row.get("target"))
    price = _safe_float(live_price)

    if side == "LONG":
        if price <= sl:
            return "SL", sl, round(sl - entry, 4), "LONG stop loss hit"
        if price >= target:
            return "TP", target, round(target - entry, 4), "LONG target hit"

    if side == "SHORT":
        if price >= sl:
            return "SL", sl, round(entry - sl, 4), "SHORT stop loss hit"
        if price <= target:
            return "TP", target, round(entry - target, 4), "SHORT target hit"

    pnl = round(price - entry if side == "LONG" else entry - price, 4)
    return "OPEN", price, pnl, "Still open"


def _save_trade_result_to_supabase(outcome_row):
    """
    Saves one CLOSED trade result to Supabase.

    Dashboard reads trade_results:
    - TP becomes WIN
    - SL becomes LOSS
    """
    if SUPABASE is None:
        print("[OutcomeTracker DB] Supabase not connected. Result not saved to dashboard DB.")
        return False

    outcome = str(outcome_row.get("outcome", "")).upper().strip()

    if outcome not in {"TP", "SL"}:
        return False

    result = "WIN" if outcome == "TP" else "LOSS"
    trade_id = str(outcome_row.get("trade_id", "")).strip()

    if not trade_id:
        print("[OutcomeTracker DB] Missing trade_id. Result not saved.")
        return False

    payload = _json_safe({
        "trade_id": trade_id,
        "symbol": outcome_row.get("symbol", ""),
        "side": outcome_row.get("side", ""),
        "entry": _safe_float(outcome_row.get("entry")),
        "exit_price": _safe_float(outcome_row.get("exit_price")),
        "stop_loss": _safe_float(outcome_row.get("sl")),
        "target": _safe_float(outcome_row.get("target")),
        "rr": _safe_float(outcome_row.get("rr")),
        "result": result,
        "outcome": outcome,
        "pnl_points": _safe_float(outcome_row.get("pnl_points")),
        "closed_at": outcome_row.get("closed_at"),
        "opened_at": outcome_row.get("opened_at"),
        "reason": outcome_row.get("result_reason", ""),
        "alert_sent": _safe_bool(outcome_row.get("alert_sent")),
        "market_status": str(outcome_row.get("market_status", "")),
    })

    try:
        existing = (
            SUPABASE.table("trade_results")
            .select("trade_id")
            .eq("trade_id", trade_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            print(f"[OutcomeTracker DB] Result already exists: {trade_id}")
            return True

        SUPABASE.table("trade_results").insert(payload).execute()
        print(f"[OutcomeTracker DB] Supabase result saved: {trade_id} -> {result}")
        return True

    except Exception as e:
        print(f"[OutcomeTracker DB ERROR] trade_results save failed: {e}")
        return False


def _append_outcome(row, outcome, exit_price, pnl_points, reason):
    outcome_row = {
        "closed_at": _now(),
        "trade_id": row.get("trade_id", ""),
        "opened_at": row.get("opened_at", ""),
        "symbol": row.get("symbol", ""),
        "side": row.get("side", ""),
        "entry": row.get("entry", ""),
        "sl": row.get("sl", ""),
        "target": row.get("target", ""),
        "rr": row.get("rr", ""),
        "score": row.get("score", ""),
        "rank_score": row.get("rank_score", ""),
        "alert_sent": row.get("alert_sent", ""),
        "market_status": row.get("market_status", ""),
        "outcome": outcome,
        "exit_price": exit_price,
        "pnl_points": pnl_points,
        "result_reason": reason,
    }

    with open(OUTCOMES_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
        writer.writerow(outcome_row)

    with open(OUTCOMES_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(outcome_row, ensure_ascii=False) + "\n")

    _save_trade_result_to_supabase(outcome_row)


# ---------------------------------------------------------
# MAIN TRACKER
# ---------------------------------------------------------

def track_trade_outcomes():
    _ensure_files()

    with open(ACTIVE_TRADES_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []

    if not rows:
        print("[OutcomeTracker] No active trades found.")
        return {"checked": 0, "closed": 0, "open": 0}

    checked = 0
    closed = 0
    still_open = 0
    updated_rows = []

    for row in rows:
        status = str(row.get("status", "")).upper().strip()

        if status != "OPEN":
            updated_rows.append(row)
            continue

        symbol = row.get("symbol", "")
        checked += 1

        try:
            live_price = get_live_price(symbol)

            if live_price is None:
                live_price = row.get("last_price") or row.get("entry")

            outcome, exit_price, pnl_points, reason = _check_outcome(row, live_price)

            row["last_checked_at"] = _now()
            row["last_price"] = exit_price
            row["pnl_points"] = pnl_points
            row["result_reason"] = reason

            if outcome in ["TP", "SL"]:
                row["status"] = outcome
                _append_outcome(row, outcome, exit_price, pnl_points, reason)
                closed += 1
                print(f"[OutcomeTracker] {symbol} closed: {outcome} @ {exit_price}")
            else:
                still_open += 1

        except Exception as e:
            row["last_checked_at"] = _now()
            row["result_reason"] = f"Outcome check error: {e}"
            still_open += 1
            print(f"[OutcomeTracker ERROR] {symbol}: {e}")

        updated_rows.append(row)

    default_fields = [
        "trade_id", "opened_at", "scan_id", "symbol", "side", "entry", "sl",
        "target", "rr", "score", "rank_score", "alert_sent", "market_status",
        "status", "last_checked_at", "last_price", "pnl_points", "result_reason"
    ]

    final_fields = fields or default_fields
    for field in default_fields:
        if field not in final_fields:
            final_fields.append(field)

    with open(ACTIVE_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=final_fields)
        writer.writeheader()
        writer.writerows(updated_rows)

    print(f"[OutcomeTracker] Checked: {checked} | Closed: {closed} | Still open: {still_open}")

    return {
        "checked": checked,
        "closed": closed,
        "open": still_open,
    }


if __name__ == "__main__":
    track_trade_outcomes()