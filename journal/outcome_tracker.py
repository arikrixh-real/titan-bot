"""
TITAN - Outcome Tracker Engine
------------------------------
Tracks whether journaled eligible setups hit TARGET or SL.

IMPORTANT:
- Reads ALL OPEN journaled setups.
- Keeps checking OPEN trades every run.
- Writes final TARGET_HIT / SL_HIT only once.
- Also writes latest OPEN snapshot so dashboard can see active trades.
- Does NOT send Telegram alerts.
- Does NOT change daily alert cap.
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
OPEN_TRADES_CSV = Path("data/journals/open_trades.csv")

OUTCOME_FIELDS = [
    "checked_at",
    "trade_id",
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

OPEN_FIELDS = OUTCOME_FIELDS


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

    if not OPEN_TRADES_CSV.exists():
        with open(OPEN_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OPEN_FIELDS)
            writer.writeheader()


def make_key(row):
    trade_id = row.get("trade_id")
    if trade_id:
        return str(trade_id)

    return "|".join([
        str(row.get("scan_id", "")),
        str(row.get("symbol", "")),
        str(row.get("side", "")),
        str(row.get("entry", "")),
        str(row.get("sl", "")),
        str(row.get("target", "")),
    ])


def load_closed_trade_keys():
    """
    Only final TARGET_HIT / SL_HIT rows close a trade.
    OPEN rows must NOT block future checks.
    """

    ensure_outcome_files()

    closed = set()

    with open(OUTCOME_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            if row.get("outcome") in ["TARGET_HIT", "SL_HIT"]:
                closed.add(make_key(row))

    return closed


def get_current_price(symbol):
    if get_live_price is None:
        return None

    try:
        return safe_float(get_live_price(symbol))
    except Exception:
        return None


def evaluate_outcome(side, entry, sl, target, current_price):
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
    symbol = str(journal_row.get("symbol", "")).upper().strip()
    side = str(journal_row.get("side", "")).upper().strip()

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

    trade_id = journal_row.get("trade_id") or make_key(journal_row)

    return {
        "checked_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "trade_id": trade_id,
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


def _write_open_trades(open_rows):
    with open(OPEN_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OPEN_FIELDS)
        writer.writeheader()
        writer.writerows(open_rows)


def _append_final_outcomes(final_rows):
    if not final_rows:
        return

    with open(OUTCOME_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
        writer.writerows(final_rows)

    with open(OUTCOME_JSONL, "a", encoding="utf-8") as f:
        for row in final_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def track_trade_outcomes(limit=None):
    """
    Main function.

    Reads journaled trades.
    Keeps checking OPEN trades every 5-min run.
    Saves final outcome once TP/SL is hit.
    """

    ensure_outcome_files()

    if not JOURNAL_FILE.exists():
        print("⚠️ Trade journal not found. Run setup engine first.")
        return 0

    closed_trade_keys = load_closed_trade_keys()

    with open(JOURNAL_FILE, "r", newline="", encoding="utf-8") as f:
        journal_rows = list(csv.DictReader(f))

    if limit is not None:
        journal_rows = journal_rows[-int(limit):]

    open_rows = []
    final_rows = []
    checked_count = 0

    for journal_row in journal_rows:
        trade_key = make_key(journal_row)

        # Already closed previously
        if trade_key in closed_trade_keys:
            continue

        outcome_row = build_outcome_row(journal_row)
        checked_count += 1

        if outcome_row["outcome"] in ["TARGET_HIT", "SL_HIT"]:
            final_rows.append(outcome_row)
            closed_trade_keys.add(trade_key)
        else:
            open_rows.append(outcome_row)

    _append_final_outcomes(final_rows)
    _write_open_trades(open_rows)

    print(f"📊 Outcome Tracker Checked: {checked_count} open/internal trades")
    print(f"✅ Newly closed targets: {sum(1 for row in final_rows if row['outcome'] == 'TARGET_HIT')}")
    print(f"❌ Newly closed SLs: {sum(1 for row in final_rows if row['outcome'] == 'SL_HIT')}")
    print(f"⏳ Still open: {len(open_rows)}")

    return checked_count


if __name__ == "__main__":
    track_trade_outcomes(limit=500)