"""
TITAN - Trade Journal Engine
----------------------------
Journals ALL eligible setups, not only Telegram alerts.

Stores:
symbol, side, entry, SL, target, RR, score, rank_score,
confirmations, reason, timestamp, alert_sent, market_status
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


def ensure_journal_files():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    if not CSV_FILE.exists():
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()

    if not JSONL_FILE.exists():
        JSONL_FILE.touch()


def build_journal_row(setup, scan_id=None, alert_sent=False, market_status=""):
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "timestamp": now,
        "scan_id": scan_id or now.replace(" ", "_").replace(":", "-"),
        "symbol": _safe_get(setup, "symbol", "stock", "ticker"),
        "side": _safe_get(setup, "side", "direction"),
        "entry": _safe_get(setup, "entry", "entry_price"),
        "sl": _safe_get(setup, "sl", "stop_loss", "stoploss"),
        "target": _safe_get(setup, "target", "tp", "t1", "target1"),
        "rr": _safe_get(setup, "rr", "risk_reward"),
        "score": _safe_get(setup, "score", "final_score"),
        "rank_score": _safe_get(setup, "rank_score", "ranking_score"),
        "confirmations": _to_text(
            _safe_get(setup, "confirmations", "signals", default=[])
        ),
        "reason": _to_text(
            _safe_get(setup, "reason", "setup_reason", default="")
        ),
        "alert_sent": bool(alert_sent),
        "market_status": _to_text(market_status),
    }


def journal_eligible_setups(
    eligible_setups,
    scan_id=None,
    alerted_symbols=None,
    market_status="",
):
    ensure_journal_files()

    if eligible_setups is None:
        eligible_setups = []

    alerted_symbols = set(alerted_symbols or [])
    rows = []

    for setup in eligible_setups:
        symbol = _safe_get(setup, "symbol", "stock", "ticker")
        alert_sent = symbol in alerted_symbols

        row = build_journal_row(
            setup=setup,
            scan_id=scan_id,
            alert_sent=alert_sent,
            market_status=market_status,
        )

        rows.append(row)

    if not rows:
        return 0

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerows(rows)

    with open(JSONL_FILE, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return len(rows)
def journal_eligible_setups(eligible_setups, scan_id, alerted_symbols, market_status):
    import csv
    from pathlib import Path
    from datetime import datetime

    file_path = Path("data/trade_journal.csv")
    file_path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = file_path.exists()

    with open(file_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "timestamp", "scan_id", "symbol", "side",
                "entry", "sl", "target", "rr",
                "score", "status", "alerted"
            ])

        for setup in eligible_setups:
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                scan_id,
                setup.get("symbol"),
                setup.get("side"),
                setup.get("entry"),
                setup.get("sl"),
                setup.get("target"),
                setup.get("rr"),
                setup.get("score"),
                "OPEN",
                "YES" if setup.get("symbol") in alerted_symbols else "NO"
            ])