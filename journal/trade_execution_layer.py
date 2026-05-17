"""
TITAN Trade Execution Layer - SAFE LIVE TRADE SYNC FINAL
--------------------------------------------------------

Purpose:
1. Good setups become OPEN internal/live trades.
2. Telegram top 3 are marked telegram_alerted=YES in local CSV.
3. Duplicate OPEN trades are prevented locally and in Supabase.
4. Supabase trades table is used for dashboard LIVE trade count.
5. Full Entry/SL/Target/RR are safely kept in active_trades.csv.
6. No broker orders are placed.

Safe fixes:
- Uses data/journals/active_trades.csv first, matching the main journal/outcome tracker.
- Local active trade save will NOT fail just because Supabase insert fails.
- Supabase insert uses schema-safe payload and auto-removes missing columns.
- Supabase trade status is updated to CLOSED when TP/SL closes.
- Does not touch alert selection logic.
"""

import os
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    from data.live_price import get_live_price
except Exception:
    get_live_price = None

from journal.trade_id import build_canonical_trade_id
from utils.market_hours import is_trade_window, trade_window_text


IST = ZoneInfo("Asia/Kolkata")

JOURNAL_DIR = Path("data/journals")
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

ACTIVE_TRADES_FILE = str(JOURNAL_DIR / "active_trades.csv")
TRADE_RESULTS_FILE = str(JOURNAL_DIR / "trade_results.csv")

# Legacy fallback files, only used if they already exist and data/journals file is empty/missing.
LEGACY_ACTIVE_TRADES_FILE = "active_trades.csv"
LEGACY_TRADE_RESULTS_FILE = "trade_results.csv"

ACTIVE_COLUMNS = [
    "trade_id",
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
    "paper_trade_id",
    "is_paper_trade",
    "market_status",
    "telegram_alerted",
    "status",
    "opened_at",
    "last_checked_at",
    "last_price",
    "close_price",
    "exit_price",
    "closed_at",
    "result",
    "realized_pnl",
    "pnl_points",
    "reason",
]

RESULT_COLUMNS = [
    "trade_id",
    "scan_id",
    "symbol",
    "side",
    "entry",
    "sl",
    "target",
    "rr",
    "score",
    "market_status",
    "telegram_alerted",
    "opened_at",
    "closed_at",
    "close_price",
    "exit_price",
    "result",
    "quantity",
    "qty",
    "position_size",
    "capital_used",
    "risk_amount",
    "risk_per_trade_pct",
    "realized_pnl",
    "pnl_points",
    "reason",
]


def _now():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _now_iso():
    return datetime.now(IST).isoformat()


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_text(value, max_len=500):
    try:
        text = str(value or "")
        return text[:max_len]
    except Exception:
        return ""


def _read_csv(path, columns, legacy_path=None):
    selected_path = path

    if (not os.path.exists(selected_path) or os.path.getsize(selected_path) == 0) and legacy_path:
        if os.path.exists(legacy_path) and os.path.getsize(legacy_path) > 0:
            selected_path = legacy_path

    if not os.path.exists(selected_path):
        return pd.DataFrame(columns=columns)

    try:
        df = pd.read_csv(selected_path, on_bad_lines="skip")

        for col in columns:
            if col not in df.columns:
                df[col] = ""

        return df

    except Exception:
        return pd.DataFrame(columns=columns)


def _write_csv(df, path, columns):
    try:
        parent = Path(path).parent
        if str(parent) not in ["", "."]:
            parent.mkdir(parents=True, exist_ok=True)

        for col in columns:
            if col not in df.columns:
                df[col] = ""

        final_columns = list(df.columns)
        for col in columns:
            if col not in final_columns:
                final_columns.append(col)
        df[final_columns].to_csv(path, index=False)

    except Exception as e:
        print(f"⚠️ Could not write {path}: {e}")


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


def _extract_missing_column(error_text):
    match = re.search(r"Could not find the '([^']+)' column", str(error_text))
    if match:
        return match.group(1)
    return None


