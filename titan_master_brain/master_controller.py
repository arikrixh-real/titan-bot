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
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
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
from utils.market_hours import TRADE_WINDOW_END, TRADE_WINDOW_START, is_trade_window

try:
    from engines.multi_agent_reasoning_engine import apply_multi_agent_reasoning
except Exception:
    apply_multi_agent_reasoning = None

try:
    from engines.phase6_shadow_observer import refresh_phase6_shadow_report
except Exception:
    refresh_phase6_shadow_report = None

try:
    from engines.market_narrative_engine import refresh_market_narrative_report
except Exception:
    refresh_market_narrative_report = None

try:
    from engines.cross_setup_intelligence import refresh_cross_setup_report
except Exception:
    refresh_cross_setup_report = None

try:
    from engines.master_shadow_command_center import refresh_master_shadow_command_center
except Exception:
    refresh_master_shadow_command_center = None

try:
    from engines.promotion_gate_engine import refresh_promotion_gate
except Exception:
    refresh_promotion_gate = None

try:
    from engines.advanced_regime_intelligence import refresh_advanced_regime_intelligence
except Exception:
    refresh_advanced_regime_intelligence = None

try:
    from engines.strategy_genome_engine import refresh_strategy_genome
except Exception:
    refresh_strategy_genome = None

try:
    from engines.meta_evolution_intelligence import refresh_meta_evolution_intelligence
except Exception:
    refresh_meta_evolution_intelligence = None

try:
    from intelligence.news_engine import run_news_engine
except Exception:
    run_news_engine = None

try:
    from engines.adaptive_memory_builder import (
        build_adaptive_memory,
        get_adaptive_state_path,
    )
except Exception:
    build_adaptive_memory = None
    get_adaptive_state_path = None

try:
    from engines.self_evaluation_report import (
        build_self_evaluation_report,
        get_strategy_family_memory_path,
    )
except Exception:
    build_self_evaluation_report = None
    get_strategy_family_memory_path = None


IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = TRADE_WINDOW_START
MARKET_CLOSE = TRADE_WINDOW_END

TEST_SYMBOLS = {"TEST", "TESTPY"}
ADAPTIVE_MEMORY_REFRESH_SECONDS = 3600
PHASE5_MEMORY_REFRESH_SECONDS = 3600


# =========================================================
# SAFE HELPERS
# =========================================================

def _now_ist():
    return datetime.now(IST)


def _is_market_alert_time():
    return is_trade_window(_now_ist())


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


def _extract_missing_column(error_text):
    match = re.search(r"Could not find the '([^']+)' column", str(error_text))
    if match:
        return match.group(1)
    return None


def _safe_supabase_insert(client, table_name, payload):
    clean = dict(payload)

    for _ in range(12):
        try:
            client.table(table_name).insert(clean).execute()
            return True
        except Exception as e:
            missing_col = _extract_missing_column(e)

            if missing_col and missing_col in clean:
                print(f"[Supabase FIX] {table_name} missing column removed: {missing_col}")
                clean.pop(missing_col, None)
                continue

            print(f"[Supabase ERROR] {table_name} insert failed: {e}")
            return False

    print(f"[Supabase ERROR] {table_name} insert failed after schema cleanup retries.")
    return False


def _safe_supabase_update(client, table_name, payload, match_column, match_value):
    clean = dict(payload)

    for _ in range(12):
        try:
            client.table(table_name).update(clean).eq(match_column, match_value).execute()
            return True
        except Exception as e:
            missing_col = _extract_missing_column(e)

            if missing_col and missing_col in clean:
                print(f"[Supabase FIX] {table_name} missing update column removed: {missing_col}")
                clean.pop(missing_col, None)
                continue

            print(f"[Supabase ERROR] {table_name} update failed: {e}")
            return False

    print(f"[Supabase ERROR] {table_name} update failed after schema cleanup retries.")
    return False


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

            updated = _safe_supabase_update(supabase, "trade_results", {
                "status": "MARKET_CLOSED",
                "outcome": "MARKET_CLOSED",
                "result": "MARKET_CLOSED",
                "closed_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "reason": "Auto closed because market session ended"
            }, "id", row_id)

            if not updated:
                continue

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

            inserted = _safe_supabase_insert(supabase, "trade_results", row)

            if not inserted:
                continue

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



