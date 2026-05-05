
"""
TITAN - Outcome Tracker Engine FINAL
------------------------------------
Fixes:
- TP/SL trades close properly.
- Closed outcomes sync safely to Supabase trade_results.
- Matching Supabase trades are marked CLOSED / EXPIRED.
- End-of-day incomplete trades become EXPIRED / NO_TRADE.
- NO_TRADE is not a win/loss and should not be used in accuracy.
- Does not send Telegram alerts.
- Does not place broker orders.

Trading-hour rules:
- Outcomes are checked only during market hours: 09:15 to 15:30 IST.
- From 15:25 IST onwards, still-open trades expire as NO_TRADE.
"""

import csv
import json
import os
import re
from pathlib import Path
from datetime import datetime, time
from zoneinfo import ZoneInfo

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    from data.live_price import get_live_price
except Exception:
    get_live_price = None


IST = ZoneInfo("Asia/Kolkata")

JOURNAL_DIR = Path("data/journals")
ACTIVE_TRADES_CSV = JOURNAL_DIR / "active_trades.csv"
OPEN_TRADES_CSV = JOURNAL_DIR / "open_trades.csv"
OUTCOME_CSV = JOURNAL_DIR / "trade_outcomes.csv"
OUTCOME_JSONL = JOURNAL_DIR / "trade_outcomes.jsonl"

MARKET_OPEN_TIME = time(9, 15)
MARKET_CLOSE_TIME = time(15, 30)
EOD_EXPIRE_TIME = time(15, 25)

ACTIVE_FIELDS = [
    "trade_id", "opened_at", "scan_id", "symbol", "side", "entry", "sl",
    "target", "rr", "score", "rank_score", "alert_sent", "market_status",
    "status", "last_checked_at", "last_price", "pnl_points", "result_reason",
]

OUTCOME_FIELDS = [
    "closed_at", "trade_id", "opened_at", "scan_id", "symbol", "side",
    "entry", "sl", "target", "rr", "score", "rank_score", "alert_sent",
    "exit_price", "outcome", "pnl_points", "result_reason",
]


def _now_dt():
    return datetime.now(IST)


def _now():
    return _now_dt().strftime("%Y-%m-%d %H:%M:%S")


def _now_iso():
    return _now_dt().isoformat()


def is_trading_day():
    return _now_dt().weekday() < 5


def is_market_hours():
    now = _now_dt()
    return is_trading_day() and MARKET_OPEN_TIME <= now.time() <= MARKET_CLOSE_TIME


def is_eod_expiry_time():
    now = _now_dt()
    return is_trading_day() and now.time() >= EOD_EXPIRE_TIME


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def clean_symbol(symbol):
    symbol = str(symbol or "").upper().strip()
    symbol = symbol.replace(".NS", "")
    return symbol


def is_valid_symbol(symbol):
    symbol = clean_symbol(symbol)
    if not symbol:
        return False
    if re.fullmatch(r"[0-9_:-]+", symbol):
        return False
    if len(symbol) > 25:
        return False
    return True


def _ensure_csv(path, fields):
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()


def ensure_files():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_csv(ACTIVE_TRADES_CSV, ACTIVE_FIELDS)
    _ensure_csv(OPEN_TRADES_CSV, ACTIVE_FIELDS)
    _ensure_csv(OUTCOME_CSV, OUTCOME_FIELDS)
    if not OUTCOME_JSONL.exists():
        OUTCOME_JSONL.touch()


def _get_price(symbol, fallback=None):
    symbol = clean_symbol(symbol)
    if not is_valid_symbol(symbol):
        return fallback
    if get_live_price is None:
        return fallback
    try:
        price = safe_float(get_live_price(symbol))
        if price is not None and price > 0:
            return price
    except Exception:
        pass
    return fallback


def _get_supabase():
    try:
        if create_client is None:
            return None
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None


def _remove_missing_column(error_text, payload):
    match = re.search(r"Could not find the '([^']+)' column", str(error_text))
    if not match:
        return False
    missing = match.group(1)
    if missing in payload:
        payload.pop(missing, None)
        return True
    return False


