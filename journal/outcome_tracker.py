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

FINAL FIX:
- Does NOT crash if Supabase trade_results table is missing columns.
- Automatically removes missing columns reported by Supabase schema cache.
- Fixes error: Could not find the 'target' column of 'trade_results'.
"""

import csv
import json
import os
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from data.live_price import get_live_price
from utils.market_hours import is_trade_window, trade_window_text


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


def _get_supabase_client():
    try:
        from titan_master_brain.supabase_client import supabase
        if supabase is not None:
            return supabase
    except Exception:
        pass

    try:
        from titan_brain.supabase_client import supabase
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


def _now():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return round(float(value), 4)
    except Exception:
        return default


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

    active_fields = [
        "trade_id", "opened_at", "scan_id", "symbol", "side", "entry", "sl",
        "target", "rr", "score", "rank_score", "alert_sent", "market_status",
        "status", "last_checked_at", "last_price", "pnl_points", "result_reason"
    ]

    if not ACTIVE_TRADES_CSV.exists():
        with open(ACTIVE_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=active_fields)
            writer.writeheader()

    if not OUTCOMES_CSV.exists():
        with open(OUTCOMES_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
            writer.writeheader()

    if not OUTCOMES_JSONL.exists():
        OUTCOMES_JSONL.touch()


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


def _extract_missing_column(error_text):
    """
    Supabase/PGRST usually says:
    Could not find the 'target' column of 'trade_results' in the schema cache
    This function extracts target.
    """

    match = re.search(r"Could not find the '([^']+)' column", str(error_text))
    if match:
        return match.group(1)

    return None


def _update_trade_result_payload(payload):
    """
    SAFE CLOSE UPDATE:
    Updates existing LIVE trade_results row instead of inserting duplicate row.

    Why:
    Supabase has unique constraint on (symbol, side) for LIVE trades.
    Closing a trade should UPDATE the existing LIVE row to WIN/LOSS,
    not INSERT another row for the same symbol + side.

    Fallback:
    If no existing LIVE row is found, it inserts a new CLOSED result safely.
    """

    update_payload = dict(payload)

    symbol = str(update_payload.get("symbol", "")).upper().strip()
    side = str(update_payload.get("side", "")).upper().strip()
    trade_id = str(update_payload.get("trade_id", "")).strip()

    if not symbol or not side:
        print("[OutcomeTracker DB] Missing symbol/side. Result not saved.")
        return False

    update_payload["status"] = "CLOSED"

    for _ in range(10):
        try:
            if trade_id:
                existing_by_trade_id = (
                    SUPABASE.table("trade_results")
                    .select("id")
                    .eq("trade_id", trade_id)
                    .limit(1)
                    .execute()
                )

                if existing_by_trade_id.data:
                    row_id = existing_by_trade_id.data[0].get("id")
                    SUPABASE.table("trade_results").update(_json_safe(update_payload)).eq("id", row_id).execute()
                    return True

            existing_live = (
                SUPABASE.table("trade_results")
                .select("id")
                .eq("symbol", symbol)
                .eq("side", side)
                .eq("status", "LIVE")
                .limit(1)
                .execute()
            )

            if existing_live.data:
                row_id = existing_live.data[0].get("id")
                SUPABASE.table("trade_results").update(_json_safe(update_payload)).eq("id", row_id).execute()
                return True

            SUPABASE.table("trade_results").insert(_json_safe(update_payload)).execute()
            return True

        except Exception as e:
            missing_col = _extract_missing_column(e)

            if missing_col and missing_col in update_payload:
                print(f"[OutcomeTracker DB FIX] Removing missing trade_results column: {missing_col}")
                update_payload.pop(missing_col, None)
                continue

            if "duplicate key value" in str(e) or "unique_live_trade_symbol_side" in str(e):
                try:
                    existing_any = (
                        SUPABASE.table("trade_results")
                        .select("id")
                        .eq("symbol", symbol)
                        .eq("side", side)
                        .limit(1)
                        .execute()
                    )

                    if existing_any.data:
                        row_id = existing_any.data[0].get("id")
                        SUPABASE.table("trade_results").update(_json_safe(update_payload)).eq("id", row_id).execute()
                        return True

                except Exception as update_error:
                    print(f"[OutcomeTracker DB ERROR] duplicate fallback update failed: {update_error}")
                    return False

            print(f"[OutcomeTracker DB ERROR] trade_results update failed: {e}")
            return False

    print("[OutcomeTracker DB ERROR] trade_results update failed after schema cleanup retries.")
    return False


def _save_trade_result_to_supabase(outcome_row):
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

    payload = {
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
        "market_status": str(outcome_row.get("market_status", "")),
    }

    payload = _json_safe(payload)

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

        saved = _update_trade_result_payload(payload)

        if saved:
            print(f"[OutcomeTracker DB] Supabase result updated: {payload.get('symbol')} {payload.get('side')} -> {result}")
            return True

        return False

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
        f.write(json.dumps(_json_safe(outcome_row), ensure_ascii=False) + "\n")

    _save_trade_result_to_supabase(outcome_row)


def track_trade_outcomes(limit=None):
    """
    Tracks OPEN trades.

    limit is optional for backward compatibility with older callers.
    If omitted, all OPEN trades are checked.
    """
    if not is_trade_window():
        print(f"[OutcomeTracker] Skipped outside trade window ({trade_window_text()}).")
        return {"checked": 0, "closed": 0, "open": 0, "skipped": "OUTSIDE_TRADE_WINDOW"}

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
    max_checks = None

    try:
        if limit is not None:
            max_checks = max(0, int(limit))
    except Exception:
        max_checks = None

    for row in rows:
        status = str(row.get("status", "")).upper().strip()

        if status != "OPEN":
            updated_rows.append(row)
            continue

        if max_checks is not None and checked >= max_checks:
            updated_rows.append(row)
            still_open += 1
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