def run_news_engine_safely():
    """
    Runs TITAN News Engine every GitHub cycle.
    This is placed in master_controller because GitHub active path runs master_controller,
    not setup_engine.
    """
    if run_news_engine is None:
        print("[NewsEngine] Not connected / import failed.")
        return []

    try:
        print("[NewsEngine] Running news intelligence update...")
        news_items = run_news_engine()
        print(f"[NewsEngine] Completed. Items collected: {len(news_items or [])}")
        return news_items or []
    except Exception as e:
        print(f"[NewsEngine ERROR] {e}")
        return []


def refresh_adaptive_memory_safely():
    """
    Phase 3 cache refresh.

    This is intentionally lightweight for GitHub's 5-minute runner:
    it rebuilds at most once per hour and never blocks trading flow.
    """
    if build_adaptive_memory is None or get_adaptive_state_path is None:
        print("[AdaptiveAI] Memory builder not connected.")
        return None

    try:
        state_path = Path(get_adaptive_state_path())
        if state_path.exists():
            age_seconds = datetime.now().timestamp() - state_path.stat().st_mtime
            if age_seconds < ADAPTIVE_MEMORY_REFRESH_SECONDS:
                print("[AdaptiveAI] Cached memory fresh. Refresh skipped.")
                return {"skipped": "CACHE_FRESH"}

        state = build_adaptive_memory(write_files=True)
        print(
            "[AdaptiveAI] Memory refreshed. "
            f"Closed trades: {state.get('total_closed_trades')}"
        )
        return state

    except Exception as e:
        print(f"[AdaptiveAI ERROR] Memory refresh skipped: {e}")
        return {"error": str(e)}


def refresh_phase5_memory_safely():
    """
    Phase 5 strategy-family memory/report refresh.

    Throttled outside the ranking hot path. It never sends alerts, creates
    trades, or changes guard behavior.
    """
    if build_self_evaluation_report is None or get_strategy_family_memory_path is None:
        print("[MetaAI] Self-evaluation builder not connected.")
        return None

    try:
        state_path = Path(get_strategy_family_memory_path())
        if state_path.exists():
            age_seconds = datetime.now().timestamp() - state_path.stat().st_mtime
            if age_seconds < PHASE5_MEMORY_REFRESH_SECONDS:
                print("[MetaAI] Strategy-family memory fresh. Refresh skipped.")
                return {"skipped": "CACHE_FRESH"}

        state = build_self_evaluation_report(write_files=True)
        print(
            "[MetaAI] Self-evaluation refreshed. "
            f"Closed trades: {state.get('total_closed_trades')}"
        )
        return state

    except Exception as e:
        print(f"[MetaAI ERROR] Self-evaluation refresh skipped: {e}")
        return {"error": str(e)}


def apply_phase6_shadow_reasoning_safely(evaluated_setups, context):
    """
    Phase 6 shadow-only advisory layer.

    It attaches multi-agent metadata after setup reasoning and before final
    decision ranking. It never blocks setups and never changes ranking.
    """
    if apply_multi_agent_reasoning is None:
        print("[Phase6] Multi-agent reasoning not connected.")
        return evaluated_setups

    try:
        enriched = apply_multi_agent_reasoning(evaluated_setups, context)
        print(f"[Phase6] Shadow reasoning applied to {len(enriched or [])} setup(s).")
        return enriched
    except Exception as e:
        print(f"[Phase6 ERROR] Shadow reasoning failed open: {e}")
        return evaluated_setups


