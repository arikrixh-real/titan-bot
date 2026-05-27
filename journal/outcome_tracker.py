"""
TITAN - Outcome Tracker Safe Engine
STEP 9A - SUPABASE DASHBOARD RESULT FIX

Purpose:
- Reads OPEN trades from data/journals/active_trades.csv
- Gets latest price
- Checks TP/SL hit
- Updates active_trades.csv status
- Writes completed outcomes to:
    data/journals/trade_outcomes.csv
    data/journals/trade_outcomes.jsonl
- Saves every CLOSED TP/SL result to Supabase trade_results
  so deployed dashboard updates without Git memory push.

Safe:
- Does not send alerts
- Does not place broker orders
- Does not delete trades

FINAL FIX:
- Does NOT crash if Supabase trade_results table is missing columns.
- Automatically removes missing columns reported by Supabase schema cache.
- Fixes error: Could not find the 'target' column of 'trade_results'.
"""

import csv
import json
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from data.live_price import get_strict_fresh_price_debug
from journal.trade_id import build_setup_signature
from journal.trade_journal import ACTIVE_FIELDS, _ensure_csv as _ensure_active_csv_schema
from core.truth_gate import validate_outcome_check, write_status as write_truth_gate_status
from utils.market_hours import is_trade_window, trade_window_text

try:
    from engines.trade_lifecycle_intelligence import (
        observe_trade_lifecycle_safely,
        update_lifecycle_memory_safely,
    )
except Exception:
    observe_trade_lifecycle_safely = None
    update_lifecycle_memory_safely = None

try:
    from engines.reinforcement_learning_layer import build_reinforcement_learning_report
    print("PHASE 20 REINFORCEMENT LEARNING ACTIVE")
except Exception:
    build_reinforcement_learning_report = None

try:
    from engines.paper_trading_engine import sync_paper_account_from_trade_results
except Exception:
    sync_paper_account_from_trade_results = None


IST = ZoneInfo("Asia/Kolkata")

JOURNAL_DIR = Path("data/journals")
LEARNING_DIR = Path("data/learning")
MEMORY_DIR = Path("data/memory")
RUNTIME_DIR = Path("data/runtime")
ACTIVE_TRADES_CSV = JOURNAL_DIR / "active_trades.csv"
OUTCOMES_CSV = JOURNAL_DIR / "trade_outcomes.csv"
LOCAL_TRADE_RESULTS_CSV = JOURNAL_DIR / "trade_results.csv"
OUTCOMES_JSONL = JOURNAL_DIR / "trade_outcomes.jsonl"
OUTCOME_TRACKER_STATUS_PATH = RUNTIME_DIR / "outcome_tracker_status.json"
TRADE_LIFECYCLE_RECONCILIATION_PATH = RUNTIME_DIR / "trade_lifecycle_reconciliation.json"
REINFORCEMENT_REPORTS_JSONL = LEARNING_DIR / "reinforcement_learning_reports.jsonl"
REINFORCEMENT_MEMORY_JSON = MEMORY_DIR / "reinforcement_learning_memory.json"
MAX_TP_SL_PRICE_AGE_SECONDS = 120

OUTCOME_FIELDS = [
    "closed_at",
    "trade_id",
    "opened_at",
    "symbol",
    "side",
    "entry",
    "sl",
    "target",
    "entry_price",
    "stop_loss",
    "tp",
    "quantity",
    "qty",
    "position_size",
    "capital_used",
    "risk_amount",
    "risk_per_trade_pct",
    "risk_per_share",
    "paper_trade_id",
    "is_paper_trade",
    "test_trade",
    "source",
    "rr",
    "score",
    "rank_score",
    "alert_sent",
    "market_status",
    "outcome",
    "exit_price",
    "realized_pnl",
    "pnl_points",
    "result_reason",
    "reinforcement_score",
    "reinforcement_learning_action",
    "reinforcement_risk_adjusted_reward",
    "reinforcement_drawdown_penalty",
    "reinforcement_false_confidence_penalty",
    "reinforcement_delayed_reward",
    "reinforcement_regime_key",
    "reinforcement_strategy_reward",
    "reinforcement_memory_priority",
    "reinforcement_exploration_score",
    "reinforcement_policy_stability",
    "reinforcement_explanations",
]


