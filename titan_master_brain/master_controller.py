"""
TITAN MASTER CONTROLLER
STEP 9B FINAL - STABLE FIX

Fixes:
1. Saves real Telegram-sent trades into Supabase trade_results.
2. Prevents duplicate LIVE trade for same symbol + side.
3. Auto-closes LIVE trades after 3:30 PM IST.
4. Prevents Telegram trade alerts outside market hours.
5. Keeps outcome tracker active.
"""

import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

from supabase import create_client

from titan_master_brain.input_aggregator import build_master_input
from titan_master_brain.context_builder import build_context
from titan_master_brain.setup_reasoning_engine import evaluate_setups
from titan_master_brain.final_decision_engine import make_final_decisions, print_final_decisions
from titan_master_brain.alert_execution_filter import filter_alert_candidates, print_alert_filter_result
from titan_master_brain.daily_alert_manager import (
    select_daily_alerts,
    print_daily_alert_selection,
    mark_alerts_sent,
)
from titan_master_brain.execution_engine import (
    prepare_execution_packets,
    print_execution_packets,
    send_telegram_signals,
)
from journal.outcome_tracker import track_trade_outcomes


IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = time(8, 30)
MARKET_CLOSE = time(15, 30)

TEST_SYMBOLS = {"TEST", "TESTPY"}


# =========================================================
# SAFE HELPERS
# =========================================================

def _now_ist():
    return datetime.now(IST)


def _is_market_alert_time():
    now = _now_ist()

    # Monday=0, Sunday=6
    if now.weekday() >= 5:
        return False

    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _deep_get(data, keys, default=None):
    if not isinstance(data, dict):
        return default

    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)

    for nested_key in ["setup", "trade", "signal", "packet", "data", "raw", "meta"]:
        nested = data.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                if key in nested and nested.get(key) is not None:
                    return nested.get(key)

    return default


def _get_supabase():
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            print("[Supabase] Missing SUPABASE_URL / SUPABASE_KEY. DB actions skipped.")
            return None

        return create_client(url, key)

    except Exception as e:
        print(f"[Supabase ERROR] Connection failed: {e}")
        return None


# =========================================================
# MARKET CLOSE HANDLER
# =========================================================

def auto_close_live_trades_after_market_close():
    """
    After 3:30 PM IST, unresolved LIVE trades become MARKET_CLOSED.
    This prevents dashboard showing fake live trades at night.
    """
    now = _now_ist()

    # Do nothing before market close
    if now.time() < MARKET_CLOSE:
        return 0

    supabase = _get_supabase()
    if supabase is None:
        return 0

    closed_count = 0

    try:
        result = (
            supabase.table("trade_results")
            .select("*")
            .eq("status", "LIVE")
            .execute()
        )

        for row in result.data or []:
            symbol = str(row.get("symbol") or "").upper()

            if symbol in TEST_SYMBOLS:
                continue

            row_id = row.get("id")
            if not row_id:
                continue

            supabase.table("trade_results").update({
                "status": "MARKET_CLOSED",
                "outcome": "MARKET_CLOSED",
                "result": "MARKET_CLOSED",
                "closed_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "reason": "Auto closed because market session ended"
            }).eq("id", row_id).execute()

            closed_count += 1
            print(f"[MarketClose] Auto-closed LIVE trade: {symbol}")

    except Exception as e:
        print(f"[MarketClose ERROR] {e}")

    if closed_count:
        print(f"[MarketClose] Auto-closed {closed_count} live trade(s).")

    return closed_count


# =========================================================
# TRADE_RESULTS SAVE
# =========================================================

def _live_trade_exists(supabase, symbol, side):
    try:
        result = (
            supabase.table("trade_results")
            .select("id")
            .eq("symbol", str(symbol))
            .eq("side", str(side))
            .eq("status", "LIVE")
            .limit(1)
            .execute()
        )

        return bool(result.data)

    except Exception as e:
        print(f"[TradeResults] Duplicate check failed for {symbol} {side}: {e}")
        return False