def refresh_phase6_shadow_report_safely(evaluated_setups):
    """
    Phase 6 observation-only reporting.

    Uses already-attached Phase 6 metadata and is throttled by report mtime.
    It never changes rankings, Telegram, alert caps, or execution.
    """
    if refresh_phase6_shadow_report is None:
        print("[Phase6] Shadow observer not connected.")
        return None

    try:
        result = refresh_phase6_shadow_report(evaluated_setups or [])

        if isinstance(result, dict) and result.get("skipped") == "CACHE_FRESH":
            print("[Phase6] Shadow report fresh. Refresh skipped.")
        elif isinstance(result, dict) and result.get("error"):
            print(f"[Phase6 ERROR] Shadow report failed open: {result.get('error')}")
        else:
            observed = result.get("observed_setup_count", 0) if isinstance(result, dict) else 0
            print(f"[Phase6] Shadow report refreshed. Observed setups: {observed}")

        return result

    except Exception as e:
        print(f"[Phase6 ERROR] Shadow report failed open: {e}")
        return {"error": str(e)}


def refresh_phase8_market_narrative_safely(master_input, context, evaluated_setups):
    """
    Phase 8 shadow-only market narrative reporting.

    Uses already-built local/cached metadata. It does not mutate context or
    setups and never feeds into ranking, Telegram, execution, or alerts.
    """
    if refresh_market_narrative_report is None:
        print("[Phase8] Market narrative engine not connected.")
        return None

    try:
        result = refresh_market_narrative_report(
            master_input=master_input,
            context=context,
            evaluated_setups=evaluated_setups,
        )

        if isinstance(result, dict) and result.get("skipped") == "CACHE_FRESH":
            snapshot = result.get("snapshot") if isinstance(result.get("snapshot"), dict) else {}
            print(
                "[Phase8] Market narrative report fresh. "
                f"Narrative: {snapshot.get('narrative_type', 'UNKNOWN')}"
            )
        elif isinstance(result, dict) and result.get("error"):
            print(f"[Phase8 ERROR] Market narrative failed open: {result.get('error')}")
        else:
            narrative = result.get("narrative_type", "UNKNOWN") if isinstance(result, dict) else "UNKNOWN"
            print(f"[Phase8] Market narrative refreshed: {narrative}")

        return result

    except Exception as e:
        print(f"[Phase8 ERROR] Market narrative failed open: {e}")
        return {"error": str(e)}


def refresh_phase9_cross_setup_safely(evaluated_setups, context, final_decisions, phase8_market_narrative_result):
    """
    Phase 9 shadow-only cross-setup relational reporting.

    Runs after final decisions and Telegram handling. It receives only copied
    snapshots, writes compact artifacts, and never feeds ranking, alerts,
    execution, broker behavior, or daily alert state.
    """
    if refresh_cross_setup_report is None:
        print("[Phase9] Cross-setup intelligence not connected.")
        return None

    try:
        result = refresh_cross_setup_report(
            evaluated_setups=deepcopy(evaluated_setups or []),
            context=deepcopy(context or {}),
            final_decisions=deepcopy(final_decisions or {}),
            market_narrative=deepcopy(phase8_market_narrative_result or {}),
        )

        if isinstance(result, dict) and result.get("skipped") == "CACHE_FRESH":
            snapshot = result.get("snapshot") if isinstance(result.get("snapshot"), dict) else {}
            print(
                "[Phase9] Cross-setup report fresh. "
                f"State: {snapshot.get('relational_state', 'UNKNOWN')}"
            )
        elif isinstance(result, dict) and result.get("error"):
            print(f"[Phase9 ERROR] Cross-setup intelligence failed open: {result.get('error')}")
        else:
            state = result.get("relational_state", "UNKNOWN") if isinstance(result, dict) else "UNKNOWN"
            print(f"[Phase9] Cross-setup intelligence refreshed: {state}")

        return result

    except Exception as e:
        print(f"[Phase9 ERROR] Cross-setup intelligence failed open: {e}")
        return {"error": str(e)}