def _get_supabase_client():
    try:
        from titan_master_brain.supabase_client import supabase
        if supabase is not None:
            return supabase
    except Exception:
        pass

    try:
        from titan_brain.supabase_client import supabase
        if supabase is not None:
            return supabase
    except Exception:
        pass

    try:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            print("[OutcomeTracker DB] Supabase secrets missing. Dashboard DB result not saved.")
            return None

        return create_client(url, key)

    except Exception as e:
        print(f"[OutcomeTracker DB] Supabase client unavailable: {e}")
        return None


SUPABASE = _get_supabase_client()


def _now():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return round(float(value), 4)
    except Exception:
        return default


def _calc_realized_pnl(row, exit_price):
    entry = _safe_float(row.get("entry_price") or row.get("entry"))
    quantity = _safe_float(row.get("quantity") or row.get("qty"))
    side = str(row.get("side") or "LONG").upper().strip()
    if entry <= 0 or exit_price <= 0 or quantity <= 0:
        return ""
    pnl = (exit_price - entry) * quantity if side == "LONG" else (entry - exit_price) * quantity
    return round(pnl, 2)


def _json_safe(value):
    try:
        if hasattr(value, "item"):
            value = value.item()
    except Exception:
        pass

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)


def _today_bounds_iso():
    start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _row_setup_signature(row):
    if not isinstance(row, dict):
        return ""
    existing = str(row.get("setup_signature") or "").strip().upper()
    if existing:
        return existing
    return build_setup_signature(
        row.get("symbol"),
        row.get("side") or row.get("direction"),
        row.get("entry") or row.get("entry_price") or row.get("price"),
        row.get("sl") or row.get("stop_loss") or row.get("stoploss"),
        row.get("target") or row.get("tp") or row.get("target_price") or row.get("t1"),
    )


def _same_day_trade_result_setup_exists(setup_signature, exclude_trade_id=""):
    if SUPABASE is None or not setup_signature:
        return False

    start_iso, end_iso = _today_bounds_iso()
    for time_col in ("opened_at", "created_at", "closed_at"):
        try:
            result = (
                SUPABASE.table("trade_results")
                .select("*")
                .gte(time_col, start_iso)
                .lt(time_col, end_iso)
                .limit(1000)
                .execute()
            )
        except Exception:
            continue

        for row in result.data or []:
            if exclude_trade_id and str(row.get("trade_id") or "").strip() == exclude_trade_id:
                continue
            if _row_setup_signature(row) == setup_signature:
                return True

    return False


