"""
TITAN MASTER CONTROLLER
STEP 9B FINAL

Flow:
Input Aggregator
→ Context Builder
→ Setup Reasoning
→ Final Decision Engine
→ Alert / Execution Filter
→ Daily Alert Manager
→ Execution Engine
→ Telegram Sender
→ Mark Alerts Sent
→ Outcome Tracker

This is the full connected Master Brain cycle.
"""

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


def run_master_brain(send_telegram=True, run_outcome_tracker=True):
    print("[MasterBrain] Step 9B Final Master Controller Running...")

    # STEP 1 — Build full master input packet safely
    master_input = build_master_input()

    # STEP 2 — Build context
    context = build_context(master_input)

    print("[MasterBrain] Context Built")
    print("[MasterBrain] Market Type:", context.get("market_type"))
    print("[MasterBrain] Trading Mode:", context.get("trading_mode"))
    print("[MasterBrain] Setup Environment:", context.get("setup_environment"))

    # STEP 3 — Read setups
    setups_packet = master_input.get("setups", {})
    setups = setups_packet.get("data", []) if isinstance(setups_packet, dict) else []

    print("[MasterBrain] Setups:", len(setups))

    # STEP 4 — Setup reasoning
    evaluated_setups = evaluate_setups(setups, context)
    _print_setup_reasoning(evaluated_setups)

    # STEP 5 — Final decision layer
    final_decisions = make_final_decisions(evaluated_setups, context)
    print_final_decisions(final_decisions)

    # STEP 6 — Alert / execution filter
    alert_filter_result = filter_alert_candidates(final_decisions)
    print_alert_filter_result(alert_filter_result)

    # STEP 7 — Daily 3 alert manager
    daily_alert_result = select_daily_alerts(alert_filter_result)
    print_daily_alert_selection(daily_alert_result)

    # STEP 8 — Prepare Telegram-ready packets
    execution_result = prepare_execution_packets(daily_alert_result)
    print_execution_packets(execution_result)

    # STEP 8C — Telegram send + mark sent
    sent_packets = []

    if send_telegram:
        sent_packets = send_telegram_signals(execution_result)

        if sent_packets:
            mark_alerts_sent(sent_packets)
            print(f"[DailyAlert] Marked {len(sent_packets)} alert(s) as sent.")
        else:
            print("[DailyAlert] No alerts marked sent because Telegram sending failed or no packets existed.")
    else:
        print("[Telegram] send_telegram=False, dry run only. Nothing sent.")

    # STEP 9 — Outcome tracking
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