def refresh_phase10_master_shadow_safely(evaluated_setups, context, final_decisions, phase_results):
    """
    Phase 10 read-only command-center reporting.

    Aggregates existing shadow memories into compact dashboard/report artifacts.
    It never feeds ranking, alerts, Telegram, execution, broker behavior, market
    data, or daily alert state.
    """
    if refresh_master_shadow_command_center is None:
        print("[Phase10] Master shadow command center not connected.")
        return None

    try:
        result = refresh_master_shadow_command_center(
            evaluated_setups=deepcopy(evaluated_setups or []),
            context=deepcopy(context or {}),
            final_decisions=deepcopy(final_decisions or {}),
            phase_results=deepcopy(phase_results or {}),
        )

        snapshot = result.get("snapshot") if isinstance(result, dict) and isinstance(result.get("snapshot"), dict) else result
        status = snapshot.get("command_status", {}) if isinstance(snapshot, dict) else {}
        state = status.get("overall_state", "UNKNOWN")

        if isinstance(result, dict) and result.get("skipped") == "CACHE_FRESH":
            print(f"[Phase10] Master shadow report fresh. State: {state}")
        elif isinstance(result, dict) and status.get("failed_open"):
            print(f"[Phase10 ERROR] Master shadow failed open. State: {state}")
        else:
            print(f"[Phase10] Master shadow refreshed. State: {state}")

        return result

    except Exception as e:
        print(f"[Phase10 ERROR] Master shadow failed open: {e}")
        return {"error": str(e)}


def refresh_phase11_promotion_gate_safely(evaluated_setups, final_decisions, phase_results):
    """
    Phase 11 shadow-only promotion governance.

    Evaluates whether shadow layers appear statistically useful. It never feeds
    ranking, alerts, Telegram, execution, broker behavior, TP/SL, market data,
    or daily alert state. Recommended live weight remains zero.
    """
    if refresh_promotion_gate is None:
        print("[Phase11] Promotion gate not connected.")
        return None

    try:
        result = refresh_promotion_gate(
            evaluated_setups=deepcopy(evaluated_setups or []),
            final_decisions=deepcopy(final_decisions or {}),
            phase_results=deepcopy(phase_results or {}),
        )

        snapshot = result.get("snapshot") if isinstance(result, dict) and isinstance(result.get("snapshot"), dict) else result
        summary = snapshot.get("promotion_summary", {}) if isinstance(snapshot, dict) else {}
        status = snapshot.get("status", "UNKNOWN") if isinstance(snapshot, dict) else "UNKNOWN"
        score = summary.get("max_promotion_score", 0.0) if isinstance(summary, dict) else 0.0

        if isinstance(result, dict) and result.get("skipped") == "CACHE_FRESH":
            print(f"[Phase11] Promotion gate report fresh. Status: {status} | score={score}")
        elif isinstance(result, dict) and "phase11_failed_open" in (result.get("warnings") or []):
            print(f"[Phase11 ERROR] Promotion gate failed open. Status: {status}")
        else:
            print(f"[Phase11] Promotion gate refreshed. Status: {status} | score={score}")

        return result

    except Exception as e:
        print(f"[Phase11 ERROR] Promotion gate failed open: {e}")
        return {"error": str(e)}


def refresh_phase12_advanced_regime_safely(evaluated_setups, context, final_decisions, phase_results):
    """
    Phase 12 shadow-only advanced regime intelligence.

    Classifies regime and tracks family/regime behavior for reports only. It
    never feeds ranking, final decisions, alerts, Telegram, execution, broker
    behavior, TP/SL, market data, alert caps, or duplicate prevention.
    """
    if refresh_advanced_regime_intelligence is None:
        print("[Phase12] Advanced regime intelligence not connected.")
        return None

    try:
        result = refresh_advanced_regime_intelligence(
            evaluated_setups=deepcopy(evaluated_setups or []),
            context=deepcopy(context or {}),
            final_decisions=deepcopy(final_decisions or {}),
            phase_results=deepcopy(phase_results or {}),
        )

        snapshot = result.get("snapshot") if isinstance(result, dict) and isinstance(result.get("snapshot"), dict) else result
        active = snapshot.get("active_regime", {}) if isinstance(snapshot, dict) else {}
        regime = active.get("primary", "UNKNOWN") if isinstance(active, dict) else "UNKNOWN"

        if isinstance(result, dict) and result.get("skipped") == "CACHE_FRESH":
            print(f"[Phase12] Advanced regime report fresh. Regime: {regime}")
        elif isinstance(result, dict) and "phase12_failed_open" in (result.get("warnings") or []):
            print(f"[Phase12 ERROR] Advanced regime failed open. Regime: {regime}")
        else:
            print(f"[Phase12] Advanced regime refreshed. Regime: {regime}")

        return result

    except Exception as e:
        print(f"[Phase12 ERROR] Advanced regime failed open: {e}")
        return {"error": str(e)}