def _safe_supabase_insert(client, table_name, payload):
    """
    Insert payload safely. If Supabase schema cache rejects a column,
    remove that column and retry.
    """
    clean = dict(payload)

    for _ in range(10):
        try:
            client.table(table_name).insert(clean).execute()
            return True

        except Exception as e:
            missing_col = _extract_missing_column(e)

            if missing_col and missing_col in clean:
                print(f"⚠️ Supabase {table_name} missing column removed: {missing_col}")
                clean.pop(missing_col, None)
                continue

            print(f"⚠️ Supabase {table_name} insert skipped: {e}")
            return False

    return False


def _safe_supabase_update_trade_closed(client, trade_id, result="", close_price=None, closed_at=None):
    """
    Updates Supabase trades row to CLOSED for dashboard live count.
    Uses safe retry if some columns do not exist.
    """
    if client is None or not trade_id:
        return False

    payload = {
        "status": "CLOSED",
        "result": result,
        "close_price": close_price,
        "closed_at": closed_at or _now_iso(),
        "updated_at": _now_iso(),
    }

    clean = dict(payload)

    for _ in range(10):
        try:
            client.table("trades").update(clean).eq("trade_id", trade_id).execute()
            return True

        except Exception as e:
            missing_col = _extract_missing_column(e)

            if missing_col and missing_col in clean:
                print(f"⚠️ Supabase trades update missing column removed: {missing_col}")
                clean.pop(missing_col, None)
                continue

            print(f"⚠️ Supabase trades status update skipped for {trade_id}: {e}")
            return False

    return False


def _supabase_open_trade_exists(client, symbol, side):
    try:
        result = (
            client.table("trades")
            .select("trade_id")
            .eq("symbol", symbol)
            .eq("side", side)
            .eq("status", "OPEN")
            .limit(1)
            .execute()
        )

        return bool(result.data)

    except Exception as e:
        print(f"⚠️ Supabase duplicate check skipped for {symbol} {side}: {e}")
        return False


def _local_open_trade_exists(active_df, symbol, side):
    try:
        open_df = active_df[
            active_df["status"]
            .astype(str)
            .str.upper()
            .isin(["OPEN", "ACTIVE", "LIVE"])
        ].copy()

        keys = set(
            open_df["symbol"].astype(str).str.upper()
            + "|"
            + open_df["side"].astype(str).str.upper()
        )

        return f"{symbol}|{side}" in keys

    except Exception:
        return False