def _sync_result_to_supabase(outcome_row):
    client = _get_supabase()
    if client is None:
        return False

    raw = str(outcome_row.get("outcome", "")).upper()
    if raw == "TARGET_HIT":
        result = "WIN"
    elif raw == "SL_HIT":
        result = "LOSS"
    elif raw == "NO_TRADE":
        result = "NO_TRADE"
    else:
        result = raw or "UNKNOWN"

    payload = {
        "created_at": _now_iso(),
        "trade_id": outcome_row.get("trade_id", ""),
        "symbol": outcome_row.get("symbol", ""),
        "side": outcome_row.get("side", ""),
        "entry": safe_float(outcome_row.get("entry")),
        "sl": safe_float(outcome_row.get("sl")),
        "target": safe_float(outcome_row.get("target")),
        "close_price": safe_float(outcome_row.get("exit_price")),
        "exit_price": safe_float(outcome_row.get("exit_price")),
        "result": result,
        "outcome": raw,
        "pnl_points": safe_float(outcome_row.get("pnl_points"), 0.0),
        "reason": outcome_row.get("result_reason", ""),
        "closed_at": outcome_row.get("closed_at", _now()),
    }

    payload_try = dict(payload)
    for _ in range(15):
        try:
            client.table("trade_results").insert(payload_try).execute()
            return True
        except Exception as e:
            if _remove_missing_column(str(e), payload_try):
                continue
            return False
    return False


def _update_supabase_trade_status(symbol, side, status):
    client = _get_supabase()
    if client is None:
        return False
    try:
        client.table("trades").update({"status": status}).eq("symbol", symbol).eq("side", side).eq("status", "OPEN").execute()
        return True
    except Exception:
        return False


def _evaluate(row, current_price):
    side = str(row.get("side", "")).upper().strip()
    entry = safe_float(row.get("entry"))
    sl = safe_float(row.get("sl"))
    target = safe_float(row.get("target"))

    if current_price is None:
        return "OPEN", "", "Live price unavailable"
    if entry is None or sl is None or target is None:
        return "OPEN", "", "Invalid trade levels"

    if side == "LONG":
        pnl = round(current_price - entry, 2)
        if current_price >= target:
            return "TARGET_HIT", pnl, "LONG target reached"
        if current_price <= sl:
            return "SL_HIT", pnl, "LONG stop loss reached"
        return "OPEN", pnl, "LONG trade still open"

    if side == "SHORT":
        pnl = round(entry - current_price, 2)
        if current_price <= target:
            return "TARGET_HIT", pnl, "SHORT target reached"
        if current_price >= sl:
            return "SL_HIT", pnl, "SHORT stop loss reached"
        return "OPEN", pnl, "SHORT trade still open"

    return "OPEN", "", "Invalid side"


def _outcome_row(row, exit_price, outcome, pnl_points, reason):
    return {
        "closed_at": _now(),
        "trade_id": row.get("trade_id", ""),
        "opened_at": row.get("opened_at", ""),
        "scan_id": row.get("scan_id", ""),
        "symbol": row.get("symbol", ""),
        "side": row.get("side", ""),
        "entry": row.get("entry", ""),
        "sl": row.get("sl", ""),
        "target": row.get("target", ""),
        "rr": row.get("rr", ""),
        "score": row.get("score", ""),
        "rank_score": row.get("rank_score", ""),
        "alert_sent": row.get("alert_sent", ""),
        "exit_price": exit_price if exit_price is not None else "",
        "outcome": outcome,
        "pnl_points": pnl_points,
        "result_reason": reason,
    }