def refresh_phase13_strategy_genome_safely(evaluated_setups, context, final_decisions, phase_results):
    """
    Phase 13 shadow-only strategy genome reporting.

    Groups observed setup DNA and family behavior for memory/report only. It
    never feeds ranking, final decisions, alerts, Telegram, execution, TP/SL,
    broker behavior, market data, alert caps, duplicate prevention, or dashboard.
    """
    if refresh_strategy_genome is None:
        print("[Phase13] Strategy genome engine not connected.")
        return None

    try:
        result = refresh_strategy_genome(
            evaluated_setups=deepcopy(evaluated_setups or []),
            context=deepcopy(context or {}),
            final_decisions=deepcopy(final_decisions or {}),
            phase_results=deepcopy(phase_results or {}),
        )

        snapshot = result.get("snapshot") if isinstance(result, dict) and isinstance(result.get("snapshot"), dict) else result
        families = snapshot.get("families", {}) if isinstance(snapshot, dict) else {}
        family_count = len(families) if isinstance(families, dict) else 0

        if isinstance(result, dict) and result.get("skipped") == "CACHE_FRESH":
            print(f"[Phase13] Strategy genome report fresh. Families: {family_count}")
        elif isinstance(result, dict) and "phase13_failed_open" in (result.get("warnings") or []):
            print("[Phase13 ERROR] Strategy genome failed open.")
        else:
            print(f"[Phase13] Strategy genome refreshed. Families: {family_count}")

        return result

    except Exception as e:
        print(f"[Phase13 ERROR] Strategy genome failed open: {e}")
        return {"error": str(e)}


def refresh_phase14_meta_evolution_safely(evaluated_setups, context, final_decisions, phase_results):
    """
    Phase 14 shadow-only meta-evolution audit.

    Evaluates intelligence-layer quality for memory/report only. It never
    changes ranking, final decisions, alerts, Telegram, execution, broker/API,
    market data, parameters, code, alert caps, duplicate prevention, or dashboard.
    """
    if refresh_meta_evolution_intelligence is None:
        print("[Phase14] Meta evolution intelligence not connected.")
        return None

    try:
        result = refresh_meta_evolution_intelligence(
            evaluated_setups=deepcopy(evaluated_setups or []),
            context=deepcopy(context or {}),
            final_decisions=deepcopy(final_decisions or {}),
            phase_results=deepcopy(phase_results or {}),
        )

        snapshot = result.get("snapshot") if isinstance(result, dict) and isinstance(result.get("snapshot"), dict) else result
        meta = snapshot.get("meta_state", {}) if isinstance(snapshot, dict) else {}
        usefulness = meta.get("overall_usefulness_score", "UNKNOWN") if isinstance(meta, dict) else "UNKNOWN"

        if isinstance(result, dict) and result.get("skipped") == "CACHE_FRESH":
            print(f"[Phase14] Meta evolution report fresh. Usefulness: {usefulness}")
        elif isinstance(result, dict) and "phase14_failed_open" in (result.get("warnings") or []):
            print("[Phase14 ERROR] Meta evolution failed open.")
        else:
            print(f"[Phase14] Meta evolution refreshed. Usefulness: {usefulness}")

        return result

    except Exception as e:
        print(f"[Phase14 ERROR] Meta evolution failed open: {e}")
        return {"error": str(e)}


# =========================================================
# MAIN MASTER BRAIN
# =========================================================

