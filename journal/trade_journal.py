"""
TITAN - Trade Journal Engine
----------------------------
Stable trade lifecycle journal.

What this does:
- Journals ALL eligible setups.
- Opens internal tracked trades for ALL valid setups.
- Telegram alert status is only a YES/NO flag.
- Prevents duplicate OPEN trades with same symbol/side/entry/sl/target.
- Does NOT send Telegram alerts.
- Does NOT modify setup selection.
"""

import csv
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.market_hours import is_trade_window, trade_window_text

IST = ZoneInfo("Asia/Kolkata")

JOURNAL_DIR = Path("data/journals")

TRADE_JOURNAL_CSV = JOURNAL_DIR / "trade_journal.csv"
TRADE_JOURNAL_JSONL = JOURNAL_DIR / "trade_journal.jsonl"

ACTIVE_TRADES_CSV = JOURNAL_DIR / "active_trades.csv"

JOURNAL_FIELDS = [
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
    "confirmations",
    "reason",
    "alert_sent",
    "market_status",
]

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


def _now():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _safe_get(setup, *keys, default=""):
    if not isinstance(setup, dict):
        return default

    for key in keys:
        if key in setup and setup[key] is not None:
            return setup[key]

    return default


def _text(value):
    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return " | ".join(map(str, value))

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def _float_text(value):
    try:
        if value is None or value == "":
            return ""
        return str(round(float(value), 4))
    except Exception:
        return _text(value)


def _symbol(value):
    value = str(value or "").upper().strip()
    value = value.replace(".NS", "")
    return value


def _side(value):
    return str(value or "").upper().strip()


def _ensure_csv(path, fields):
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    if not path.exists() or path.stat().st_size == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()


def ensure_files():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_csv(TRADE_JOURNAL_CSV, JOURNAL_FIELDS)
    _ensure_csv(ACTIVE_TRADES_CSV, ACTIVE_FIELDS)

    if not TRADE_JOURNAL_JSONL.exists():
        TRADE_JOURNAL_JSONL.touch()


def _active_key(row):
    return "|".join([
        _symbol(row.get("symbol", "")),
        _side(row.get("side", "")),
        _float_text(row.get("entry", "")),
        _float_text(row.get("sl", "")),
        _float_text(row.get("target", "")),
    ])


