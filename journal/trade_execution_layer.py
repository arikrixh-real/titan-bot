"""
TITAN Trade Execution Layer - DEDUP FINAL
-----------------------------------------
Purpose:
1. Converts all eligible good setups into OPEN internal/live trades.
2. Telegram top 3 are marked telegram_alerted=YES.
3. Remaining good setups are also stored as internal live trades.
4. Prevents duplicate OPEN trades:
   - local active_trades.csv duplicate check
   - Supabase trades table duplicate check using symbol + side + status='OPEN'
5. Stores proper trade details in Supabase trades table.
6. Does NOT insert missing columns like result into trades table.
7. Tracks TP/SL locally every run.

Important:
- This does NOT place real broker orders.
- This does NOT change Telegram alert limit.
"""

import os
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


IST = ZoneInfo("Asia/Kolkata")

ACTIVE_TRADES_FILE = "active_trades.csv"
TRADE_RESULTS_FILE = "trade_results.csv"

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
    "market_status",
    "telegram_alerted",
    "status",
    "opened_at",
    "last_checked_at",
    "last_price",
    "close_price",
    "closed_at",
    "result",
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
    "result",
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


def _read_csv(path, columns):
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns)

    try:
        df = pd.read_csv(path)

        for col in columns:
            if col not in df.columns:
                df[col] = ""

        return df[columns]

    except Exception:
        return pd.DataFrame(columns=columns)


def _write_csv(df, path, columns):
    try:
        for col in columns:
            if col not in df.columns:
                df[col] = ""

        df[columns].to_csv(path, index=False)

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


def _supabase_open_trade_exists(client, symbol, side):
    """
    Checks if same symbol+side is already OPEN in Supabase.
    Prevents duplicate open trades across GitHub runs.
    """
    try:
        result = (
            client.table("trades")
            .select("id")
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


def _insert_trade_to_supabase(row):
    """
    Inserts only columns that exist in your current Supabase trades table.
    Does not insert 'result' because your trades table does not have result column.
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

    payload = {
        "trade_id": str(row.get("trade_id", "")),
        "symbol": symbol,
        "side": side,
        "entry": _safe_float(row.get("entry")),
        "sl": _safe_float(row.get("sl")),
        "target": _safe_float(row.get("target")),
        "rr": _safe_float(row.get("rr")),
        "reason": str(row.get("reason", ""))[:500],
        "trigger_status": "INTERNAL_TRADE",
        "status": "OPEN",
        "created_at": _now_iso(),
    }

    # Optional JSON columns available in your table
    payload["scores"] = {
        "score": _safe_float(row.get("score")),
        "rank_score": _safe_float(row.get("rank_score")),
    }

    payload["market_context"] = {
        "market_status": str(row.get("market_status", "")),
    }

    payload["setup_context"] = {
        "scan_id": str(row.get("scan_id", "")),
        "telegram_alerted": str(row.get("telegram_alerted", "NO")),
        "opened_at": str(row.get("opened_at", "")),
    }

    try:
        client.table("trades").insert(payload).execute()
        return True

    except Exception as e:
        print(f"⚠️ Supabase trade insert skipped for {symbol} {side}: {e}")
        return False


def _insert_result_to_supabase_minimal():
    """
    Safe result insert.
    If trade_results schema is limited, no crash.
    """
    client = _get_supabase()

    if client is None:
        return False

    try:
        client.table("trade_results").insert({
            "created_at": _now_iso()
        }).execute()
        return True

    except Exception:
        return False


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
    Converts good setups into OPEN live/internal trades.

    Duplicate protection:
    - Skips if same symbol+side already OPEN in local CSV.
    - Skips if same symbol+side already OPEN in Supabase.
    """
    alerted_symbols = set(alerted_symbols or [])

    active_df = _read_csv(ACTIVE_TRADES_FILE, ACTIVE_COLUMNS)

    open_df = active_df[
        active_df["status"]
        .astype(str)
        .str.upper()
        .isin(["OPEN", "ACTIVE", "LIVE"])
    ].copy()

    existing_open_keys = set(
        open_df["symbol"].astype(str).str.upper()
        + "|"
        + open_df["side"].astype(str).str.upper()
    )

    new_rows = []
    supabase_added = 0
    local_added = 0
    duplicate_skipped = 0

    for setup in eligible_setups or []:
        if max_new_trades is not None and local_added >= max_new_trades:
            break

        symbol = str(setup.get("symbol", "")).strip().upper()
        side = str(setup.get("side", "")).strip().upper()

        if not symbol or side not in ["LONG", "SHORT"]:
            continue

        key = f"{symbol}|{side}"

        if key in existing_open_keys:
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

        if entry <= 0 or sl <= 0 or target <= 0 or rr <= 0:
            continue

        now_text = _now()
        trade_id = f"{scan_id}_{symbol}_{side}_{len(active_df) + len(new_rows) + 1}"

        row = {
            "trade_id": trade_id,
            "scan_id": scan_id,
            "symbol": symbol,
            "side": side,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "target": round(target, 2),
            "rr": round(rr, 2),
            "score": round(score, 2),
            "rank_score": round(rank_score, 2),
            "market_status": str(setup.get("market_status", market_status)),
            "telegram_alerted": "YES" if symbol in alerted_symbols else "NO",
            "status": "OPEN",
            "opened_at": now_text,
            "last_checked_at": now_text,
            "last_price": "",
            "close_price": "",
            "closed_at": "",
            "result": "",
            "reason": str(setup.get("reason", ""))[:500],
        }

        # Insert to Supabase first. If duplicate exists there, it returns False.
        inserted_to_supabase = _insert_trade_to_supabase(row)

        if not inserted_to_supabase:
            duplicate_skipped += 1
            continue

        new_rows.append(row)
        existing_open_keys.add(key)
        local_added += 1
        supabase_added += 1

    if new_rows:
        active_df = pd.concat([active_df, pd.DataFrame(new_rows)], ignore_index=True)

    _write_csv(active_df, ACTIVE_TRADES_FILE, ACTIVE_COLUMNS)

    print(f"📌 Active Trades Added: {len(new_rows)} new OPEN trades")
    print(f"☁️ Supabase Trades Stored: {supabase_added}")
    print(f"♻️ Duplicate OPEN trades skipped: {duplicate_skipped}")

    return len(new_rows)


def update_live_trade_outcomes():
    """
    Checks active_trades.csv and closes trades when SL/TP is hit.
    """
    active_df = _read_csv(ACTIVE_TRADES_FILE, ACTIVE_COLUMNS)
    results_df = _read_csv(TRADE_RESULTS_FILE, RESULT_COLUMNS)

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
        result = "WIN" if hit == "TARGET" else "LOSS"
        pnl = _pnl_points(side, entry, price)

        active_df.at[idx, "status"] = "CLOSED"
        active_df.at[idx, "close_price"] = round(price, 2)
        active_df.at[idx, "closed_at"] = close_time
        active_df.at[idx, "result"] = result

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
            "result": result,
            "pnl_points": pnl,
            "reason": row.get("reason", ""),
        }

        results_df = pd.concat(
            [results_df, pd.DataFrame([result_row])],
            ignore_index=True,
        )

        _insert_result_to_supabase_minimal()

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
    active_df = _read_csv(ACTIVE_TRADES_FILE, ACTIVE_COLUMNS)

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