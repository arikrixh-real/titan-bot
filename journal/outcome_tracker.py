"""
TITAN Outcome Tracker - FINAL ACTIVE ONLY FIX
--------------------------------------------
Fixes "Still open: 200+" by tracking only valid current OPEN trades.
- Old/stale OPEN rows become EXPIRED / NO_TRADE.
- Duplicate OPEN rows by symbol+side become EXPIRED / NO_TRADE.
- TP hit => CLOSED + WIN in Supabase trade_results.
- SL hit => CLOSED + LOSS in Supabase trade_results.
- EOD incomplete trades => EXPIRED + NO_TRADE.
- NO_TRADE should not count in accuracy.
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


def now_dt():
    return datetime.now(IST)


def now_text():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def now_iso():
    return now_dt().isoformat()


def is_trading_day():
    return now_dt().weekday() < 5


def is_market_hours():
    n = now_dt()
    return is_trading_day() and MARKET_OPEN_TIME <= n.time() <= MARKET_CLOSE_TIME


def is_eod_expiry_time():
    n = now_dt()
    return is_trading_day() and n.time() >= EOD_EXPIRE_TIME


def safe_float(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def clean_symbol(symbol):
    return str(symbol or "").upper().strip().replace(".NS", "")


def is_valid_symbol(symbol):
    symbol = clean_symbol(symbol)
    if not symbol:
        return False
    if re.fullmatch(r"[0-9_:-]+", symbol):
        return False
    return len(symbol) <= 25


def parse_dt(value):
    if not value:
        return None
    value = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt.astimezone(IST)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value[:19], fmt).replace(tzinfo=IST)
        except Exception:
            pass
    return None


def is_today_trade(row):
    dt = parse_dt(row.get("opened_at"))
    return bool(dt and dt.date() == now_dt().date())


def ensure_csv(path, fields):
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()


def ensure_files():
    ensure_csv(ACTIVE_TRADES_CSV, ACTIVE_FIELDS)
    ensure_csv(OPEN_TRADES_CSV, ACTIVE_FIELDS)
    ensure_csv(OUTCOME_CSV, OUTCOME_FIELDS)
    if not OUTCOME_JSONL.exists():
        OUTCOME_JSONL.touch()


def normalize_row(row):
    out = {k: row.get(k, "") for k in ACTIVE_FIELDS}
    out["symbol"] = clean_symbol(out.get("symbol"))
    out["side"] = str(out.get("side", "")).upper().strip()
    status = str(out.get("status", "")).upper().strip()
    if status in ("ACTIVE", "LIVE", "RUNNING"):
        status = "OPEN"
    out["status"] = status
    return out


def get_price(symbol, fallback=None):
    symbol = clean_symbol(symbol)
    if not is_valid_symbol(symbol) or get_live_price is None:
        return fallback
    try:
        p = safe_float(get_live_price(symbol))
        if p and p > 0:
            return p
    except Exception:
        pass
    return fallback


def get_supabase():
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


def remove_missing_column(err, payload):
    m = re.search(r"Could not find the '([^']+)' column", str(err))
    if not m:
        return False
    col = m.group(1)
    if col in payload:
        payload.pop(col, None)
        return True
    return False


def sync_result(outcome_row):
    client = get_supabase()
    if client is None:
        return False

    raw = str(outcome_row.get("outcome", "")).upper()
    result = "WIN" if raw == "TARGET_HIT" else "LOSS" if raw == "SL_HIT" else "NO_TRADE" if raw == "NO_TRADE" else raw

    payload = {
        "created_at": now_iso(),
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
        "closed_at": outcome_row.get("closed_at", now_text()),
    }

    for _ in range(15):
        try:
            client.table("trade_results").insert(payload).execute()
            return True
        except Exception as e:
            if remove_missing_column(e, payload):
                continue
            return False
    return False


def update_trade_status(row, status):
    client = get_supabase()
    if client is None:
        return False

    trade_id = str(row.get("trade_id", "")).strip()
    symbol = clean_symbol(row.get("symbol", ""))
    side = str(row.get("side", "")).upper().strip()

    try:
        if trade_id:
            client.table("trades").update({"status": status}).eq("trade_id", trade_id).eq("status", "OPEN").execute()
        else:
            client.table("trades").update({"status": status}).eq("symbol", symbol).eq("side", side).eq("status", "OPEN").execute()
        return True
    except Exception:
        return False


def evaluate_trade(row, price):
    side = str(row.get("side", "")).upper().strip()
    entry = safe_float(row.get("entry"))
    sl = safe_float(row.get("sl"))
    target = safe_float(row.get("target"))

    if price is None:
        return "OPEN", "", "Live price unavailable"
    if entry is None or sl is None or target is None:
        return "OPEN", "", "Invalid trade levels"

    if side == "LONG":
        pnl = round(price - entry, 2)
        if price >= target:
            return "TARGET_HIT", pnl, "LONG target reached"
        if price <= sl:
            return "SL_HIT", pnl, "LONG stop loss reached"
        return "OPEN", pnl, "LONG trade still open"

    if side == "SHORT":
        pnl = round(entry - price, 2)
        if price <= target:
            return "TARGET_HIT", pnl, "SHORT target reached"
        if price >= sl:
            return "SL_HIT", pnl, "SHORT stop loss reached"
        return "OPEN", pnl, "SHORT trade still open"

    return "OPEN", "", "Invalid side"


def make_outcome(row, exit_price, outcome, pnl, reason):
    return {
        "closed_at": now_text(),
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
        "pnl_points": pnl,
        "result_reason": reason,
    }


def expire_trade(row, reason):
    fallback = safe_float(row.get("last_price"))
    price = get_price(row.get("symbol"), fallback=fallback)
    entry = safe_float(row.get("entry"))
    side = str(row.get("side", "")).upper().strip()

    pnl = ""
    if price is not None and entry is not None:
        pnl = round(price - entry, 2) if side == "LONG" else round(entry - price, 2) if side == "SHORT" else ""

    row["last_checked_at"] = now_text()
    row["last_price"] = price if price is not None else ""
    row["pnl_points"] = pnl
    row["result_reason"] = reason
    row["status"] = "EXPIRED"

    out = make_outcome(row, price, "NO_TRADE", pnl, reason)
    sync_result(out)
    update_trade_status(row, "EXPIRED")
    return row, out


def write_active(rows):
    with open(ACTIVE_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ACTIVE_FIELDS)
        w.writeheader()
        w.writerows(rows)


def write_open(rows):
    open_rows = [r for r in rows if str(r.get("status", "")).upper().strip() == "OPEN"]
    with open(OPEN_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ACTIVE_FIELDS)
        w.writeheader()
        w.writerows(open_rows)


def append_outcomes(rows):
    if not rows:
        return
    with open(OUTCOME_CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=OUTCOME_FIELDS).writerows(rows)
    with open(OUTCOME_JSONL, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def track_trade_outcomes(limit=50):
    ensure_files()

    with open(ACTIVE_TRADES_CSV, "r", newline="", encoding="utf-8") as f:
        rows = [normalize_row(r) for r in csv.DictReader(f)]

    updated = []
    finals = []
    checked = 0
    bad = 0
    expired = 0
    stale_expired = 0
    duplicate_expired = 0
    seen = set()

    market_now = is_market_hours()
    eod_now = is_eod_expiry_time()

    for row in rows:
        symbol = clean_symbol(row.get("symbol"))
        side = str(row.get("side", "")).upper().strip()
        row["symbol"] = symbol
        row["side"] = side

        if not is_valid_symbol(symbol) or side not in ("LONG", "SHORT"):
            bad += 1
            continue

        if row.get("status") != "OPEN":
            updated.append(row)
            continue

        key = f"{symbol}|{side}"

        if not is_today_trade(row):
            row, out = expire_trade(row, "Expired stale/missing-date OPEN row; not counted in accuracy")
            updated.append(row); finals.append(out)
            expired += 1; stale_expired += 1
            continue

        if key in seen:
            row, out = expire_trade(row, "Expired duplicate OPEN row; not counted in accuracy")
            updated.append(row); finals.append(out)
            expired += 1; duplicate_expired += 1
            continue

        seen.add(key)

        if eod_now:
            row, out = expire_trade(row, "Expired at end of trading day; not counted in accuracy")
            updated.append(row); finals.append(out)
            expired += 1
            continue

        if not market_now:
            row["last_checked_at"] = now_text()
            row["result_reason"] = "Outside market hours; outcome check skipped"
            updated.append(row)
            continue

        if limit is not None and checked >= int(limit):
            updated.append(row)
            continue

        price = get_price(symbol, fallback=safe_float(row.get("last_price")))
        outcome, pnl, reason = evaluate_trade(row, price)
        checked += 1

        row["last_checked_at"] = now_text()
        row["last_price"] = price if price is not None else ""
        row["pnl_points"] = pnl
        row["result_reason"] = reason

        if outcome in ("TARGET_HIT", "SL_HIT"):
            row["status"] = "CLOSED"
            out = make_outcome(row, price, outcome, pnl, reason)
            finals.append(out)
            sync_result(out)
            update_trade_status(row, "CLOSED")
        else:
            row["status"] = "OPEN"

        updated.append(row)

    write_active(updated)
    write_open(updated)
    append_outcomes(finals)

    targets = sum(1 for r in finals if r["outcome"] == "TARGET_HIT")
    sls = sum(1 for r in finals if r["outcome"] == "SL_HIT")
    still_open = sum(1 for r in updated if str(r.get("status", "")).upper().strip() == "OPEN")

    print(f"📊 Outcome Tracker Checked: {checked} current OPEN trades")
    print(f"🧹 Skipped bad old rows: {bad}")
    print(f"✅ Newly closed targets: {targets}")
    print(f"❌ Newly closed SLs: {sls}")
    print(f"⏳ Expired NO_TRADE at EOD/stale/duplicate: {expired}")
    print(f"   └─ stale expired: {stale_expired}")
    print(f"   └─ duplicate expired: {duplicate_expired}")
    print(f"⏳ Still open: {still_open}")

    return checked


if __name__ == "__main__":
    track_trade_outcomes(limit=50)