def _write_active(rows):
    with open(ACTIVE_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ACTIVE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_open(rows):
    open_rows = [r for r in rows if str(r.get("status", "")).upper().strip() == "OPEN"]
    with open(OPEN_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ACTIVE_FIELDS)
        writer.writeheader()
        writer.writerows(open_rows)


def _append_outcomes(rows):
    if not rows:
        return
    with open(OUTCOME_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
        writer.writerows(rows)
    with open(OUTCOME_JSONL, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def track_trade_outcomes(limit=50):
    ensure_files()

    with open(ACTIVE_TRADES_CSV, "r", newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    updated_rows = []
    final_rows = []

    checked_count = 0
    skipped_bad_rows = 0
    expired_count = 0

    open_indices = [
        i for i, row in enumerate(all_rows)
        if str(row.get("status", "")).upper().strip() == "OPEN"
    ]

    if limit is not None:
        open_indices_to_check = open_indices[:int(limit)]
    else:
        open_indices_to_check = open_indices

    indices_to_check = set(open_indices_to_check)

    expire_now = is_eod_expiry_time()
    market_open_now = is_market_hours()

    for i, row in enumerate(all_rows):
        symbol = clean_symbol(row.get("symbol", ""))
        side = str(row.get("side", "")).upper().strip()
        row["symbol"] = symbol

        if not is_valid_symbol(symbol) or side not in ["LONG", "SHORT"]:
            skipped_bad_rows += 1
            continue

        current_status = str(row.get("status", "")).upper().strip()

        if current_status != "OPEN":
            updated_rows.append(row)
            continue

        if expire_now:
            fallback_price = safe_float(row.get("last_price"))
            current_price = _get_price(symbol, fallback=fallback_price)

            pnl_points = ""
            entry = safe_float(row.get("entry"))

            if current_price is not None and entry is not None:
                if side == "LONG":
                    pnl_points = round(current_price - entry, 2)
                elif side == "SHORT":
                    pnl_points = round(entry - current_price, 2)

            row["last_checked_at"] = _now()
            row["last_price"] = current_price if current_price is not None else ""
            row["pnl_points"] = pnl_points
            row["result_reason"] = "Expired at end of trading day; not counted in accuracy"
            row["status"] = "EXPIRED"

            out = _outcome_row(
                row=row,
                exit_price=current_price,
                outcome="NO_TRADE",
                pnl_points=pnl_points,
                reason="Expired at end of trading day; not counted in accuracy",
            )

            final_rows.append(out)
            _sync_result_to_supabase(out)
            _update_supabase_trade_status(symbol, side, "EXPIRED")
            expired_count += 1
            updated_rows.append(row)
            continue

        if not market_open_now:
            row["last_checked_at"] = _now()
            row["result_reason"] = "Outside market hours; outcome check skipped"
            updated_rows.append(row)
            continue

        if i not in indices_to_check:
            updated_rows.append(row)
            continue

        fallback_price = safe_float(row.get("last_price"))
        current_price = _get_price(symbol, fallback=fallback_price)

        outcome, pnl_points, reason = _evaluate(row, current_price)
        checked_count += 1

        row["last_checked_at"] = _now()
        row["last_price"] = current_price if current_price is not None else ""
        row["pnl_points"] = pnl_points
        row["result_reason"] = reason

        if outcome in ["TARGET_HIT", "SL_HIT"]:
            row["status"] = "CLOSED"
            final_row = _outcome_row(row, current_price, outcome, pnl_points, reason)
            final_rows.append(final_row)
            _sync_result_to_supabase(final_row)
            _update_supabase_trade_status(symbol, side, "CLOSED")
        else:
            row["status"] = "OPEN"

        updated_rows.append(row)

    _write_active(updated_rows)
    _write_open(updated_rows)
    _append_outcomes(final_rows)

    closed_targets = sum(1 for r in final_rows if r["outcome"] == "TARGET_HIT")
    closed_sls = sum(1 for r in final_rows if r["outcome"] == "SL_HIT")
    still_open = sum(1 for r in updated_rows if str(r.get("status", "")).upper().strip() == "OPEN")

    print(f"📊 Outcome Tracker Checked: {checked_count} open/internal trades")
    print(f"🧹 Skipped bad old rows: {skipped_bad_rows}")
    print(f"✅ Newly closed targets: {closed_targets}")
    print(f"❌ Newly closed SLs: {closed_sls}")
    print(f"⏳ Expired NO_TRADE at EOD: {expired_count}")
    print(f"⏳ Still open: {still_open}")

    return checked_count


if __name__ == "__main__":
    track_trade_outcomes(limit=50)