def _insert_trade_to_supabase(row):
    """
    Safe Supabase insert for dashboard live-trade sync.
    Full details stay in local active_trades.csv.
    """
    client = _get_supabase()

    if client is None:
        return False

    symbol = str(row.get("symbol", "")).strip().upper()
    side = str(row.get("side", "")).strip().upper()

    if not symbol or not side:
        return False

    if _supabase_open_trade_exists(client, symbol, side):
        return False

    # Include useful fields; _safe_supabase_insert removes any missing schema columns.
    payload = {
        "trade_id": str(row.get("trade_id", "")),
        "symbol": symbol,
        "side": side,
        "status": "OPEN",
        "entry": _safe_float(row.get("entry")),
        "sl": _safe_float(row.get("sl")),
        "stop_loss": _safe_float(row.get("sl")),
        "target": _safe_float(row.get("target")),
        "rr": _safe_float(row.get("rr")),
        "score": _safe_float(row.get("score")),
        "rank_score": _safe_float(row.get("rank_score")),
        "quantity": _safe_float(row.get("quantity") or row.get("qty")),
        "qty": _safe_float(row.get("quantity") or row.get("qty")),
        "position_size": _safe_float(row.get("position_size")),
        "capital_used": _safe_float(row.get("capital_used") or row.get("position_size")),
        "risk_amount": _safe_float(row.get("risk_amount")),
        "risk_per_trade_pct": _safe_float(row.get("risk_per_trade_pct"), 1.0),
        "paper_trade_id": row.get("paper_trade_id"),
        "is_paper_trade": row.get("is_paper_trade") or True,
        "market_status": _safe_text(row.get("market_status"), 1000),
        "telegram_alerted": str(row.get("telegram_alerted", "NO")),
        "reason": _safe_text(row.get("reason"), 500),
        "trigger_status": "INTERNAL_TRADE",
        "opened_at": _now_iso(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    return _safe_supabase_insert(client, "trades", payload)


def _insert_result_to_supabase_minimal(result_row):
    """
    Minimal trade_results insert. If outcome tracker already saves results,
    duplicate/schema errors are skipped safely.
    """
    client = _get_supabase()

    if client is None:
        return False

    payload = {
        "trade_id": str(result_row.get("trade_id", "")),
        "symbol": str(result_row.get("symbol", "")).upper(),
        "side": str(result_row.get("side", "")).upper(),
        "entry": _safe_float(result_row.get("entry")),
        "exit_price": _safe_float(result_row.get("close_price")),
        "close_price": _safe_float(result_row.get("close_price")),
        "result": str(result_row.get("result", "")),
        "outcome": "TP" if str(result_row.get("result", "")).upper() == "WIN" else "SL",
        "pnl_points": _safe_float(result_row.get("pnl_points")),
        "pnl": _safe_float(result_row.get("realized_pnl")),
        "realized_pnl": _safe_float(result_row.get("realized_pnl")),
        "quantity": _safe_float(result_row.get("quantity") or result_row.get("qty")),
        "qty": _safe_float(result_row.get("quantity") or result_row.get("qty")),
        "position_size": _safe_float(result_row.get("position_size")),
        "capital_used": _safe_float(result_row.get("capital_used") or result_row.get("position_size")),
        "risk_amount": _safe_float(result_row.get("risk_amount")),
        "risk_per_trade_pct": _safe_float(result_row.get("risk_per_trade_pct"), 1.0),
        "closed_at": result_row.get("closed_at") or _now_iso(),
        "reason": _safe_text(result_row.get("reason"), 500),
        "created_at": _now_iso(),
    }

    return _safe_supabase_insert(client, "trade_results", payload)


def _trade_hit_result(side, price, sl, target):
    side = str(side).upper()

    if side == "LONG":
        if price >= target:
            return "TARGET"
        if price <= sl:
            return "SL"

    if side == "SHORT":
        if price <= target:
            return "TARGET"
        if price >= sl:
            return "SL"

    return ""


def _pnl_points(side, entry, close_price):
    side = str(side).upper()

    if side == "LONG":
        return round(close_price - entry, 2)

    if side == "SHORT":
        return round(entry - close_price, 2)

    return 0.0


def add_good_setups_as_live_trades(
    eligible_setups,
    scan_id,
    alerted_symbols=None,
    market_status="",
    max_new_trades=None,
):
    """
    Adds valid setups as OPEN trades.

    Important safety:
    - Local active trade is saved even if Supabase insert fails.
    - Duplicate prevention is local-first.
    - Supabase sync is best-effort for dashboard live count.
    """
    if not is_trade_window():
        print(f"🛡️ Trade Execution add skipped outside trade window ({trade_window_text()})")
        return 0

    alerted_symbols = set(alerted_symbols or [])

    active_df = _read_csv(
        ACTIVE_TRADES_FILE,
        ACTIVE_COLUMNS,
        legacy_path=LEGACY_ACTIVE_TRADES_FILE,
    )

    new_rows = []
    supabase_added = 0
    local_added = 0
    duplicate_skipped = 0

    for setup in eligible_setups or []:
        if max_new_trades is not None and local_added >= max_new_trades:
            break
        try:
            from engines.paper_trading_engine import prepare_paper_trade_fields
            setup = prepare_paper_trade_fields(setup if isinstance(setup, dict) else {})
        except Exception:
            setup = setup if isinstance(setup, dict) else {}

        symbol = str(setup.get("symbol", "")).strip().upper()
        side = str(setup.get("side", "")).strip().upper()

        if not symbol or side not in ["LONG", "SHORT"]:
            continue

        if _local_open_trade_exists(active_df, symbol, side):
            duplicate_skipped += 1
            continue

        entry = _safe_float(setup.get("entry"))
        sl = _safe_float(setup.get("sl"))
        target = _safe_float(setup.get("target"))
        rr = _safe_float(setup.get("rr"))
        score = _safe_float(setup.get("score"))
        rank_score = _safe_float(
            setup.get("rank_score", setup.get("elite_probability_score", score))
        )
        quantity = _safe_float(setup.get("quantity") or setup.get("qty"))
        position_size = _safe_float(setup.get("position_size"))
        skip_reason = str(setup.get("skip_reason") or "").strip()

        if entry <= 0 or sl <= 0 or target <= 0 or rr <= 0:
            continue
        if quantity < 1 or position_size <= 0 or skip_reason:
            continue

        now_text = _now()

        safe_scan_id = str(scan_id or "")
        trade_id = build_canonical_trade_id(
            safe_scan_id,
            symbol,
            side,
            entry,
            sl,
            target,
            source="TradeExecution",
        )
        if not trade_id:
            continue

        row = {
            "trade_id": trade_id,
            "scan_id": safe_scan_id,
            "symbol": symbol,
            "side": side,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "target": round(target, 2),
            "rr": round(rr, 2),
            "score": round(score, 2),
            "rank_score": round(rank_score, 2),
            "quantity": quantity,
            "qty": quantity,
            "position_size": round(position_size, 2),
            "capital_used": round(_safe_float(setup.get("capital_used"), position_size), 2),
            "risk_amount": round(_safe_float(setup.get("risk_amount")), 2),
            "risk_per_trade_pct": round(_safe_float(setup.get("risk_per_trade_pct"), 1.0), 4),
            "risk_per_share": round(_safe_float(setup.get("risk_per_share")), 4),
            "paper_trade_id": setup.get("paper_trade_id", ""),
            "is_paper_trade": setup.get("is_paper_trade", True),
            "market_status": str(setup.get("market_status", market_status)),
            "telegram_alerted": "YES" if symbol in alerted_symbols else "NO",
            "status": "OPEN",
            "opened_at": now_text,
            "last_checked_at": now_text,
            "last_price": "",
            "close_price": "",
            "exit_price": "",
            "closed_at": "",
            "result": "",
            "realized_pnl": "",
            "pnl_points": "",
            "reason": _safe_text(setup.get("reason", ""), 500),
        }

        # Local trade is always added first.
        new_rows.append(row)
        local_added += 1

        # Supabase sync is best-effort and will not block local tracking.
        if _insert_trade_to_supabase(row):
            supabase_added += 1

        active_df = pd.concat([active_df, pd.DataFrame([row])], ignore_index=True)

    _write_csv(active_df, ACTIVE_TRADES_FILE, ACTIVE_COLUMNS)

    print(f"📌 Active Trades Added: {len(new_rows)} new OPEN trades")
    print(f"☁️ Supabase Trades Stored: {supabase_added}")
    print(f"♻️ Duplicate OPEN trades skipped: {duplicate_skipped}")

    return len(new_rows)


def update_live_trade_outcomes():
    if not is_trade_window():
        print(f"🛡️ Trade Execution outcome update skipped outside trade window ({trade_window_text()})")
        return {
            "checked": 0,
            "closed_targets": 0,
            "closed_sls": 0,
            "still_open": 0,
            "skipped": "OUTSIDE_TRADE_WINDOW",
        }

    active_df = _read_csv(
        ACTIVE_TRADES_FILE,
        ACTIVE_COLUMNS,
        legacy_path=LEGACY_ACTIVE_TRADES_FILE,
    )
    results_df = _read_csv(
        TRADE_RESULTS_FILE,
        RESULT_COLUMNS,
        legacy_path=LEGACY_TRADE_RESULTS_FILE,
    )

    if active_df.empty:
        print("📊 Trade Execution Layer: 0 active trades")
        return {
            "checked": 0,
            "closed_targets": 0,
            "closed_sls": 0,
            "still_open": 0,
        }

    open_indices = active_df[
        active_df["status"]
        .astype(str)
        .str.upper()
        .isin(["OPEN", "ACTIVE", "LIVE"])
    ].index.tolist()

    checked = 0
    closed_targets = 0
    closed_sls = 0

    client = _get_supabase()

    for idx in open_indices:
        row = active_df.loc[idx]

        symbol = str(row.get("symbol", "")).strip().upper()
        side = str(row.get("side", "")).strip().upper()

        entry = _safe_float(row.get("entry"))
        sl = _safe_float(row.get("sl"))
        target = _safe_float(row.get("target"))

        if not symbol or get_live_price is None:
            continue

        try:
            price = _safe_float(get_live_price(symbol))
        except Exception:
            price = 0.0

        if price <= 0:
            continue

        checked += 1

        active_df.at[idx, "last_checked_at"] = _now()
        active_df.at[idx, "last_price"] = round(price, 2)

        hit = _trade_hit_result(side, price, sl, target)

        if hit not in ["TARGET", "SL"]:
            continue

        close_time = _now()
        close_iso = _now_iso()
        result = "WIN" if hit == "TARGET" else "LOSS"
        pnl = _pnl_points(side, entry, price)
        quantity = _safe_float(row.get("quantity") or row.get("qty"))
        realized_pnl = round(pnl * quantity, 2) if quantity > 0 else ""

        active_df.at[idx, "status"] = "CLOSED"
        active_df.at[idx, "close_price"] = round(price, 2)
        active_df.at[idx, "exit_price"] = round(price, 2)
        active_df.at[idx, "closed_at"] = close_time
        active_df.at[idx, "result"] = result
        active_df.at[idx, "realized_pnl"] = realized_pnl

        result_row = {
            "trade_id": row.get("trade_id", ""),
            "scan_id": row.get("scan_id", ""),
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "sl": sl,
            "target": target,
            "rr": _safe_float(row.get("rr")),
            "score": _safe_float(row.get("score")),
            "market_status": row.get("market_status", ""),
            "telegram_alerted": row.get("telegram_alerted", ""),
            "opened_at": row.get("opened_at", ""),
            "closed_at": close_time,
            "close_price": round(price, 2),
            "exit_price": round(price, 2),
            "result": result,
            "quantity": quantity,
            "qty": quantity,
            "position_size": _safe_float(row.get("position_size")),
            "capital_used": _safe_float(row.get("capital_used") or row.get("position_size")),
            "risk_amount": _safe_float(row.get("risk_amount")),
            "risk_per_trade_pct": _safe_float(row.get("risk_per_trade_pct"), 1.0),
            "realized_pnl": realized_pnl,
            "pnl_points": pnl,
            "reason": row.get("reason", ""),
        }

        results_df = pd.concat(
            [results_df, pd.DataFrame([result_row])],
            ignore_index=True,
        )

        _safe_supabase_update_trade_closed(
            client=client,
            trade_id=str(row.get("trade_id", "")),
            result=result,
            close_price=round(price, 2),
            closed_at=close_iso,
        )

        _insert_result_to_supabase_minimal(result_row)

        if result == "WIN":
            closed_targets += 1
        else:
            closed_sls += 1

    _write_csv(active_df, ACTIVE_TRADES_FILE, ACTIVE_COLUMNS)
    _write_csv(results_df, TRADE_RESULTS_FILE, RESULT_COLUMNS)

    still_open = len(
        active_df[
            active_df["status"]
            .astype(str)
            .str.upper()
            .isin(["OPEN", "ACTIVE", "LIVE"])
        ]
    )

    print(f"📊 Trade Execution Checked: {checked} OPEN trades")
    print(f"✅ Newly closed targets: {closed_targets}")
    print(f"❌ Newly closed SLs: {closed_sls}")
    print(f"⏳ Still open: {still_open}")

    return {
        "checked": checked,
        "closed_targets": closed_targets,
        "closed_sls": closed_sls,
        "still_open": still_open,
    }


def get_live_trades_count():
    active_df = _read_csv(
        ACTIVE_TRADES_FILE,
        ACTIVE_COLUMNS,
        legacy_path=LEGACY_ACTIVE_TRADES_FILE,
    )

    if active_df.empty:
        return 0

    return len(
        active_df[
            active_df["status"]
            .astype(str)
            .str.upper()
            .isin(["OPEN", "ACTIVE", "LIVE"])
        ]
    )