def save_sent_packets_to_trade_results(sent_packets, context=None):
    """
    Saves only Telegram-sent trades into trade_results.
    Prevents duplicate LIVE trade for same symbol + side.
    """
    if not sent_packets:
        print("[TradeResults] No sent packets to save.")
        return 0

    supabase = _get_supabase()
    if supabase is None:
        return 0

    saved_count = 0
    now_iso = _now_ist().isoformat()

    market_status = None
    if isinstance(context, dict):
        market_status = (
            context.get("market_type")
            or context.get("market_status")
            or context.get("setup_environment")
            or context.get("trading_mode")
        )

    for packet in sent_packets:
        try:
            if not isinstance(packet, dict):
                print(f"[TradeResults] Skipped non-dict packet: {packet}")
                continue

            symbol = _deep_get(packet, ["symbol", "stock", "ticker", "name"])
            side = _deep_get(packet, ["side", "direction", "trade_side"])

            entry = _safe_float(_deep_get(packet, ["entry", "entry_price", "price"]))
            sl = _safe_float(_deep_get(packet, ["sl", "stop_loss", "stoploss"]))
            tp = _safe_float(_deep_get(packet, ["tp", "target", "target_price", "t1"]))

            rr = _safe_float(_deep_get(packet, ["rr", "risk_reward", "actual_rr"]), 0)
            score = _safe_float(_deep_get(packet, ["score", "final_score", "rank_score"]), 0)
            reason = _deep_get(packet, ["reason", "reasoning", "message", "note"], "")

            if not symbol or not side or entry is None or sl is None or tp is None:
                print(f"[TradeResults] Skipped invalid packet: {packet}")
                continue

            symbol = str(symbol).upper()
            side = str(side).upper()

            if symbol in TEST_SYMBOLS:
                print(f"[TradeResults] Skipped test symbol: {symbol}")
                continue

            # FINAL DUPLICATE PROTECTION
            if _live_trade_exists(supabase, symbol, side):
                print(f"[TradeResults] LIVE trade already exists for {symbol} {side}. Skipping duplicate.")
                continue

            row = {
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "target_price": tp,
                "stop_loss": sl,
                "status": "LIVE",
                "result": None,
                "outcome": None,
                "pnl": 0,
                "pnl_points": None,
                "exit_price": None,
                "close_price": None,
                "market_status": str(market_status) if market_status is not None else None,
                "rr": rr,
                "score": score,
                "reason": str(reason) if reason is not None else "",
                "opened_at": now_iso,
                "created_at": now_iso,
                "updated_at": now_iso,
            }

            supabase.table("trade_results").insert(row).execute()

            saved_count += 1
            print(
                f"[TradeResults] SAVED REAL TRADE: "
                f"{symbol} | {side} | entry={entry} | sl={sl} | tp={tp}"
            )

        except Exception as e:
            print(f"[TradeResults ERROR] Save failed for packet {packet}: {e}")

    print(f"[TradeResults] Saved {saved_count}/{len(sent_packets)} sent trade(s).")
    return saved_count


# =========================================================
# PRINT HELPERS
# =========================================================

def _print_setup_reasoning(evaluated_setups):
    print("\n[MasterBrain] Setup Reasoning:\n")

    if not evaluated_setups:
        print("[Reasoning] No setups to evaluate.")
        return

    for setup in evaluated_setups:
        symbol = setup.get("symbol", "UNKNOWN")
        decision = setup.get("decision", "UNKNOWN")
        confidence = setup.get("confidence", "UNKNOWN")
        reasoning = setup.get("reasoning", [])

        if isinstance(reasoning, list):
            reasoning_text = ", ".join(str(x) for x in reasoning)
        else:
            reasoning_text = str(reasoning)

        print(f"{symbol} → {decision} | {confidence} | {reasoning_text}")


# =========================================================
# MAIN MASTER BRAIN
# =========================================================

def run_master_brain(send_telegram=True, run_outcome_tracker=True):
    print("[MasterBrain] Step 9B Final Master Controller Running...")

    # Always clean stale LIVE trades first after market close
    auto_close_live_trades_after_market_close()

    master_input = build_master_input()
    context = build_context(master_input)

    print("[MasterBrain] Context Built")
    print("[MasterBrain] Market Type:", context.get("market_type"))
    print("[MasterBrain] Trading Mode:", context.get("trading_mode"))
    print("[MasterBrain] Setup Environment:", context.get("setup_environment"))

    setups_packet = master_input.get("setups", {})
    setups = setups_packet.get("data", []) if isinstance(setups_packet, dict) else []

    print("[MasterBrain] Setups:", len(setups))

    evaluated_setups = evaluate_setups(setups, context)
    _print_setup_reasoning(evaluated_setups)

    final_decisions = make_final_decisions(evaluated_setups, context)
    print_final_decisions(final_decisions)

    alert_filter_result = filter_alert_candidates(final_decisions)
    print_alert_filter_result(alert_filter_result)

    daily_alert_result = select_daily_alerts(alert_filter_result)
    print_daily_alert_selection(daily_alert_result)

    execution_result = prepare_execution_packets(daily_alert_result)
    print_execution_packets(execution_result)

    sent_packets = []

    # Telegram only during market alert window
    if send_telegram:
        if not _is_market_alert_time():
            print("[Telegram] Market closed / outside alert window. No trade alerts sent.")
        else:
            sent_packets = send_telegram_signals(execution_result)

            if sent_packets:
                save_sent_packets_to_trade_results(sent_packets, context=context)

                mark_alerts_sent(sent_packets)
                print(f"[DailyAlert] Marked {len(sent_packets)} alert(s) as sent.")
            else:
                print("[DailyAlert] No alerts marked sent because Telegram sending failed or no packets existed.")
    else:
        print("[Telegram] send_telegram=False, dry run only. Nothing sent.")

    outcome_result = None

    if run_outcome_tracker:
        print("\n[MasterBrain] Running Outcome Tracker...")
        try:
            outcome_result = track_trade_outcomes()
        except Exception as e:
            print(f"[MasterBrain ERROR] Outcome tracker failed: {e}")
            outcome_result = {"error": str(e)}
    else:
        print("[OutcomeTracker] run_outcome_tracker=False, skipped.")

    # Run market close cleanup again after outcome tracker
    auto_close_live_trades_after_market_close()

    print("\n[MasterBrain] Cycle Complete\n")

    return {
        "master_input": master_input,
        "context": context,
        "evaluated_setups": evaluated_setups,
        "final_decisions": final_decisions,
        "alert_filter_result": alert_filter_result,
        "daily_alert_result": daily_alert_result,
        "execution_result": execution_result,
        "sent_packets": sent_packets,
        "outcome_result": outcome_result,
    }


if __name__ == "__main__":
    run_master_brain()