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
import shutil
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from journal.trade_id import build_canonical_trade_id
from core.truth_gate import validate_trade_setup, write_status as write_truth_gate_status
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
    "quantity",
    "qty",
    "position_size",
    "capital_used",
    "risk_amount",
    "risk_per_trade_pct",
    "risk_per_share",
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
    "entry_price",
    "stop_loss",
    "tp",
    "rr",
    "score",
    "rank_score",
    "quantity",
    "qty",
    "position_size",
    "capital_used",
    "risk_amount",
    "risk_per_trade_pct",
    "risk_per_share",
    "sizing_valid",
    "skip_reason",
    "paper_trade_id",
    "is_paper_trade",
    "test_trade",
    "source",
    "alert_sent",
    "market_status",
    "status",
    "outcome",
    "result",
    "last_checked_at",
    "last_price",
    "pnl_points",
    "result_reason",
]

LEGACY_SHIFTED_ACTIVE_FIELDS = [
    "trade_id",
    "opened_at",
    "scan_id",
    "symbol",
    "side",
    "entry",
    "sl",
    "target",
    "entry_price",
    "stop_loss",
    "tp",
    "rr",
    "score",
    "rank_score",
    "quantity",
    "qty",
    "position_size",
    "capital_used",
    "risk_amount",
    "risk_per_trade_pct",
    "risk_per_share",
    "sizing_valid",
    "skip_reason",
    "paper_trade_id",
    "is_paper_trade",
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


def _looks_like_trade_id(value):
    parts = str(value or "").strip().split("|")
    return len(parts) >= 6 and parts[2].upper() in {"LONG", "SHORT"}


def _is_number(value):
    try:
        float(value)
        return True
    except Exception:
        return False


def _looks_shifted_active_row(header, raw_row):
    if not raw_row:
        return False

    row_by_header = {
        field: raw_row[index] if index < len(raw_row) else ""
        for index, field in enumerate(header)
    }

    return (
        _looks_like_trade_id(raw_row[0])
        or _looks_like_trade_id(row_by_header.get("symbol"))
        or (
            _is_number(row_by_header.get("status"))
            and str(row_by_header.get("last_checked_at", "")).upper().strip() in {"OPEN", "CLOSED", "TP", "SL"}
        )
    )


def _active_row_from_position(raw_row):
    source_fields = ACTIVE_FIELDS if len(raw_row) >= len(ACTIVE_FIELDS) else LEGACY_SHIFTED_ACTIVE_FIELDS
    repaired = {field: "" for field in ACTIVE_FIELDS}

    for index, value in enumerate(raw_row):
        if index >= len(source_fields):
            break
        repaired[source_fields[index]] = value

    if not repaired.get("entry_price"):
        repaired["entry_price"] = repaired.get("entry", "")
    if not repaired.get("stop_loss"):
        repaired["stop_loss"] = repaired.get("sl", "")
    if not repaired.get("tp"):
        repaired["tp"] = repaired.get("target", "")

    status = str(repaired.get("status", "")).upper().strip()
    if status in {"TP", "SL"}:
        repaired["outcome"] = repaired.get("outcome") or status
        repaired["result"] = repaired.get("result") or ("WIN" if status == "TP" else "LOSS")
        repaired["status"] = "CLOSED"

    return repaired


def _backup_csv_before_rewrite(path):
    backup_path = path.with_name(f"{path.stem}.backup{path.suffix}")
    shutil.copyfile(path, backup_path)
    return backup_path


def _rewrite_csv(path, fields, rows, repaired_count=0, backup_path=None):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    if path == ACTIVE_TRADES_CSV:
        print(f"[TradeJournal CSV Repair] repaired rows: {repaired_count}")
        print(f"[TradeJournal CSV Repair] rewritten schema: {','.join(fields)}")
        if backup_path is not None:
            print(f"[TradeJournal CSV Repair] backup path: {backup_path}")


def _ensure_csv(path, fields):
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    if not path.exists() or path.stat().st_size == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
        return

    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            raw_rows = list(reader)

        if not raw_rows:
            return

        existing_fields = raw_rows[0]
        data_rows = raw_rows[1:]
        repaired_count = 0
        normalized_rows = []

        for raw_row in data_rows:
            if path == ACTIVE_TRADES_CSV and _looks_shifted_active_row(existing_fields, raw_row):
                normalized_rows.append(_active_row_from_position(raw_row))
                repaired_count += 1
                continue

            row = {
                field: raw_row[index] if index < len(raw_row) else ""
                for index, field in enumerate(existing_fields)
            }
            normalized_rows.append({field: row.get(field, "") for field in fields})

        if existing_fields == fields and repaired_count == 0:
            return

        backup_path = _backup_csv_before_rewrite(path) if path == ACTIVE_TRADES_CSV else None
        _rewrite_csv(path, fields, normalized_rows, repaired_count, backup_path)

    except Exception as e:
        print(f"[TradeJournal CSV Repair] schema validation failed for {path}: {e}")


def _paper_fields(setup):
    try:
        from engines.paper_trading_engine import prepare_paper_trade_fields
        return prepare_paper_trade_fields(setup if isinstance(setup, dict) else {})
    except Exception:
        return setup if isinstance(setup, dict) else {}


def ensure_files():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_csv(TRADE_JOURNAL_CSV, JOURNAL_FIELDS)

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
        from data.active_trade_store import load_canonical_open_trades

        for row in load_canonical_open_trades():
            if str(row.get("status", "")).upper().strip() == "OPEN":
                keys.add(_active_key(row))

    except Exception:
        pass

    return keys


def _build_trade_id(scan_id, symbol, side, entry, sl, target):
    return build_canonical_trade_id(
        scan_id,
        symbol,
        side,
        entry,
        sl,
        target,
        source="TradeJournal",
    )


def _build_rows(setup, scan_id, alert_sent, market_status):
    timestamp = _now()
    setup = _paper_fields(setup)

    symbol = _symbol(_safe_get(setup, "symbol", "stock", "ticker"))
    side = _side(_safe_get(setup, "side", "direction"))

    entry = _float_text(_safe_get(setup, "entry", "entry_price"))
    sl = _float_text(_safe_get(setup, "sl", "stop_loss", "stoploss"))
    target = _float_text(_safe_get(setup, "target", "tp", "t1", "target1"))
    quantity = _float_text(_safe_get(setup, "quantity", "qty"))
    position_size = _float_text(_safe_get(setup, "position_size"))
    capital_used = _float_text(_safe_get(setup, "capital_used", "position_size"))
    risk_amount = _float_text(_safe_get(setup, "risk_amount"))
    risk_pct = _float_text(_safe_get(setup, "risk_per_trade_pct", default=1.0))
    risk_per_share = _float_text(_safe_get(setup, "risk_per_share"))
    sizing_valid = _text(_safe_get(setup, "sizing_valid", default=""))
    skip_reason = _text(_safe_get(setup, "skip_reason", default=""))
    paper_trade_id = _text(_safe_get(setup, "paper_trade_id", "trade_id", default=""))

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
        "quantity": quantity,
        "qty": quantity,
        "position_size": position_size,
        "capital_used": capital_used,
        "risk_amount": risk_amount,
        "risk_per_trade_pct": risk_pct,
        "risk_per_share": risk_per_share,
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
        "entry_price": entry,
        "stop_loss": sl,
        "tp": target,
        "rr": rr,
        "score": score,
        "rank_score": rank_score,
        "quantity": quantity,
        "qty": quantity,
        "position_size": position_size,
        "capital_used": capital_used,
        "risk_amount": risk_amount,
        "risk_per_trade_pct": risk_pct,
        "risk_per_share": risk_per_share,
        "sizing_valid": sizing_valid,
        "skip_reason": skip_reason,
        "paper_trade_id": paper_trade_id,
        "is_paper_trade": "true",
        "alert_sent": alert_text,
        "market_status": market_text,
        "status": "OPEN",
        "outcome": "",
        "result": "",
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

    try:
        if float(row.get("quantity") or row.get("qty") or 0) < 1:
            return False
        if row.get("sizing_valid") not in ["", None, True, "True", "true", "1", "YES"]:
            return False
        if str(row.get("skip_reason") or "").strip():
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
        trade_gate = validate_trade_setup(setup)
        write_truth_gate_status(trade_validation_status=trade_gate)
        if trade_gate.get("status") != "PASS":
            print(f"[TruthGate] Trade journal skipped invalid setup: {trade_gate.get('reason')}")
            continue

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
        from data.active_trade_store import append_open_trade

        for row in new_active_rows:
            append_open_trade(row)

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

        trade_gate = validate_trade_setup(trade_data)
        write_truth_gate_status(trade_validation_status=trade_gate)
        if trade_gate.get("status") != "PASS":
            print(f"[TruthGate] log_trade skipped invalid setup: {trade_gate.get('reason')}")
            return ""

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