def run_master_brain(send_telegram=True, run_outcome_tracker=True):
    print("[MasterBrain] Step 9B Final Master Controller Running...")

    trade_window_open = _is_market_alert_time()

    # Always keep market-close cleanup safe.
    auto_close_live_trades_after_market_close()

    # Run news every GitHub cycle from active master_controller path.
    # This is safe before market open.
    news_items = run_news_engine_safely()

    # SAFETY FIX:
    # Before 9:20 AM IST / after 3:20 PM IST / weekends:
    # - Do NOT call build_master_input()
    # - Do NOT scan/journal setups
    # - Do NOT create active trades
    # - Do NOT run outcome tracker on stale prices
    # This keeps TITAN in research-only mode outside the real trading window.
    if not trade_window_open:
        print("[MasterBrain] Outside trade window: research-only mode active.")
        print("[MasterBrain] Trade execution, journaling, and outcome tracker skipped.")
        print("[Telegram] Market closed / outside alert window. No trade alerts sent.")

        phase10_master_shadow_result = refresh_phase10_master_shadow_safely(
            evaluated_setups=[],
            context={},
            final_decisions={},
            phase_results={"news_items_collected": len(news_items or [])},
        )
        phase11_promotion_gate_result = refresh_phase11_promotion_gate_safely(
            evaluated_setups=[],
            final_decisions={},
            phase_results={"phase10_master_shadow_result": phase10_master_shadow_result},
        )
        phase12_advanced_regime_result = refresh_phase12_advanced_regime_safely(
            evaluated_setups=[],
            context={},
            final_decisions={},
            phase_results={
                "phase10_master_shadow_result": phase10_master_shadow_result,
                "phase11_promotion_gate_result": phase11_promotion_gate_result,
            },
        )
        phase13_strategy_genome_result = refresh_phase13_strategy_genome_safely(
            evaluated_setups=[],
            context={},
            final_decisions={},
            phase_results={
                "phase10_master_shadow_result": phase10_master_shadow_result,
                "phase11_promotion_gate_result": phase11_promotion_gate_result,
                "phase12_advanced_regime_result": phase12_advanced_regime_result,
            },
        )
        phase14_meta_evolution_result = refresh_phase14_meta_evolution_safely(
            evaluated_setups=[],
            context={},
            final_decisions={},
            phase_results={
                "phase10_master_shadow_result": phase10_master_shadow_result,
                "phase11_promotion_gate_result": phase11_promotion_gate_result,
                "phase12_advanced_regime_result": phase12_advanced_regime_result,
                "phase13_strategy_genome_result": phase13_strategy_genome_result,
            },
        )

        print("\n[MasterBrain] Cycle Complete\n")

        return {
            "mode": "RESEARCH_ONLY",
            "news_items": news_items,
            "master_input": None,
            "context": None,
            "evaluated_setups": [],
            "final_decisions": {},
            "alert_filter_result": {},
            "daily_alert_result": {},
            "execution_result": {},
            "sent_packets": [],
            "outcome_result": None,
            "phase9_cross_setup_result": None,
            "phase10_master_shadow_result": phase10_master_shadow_result,
            "phase11_promotion_gate_result": phase11_promotion_gate_result,
            "phase12_advanced_regime_result": phase12_advanced_regime_result,
            "phase13_strategy_genome_result": phase13_strategy_genome_result,
            "phase14_meta_evolution_result": phase14_meta_evolution_result,
        }

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
    evaluated_setups = apply_phase6_shadow_reasoning_safely(evaluated_setups, context)
    phase6_shadow_report_result = refresh_phase6_shadow_report_safely(evaluated_setups)
    phase8_market_narrative_result = refresh_phase8_market_narrative_safely(
        master_input,
        context,
        evaluated_setups,
    )
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

    phase9_cross_setup_result = refresh_phase9_cross_setup_safely(
        evaluated_setups=evaluated_setups,
        context=context,
        final_decisions=final_decisions,
        phase8_market_narrative_result=phase8_market_narrative_result,
    )

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

    adaptive_memory_result = refresh_adaptive_memory_safely()
    phase5_memory_result = refresh_phase5_memory_safely()

    phase10_master_shadow_result = refresh_phase10_master_shadow_safely(
        evaluated_setups=evaluated_setups,
        context=context,
        final_decisions=final_decisions,
        phase_results={
            "phase5_memory_result": phase5_memory_result,
            "phase6_shadow_report_result": phase6_shadow_report_result,
            "phase8_market_narrative_result": phase8_market_narrative_result,
            "phase9_cross_setup_result": phase9_cross_setup_result,
            "adaptive_memory_result": adaptive_memory_result,
            "outcome_result": outcome_result,
        },
    )
    phase11_promotion_gate_result = refresh_phase11_promotion_gate_safely(
        evaluated_setups=evaluated_setups,
        final_decisions=final_decisions,
        phase_results={
            "phase10_master_shadow_result": phase10_master_shadow_result,
            "phase5_memory_result": phase5_memory_result,
            "phase6_shadow_report_result": phase6_shadow_report_result,
            "phase8_market_narrative_result": phase8_market_narrative_result,
            "phase9_cross_setup_result": phase9_cross_setup_result,
            "outcome_result": outcome_result,
        },
    )
    phase12_advanced_regime_result = refresh_phase12_advanced_regime_safely(
        evaluated_setups=evaluated_setups,
        context=context,
        final_decisions=final_decisions,
        phase_results={
            "phase10_master_shadow_result": phase10_master_shadow_result,
            "phase11_promotion_gate_result": phase11_promotion_gate_result,
            "phase5_memory_result": phase5_memory_result,
            "phase6_shadow_report_result": phase6_shadow_report_result,
            "phase8_market_narrative_result": phase8_market_narrative_result,
            "phase9_cross_setup_result": phase9_cross_setup_result,
            "outcome_result": outcome_result,
        },
    )
    phase13_strategy_genome_result = refresh_phase13_strategy_genome_safely(
        evaluated_setups=evaluated_setups,
        context=context,
        final_decisions=final_decisions,
        phase_results={
            "phase10_master_shadow_result": phase10_master_shadow_result,
            "phase11_promotion_gate_result": phase11_promotion_gate_result,
            "phase12_advanced_regime_result": phase12_advanced_regime_result,
            "phase5_memory_result": phase5_memory_result,
            "phase6_shadow_report_result": phase6_shadow_report_result,
            "phase8_market_narrative_result": phase8_market_narrative_result,
            "phase9_cross_setup_result": phase9_cross_setup_result,
            "outcome_result": outcome_result,
        },
    )
    phase14_meta_evolution_result = refresh_phase14_meta_evolution_safely(
        evaluated_setups=evaluated_setups,
        context=context,
        final_decisions=final_decisions,
        phase_results={
            "phase10_master_shadow_result": phase10_master_shadow_result,
            "phase11_promotion_gate_result": phase11_promotion_gate_result,
            "phase12_advanced_regime_result": phase12_advanced_regime_result,
            "phase13_strategy_genome_result": phase13_strategy_genome_result,
            "phase5_memory_result": phase5_memory_result,
            "phase6_shadow_report_result": phase6_shadow_report_result,
            "phase8_market_narrative_result": phase8_market_narrative_result,
            "phase9_cross_setup_result": phase9_cross_setup_result,
            "outcome_result": outcome_result,
        },
    )

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
        "adaptive_memory_result": adaptive_memory_result,
        "phase5_memory_result": phase5_memory_result,
        "phase6_shadow_report_result": phase6_shadow_report_result,
        "phase8_market_narrative_result": phase8_market_narrative_result,
        "phase9_cross_setup_result": phase9_cross_setup_result,
        "phase10_master_shadow_result": phase10_master_shadow_result,
        "phase11_promotion_gate_result": phase11_promotion_gate_result,
        "phase12_advanced_regime_result": phase12_advanced_regime_result,
        "phase13_strategy_genome_result": phase13_strategy_genome_result,
        "phase14_meta_evolution_result": phase14_meta_evolution_result,
    }


if __name__ == "__main__":
    run_master_brain()