def _load_existing_open_keys():
    ensure_files()

    keys = set()

    try:
        with open(ACTIVE_TRADES_CSV, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                if str(row.get("status", "")).upper().strip() == "OPEN":
                    keys.add(_active_key(row))

    except Exception:
        pass

    return keys


def _build_trade_id(scan_id, symbol, side, entry, sl, target):
    return f"{scan_id}|{symbol}|{side}|{entry}|{sl}|{target}"


def _build_rows(setup, scan_id, alert_sent, market_status):
    timestamp = _now()

    symbol = _symbol(_safe_get(setup, "symbol", "stock", "ticker"))
    side = _side(_safe_get(setup, "side", "direction"))

    entry = _float_text(_safe_get(setup, "entry", "entry_price"))
    sl = _float_text(_safe_get(setup, "sl", "stop_loss", "stoploss"))
    target = _float_text(_safe_get(setup, "target", "tp", "t1", "target1"))

    rr = _float_text(_safe_get(setup, "rr", "risk_reward"))
    score = _float_text(_safe_get(setup, "score", "final_score"))
    rank_score = _float_text(_safe_get(setup, "rank_score", "ranking_score"))

    confirmations = _text(_safe_get(setup, "confirmations", "signals", default=[]))
    reason = _text(_safe_get(setup, "reason", "setup_reason", default=""))

    alert_text = "YES" if alert_sent else "NO"
    market_text = _text(market_status)

    journal_row = {
        "timestamp": timestamp,
        "scan_id": scan_id,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "sl": sl,
        "target": target,
        "rr": rr,
        "score": score,
        "rank_score": rank_score,
        "confirmations": confirmations,
        "reason": reason,
        "alert_sent": alert_text,
        "market_status": market_text,
    }

    active_row = {
        "trade_id": _build_trade_id(scan_id, symbol, side, entry, sl, target),
        "opened_at": timestamp,
        "scan_id": scan_id,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "sl": sl,
        "target": target,
        "rr": rr,
        "score": score,
        "rank_score": rank_score,
        "alert_sent": alert_text,
        "market_status": market_text,
        "status": "OPEN",
        "last_checked_at": "",
        "last_price": "",
        "pnl_points": "",
        "result_reason": "New internal trade opened",
    }

    return journal_row, active_row


def _valid_trade(row):
    if row["symbol"] == "" or row["side"] not in ["LONG", "SHORT"]:
        return False

    for field in ["entry", "sl", "target"]:
        try:
            value = float(row[field])
            if value <= 0:
                return False
        except Exception:
            return False

    return True


def journal_eligible_setups(
    eligible_setups,
    scan_id=None,
    alerted_symbols=None,
    market_status="",
):
    """
    Called by setup_engine.py.

    Every eligible setup:
    - is written to trade_journal.csv
    - becomes an OPEN active internal trade unless same trade is already OPEN
    """

    if not is_trade_window():
        print(f"🛡️ Trade Journal skipped outside trade window ({trade_window_text()})")
        return 0

    ensure_files()

    eligible_setups = eligible_setups or []
    alerted_symbols = set(alerted_symbols or [])

    if scan_id is None:
        scan_id = datetime.now(IST).strftime("%Y%m%d_%H%M%S")

    journal_rows = []
    new_active_rows = []

    existing_open_keys = _load_existing_open_keys()

    for setup in eligible_setups:
        symbol = _symbol(_safe_get(setup, "symbol", "stock", "ticker"))
        alert_sent = symbol in {_symbol(s) for s in alerted_symbols}

        journal_row, active_row = _build_rows(
            setup=setup,
            scan_id=scan_id,
            alert_sent=alert_sent,
            market_status=market_status,
        )

        if not _valid_trade(active_row):
            continue

        journal_rows.append(journal_row)

        key = _active_key(active_row)

        if key not in existing_open_keys:
            new_active_rows.append(active_row)
            existing_open_keys.add(key)

    if journal_rows:
        with open(TRADE_JOURNAL_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=JOURNAL_FIELDS)
            writer.writerows(journal_rows)

        with open(TRADE_JOURNAL_JSONL, "a", encoding="utf-8") as f:
            for row in journal_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if new_active_rows:
        with open(ACTIVE_TRADES_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ACTIVE_FIELDS)
            writer.writerows(new_active_rows)

    print(f"📘 Trade Journal Updated: {len(journal_rows)} setups journaled")
    print(f"📌 Active Trades Added: {len(new_active_rows)} new OPEN trades")

    return len(journal_rows)

# ------------------------------------------------------------
# TITAN COMPATIBILITY FIX
# ------------------------------------------------------------
# Some existing engines import:
#     from journal.trade_journal import log_trade
#
# Your journal engine mainly uses journal_eligible_setups().
# This wrapper keeps old imports working without changing the
# existing trade journal lifecycle.
# ------------------------------------------------------------

def log_trade(trade_data, scan_id=None, alert_sent=False, market_status=""):
    """
    Compatibility wrapper for engines that expect log_trade().

    IMPORTANT:
    This function returns a generated trade_id string, not True/False.
    Returning True was causing Supabase to receive trade_id=true,
    which created duplicate key errors.

    Returns:
        str -> generated trade_id when trade is valid/logged
        ""  -> failed safely / invalid trade
    """

    try:
        if not is_trade_window():
            print(f"[TradeJournal] log_trade skipped outside trade window ({trade_window_text()})")
            return ""

        if trade_data is None:
            return ""

        if not isinstance(trade_data, dict):
            trade_data = {"reason": str(trade_data)}

        if scan_id is None:
            scan_id = datetime.now(IST).strftime("%Y%m%d_%H%M%S")

        journal_row, active_row = _build_rows(
            setup=trade_data,
            scan_id=scan_id,
            alert_sent=alert_sent,
            market_status=market_status,
        )

        if not _valid_trade(active_row):
            return ""

        journal_eligible_setups(
            eligible_setups=[trade_data],
            scan_id=scan_id,
            alerted_symbols=[active_row["symbol"]] if alert_sent else [],
            market_status=market_status,
        )

        return active_row["trade_id"]

    except Exception as e:
        print(f"[TradeJournal] log_trade compatibility wrapper failed: {e}")
        return ""
