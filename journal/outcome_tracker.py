"""
TITAN - Outcome Tracker Engine
------------------------------
Stable trade lifecycle tracker.

What this does:
- Reads data/journals/active_trades.csv
- Checks OPEN trades every run
- Keeps OPEN trades active until TP or SL hits
- Writes final results to trade_outcomes.csv/jsonl
- Updates open_trades.csv for dashboard
- Does NOT send Telegram alerts
"""

import csv
import json
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

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

ACTIVE_FIELDS = [
    "trade_id",
    "opened_at",
    "scan_id",
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
    "status",
    "last_checked_at",
    "last_price",
    "pnl_points",
    "result_reason",
]

OUTCOME_FIELDS = [
    "closed_at",
    "trade_id",
    "opened_at",
    "scan_id",
    "symbol",
    "side",
    "entry",
    "sl",
    "target",
    "rr",
    "score",
    "rank_score",
    "alert_sent",
    "exit_price",
    "outcome",
    "pnl_points",
    "result_reason",
]


def _now():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


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
    open_rows = [
        row for row in rows
        if str(row.get("status", "")).upper().strip() == "OPEN"
    ]

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

    open_indices = [
        i for i, row in enumerate(all_rows)
        if str(row.get("status", "")).upper().strip() == "OPEN"
    ]

    if limit is not None:
        open_indices_to_check = open_indices[:int(limit)]
    else:
        open_indices_to_check = open_indices

    indices_to_check = set(open_indices_to_check)

    for i, row in enumerate(all_rows):
        symbol = clean_symbol(row.get("symbol", ""))
        row["symbol"] = symbol

        if not is_valid_symbol(symbol) or row.get("side", "").upper().strip() not in ["LONG", "SHORT"]:
            skipped_bad_rows += 1
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
            row["status"] = outcome
            final_rows.append(_outcome_row(row, current_price, outcome, pnl_points, reason))
        else:
            row["status"] = "OPEN"

        updated_rows.append(row)

    _write_active(updated_rows)
    _write_open(updated_rows)
    _append_outcomes(final_rows)

    print(f"📊 Outcome Tracker Checked: {checked_count} open/internal trades")
    print(f"🧹 Skipped bad old rows: {skipped_bad_rows}")
    print(f"✅ Newly closed targets: {sum(1 for row in final_rows if row['outcome'] == 'TARGET_HIT')}")
    print(f"❌ Newly closed SLs: {sum(1 for row in final_rows if row['outcome'] == 'SL_HIT')}")
    print(f"⏳ Still open: {sum(1 for row in updated_rows if row.get('status') == 'OPEN')}")

    return checked_count


if __name__ == "__main__":
    track_trade_outcomes(limit=50)