"""
TITAN - Outcome Tracker Engine
------------------------------
Tracks whether journaled eligible setups hit TARGET or SL.

Input:
- data/journals/trade_journal.csv

Output:
- data/journals/trade_outcomes.csv
- data/journals/trade_outcomes.jsonl

This file does NOT:
- Send Telegram alerts
- Change daily alert cap
- Change scan/filter logic
"""

import csv
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from data.live_price import get_live_price
except Exception:
    get_live_price = None


IST = ZoneInfo("Asia/Kolkata")

JOURNAL_FILE = Path("data/journals/trade_journal.csv")
OUTCOME_CSV = Path("data/journals/trade_outcomes.csv")
OUTCOME_JSONL = Path("data/journals/trade_outcomes.jsonl")

OUTCOME_FIELDS = [
    "checked_at",
    "timestamp",
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
    "current_price",
    "outcome",
    "pnl_points",
    "result_reason",
]


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def ensure_outcome_files():
    OUTCOME_CSV.parent.mkdir(parents=True, exist_ok=True)

    if not OUTCOME_CSV.exists():
        with open(OUTCOME_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
            writer.writeheader()

    if not OUTCOME_JSONL.exists():
        OUTCOME_JSONL.touch()


def load_existing_keys():
    """
    Prevent duplicate outcome rows for same setup.
    Key = scan_id + symbol + side + entry
    """
    ensure_outcome_files()

    keys = set()

    with open(OUTCOME_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            key = make_key(row)
            keys.add(key)

    return keys


def make_key(row):
    return (
        str(row.get("scan_id", "")),
        str(row.get("symbol", "")),
        str(row.get("side", "")),
        str(row.get("entry", "")),
    )


def get_current_price(symbol):
    """
    Uses existing TITAN live price engine.
    If unavailable, returns None safely.
    """
    if get_live_price is None:
        return None

    try:
        return safe_float(get_live_price(symbol))
    except Exception:
        return None


def evaluate_outcome(side, entry, sl, target, current_price):
    """
    Evaluates current outcome.

    LONG:
    - target hit if current_price >= target
    - SL hit if current_price <= sl

    SHORT:
    - target hit if current_price <= target
    - SL hit if current_price >= sl
    """

    side = str(side).upper().strip()

    if current_price is None:
        return "OPEN", 0.0, "Live price unavailable"

    if entry is None or sl is None or target is None:
        return "OPEN", 0.0, "Invalid trade levels"

    if side == "LONG":
        pnl_points = current_price - entry

        if current_price >= target:
            return "TARGET_HIT", round(pnl_points, 2), "LONG target reached"

        if current_price <= sl:
            return "SL_HIT", round(pnl_points, 2), "LONG stop loss reached"

        return "OPEN", round(pnl_points, 2), "LONG trade still open"

    if side == "SHORT":
        pnl_points = entry - current_price

        if current_price <= target:
            return "TARGET_HIT", round(pnl_points, 2), "SHORT target reached"

        if current_price >= sl:
            return "SL_HIT", round(pnl_points, 2), "SHORT stop loss reached"

        return "OPEN", round(pnl_points, 2), "SHORT trade still open"

    return "OPEN", 0.0, "Invalid side"


def build_outcome_row(journal_row):
    symbol = journal_row.get("symbol", "")
    side = journal_row.get("side", "")

    entry = safe_float(journal_row.get("entry"))
    sl = safe_float(journal_row.get("sl"))
    target = safe_float(journal_row.get("target"))

    current_price = get_current_price(symbol)

    outcome, pnl_points, result_reason = evaluate_outcome(
        side=side,
        entry=entry,
        sl=sl,
        target=target,
        current_price=current_price,
    )

    return {
        "checked_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": journal_row.get("timestamp", ""),
        "scan_id": journal_row.get("scan_id", ""),
        "symbol": symbol,
        "side": side,
        "entry": journal_row.get("entry", ""),
        "sl": journal_row.get("sl", ""),
        "target": journal_row.get("target", ""),
        "rr": journal_row.get("rr", ""),
        "score": journal_row.get("score", ""),
        "rank_score": journal_row.get("rank_score", ""),
        "alert_sent": journal_row.get("alert_sent", ""),
        "current_price": current_price if current_price is not None else "",
        "outcome": outcome,
        "pnl_points": pnl_points,
        "result_reason": result_reason,
    }


def track_trade_outcomes(limit=None):
    """
    Main function.
    Reads trade journal and writes outcome rows.
    """

    ensure_outcome_files()

    if not JOURNAL_FILE.exists():
        print("⚠️ Trade journal not found. Run setup engine first.")
        return 0

    existing_keys = load_existing_keys()
    new_rows = []

    with open(JOURNAL_FILE, "r", newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    if limit is not None:
        reader = reader[-int(limit):]

    for journal_row in reader:
        key = make_key(journal_row)

        if key in existing_keys:
            continue

        outcome_row = build_outcome_row(journal_row)
        new_rows.append(outcome_row)
        existing_keys.add(key)

    if not new_rows:
        print("ℹ️ No new trades to track.")
        return 0

    with open(OUTCOME_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
        writer.writerows(new_rows)

    with open(OUTCOME_JSONL, "a", encoding="utf-8") as f:
        for row in new_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"📊 Outcome Tracker Updated: {len(new_rows)} trades checked")

    target_hits = sum(1 for row in new_rows if row["outcome"] == "TARGET_HIT")
    sl_hits = sum(1 for row in new_rows if row["outcome"] == "SL_HIT")
    open_trades = sum(1 for row in new_rows if row["outcome"] == "OPEN")

    print(f"✅ Target hits: {target_hits}")
    print(f"❌ SL hits: {sl_hits}")
    print(f"⏳ Open trades: {open_trades}")

    return len(new_rows)


if __name__ == "__main__":
    track_trade_outcomes(limit=200)