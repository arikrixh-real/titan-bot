"""
TITAN - Trade Journal Engine
----------------------------
Journals ALL eligible setups, not only Telegram alerts.

IMPORTANT:
- Every eligible setup is stored as an internal tracked trade idea.
- Telegram alert status is only a flag.
- This does NOT send alerts.
- This does NOT limit scans.
"""

import csv
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

JOURNAL_DIR = Path("data/journals")
CSV_FILE = JOURNAL_DIR / "trade_journal.csv"
JSONL_FILE = JOURNAL_DIR / "trade_journal.jsonl"

FIELDS = [
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
    "confirmations",
    "reason",
    "alert_sent",
    "market_status",
    "status",
]


def _safe_get(setup, *keys, default=""):
    if not isinstance(setup, dict):
        return default

    for key in keys:
        if key in setup and setup[key] is not None:
            return setup[key]

    return default


def _to_text(value):
    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return " | ".join(map(str, value))

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def _safe_float_text(value):
    try:
        if value is None or value == "":
            return ""
        return str(round(float(value), 4))
    except Exception:
        return _to_text(value)


def ensure_journal_files():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    if not CSV_FILE.exists():
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()

    if not JSONL_FILE.exists():
        JSONL_FILE.touch()


def build_trade_id(scan_id, symbol, side, entry, sl, target):
    return f"{scan_id}|{symbol}|{side}|{entry}|{sl}|{target}"


def build_journal_row(setup, scan_id=None, alert_sent=False, market_status=""):
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    symbol = _to_text(_safe_get(setup, "symbol", "stock", "ticker")).upper().strip()
    side = _to_text(_safe_get(setup, "side", "direction")).upper().strip()

    entry = _safe_float_text(_safe_get(setup, "entry", "entry_price"))
    sl = _safe_float_text(_safe_get(setup, "sl", "stop_loss", "stoploss"))
    target = _safe_float_text(_safe_get(setup, "target", "tp", "t1", "target1"))

    final_scan_id = scan_id or now.replace(" ", "_").replace(":", "-")

    return {
        "trade_id": build_trade_id(final_scan_id, symbol, side, entry, sl, target),
        "timestamp": now,
        "scan_id": final_scan_id,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "sl": sl,
        "target": target,
        "rr": _safe_float_text(_safe_get(setup, "rr", "risk_reward")),
        "score": _safe_float_text(_safe_get(setup, "score", "final_score")),
        "rank_score": _safe_float_text(_safe_get(setup, "rank_score", "ranking_score")),
        "confirmations": _to_text(_safe_get(setup, "confirmations", "signals", default=[])),
        "reason": _to_text(_safe_get(setup, "reason", "setup_reason", default="")),
        "alert_sent": "YES" if alert_sent else "NO",
        "market_status": _to_text(market_status),
        "status": "OPEN",
    }


def _load_existing_trade_ids():
    ensure_journal_files()

    existing = set()

    try:
        with open(CSV_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trade_id = row.get("trade_id")
                if trade_id:
                    existing.add(trade_id)
    except Exception:
        pass

    return existing


def journal_eligible_setups(
    eligible_setups,
    scan_id=None,
    alerted_symbols=None,
    market_status="",
):
    """
    Journals ALL eligible setups.

    This is the main function called by setup_engine.py.
    Every eligible setup becomes an OPEN internal tracked trade idea.
    Telegram alerts remain only a YES/NO flag.
    """

    ensure_journal_files()

    if eligible_setups is None:
        eligible_setups = []

    alerted_symbols = set(alerted_symbols or [])
    existing_trade_ids = _load_existing_trade_ids()
    rows = []

    for setup in eligible_setups:
        symbol = _to_text(_safe_get(setup, "symbol", "stock", "ticker")).upper().strip()
        alert_sent = symbol in alerted_symbols

        row = build_journal_row(
            setup=setup,
            scan_id=scan_id,
            alert_sent=alert_sent,
            market_status=market_status,
        )

        # Avoid exact duplicate rows if same scan is re-run
        if row["trade_id"] in existing_trade_ids:
            continue

        rows.append(row)
        existing_trade_ids.add(row["trade_id"])

    if not rows:
        print("ℹ️ No new eligible setups to journal.")
        return 0

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerows(rows)

    with open(JSONL_FILE, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"📘 Trade Journal Updated: {len(rows)} internal trades journaled")
    return len(rows)