def _read_reinforcement_memory():
    try:
        if not REINFORCEMENT_MEMORY_JSON.exists() or REINFORCEMENT_MEMORY_JSON.stat().st_size == 0:
            return {}
        data = json.loads(REINFORCEMENT_MEMORY_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _reinforcement_context(row, outcome_row):
    context = {
        "market_status": row.get("market_status") or outcome_row.get("market_status"),
    }
    market_status = str(context.get("market_status") or "").strip()
    if market_status:
        context["market_regime"] = market_status
    return context


def _append_reinforcement_report(report):
    try:
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
        with open(REINFORCEMENT_REPORTS_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(_json_safe(report), ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _attach_reinforcement_learning_fields(row, outcome_row):
    """
    Shadow-only reinforcement learning attachment.
    Does not mutate live strategy weights, execution, alerts, or policy.
    """
    if build_reinforcement_learning_report is None:
        return outcome_row

    result = dict(outcome_row)

    try:
        memory = _read_reinforcement_memory()
        context = _reinforcement_context(row, result)
        report = build_reinforcement_learning_report(row, result, context=context, memory=memory)

        result["reinforcement_score"] = report.get("final_reinforcement_score")
        result["reinforcement_learning_action"] = report.get("learning_action")
        result["reinforcement_risk_adjusted_reward"] = report.get("risk_adjusted_reward")
        result["reinforcement_drawdown_penalty"] = report.get("drawdown_penalty")
        result["reinforcement_false_confidence_penalty"] = report.get("false_confidence_penalty")
        result["reinforcement_delayed_reward"] = report.get("delayed_reward")
        result["reinforcement_regime_key"] = report.get("regime_reward_key")
        result["reinforcement_strategy_reward"] = report.get("strategy_reward")
        result["reinforcement_memory_priority"] = report.get("memory_priority")
        result["reinforcement_exploration_score"] = report.get("exploration_exploitation_score")
        result["reinforcement_policy_stability"] = json.dumps(
            _json_safe(report.get("policy_stability", {})),
            ensure_ascii=False,
        )
        result["reinforcement_explanations"] = json.dumps(
            _json_safe(report.get("explanations", [])),
            ensure_ascii=False,
        )

        stored_report = dict(report)
        stored_report["trade_id"] = result.get("trade_id")
        stored_report["closed_at"] = result.get("closed_at")
        _append_reinforcement_report(stored_report)
    except Exception as e:
        result["reinforcement_error"] = str(e)

    return result


def _ensure_files():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)

    if not ACTIVE_TRADES_CSV.exists():
        with open(ACTIVE_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ACTIVE_FIELDS)
            writer.writeheader()
    else:
        _ensure_active_csv_schema(ACTIVE_TRADES_CSV, ACTIVE_FIELDS)

    if not OUTCOMES_CSV.exists():
        with open(OUTCOMES_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
            writer.writeheader()
    else:
        _ensure_csv_columns(OUTCOMES_CSV, OUTCOME_FIELDS)

    if LOCAL_TRADE_RESULTS_CSV.exists():
        _ensure_csv_columns(LOCAL_TRADE_RESULTS_CSV, OUTCOME_FIELDS)

    if not OUTCOMES_JSONL.exists():
        OUTCOMES_JSONL.touch()

    if not REINFORCEMENT_REPORTS_JSONL.exists():
        REINFORCEMENT_REPORTS_JSONL.touch()


def _ensure_csv_columns(path, required_fields):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_fields = reader.fieldnames or []
            rows = list(reader)
        ordered_fields = []
        seen = set()
        for field in list(required_fields or []) + list(existing_fields or []):
            if field and field not in seen:
                ordered_fields.append(field)
                seen.add(field)
        if existing_fields == ordered_fields:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ordered_fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in ordered_fields})
    except Exception:
        pass


def _write_outcome_tracker_status(result):
    payload = dict(result or {})
    payload.setdefault("generated_at_ist", datetime.now(IST).isoformat())
    payload.setdefault("timestamp_ist", payload["generated_at_ist"])
    payload.setdefault("status", "OUTCOME_TRACKER_STATUS_UPDATED")
    payload.setdefault("mode", "visibility_only")
    payload["broker_orders"] = False
    payload["telegram_alerts"] = False
    payload["supabase_destructive_cleanup"] = False
    payload["live_execution_mutation"] = False
    payload["safety_flags"] = {
        "advisory_only": True,
        "affects_live_ranking": False,
        "affects_execution": False,
        "broker_mutation": False,
        "telegram_mutation": False,
        "supabase_mutation": False,
        "live_order_behavior": False,
        "recommended_live_weight": 0.0,
        "rank_adjustment": 0.0,
    }
    try:
        reconciliation = json.loads(TRADE_LIFECYCLE_RECONCILIATION_PATH.read_text(encoding="utf-8"))
        if isinstance(reconciliation, dict):
            stale_count = int((reconciliation.get("stale_open_trades") or {}).get("count") or 0)
            eod_count = int((reconciliation.get("eod_unresolved_trades") or {}).get("count") or 0)
            learning_count = int((reconciliation.get("learning_open_trades") or {}).get("count") or 0)
            payload["lifecycle_reconciliation_status"] = {
                "status": "MANUAL_RECONCILIATION_REQUIRED" if stale_count or eod_count else "CLEAR",
                "stale_open_trades": stale_count,
                "eod_unresolved_trades": eod_count,
                "learning_open_trades": learning_count,
                "message": "Stale/EOD unresolved trades are visibility-only and were not fake closed.",
            }
    except Exception:
        payload["lifecycle_reconciliation_status"] = {
            "status": "UNKNOWN",
            "message": "Trade lifecycle reconciliation artifact unavailable.",
        }
    OUTCOME_TRACKER_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTCOME_TRACKER_STATUS_PATH.with_suffix(f"{OUTCOME_TRACKER_STATUS_PATH.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(OUTCOME_TRACKER_STATUS_PATH)
    return payload


def _parse_opened_at_date(value):
    text = str(value or "").strip()
    if not text:
        return None

    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)

    return parsed.astimezone(IST).date()


def _expire_previous_day_open_trades():
    """
    Closes stale local OPEN rows without creating TP/SL outcomes.

    Previous-day local active trades must not be evaluated against a later
    session's prices. This only rewrites active_trades.csv and deliberately
    avoids trade_outcomes, JSONL, and Supabase result sync.
    """
    summary = {
        "expired_count": 0,
        "expired_symbols": [],
        "skipped_same_day_count": 0,
        "error": None,
    }

    try:
        _ensure_files()

        with open(ACTIVE_TRADES_CSV, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        today = datetime.now(IST).date()
        checked_at = _now()
        updated_rows = []

        for row in rows:
            status = str(row.get("status", "")).upper().strip()
            if status != "OPEN":
                updated_rows.append(row)
                continue

            opened_date = _parse_opened_at_date(row.get("opened_at"))
            if opened_date is None:
                updated_rows.append(row)
                continue

            if opened_date >= today:
                summary["skipped_same_day_count"] += 1
                updated_rows.append(row)
                continue

            row["status"] = "EOD_UNRESOLVED"
            row["outcome"] = ""
            row["result"] = ""
            row["last_checked_at"] = checked_at
            row["result_reason"] = "EOD_UNRESOLVED: previous trading date open without TP/SL confirmation"

            symbol = str(row.get("symbol", "")).upper().strip()
            if symbol:
                summary["expired_symbols"].append(symbol)
            summary["expired_count"] += 1
            updated_rows.append(row)

        if summary["expired_count"]:
            with open(ACTIVE_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=ACTIVE_FIELDS, extrasaction="ignore")
                writer.writeheader()
                for row in updated_rows:
                    writer.writerow({field: row.get(field, "") for field in ACTIVE_FIELDS})

        print(
            "[OutcomeTracker EXPIRE] "
            f"expired_count={summary['expired_count']} "
            f"expired_symbols={summary['expired_symbols']} "
            f"skipped_same_day_count={summary['skipped_same_day_count']}"
        )
        return summary

    except Exception as e:
        summary["error"] = str(e)
        print(f"[OutcomeTracker EXPIRE ERROR] {e}")
        return summary


def _check_outcome(row, live_price):
    side = str(row.get("side", "")).upper().strip()

    entry = _safe_float(row.get("entry"))
    sl = _safe_float(row.get("sl"))
    target = _safe_float(row.get("target"))
    price = _safe_float(live_price)

    if side == "LONG":
        if price <= sl:
            return "SL", sl, round(sl - entry, 4), "LONG stop loss hit"
        if price >= target:
            return "TP", target, round(target - entry, 4), "LONG target hit"

    if side == "SHORT":
        if price >= sl:
            return "SL", sl, round(entry - sl, 4), "SHORT stop loss hit"
        if price <= target:
            return "TP", target, round(entry - target, 4), "SHORT target hit"

    pnl = round(price - entry if side == "LONG" else entry - price, 4)
    return "OPEN", price, pnl, "Still open"


def _result_from_outcome(outcome):
    outcome = str(outcome or "").upper().strip()
    if outcome == "TP":
        return "WIN"
    if outcome == "SL":
        return "LOSS"
    return ""


def _normalize_active_trade_lifecycle(row):
    """
    Backward-compatible migration for old active_trades rows that used TP/SL
    as lifecycle status. New lifecycle status is OPEN or CLOSED only.
    """
    status = str(row.get("status", "")).upper().strip()

    if status not in {"TP", "SL"}:
        return status, False

    outcome = status
    result = _result_from_outcome(outcome)

    row["status"] = "CLOSED"
    row["outcome"] = row.get("outcome") or outcome
    row["result"] = row.get("result") or result
    if not row.get("result_reason"):
        row["result_reason"] = "Legacy TP/SL lifecycle status normalized"

    symbol = str(row.get("symbol", "")).upper().strip() or "UNKNOWN"
    print(
        f"[OutcomeTracker NORMALIZE] {symbol}: legacy status={status} "
        f"normalized to status=CLOSED outcome={outcome} result={result}"
    )

    return "CLOSED", True


def _extract_missing_column(error_text):
    """
    Supabase/PGRST usually says:
    Could not find the 'target' column of 'trade_results' in the schema cache
    This function extracts target.
    """

    match = re.search(r"Could not find the '([^']+)' column", str(error_text))
    if match:
        return match.group(1)

    return None


def _update_trade_result_payload(payload):
    """
    SAFE CLOSE UPDATE:
    Updates existing LIVE trade_results row instead of inserting duplicate row.

    Why:
    Supabase has unique constraint on (symbol, side) for LIVE trades.
    Closing a trade should UPDATE the existing LIVE row to WIN/LOSS,
    not INSERT another row for the same symbol + side.

    Fallback:
    If no existing LIVE row is found, it inserts a new CLOSED result safely.
    """

    update_payload = dict(payload)

    symbol = str(update_payload.get("symbol", "")).upper().strip()
    side = str(update_payload.get("side", "")).upper().strip()
    trade_id = str(update_payload.get("trade_id", "")).strip()

    if not symbol or not side:
        print("[OutcomeTracker DB] Missing symbol/side. Result not saved.")
        return False

    update_payload["status"] = "CLOSED"

    for _ in range(10):
        try:
            if trade_id:
                existing_by_trade_id = (
                    SUPABASE.table("trade_results")
                    .select("id")
                    .eq("trade_id", trade_id)
                    .limit(1)
                    .execute()
                )

                if existing_by_trade_id.data:
                    row_id = existing_by_trade_id.data[0].get("id")
                    SUPABASE.table("trade_results").update({
                        "status": update_payload.get("status"),
                        "result": update_payload.get("result"),
                        "outcome": update_payload.get("outcome"),
                        "entry": update_payload.get("entry"),
                        "exit_price": update_payload.get("exit_price"),
                        "stop_loss": update_payload.get("stop_loss"),
                        "target": update_payload.get("target"),
                        "quantity": update_payload.get("quantity"),
                        "qty": update_payload.get("qty"),
                        "position_size": update_payload.get("position_size"),
                        "capital_used": update_payload.get("capital_used"),
                        "risk_amount": update_payload.get("risk_amount"),
                        "risk_per_trade_pct": update_payload.get("risk_per_trade_pct"),
                        "pnl": update_payload.get("realized_pnl"),
                        "realized_pnl": update_payload.get("realized_pnl"),
                        "pnl_points": update_payload.get("pnl_points"),
                        "closed_at": update_payload.get("closed_at"),
                        "reason": update_payload.get("reason"),
                        "market_status": update_payload.get("market_status"),
                        "updated_at": _now(),
                    }).eq("id", row_id).execute()
                    return True

            existing_live = (
                SUPABASE.table("trade_results")
                .select("id")
                .eq("symbol", symbol)
                .eq("side", side)
                .eq("status", "LIVE")
                .limit(1)
                .execute()
            )

            if existing_live.data:
                row_id = existing_live.data[0].get("id")
                SUPABASE.table("trade_results").update({
                    "status": update_payload.get("status"),
                    "result": update_payload.get("result"),
                    "outcome": update_payload.get("outcome"),
                    "entry": update_payload.get("entry"),
                    "exit_price": update_payload.get("exit_price"),
                    "stop_loss": update_payload.get("stop_loss"),
                    "target": update_payload.get("target"),
                    "quantity": update_payload.get("quantity"),
                    "qty": update_payload.get("qty"),
                    "position_size": update_payload.get("position_size"),
                    "capital_used": update_payload.get("capital_used"),
                    "risk_amount": update_payload.get("risk_amount"),
                    "risk_per_trade_pct": update_payload.get("risk_per_trade_pct"),
                    "pnl": update_payload.get("realized_pnl"),
                    "realized_pnl": update_payload.get("realized_pnl"),
                    "pnl_points": update_payload.get("pnl_points"),
                    "closed_at": update_payload.get("closed_at"),
                    "reason": update_payload.get("reason"),
                    "market_status": update_payload.get("market_status"),
                    "updated_at": _now(),
                }).eq("id", row_id).execute()
                return True

            SUPABASE.table("trade_results").insert(_json_safe(update_payload)).execute()
            return True

        except Exception as e:
            missing_col = _extract_missing_column(e)

            if missing_col and missing_col in update_payload:
                print(f"[OutcomeTracker DB FIX] Removing missing trade_results column: {missing_col}")
                update_payload.pop(missing_col, None)
                continue

            if "duplicate key value" in str(e) or "unique_live_trade_symbol_side" in str(e):
                try:
                    existing_any = (
                        SUPABASE.table("trade_results")
                        .select("id")
                        .eq("symbol", symbol)
                        .eq("side", side)
                        .limit(1)
                        .execute()
                    )

                    if existing_any.data:
                        row_id = existing_any.data[0].get("id")
                        SUPABASE.table("trade_results").update({
                            "status": update_payload.get("status"),
                            "result": update_payload.get("result"),
                            "outcome": update_payload.get("outcome"),
                            "entry": update_payload.get("entry"),
                            "exit_price": update_payload.get("exit_price"),
                            "stop_loss": update_payload.get("stop_loss"),
                            "target": update_payload.get("target"),
                            "quantity": update_payload.get("quantity"),
                            "qty": update_payload.get("qty"),
                            "position_size": update_payload.get("position_size"),
                            "capital_used": update_payload.get("capital_used"),
                            "risk_amount": update_payload.get("risk_amount"),
                            "risk_per_trade_pct": update_payload.get("risk_per_trade_pct"),
                            "pnl": update_payload.get("realized_pnl"),
                            "realized_pnl": update_payload.get("realized_pnl"),
                            "pnl_points": update_payload.get("pnl_points"),
                            "closed_at": update_payload.get("closed_at"),
                            "reason": update_payload.get("reason"),
                            "market_status": update_payload.get("market_status"),
                            "updated_at": _now(),
                        }).eq("id", row_id).execute()
                        return True

                except Exception as update_error:
                    print(f"[OutcomeTracker DB ERROR] duplicate fallback update failed: {update_error}")
                    return False

            print(f"[OutcomeTracker DB ERROR] trade_results update failed: {e}")
            return False

    print("[OutcomeTracker DB ERROR] trade_results update failed after schema cleanup retries.")
    return False


def _save_trade_result_to_supabase(outcome_row):
    if SUPABASE is None:
        print("[OutcomeTracker DB] Supabase not connected. Result not saved to dashboard DB.")
        return False

    outcome = str(outcome_row.get("outcome", "")).upper().strip()

    if outcome not in {"TP", "SL"}:
        return False

    result = "WIN" if outcome == "TP" else "LOSS"
    trade_id = str(outcome_row.get("trade_id", "")).strip()
    setup_signature = _row_setup_signature(outcome_row)

    if not trade_id:
        print("[OutcomeTracker DB] Missing trade_id. Result not saved.")
        return False
    if setup_signature and _same_day_trade_result_setup_exists(setup_signature, exclude_trade_id=trade_id):
        print(f"[OutcomeTracker DB] DUPLICATE_SETUP_SKIPPED: {setup_signature}")
        return False

    payload = {
        "trade_id": trade_id,
        "setup_signature": setup_signature,
        "trade_date": datetime.now(IST).strftime("%Y-%m-%d"),
        "symbol": outcome_row.get("symbol", ""),
        "side": outcome_row.get("side", ""),
        "entry": _safe_float(outcome_row.get("entry")),
        "exit_price": _safe_float(outcome_row.get("exit_price")),
        "stop_loss": _safe_float(outcome_row.get("sl")),
        "target": _safe_float(outcome_row.get("target")),
        "rr": _safe_float(outcome_row.get("rr")),
        "result": result,
        "outcome": outcome,
        "pnl_points": _safe_float(outcome_row.get("pnl_points")),
        "pnl": _safe_float(outcome_row.get("realized_pnl")),
        "realized_pnl": _safe_float(outcome_row.get("realized_pnl")),
        "quantity": _safe_float(outcome_row.get("quantity") or outcome_row.get("qty")),
        "qty": _safe_float(outcome_row.get("quantity") or outcome_row.get("qty")),
        "position_size": _safe_float(outcome_row.get("position_size")),
        "capital_used": _safe_float(outcome_row.get("capital_used") or outcome_row.get("position_size")),
        "risk_amount": _safe_float(outcome_row.get("risk_amount")),
        "risk_per_trade_pct": _safe_float(outcome_row.get("risk_per_trade_pct"), 1.0),
        "paper_trade_id": outcome_row.get("paper_trade_id"),
        "is_paper_trade": outcome_row.get("is_paper_trade"),
        "closed_at": outcome_row.get("closed_at"),
        "opened_at": outcome_row.get("opened_at"),
        "reason": outcome_row.get("result_reason", ""),
        "market_status": str(outcome_row.get("market_status", "")),
    }

    payload = _json_safe(payload)

    try:
        existing = (
            SUPABASE.table("trade_results")
            .select("trade_id")
            .eq("trade_id", trade_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            updated = _update_trade_result_payload(payload)
            if updated:
                print(f"[OutcomeTracker DB] Existing Supabase result updated with real PnL: {payload.get('symbol')} {payload.get('side')} -> {result}")
                return True
            return False

        saved = _update_trade_result_payload(payload)

        if saved:
            print(f"[OutcomeTracker DB] Supabase result updated: {payload.get('symbol')} {payload.get('side')} -> {result}")
            return True

        return False

    except Exception as e:
        print(f"[OutcomeTracker DB ERROR] trade_results save failed: {e}")
        return False


def _append_outcome(row, outcome, exit_price, pnl_points, reason):
    realized_pnl = _calc_realized_pnl(row, _safe_float(exit_price))
    outcome_row = {
        "closed_at": _now(),
        "trade_id": row.get("trade_id", ""),
        "opened_at": row.get("opened_at", ""),
        "symbol": row.get("symbol", ""),
        "side": row.get("side", ""),
        "entry": row.get("entry", ""),
        "sl": row.get("sl", ""),
        "target": row.get("target", ""),
        "entry_price": row.get("entry_price") or row.get("entry", ""),
        "stop_loss": row.get("stop_loss") or row.get("sl", ""),
        "tp": row.get("tp") or row.get("target", ""),
        "quantity": row.get("quantity") or row.get("qty", ""),
        "qty": row.get("qty") or row.get("quantity", ""),
        "position_size": row.get("position_size", ""),
        "capital_used": row.get("capital_used") or row.get("position_size", ""),
        "risk_amount": row.get("risk_amount", ""),
        "risk_per_trade_pct": row.get("risk_per_trade_pct", ""),
        "risk_per_share": row.get("risk_per_share", ""),
        "paper_trade_id": row.get("paper_trade_id") or row.get("trade_id", ""),
        "is_paper_trade": row.get("is_paper_trade") or "true",
        "test_trade": row.get("test_trade", ""),
        "source": row.get("source", ""),
        "rr": row.get("rr", ""),
        "score": row.get("score", ""),
        "rank_score": row.get("rank_score", ""),
        "alert_sent": row.get("alert_sent", ""),
        "market_status": row.get("market_status", ""),
        "outcome": outcome,
        "exit_price": exit_price,
        "realized_pnl": realized_pnl,
        "pnl_points": pnl_points,
        "result_reason": reason,
    }
    outcome_row = _attach_reinforcement_learning_fields(row, outcome_row)

    with open(OUTCOMES_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
        writer.writerow({field: outcome_row.get(field, "") for field in OUTCOME_FIELDS})

    with open(OUTCOMES_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(_json_safe(outcome_row), ensure_ascii=False) + "\n")

    if str(outcome_row.get("test_trade") or "").strip().lower() in {"1", "true", "yes", "y"}:
        if not LOCAL_TRADE_RESULTS_CSV.exists():
            with open(LOCAL_TRADE_RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
                writer.writeheader()
        else:
            _ensure_csv_columns(LOCAL_TRADE_RESULTS_CSV, OUTCOME_FIELDS)
        with open(LOCAL_TRADE_RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTCOME_FIELDS)
            writer.writerow({field: outcome_row.get(field, "") for field in OUTCOME_FIELDS})

    _save_trade_result_to_supabase(outcome_row)
    if sync_paper_account_from_trade_results is not None:
        try:
            sync_paper_account_from_trade_results(outcome_row)
        except Exception as e:
            print(f"[OutcomeTracker WARN] Paper account sync skipped: {e}")


def track_trade_outcomes(limit=None):
    """
    Tracks OPEN trades.

    limit is optional for backward compatibility with older callers.
    If omitted, all OPEN trades are checked.
    """
    expiry_result = _expire_previous_day_open_trades()

    if not is_trade_window():
        print(f"[OutcomeTracker] Skipped outside trade window ({trade_window_text()}).")
        return _write_outcome_tracker_status({
            "checked": 0,
            "closed": 0,
            "open": 0,
            "skipped": "OUTSIDE_TRADE_WINDOW",
            "expired_previous_day_open": expiry_result,
        })

    _ensure_files()

    with open(ACTIVE_TRADES_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []

    if not rows:
        print("[OutcomeTracker] No active trades found.")
        return _write_outcome_tracker_status({"checked": 0, "closed": 0, "open": 0})

    checked = 0
    closed = 0
    still_open = 0
    price_stale_skipped = 0
    deferred_open = 0
    updated_rows = []
    lifecycle_observations = []
    max_checks = None

    try:
        if limit is not None:
            max_checks = max(0, int(limit))
    except Exception:
        max_checks = None

    backlog_size = 0
    for row in rows:
        status_text = str(row.get("status", "")).upper().strip()
        if status_text in {"OPEN", "TP", "SL"}:
            backlog_size += 1

    limit_text = "ALL" if max_checks is None else str(max_checks)
    print(f"[OutcomeTracker DEBUG] Backlog eligible rows: {backlog_size} | limit={limit_text}")

    for row in rows:
        status, _ = _normalize_active_trade_lifecycle(row)

        if status != "OPEN":
            updated_rows.append(row)
            continue

        if max_checks is not None and checked >= max_checks:
            updated_rows.append(row)
            still_open += 1
            deferred_open += 1
            continue

        symbol = row.get("symbol", "")
        checked += 1

        try:
            price_result = get_strict_fresh_price_debug(
                symbol,
                max_age_seconds=MAX_TP_SL_PRICE_AGE_SECONDS,
                debug=False,
            )

            if not isinstance(price_result, dict):
                price_result = {
                    "price": None,
                    "source": "UNKNOWN",
                    "status": "PRICE_STALE",
                    "reason": "Strict price helper returned non-dict result",
                    "fresh": False,
                }

            live_price = price_result.get("price")
            price_source = str(price_result.get("source") or "").upper()
            price_status = str(price_result.get("status") or "").upper()
            price_fresh = bool(price_result.get("fresh"))

            outcome_gate = validate_outcome_check(
                row,
                price_result=price_result,
                source_table="active_trades",
            )
            write_truth_gate_status(outcome_validation_status=outcome_gate)
            if outcome_gate.get("status") != "PASS":
                row["last_checked_at"] = _now()
                row["result_reason"] = f"TRUTH_GATE_BLOCKED:{outcome_gate.get('reason')}"
                price_stale_skipped += 1
                still_open += 1
                print(f"[TruthGate] Outcome check skipped for {symbol}: {outcome_gate.get('reason')}")
                updated_rows.append(row)
                continue

            strict_price_ok = (
                live_price is not None
                and price_fresh
                and (
                    (price_source == "UPSTOX" and price_status == "ACTIVE")
                    or price_status == "CACHE_FRESH"
                )
            )

            if not strict_price_ok:
                row["last_checked_at"] = _now()
                row["result_reason"] = "PRICE_STALE"
                price_stale_skipped += 1
                still_open += 1
                print(
                    f"[OutcomeTracker] {symbol} PRICE_STALE: "
                    f"{price_result.get('reason')}"
                )
                updated_rows.append(row)
                continue

            outcome, exit_price, pnl_points, reason = _check_outcome(row, live_price)

            if observe_trade_lifecycle_safely is not None:
                try:
                    lifecycle_observation = observe_trade_lifecycle_safely(
                        row=row,
                        live_price=live_price,
                        outcome_status=outcome,
                    )
                    if lifecycle_observation:
                        lifecycle_observations.append(lifecycle_observation)
                except Exception:
                    pass

            row["last_checked_at"] = _now()
            row["last_price"] = exit_price
            row["pnl_points"] = pnl_points
            row["result_reason"] = reason

            if outcome in ["TP", "SL"]:
                result = _result_from_outcome(outcome)
                row["status"] = "CLOSED"
                row["outcome"] = outcome
                row["result"] = result
                _append_outcome(row, outcome, exit_price, pnl_points, reason)
                closed += 1
                print(
                    f"[OutcomeTracker NORMALIZE] {symbol}: "
                    f"status=CLOSED outcome={outcome} result={result}"
                )
                print(f"[OutcomeTracker] {symbol} closed: {outcome} @ {exit_price}")
            else:
                still_open += 1

        except Exception as e:
            row["last_checked_at"] = _now()
            row["result_reason"] = f"Outcome check error: {e}"
            still_open += 1
            print(f"[OutcomeTracker ERROR] {symbol}: {e}")

        updated_rows.append(row)

    with open(ACTIVE_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ACTIVE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in updated_rows:
            writer.writerow({field: row.get(field, "") for field in ACTIVE_FIELDS})

    lifecycle_result = None
    if update_lifecycle_memory_safely is not None:
        try:
            lifecycle_result = update_lifecycle_memory_safely(lifecycle_observations)
            if isinstance(lifecycle_result, dict) and lifecycle_result.get("error"):
                print(f"[Lifecycle ERROR] Shadow lifecycle failed open: {lifecycle_result.get('error')}")
            elif isinstance(lifecycle_result, dict) and lifecycle_result.get("updated"):
                print(f"[Lifecycle] Shadow observations updated: {lifecycle_result.get('updated')}")
        except Exception as e:
            lifecycle_result = {"error": str(e)}
            print(f"[Lifecycle ERROR] Shadow lifecycle failed open: {e}")

    print(
        "[OutcomeTracker DEBUG] "
        f"Processed rows: {checked} | PRICE_STALE skipped: {price_stale_skipped} | "
        f"Deferred open rows: {deferred_open}"
    )
    print(f"[OutcomeTracker] Checked: {checked} | Closed: {closed} | Still open: {still_open}")

    return _write_outcome_tracker_status({
        "checked": checked,
        "closed": closed,
        "open": still_open,
        "backlog_size": backlog_size,
        "price_stale_skipped": price_stale_skipped,
        "deferred_open": deferred_open,
        "expired_previous_day_open": expiry_result,
        "lifecycle_shadow_result": lifecycle_result,
    })


if __name__ == "__main__":
    track_trade_outcomes()
