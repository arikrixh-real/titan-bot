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
import csv
import json
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
from journal.trade_id import build_canonical_trade_id, build_setup_signature
from journal.outcome_tracker import track_trade_outcomes
from runtime_global_lock import acquire_global_runtime_lock, release_global_runtime_lock
from utils.market_hours import TRADE_WINDOW_END, TRADE_WINDOW_START, is_trade_window

_SUPABASE_WARNED = set()

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
    from engines.meta_regime_intelligence import run_meta_regime_intelligence
    print("PHASE 43 META-REGIME INTELLIGENCE CONNECTED")
except Exception:
    run_meta_regime_intelligence = None

try:
    from engines.autonomous_research_brain import build_autonomous_research_report
    print("PHASE 21 AUTONOMOUS RESEARCH BRAIN ACTIVE")
except Exception:
    build_autonomous_research_report = None

try:
    from engines.backtesting_validation_framework import build_validation_report
    print("PHASE 22 BACKTESTING VALIDATION ACTIVE")
except Exception:
    build_validation_report = None

try:
    from engines.paper_trading_engine import (
        build_paper_trading_report,
        load_paper_account,
        open_paper_position,
        place_paper_order,
        save_paper_account,
        simulate_fill,
        sync_paper_account_from_trade_results,
    )
    print("PHASE 23 PAPER TRADING ACTIVE")
except Exception:
    build_paper_trading_report = None
    load_paper_account = None
    open_paper_position = None
    place_paper_order = None
    save_paper_account = None
    simulate_fill = None
    sync_paper_account_from_trade_results = None

try:
    from engines.broker_execution_safety_system import (
        build_execution_safety_report,
        run_pre_order_safety_checks,
        write_latest_execution_safety_report,
    )
    print("PHASE 24 BROKER EXECUTION SAFETY ACTIVE")
except Exception:
    build_execution_safety_report = None
    run_pre_order_safety_checks = None
    write_latest_execution_safety_report = None

try:
    from engines.smart_execution_engine import build_smart_execution_report
    print("PHASE 25 SMART EXECUTION ENGINE ACTIVE")
except Exception:
    build_smart_execution_report = None

try:
    from engines.order_book_microstructure_engine import build_microstructure_report
    print("PHASE 26 MICROSTRUCTURE ENGINE ACTIVE")
except Exception:
    build_microstructure_report = None

try:
    from engines.options_flow_intelligence_engine import build_options_flow_report
    print("PHASE 27 OPTIONS FLOW ENGINE ACTIVE")
except Exception:
    build_options_flow_report = None

try:
    from engines.news_intelligence_2_engine import build_news_intelligence_report
    print("PHASE 28 NEWS INTELLIGENCE 2 ACTIVE")
except Exception:
    build_news_intelligence_report = None

try:
    from engines.economic_calendar_intelligence_engine import build_economic_calendar_report
    print("PHASE 29 ECONOMIC CALENDAR INTELLIGENCE ACTIVE")
except Exception:
    build_economic_calendar_report = None

try:
    from engines.institutional_liquidity_map_engine import build_institutional_liquidity_report
    print("PHASE 30 INSTITUTIONAL LIQUIDITY MAP ACTIVE")
except Exception:
    build_institutional_liquidity_report = None

try:
    from engines.scenario_simulation_engine import build_scenario_simulation_report
    print("PHASE 31 SCENARIO SIMULATION ENGINE ACTIVE")
except Exception:
    build_scenario_simulation_report = None

try:
    from engines.multi_agent_debate_engine import build_multi_agent_debate_report
    print("PHASE 32 MULTI-AGENT DEBATE ENGINE ACTIVE")
except Exception:
    build_multi_agent_debate_report = None

try:
    from engines.self_reflection_meta_cognition_engine import build_self_reflection_report
    print("PHASE 33 SELF-REFLECTION META-COGNITION ACTIVE")
except Exception:
    build_self_reflection_report = None

try:
    from engines.confidence_calibration_engine import build_confidence_calibration_report
    print("PHASE 34 CONFIDENCE CALIBRATION ENGINE ACTIVE")
except Exception:
    build_confidence_calibration_report = None

try:
    from engines.no_trade_intelligence_engine import build_no_trade_intelligence_report
    print("PHASE 35 NO-TRADE INTELLIGENCE ACTIVE")
except Exception:
    build_no_trade_intelligence_report = None

try:
    from engines.memory_consolidation_engine import build_memory_consolidation_report
    print("PHASE 36 MEMORY CONSOLIDATION ENGINE ACTIVE")
except Exception:
    build_memory_consolidation_report = None

try:
    from engines.auto_repair_assistant_engine import build_auto_repair_report
    print("PHASE 37 AUTO-REPAIR ASSISTANT ACTIVE")
except Exception:
    build_auto_repair_report = None

try:
    from engines.phase38_test_mode_guard import evaluate_phase38_runtime_guard, write_phase38_runtime_status
    print("PHASE 38 TEST MODE GUARD ACTIVE")
except Exception:
    evaluate_phase38_runtime_guard = None
    write_phase38_runtime_status = None

try:
    from engines.accuracy_validation_framework import run_accuracy_validation
    print("PHASE 40 ACCURACY VALIDATION FRAMEWORK CONNECTED")
except Exception:
    run_accuracy_validation = None

try:
    from engines.meta_learning_engine import run_meta_learning
    print("PHASE 41 META-LEARNING ENGINE CONNECTED")
except Exception:
    run_meta_learning = None

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
RESEARCH_DIR = Path("data/research")
AUTONOMOUS_RESEARCH_REPORT_PATH = RESEARCH_DIR / "autonomous_research_report.json"
BACKTESTING_VALIDATION_REPORT_PATH = RESEARCH_DIR / "backtesting_validation_report.json"
EXECUTION_SAFETY_DIR = Path("data/execution_safety")
LATEST_EXECUTION_SAFETY_REPORT_PATH = EXECUTION_SAFETY_DIR / "latest_execution_safety_report.json"
LATEST_SMART_EXECUTION_REPORT_PATH = EXECUTION_SAFETY_DIR / "latest_smart_execution_report.json"
LATEST_PAPER_TRADING_REPORT_PATH = Path("data") / "paper_trading" / "latest_paper_trading_report.json"
MAX_RESEARCH_ROWS = 300

TRADE_HISTORY_PATHS = [
    Path("data/journals/trade_outcomes.jsonl"),
    Path("data/journals/trade_outcomes.csv"),
    Path("data/journals/trade_journal.jsonl"),
    Path("data/journals/trade_journal.csv"),
]

SCAN_HISTORY_PATHS = [
    Path("data/journals/scan_journal.jsonl"),
    Path("data/journals/scan_journal.csv"),
    Path("journal/scan_journal.json"),
    Path("journal/scan_journal.csv"),
]


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
        text = str(e)
        if "WinError 10013" in text:
            key = "socket"
            if key not in _SUPABASE_WARNED:
                _SUPABASE_WARNED.add(key)
                print("[Supabase WARN] socket unavailable; DB actions skipped.")
        else:
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

            if "WinError 10013" in str(e):
                key = f"{table_name}:insert:socket"
                if key not in _SUPABASE_WARNED:
                    _SUPABASE_WARNED.add(key)
                    print(f"[Supabase WARN] {table_name} insert skipped; socket unavailable.")
            else:
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

            if "WinError 10013" in str(e):
                key = f"{table_name}:update:socket"
                if key not in _SUPABASE_WARNED:
                    _SUPABASE_WARNED.add(key)
                    print(f"[Supabase WARN] {table_name} update skipped; socket unavailable.")
            else:
                print(f"[Supabase ERROR] {table_name} update failed: {e}")
            return False

    print(f"[Supabase ERROR] {table_name} update failed after schema cleanup retries.")
    return False


def _day_bounds_iso():
    start = _now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _packet_setup_signature(packet):
    if not isinstance(packet, dict):
        return ""

    symbol = _deep_get(packet, ["symbol", "stock", "ticker", "name"])
    side = _deep_get(packet, ["side", "direction", "trade_side"])
    entry = _deep_get(packet, ["entry", "entry_price", "price"])
    sl = _deep_get(packet, ["sl", "stop_loss", "stoploss"])
    target = _deep_get(packet, ["target", "tp", "target_price", "t1"])
    return build_setup_signature(symbol, side, entry, sl, target)


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


def _same_day_setup_exists(client, setup_signature):
    if client is None or not setup_signature:
        return False

    start_iso, end_iso = _day_bounds_iso()

    for time_col in ("opened_at", "created_at", "closed_at"):
        try:
            result = (
                client.table("trade_results")
                .select("*")
                .gte(time_col, start_iso)
                .lt(time_col, end_iso)
                .limit(1000)
                .execute()
            )
        except Exception:
            continue

        for row in result.data or []:
            if _row_setup_signature(row) == setup_signature:
                return True

    return False


def filter_duplicate_setup_packets(execution_result):
    """
    Suppress same-day duplicate setup packets before Telegram send.
    """
    if not isinstance(execution_result, dict):
        return execution_result

    packets = execution_result.get("packets", []) or []
    if not packets:
        return execution_result

    supabase = _get_supabase()
    if supabase is None:
        return execution_result

    filtered = []
    skipped = []
    seen = set()

    for packet in packets:
        signature = _packet_setup_signature(packet)
        if not signature:
            filtered.append(packet)
            continue

        if signature in seen or _same_day_setup_exists(supabase, signature):
            skipped.append(signature)
            print(f"[TradeResults] DUPLICATE_SETUP_SKIPPED before Telegram: {signature}")
            continue

        seen.add(signature)
        packet["setup_signature"] = signature
        filtered.append(packet)

    if skipped:
        execution_result = dict(execution_result)
        execution_result["packets"] = filtered
        execution_result["count"] = len(filtered)
        execution_result["duplicate_setup_skipped"] = skipped
        execution_result["execution_mode"] = "READY_FOR_TELEGRAM" if filtered else "NO_EXECUTION"

    return execution_result


# =========================================================
# MARKET CLOSE HANDLER
# =========================================================

_MARKET_CLOSE_WARNED_KEYS = set()


def _market_close_warn_once(key, message):
    if key in _MARKET_CLOSE_WARNED_KEYS:
        return
    _MARKET_CLOSE_WARNED_KEYS.add(key)
    print(message)


def auto_close_live_trades_after_market_close():
    """
    After 3:30 PM IST, unresolved LIVE trades become MARKET_CLOSED.
    This prevents dashboard showing fake live trades at night.
    """
    now = _now_ist()

    # Do nothing before market close or on non-trading days. This avoids
    # unnecessary Supabase/socket calls during weekend research-only cycles.
    if now.weekday() >= 5 or now.time() < MARKET_CLOSE:
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
        error_text = str(e)
        if "WinError 10013" in error_text:
            _market_close_warn_once(
                "winerror_10013",
                "[MarketClose WARN] skipped safely during market-closed/off-hours",
            )
        else:
            _market_close_warn_once("cleanup", f"[MarketClose WARN] Cleanup skipped safely: {e}")

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
            try:
                from engines.paper_trading_engine import load_paper_account, prepare_paper_trade_fields
                packet = prepare_paper_trade_fields(packet, load_paper_account())
            except Exception:
                pass

            symbol = _deep_get(packet, ["symbol", "stock", "ticker", "name"])
            side = _deep_get(packet, ["side", "direction", "trade_side"])

            entry = _safe_float(_deep_get(packet, ["entry", "entry_price", "price"]))
            sl = _safe_float(_deep_get(packet, ["sl", "stop_loss", "stoploss"]))
            tp = _safe_float(_deep_get(packet, ["tp", "target", "target_price", "t1"]))
            quantity = _safe_float(_deep_get(packet, ["quantity", "qty"]), 0)
            position_size = _safe_float(_deep_get(packet, ["position_size"]), 0)
            risk_amount = _safe_float(_deep_get(packet, ["risk_amount"]), 0)
            risk_pct = _safe_float(_deep_get(packet, ["risk_per_trade_pct"]), 1.0)

            rr = _safe_float(_deep_get(packet, ["rr", "risk_reward", "actual_rr"]), 0)
            score = _safe_float(_deep_get(packet, ["score", "final_score", "rank_score"]), 0)
            reason = _deep_get(packet, ["reason", "reasoning", "message", "note"], "")
            scan_id = _deep_get(packet, ["scan_id", "scan_uuid", "scan"])
            existing_trade_id = _deep_get(packet, ["trade_id"])

            if not scan_id and isinstance(existing_trade_id, str) and existing_trade_id.count("|") == 5:
                scan_id = existing_trade_id.split("|", 1)[0]

            if not scan_id and isinstance(context, dict):
                scan_id = (
                    context.get("scan_id")
                    or context.get("scan_uuid")
                    or context.get("cycle_id")
                )

            if not symbol or not side or entry is None or sl is None or tp is None or quantity <= 0:
                print(f"[TradeResults] Skipped invalid packet: {packet}")
                continue

            symbol = str(symbol).upper()
            side = str(side).upper()
            trade_id = build_canonical_trade_id(
                scan_id,
                symbol,
                side,
                entry,
                sl,
                tp,
                source="TradeResults",
            )
            setup_signature = build_setup_signature(symbol, side, entry, sl, tp)

            if not trade_id:
                print(f"[TradeResults] Skipped packet because canonical trade_id could not be generated: {symbol} {side}")
                continue
            if not setup_signature:
                print(f"[TradeResults] Skipped packet because setup_signature could not be generated: {symbol} {side}")
                continue

            if symbol in TEST_SYMBOLS:
                print(f"[TradeResults] Skipped test symbol: {symbol}")
                continue

            if _same_day_setup_exists(supabase, setup_signature):
                print(f"[TradeResults] DUPLICATE_SETUP_SKIPPED: {setup_signature}")
                continue

            # FINAL DUPLICATE PROTECTION
            if _live_trade_exists(supabase, symbol, side):
                print(f"[TradeResults] LIVE trade already exists for {symbol} {side}. Skipping duplicate.")
                continue

            row = {
                "trade_id": trade_id,
                "setup_signature": setup_signature,
                "trade_date": _now_ist().strftime("%Y-%m-%d"),
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "entry_price": entry,
                "sl": sl,
                "tp": tp,
                "target_price": tp,
                "stop_loss": sl,
                "quantity": quantity,
                "qty": quantity,
                "position_size": position_size,
                "risk_amount": risk_amount,
                "risk_per_trade_pct": risk_pct,
                "paper_trade_id": packet.get("paper_trade_id"),
                "is_paper_trade": True,
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


def _read_csv_rows_limited(path, limit=MAX_RESEARCH_ROWS):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        return [row for row in rows if isinstance(row, dict)][-limit:]
    except Exception:
        return []


def _read_json_rows_limited(path, limit=MAX_RESEARCH_ROWS):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return []
        if path.suffix == ".jsonl":
            rows = []
            for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
            return rows[-limit:]

        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)][-limit:]
        if isinstance(data, dict):
            for key in ("trades", "outcomes", "records", "items", "data", "scans"):
                items = data.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)][-limit:]
            return [data]
    except Exception:
        return []
    return []


def _read_research_rows(paths, limit=MAX_RESEARCH_ROWS):
    rows = []
    for path in paths:
        if path.suffix == ".csv":
            rows.extend(_read_csv_rows_limited(path, limit))
        elif path.suffix in {".json", ".jsonl"}:
            rows.extend(_read_json_rows_limited(path, limit))
        if len(rows) >= limit:
            rows = rows[-limit:]
    return rows[-limit:]


def refresh_phase21_autonomous_research_safely(
    context=None,
    news_items=None,
    evaluated_setups=None,
    final_decisions=None,
):
    """
    Phase 21 research-only autonomous research report.

    Reads bounded local history and current-cycle context snapshots, writes a
    JSON research artifact, and never changes live trading rules, ranking,
    alerts, Telegram, dashboard, broker/execution, or strategy promotion.
    """
    if build_autonomous_research_report is None:
        print("[Phase21] Autonomous research brain not connected.")
        return None

    try:
        trade_history = _read_research_rows(TRADE_HISTORY_PATHS)
        scan_history = _read_research_rows(SCAN_HISTORY_PATHS)

        if evaluated_setups:
            for setup in evaluated_setups[-MAX_RESEARCH_ROWS:]:
                if isinstance(setup, dict):
                    scan_history.append(dict(setup))
            scan_history = scan_history[-MAX_RESEARCH_ROWS:]

        research_context = deepcopy(context or {})
        if not isinstance(research_context, dict):
            research_context = {}
        research_context["news_items"] = deepcopy(news_items or [])
        research_context["final_decisions_summary"] = deepcopy(final_decisions or {})

        report = build_autonomous_research_report(
            trade_history=trade_history,
            scan_history=scan_history,
            context=research_context,
        )
        if isinstance(report, dict):
            report.update({
                "advisory_only": True,
                "research_only": True,
                "shadow_mode": True,
                "live_order_allowed": False,
                "live_rank_mutation_allowed": False,
                "pyramid_placement": "master_controller_research_sidecar",
            })

        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        with open(AUTONOMOUS_RESEARCH_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        mode = report.get("research_mode", "UNKNOWN") if isinstance(report, dict) else "UNKNOWN"
        score = report.get("research_priority_score", "UNKNOWN") if isinstance(report, dict) else "UNKNOWN"
        print(f"[Phase21] Autonomous research report saved: {AUTONOMOUS_RESEARCH_REPORT_PATH} | mode={mode} | score={score}")
        return report

    except Exception as e:
        print(f"[Phase21 ERROR] Autonomous research failed open: {e}")
        return {"error": str(e), "failed_open": True}


def refresh_phase22_backtesting_validation_safely(
    autonomous_research_report=None,
    context=None,
    trade_history=None,
    scan_history=None,
):
    """
    Phase 22 validation-only report.

    Consumes research ideas/backtest queue and bounded local history, writes a
    validation artifact, and never promotes strategies or changes live rules.
    """
    if build_validation_report is None:
        print("[Phase22] Backtesting validation framework not connected.")
        return None

    try:
        research_report = autonomous_research_report if isinstance(autonomous_research_report, dict) else {}
        history = trade_history if isinstance(trade_history, list) else _read_research_rows(TRADE_HISTORY_PATHS)
        if not history and isinstance(scan_history, list):
            history = scan_history

        candidates = []
        for key in ("backtest_queue", "strategy_ideas", "generated_hypotheses"):
            value = research_report.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))

        strategy = candidates[0] if candidates else {"name": "GENERAL_RESEARCH_VALIDATION"}
        validation_context = deepcopy(context or {})
        if not isinstance(validation_context, dict):
            validation_context = {}
        validation_context["strategy_results"] = candidates[:20]

        report = build_validation_report(
            strategy=strategy,
            historical_data=history,
            context=validation_context,
        )
        if isinstance(report, dict):
            report.update({
                "advisory_only": True,
                "research_only": True,
                "shadow_mode": True,
                "live_order_allowed": False,
                "live_rank_mutation_allowed": False,
                "pyramid_placement": "master_controller_validation_sidecar",
            })

        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        with open(BACKTESTING_VALIDATION_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        status = report.get("validation_status", "UNKNOWN") if isinstance(report, dict) else "UNKNOWN"
        score = report.get("validation_score", "UNKNOWN") if isinstance(report, dict) else "UNKNOWN"
        print(f"[Phase22] Backtesting validation report saved: {BACKTESTING_VALIDATION_REPORT_PATH} | status={status} | score={score}")
        return report

    except Exception as e:
        print(f"[Phase22 ERROR] Backtesting validation failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_deployment_allowed": False}


def refresh_phase23_paper_trading_safely(final_decisions=None, context=None):
    """
    Phase 23 paper-only simulator.

    It may create internal simulated orders from final selected candidates.
    It never calls broker execution, never sends alerts, and never changes live
    execution or daily alert behavior.
    """
    required = [
        build_paper_trading_report,
        load_paper_account,
        open_paper_position,
        place_paper_order,
        simulate_fill,
    ]
    if any(item is None for item in required):
        print("[Phase23] Paper trading engine not connected.")
        return None

    try:
        account = load_paper_account()
        selected = []
        if isinstance(final_decisions, dict):
            selected = final_decisions.get("selected") if isinstance(final_decisions.get("selected"), list) else []

        paper_orders = []
        for candidate in selected:
            if not isinstance(candidate, dict):
                continue
            order = place_paper_order(account, candidate)
            paper_orders.append(order)
            if not isinstance(order, dict) or not order.get("accepted"):
                continue
            filled = simulate_fill(order, context if isinstance(context, dict) else {})
            account = open_paper_position(load_paper_account(), filled)

        if sync_paper_account_from_trade_results is not None:
            sync_paper_account_from_trade_results()

        report = build_paper_trading_report(load_paper_account())
        if isinstance(report, dict):
            report.update({
                "advisory_only": True,
                "paper_only": True,
                "shadow_mode": True,
                "live_order_allowed": False,
                "broker_orders": False,
                "telegram_changes": False,
                "supabase_writes": False,
                "live_rank_mutation_allowed": False,
                "pyramid_placement": "master_controller_paper_sidecar",
            })
        print(
            "[Phase23] Paper trading refreshed. "
            f"status={report.get('paper_trading_status')} | "
            f"balance={report.get('current_balance')} | "
            f"orders={len(paper_orders)}"
        )
        report["paper_orders_created"] = paper_orders
        LATEST_PAPER_TRADING_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LATEST_PAPER_TRADING_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return report

    except Exception as e:
        print(f"[Phase23 ERROR] Paper trading failed open: {e}")
        return {"error": str(e), "failed_open": True, "paper_only": True}


def refresh_phase24_execution_safety_safely(final_decisions=None, context=None):
    """
    Phase 24 broker execution safety monitoring only.

    Builds and saves a fail-closed broker safety report. It does not place
    orders, enable live mode, call execution, or alter alert behavior.
    """
    if (
        build_execution_safety_report is None
        or run_pre_order_safety_checks is None
        or write_latest_execution_safety_report is None
    ):
        print("[Phase24] Broker execution safety not connected.")
        return None

    try:
        selected = []
        if isinstance(final_decisions, dict) and isinstance(final_decisions.get("selected"), list):
            selected = final_decisions.get("selected")
        sample_order = selected[0] if selected and isinstance(selected[0], dict) else {}
        account_snapshot = {}
        if isinstance(context, dict):
            account_snapshot = {
                "balance": context.get("account_balance") or context.get("capital") or 1000,
                "daily_loss_pct": context.get("daily_loss_pct") or 0.0,
            }
        order_history = selected if isinstance(selected, list) else []
        broker_status = {"connected": False, "status": "DISCONNECTED"}
        pre_order = run_pre_order_safety_checks(
            order=sample_order,
            account_snapshot=account_snapshot,
            order_history=order_history,
            broker_status=broker_status,
        )
        report = write_latest_execution_safety_report(
            account_snapshot=account_snapshot,
            order_history=order_history,
            broker_status=broker_status,
            extra_fields={"pre_order_safety_checks": pre_order},
        )
        if isinstance(report, dict):
            report.update({
                "advisory_only": True,
                "safety_only": True,
                "shadow_mode": True,
                "live_order_allowed": False,
                "broker_orders": False,
                "telegram_changes": False,
                "live_rank_mutation_allowed": False,
                "pyramid_placement": "master_controller_execution_safety_sidecar",
            })
            with open(LATEST_EXECUTION_SAFETY_REPORT_PATH, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        print(
            "[Phase24] Execution safety report saved: "
            f"{LATEST_EXECUTION_SAFETY_REPORT_PATH} | "
            f"mode={report.get('broker_execution_mode')} | "
            f"allowed={report.get('execution_allowed')}"
        )
        return report
    except Exception as e:
        print(f"[Phase24 ERROR] Broker execution safety failed open for TITAN: {e}")
        return {"error": str(e), "failed_open": True, "execution_allowed": False}


def refresh_phase25_smart_execution_safely(final_decisions=None, paper_result=None, context=None):
    """
    Phase 25 smart execution analysis only.

    Builds one latest execution-quality report from selected candidates or
    paper orders. It never places orders or enables live execution.
    """
    if build_smart_execution_report is None:
        print("[Phase25] Smart execution engine not connected.")
        return None

    try:
        order = {}
        if isinstance(final_decisions, dict) and isinstance(final_decisions.get("selected"), list) and final_decisions.get("selected"):
            candidate = final_decisions.get("selected")[0]
            if isinstance(candidate, dict):
                order = dict(candidate)
        if not order and isinstance(paper_result, dict):
            paper_orders = paper_result.get("paper_orders_created")
            if isinstance(paper_orders, list) and paper_orders and isinstance(paper_orders[0], dict):
                order = dict(paper_orders[0])
        report = build_smart_execution_report(order, context if isinstance(context, dict) else {})
        if isinstance(report, dict):
            report.update({
                "advisory_only": True,
                "execution_analysis_only": True,
                "shadow_mode": True,
                "live_order_allowed": False,
                "broker_orders": False,
                "telegram_changes": False,
                "live_rank_mutation_allowed": False,
                "pyramid_placement": "master_controller_execution_quality_sidecar",
            })
        EXECUTION_SAFETY_DIR.mkdir(parents=True, exist_ok=True)
        with open(LATEST_SMART_EXECUTION_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(
            "[Phase25] Smart execution report saved: "
            f"{LATEST_SMART_EXECUTION_REPORT_PATH} | "
            f"recommendation={report.get('execution_recommendation')} | "
            f"live_allowed={report.get('live_order_allowed')}"
        )
        return report
    except Exception as e:
        print(f"[Phase25 ERROR] Smart execution failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def _selected_sidecar_candidate(final_decisions=None):
    """
    Snapshot one selected candidate for Phase 26-34 report-only sidecars.
    Sidecar report builders may annotate their local setup, but must not mutate
    final selected/rejected pools or downstream alert/execution state.
    """
    if not isinstance(final_decisions, dict):
        return {}
    selected = final_decisions.get("selected")
    if not isinstance(selected, list) or not selected or not isinstance(selected[0], dict):
        return {}
    return deepcopy(selected[0])


def refresh_phase26_microstructure_safely(final_decisions=None, context=None):
    """
    Phase 26 microstructure sidecar report.

    Uses selected candidate and any available depth/tick/context data. If no
    depth exists, the engine falls back to proxy or insufficient mode.
    """
    if build_microstructure_report is None:
        print("[Phase26] Microstructure engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        depth_data = market_context.get("depth_data") or market_context.get("market_depth")
        tick_data = market_context.get("tick_data") or market_context.get("ticks")
        report = build_microstructure_report(setup=setup, depth_data=depth_data, tick_data=tick_data, market_context=market_context)
        print(
            "[Phase26] Microstructure report saved: data/microstructure/latest_microstructure_report.json | "
            f"mode={report.get('data_mode')} | score={report.get('microstructure_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase26 ERROR] Microstructure failed open: {e}")
        return {"error": str(e), "failed_open": True}


def refresh_phase27_options_flow_safely(final_decisions=None, context=None):
    """
    Phase 27 options-flow sidecar report.

    Uses selected candidate and any available option-chain/context data. If no
    option chain exists, the engine falls back to proxy or insufficient mode.
    """
    if build_options_flow_report is None:
        print("[Phase27] Options flow engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        option_chain = setup.get("option_chain") or market_context.get("option_chain")
        symbol = str(setup.get("symbol") or setup.get("stock") or "").strip()
        option_chains = market_context.get("option_chains")
        if option_chain is None and isinstance(option_chains, dict) and symbol:
            option_chain = option_chains.get(symbol) or option_chains.get(symbol.upper()) or option_chains.get(symbol.lower())
        report = build_options_flow_report(setup=setup, option_chain=option_chain, context=market_context)
        print(
            "[Phase27] Options flow report saved: data/options_flow/latest_options_flow_report.json | "
            f"mode={report.get('data_mode')} | score={report.get('options_flow_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase27 ERROR] Options flow failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase28_news_intelligence_safely(final_decisions=None, context=None, news_items=None):
    """
    Phase 28 news intelligence sidecar report.

    Uses selected candidate and any available real news/context data. If no real
    news exists, the engine falls back to proxy or insufficient mode.
    """
    if build_news_intelligence_report is None:
        print("[Phase28] News intelligence 2 engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        candidate_news = setup.get("news_items") or news_items or market_context.get("news_items") or market_context.get("news")
        report = build_news_intelligence_report(setup=setup, news_items=candidate_news, context=market_context)
        print(
            "[Phase28] News intelligence report saved: data/news_intelligence/latest_news_intelligence_2_report.json | "
            f"mode={report.get('news_data_mode')} | score={report.get('news_intelligence_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase28 ERROR] News intelligence failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase29_economic_calendar_safely(final_decisions=None, context=None):
    """
    Phase 29 economic calendar sidecar report.

    Uses selected candidate and any available calendar/context data. If no real
    calendar exists, the engine falls back to proxy or insufficient mode.
    """
    if build_economic_calendar_report is None:
        print("[Phase29] Economic calendar engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        calendar_events = setup.get("calendar_events") or market_context.get("calendar_events") or market_context.get("economic_calendar")
        report = build_economic_calendar_report(setup=setup, calendar_events=calendar_events, context=market_context)
        print(
            "[Phase29] Economic calendar report saved: data/economic_calendar/latest_economic_calendar_report.json | "
            f"mode={report.get('calendar_data_mode')} | score={report.get('calendar_intelligence_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase29 ERROR] Economic calendar failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase30_liquidity_map_safely(final_decisions=None, context=None):
    """
    Phase 30 institutional liquidity-map sidecar report.

    Uses selected candidate and any available OHLCV/liquidity/context data. If
    no real data exists, the engine falls back to proxy or insufficient mode.
    """
    if build_institutional_liquidity_report is None:
        print("[Phase30] Institutional liquidity map engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        liquidity_data = (
            setup.get("liquidity_data")
            or setup.get("ohlcv")
            or market_context.get("liquidity_data")
            or market_context.get("ohlcv")
            or market_context.get("candles")
        )
        report = build_institutional_liquidity_report(setup=setup, liquidity_data=liquidity_data, context=market_context)
        print(
            "[Phase30] Institutional liquidity report saved: data/liquidity_map/latest_institutional_liquidity_report.json | "
            f"mode={report.get('liquidity_data_mode')} | score={report.get('liquidity_map_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase30 ERROR] Institutional liquidity map failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase31_scenario_simulation_safely(final_decisions=None, context=None):
    """
    Phase 31 scenario simulation sidecar report.

    Uses selected candidate and any available market/context data. If no real
    market data exists, the engine falls back to proxy or insufficient mode.
    """
    if build_scenario_simulation_report is None:
        print("[Phase31] Scenario simulation engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        market_data = (
            setup.get("market_data")
            or setup.get("ohlcv")
            or market_context.get("market_data")
            or market_context.get("ohlcv")
            or market_context.get("candles")
        )
        report = build_scenario_simulation_report(setup=setup, context=market_context, market_data=market_data)
        print(
            "[Phase31] Scenario simulation report saved: data/scenario_simulation/latest_scenario_simulation_report.json | "
            f"mode={report.get('scenario_data_mode')} | score={report.get('scenario_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase31 ERROR] Scenario simulation failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase32_multi_agent_debate_safely(final_decisions=None, context=None):
    """
    Phase 32 multi-agent debate sidecar report.

    Uses the selected candidate and full available context. If no rich context
    exists, the engine falls back to proxy or insufficient mode.
    """
    if build_multi_agent_debate_report is None:
        print("[Phase32] Multi-agent debate engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        report = build_multi_agent_debate_report(setup=setup, context=market_context)
        print(
            "[Phase32] Multi-agent debate report saved: data/multi_agent_debate/latest_multi_agent_debate_report.json | "
            f"mode={report.get('debate_data_mode')} | score={report.get('debate_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase32 ERROR] Multi-agent debate failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase33_self_reflection_safely(final_decisions=None, context=None):
    """
    Phase 33 self-reflection sidecar report.

    Uses the selected candidate plus any available context/trade history. If no
    rich evidence exists, the engine falls back to proxy or insufficient mode.
    """
    if build_self_reflection_report is None:
        print("[Phase33] Self-reflection meta-cognition engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        trade_result = (
            setup.get("trade_result")
            or market_context.get("latest_trade_result")
            or market_context.get("trade_result")
            or {}
        )
        trade_history = (
            market_context.get("trade_history")
            or market_context.get("trade_results")
            or market_context.get("closed_trades")
            or market_context.get("recent_trades")
            or []
        )
        report = build_self_reflection_report(
            setup=setup,
            context=market_context,
            trade_result=trade_result,
            trade_history=trade_history,
        )
        print(
            "[Phase33] Self-reflection report saved: data/self_reflection/latest_self_reflection_report.json | "
            f"mode={report.get('reflection_data_mode')} | score={report.get('reflection_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase33 ERROR] Self-reflection failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase34_confidence_calibration_safely(final_decisions=None, context=None):
    """
    Phase 34 confidence calibration sidecar report.

    Uses selected candidate plus prediction/outcome history when available. If
    history is missing, the engine falls back to proxy or insufficient mode.
    """
    if build_confidence_calibration_report is None:
        print("[Phase34] Confidence calibration engine not connected.")
        return None

    try:
        setup = _selected_sidecar_candidate(final_decisions)
        market_context = context if isinstance(context, dict) else {}
        prediction_history = (
            market_context.get("prediction_history")
            or market_context.get("predictions")
            or market_context.get("confidence_predictions")
            or market_context.get("calibration_predictions")
            or []
        )
        outcome_history = (
            market_context.get("outcome_history")
            or market_context.get("trade_results")
            or market_context.get("closed_trades")
            or market_context.get("recent_trades")
            or []
        )
        report = build_confidence_calibration_report(
            setup=setup,
            prediction_history=prediction_history,
            outcome_history=outcome_history,
            context=market_context,
        )
        print(
            "[Phase34] Confidence calibration report saved: data/confidence_calibration/latest_confidence_calibration_report.json | "
            f"mode={report.get('calibration_data_mode')} | score={report.get('calibrated_confidence_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase34 ERROR] Confidence calibration failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase35_no_trade_intelligence_safely(final_decisions=None, context=None):
    """
    Phase 35 no-trade intelligence sidecar report.

    Uses selected candidate plus market context/recent setups. If data is
    missing, the engine stays non-blocking and insufficient-mode.
    """
    if build_no_trade_intelligence_report is None:
        print("[Phase35] No-trade intelligence engine not connected.")
        return None

    try:
        setup = {}
        recent_setups = []
        if isinstance(final_decisions, dict):
            recent_setups = final_decisions.get("selected") or final_decisions.get("rejected") or []
            if isinstance(final_decisions.get("selected"), list) and final_decisions.get("selected"):
                candidate = final_decisions.get("selected")[0]
                if isinstance(candidate, dict):
                    setup = dict(candidate)
        market_context = context if isinstance(context, dict) else {}
        recent_setups = market_context.get("recent_setups") or market_context.get("evaluated_setups") or recent_setups
        report = build_no_trade_intelligence_report(
            setup=setup,
            context=market_context,
            recent_setups=recent_setups,
        )
        print(
            "[Phase35] No-trade intelligence report saved: data/no_trade/latest_no_trade_intelligence_report.json | "
            f"mode={report.get('no_trade_data_mode')} | score={report.get('no_trade_score')} | permission={report.get('trade_permission')}"
        )
        return report
    except Exception as e:
        print(f"[Phase35 ERROR] No-trade intelligence failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def _load_phase36_memory_sources():
    memory_items = []
    for directory in [Path("data/memory"), Path("titan_brain/memory")]:
        try:
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(payload, dict):
                    item = dict(payload)
                    item.setdefault("memory_key", path.stem)
                    item.setdefault("source_path", str(path))
                    memory_items.append(item)
                elif isinstance(payload, list):
                    for index, value in enumerate(payload):
                        if isinstance(value, dict):
                            item = dict(value)
                            item.setdefault("memory_key", f"{path.stem}_{index}")
                            item.setdefault("source_path", str(path))
                            memory_items.append(item)
        except Exception:
            continue
    return memory_items


def _phase36_trade_history(context=None):
    market_context = context if isinstance(context, dict) else {}
    for key in ("trade_history", "trade_results", "closed_trades", "recent_trades", "outcome_history"):
        value = market_context.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def refresh_phase36_memory_consolidation_safely(context=None):
    """
    Phase 36 memory consolidation sidecar report.

    Reads existing memory snapshots and available trade history, then writes
    optional consolidation artifacts. Core TITAN memory files are not deleted.
    """
    if build_memory_consolidation_report is None:
        print("[Phase36] Memory consolidation engine not connected.")
        return None

    try:
        market_context = context if isinstance(context, dict) else {}
        memory_data = market_context.get("memory_data") or _load_phase36_memory_sources()
        trade_history = _phase36_trade_history(market_context)
        report = build_memory_consolidation_report(
            memory_data=memory_data,
            trade_history=trade_history,
            context=market_context,
        )
        if isinstance(report, dict):
            report.update({
                "advisory_only": True,
                "research_only": True,
                "shadow_mode": True,
                "live_order_allowed": False,
                "live_rank_mutation_allowed": False,
                "pyramid_placement": "master_controller_memory_sidecar",
            })
            memory_report_path = Path("data") / "memory_consolidation" / "latest_memory_consolidation_report.json"
            memory_report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(memory_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        print(
            "[Phase36] Memory consolidation report saved: data/memory_consolidation/latest_memory_consolidation_report.json | "
            f"mode={report.get('memory_data_mode')} | score={report.get('memory_quality_score')}"
        )
        return {
            "memory_quality_score": report.get("memory_quality_score"),
            "memory_bias": report.get("memory_bias"),
            "memory_warning": report.get("memory_warning"),
            "memory_data_mode": report.get("memory_data_mode"),
            "strategic_memory_index": report.get("strategic_memory_index"),
            "adaptive_recall_weights": report.get("adaptive_recall_weights"),
            "important_patterns": report.get("important_patterns"),
            "memory_explanations": report.get("explanations", []),
            "report": report,
        }
    except Exception as e:
        print(f"[Phase36 ERROR] Memory consolidation failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False}


def refresh_phase37_auto_repair_safely(context=None, github_logs=None):
    """
    Phase 37 auto-repair assistant sidecar report.

    Diagnostic and recommendation only. It never edits, deletes, pushes, or
    enables live trading.
    """
    if build_auto_repair_report is None:
        print("[Phase37] Auto-repair assistant engine not connected.")
        return None

    try:
        market_context = context if isinstance(context, dict) else {}
        error_logs = (
            market_context.get("runtime_errors")
            or market_context.get("errors")
            or market_context.get("last_error")
            or ["[MarketClose WARN] skipped safely during market-closed/off-hours"]
        )
        report = build_auto_repair_report(
            error_logs=error_logs,
            runtime_context=market_context,
            github_logs=github_logs or market_context.get("github_logs"),
        )
        if isinstance(report, dict):
            report.update({
                "advisory_only": True,
                "diagnostic_only": True,
                "shadow_mode": True,
                "live_order_allowed": False,
                "live_rank_mutation_allowed": False,
                "auto_file_changes_allowed": False,
                "pyramid_placement": "master_controller_diagnostic_sidecar",
            })
            auto_repair_report_path = Path("data") / "auto_repair" / "latest_auto_repair_report.json"
            auto_repair_report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(auto_repair_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        print(
            "[Phase37] Auto-repair report saved: data/auto_repair/latest_auto_repair_report.json | "
            f"status={report.get('repair_status')} | severity={report.get('severity_score')}"
        )
        return report
    except Exception as e:
        print(f"[Phase37 ERROR] Auto-repair assistant failed open: {e}")
        return {"error": str(e), "failed_open": True, "live_order_allowed": False, "auto_file_changes_allowed": False}


def refresh_phase38_test_mode_guard_safely(context=None):
    """
    Phase 38 runtime guard sidecar.

    Advisory visibility only in the master controller; it does not alter ranks,
    scanner output, broker state, Telegram state, Supabase, or final decisions.
    """
    if evaluate_phase38_runtime_guard is None:
        print("[Phase38] Test mode guard not connected.")
        return None

    try:
        runtime_context = context if isinstance(context, dict) else {}
        report = evaluate_phase38_runtime_guard(runtime_context)
        if write_phase38_runtime_status is not None:
            write_phase38_runtime_status(runtime_context)
        print(
            "[Phase38] Runtime guard evaluated | "
            f"allowed={report.get('phase38_runtime_allowed')} | "
            f"unsafe={report.get('phase38_unsafe_states')}"
        )
        return report
    except Exception as e:
        print(f"[Phase38 ERROR] Runtime guard failed closed: {e}")
        return {
            "phase38_runtime_guard_applied": True,
            "phase38_runtime_allowed": False,
            "phase38_fail_closed": True,
            "phase38_unsafe_states": ["PHASE38_GUARD_ERROR_FAIL_CLOSED"],
            "error": str(e),
        }


def refresh_phase40_accuracy_validation_safely(context=None):
    """
    Phase 40 accuracy validation sidecar.

    Reads existing outcome/replay artifacts and writes advisory memory/status
    only. It is not allowed to alter final_decision_engine ranking, alert
    filtering, scanner output, broker state, Telegram, or Supabase.
    """
    if run_accuracy_validation is None:
        print("[Phase40] Accuracy validation framework not connected.")
        return None

    try:
        report = run_accuracy_validation(write_files=True)
        print(
            "[Phase40] Accuracy validation refreshed: data/memory/accuracy_validation_state.json | "
            f"status={report.get('status')} | run_count={report.get('run_count')} | "
            f"closed={report.get('closed_records_this_run')}"
        )
        return report
    except Exception as e:
        print(f"[Phase40 ERROR] Accuracy validation failed open: {e}")
        return {
            "error": str(e),
            "failed_open": True,
            "advisory_only": True,
            "research_only": True,
            "shadow_mode": True,
            "affects_live_ranking": False,
            "affects_execution": False,
            "broker_mutation": False,
            "telegram_mutation": False,
            "supabase_mutation": False,
        }


def refresh_phase41_meta_learning_safely(accuracy_state=None, context=None):
    """
    Phase 41 meta-learning sidecar.

    Consumes Phase 40 state plus existing memories to produce advisory learning
    priorities. It never writes live weights or changes final decisions.
    """
    if run_meta_learning is None:
        print("[Phase41] Meta-learning engine not connected.")
        return None

    try:
        report = run_meta_learning(accuracy_state=accuracy_state, write_files=True)
        print(
            "[Phase41] Meta-learning refreshed: data/memory/meta_learning_state.json | "
            f"status={report.get('status')} | run_count={report.get('run_count')} | "
            f"priorities={report.get('priority_count')}"
        )
        return report
    except Exception as e:
        print(f"[Phase41 ERROR] Meta-learning failed open: {e}")
        return {
            "error": str(e),
            "failed_open": True,
            "advisory_only": True,
            "research_only": True,
            "shadow_mode": True,
            "affects_live_ranking": False,
            "affects_execution": False,
            "broker_mutation": False,
            "telegram_mutation": False,
            "supabase_mutation": False,
        }


def refresh_phase43_meta_regime_safely(context=None):
    """
    Phase 43 meta-regime intelligence sidecar.

    Reads Phase 42 strategy genome state plus existing regime/replay/research
    memories and writes advisory status/report artifacts only. It never changes
    final_decision_engine ranking, scanners, alerts, execution, broker state,
    Telegram, Supabase, dashboards, or live orders.
    """
    if run_meta_regime_intelligence is None:
        print("[Phase43] Meta-regime intelligence not connected.")
        return None

    try:
        report = run_meta_regime_intelligence(write_files=True)
        print(
            "[Phase43] Meta-regime intelligence refreshed: data/memory/meta_regime_intelligence_state.json | "
            f"status={report.get('status')} | run_count={report.get('run_count')} | "
            f"phase42_consumed={report.get('phase42_consumed')}"
        )
        return report
    except Exception as e:
        print(f"[Phase43 ERROR] Meta-regime intelligence failed open: {e}")
        return {
            "error": str(e),
            "failed_open": True,
            "advisory_only": True,
            "research_only": True,
            "shadow_mode": True,
            "affects_live_ranking": False,
            "affects_execution": False,
            "broker_mutation": False,
            "telegram_mutation": False,
            "supabase_mutation": False,
        }


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

def _run_master_brain_unlocked(send_telegram=True, run_outcome_tracker=True, health_check=False):
    print("[MasterBrain] Step 9B Final Master Controller Running...")

    if health_check:
        print("[MasterBrain] Health check mode: read-only status checks only.")
        phase38_runtime_guard = refresh_phase38_test_mode_guard_safely(
            {
                "runtime_mode": "HEALTH",
                "live_execution_enabled": False,
                "telegram_enabled": False,
                "broker_enabled": False,
                "lifecycle_mutation_enabled": False,
            }
        )
        return {
            "mode": "HEALTH_CHECK",
            "trade_window_open": _is_market_alert_time(),
            "supabase_configured": bool(os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY"))),
            "telegram_enabled": bool(send_telegram),
            "outcome_tracker_enabled": bool(run_outcome_tracker),
            "phase38_runtime_guard": phase38_runtime_guard,
            "status": "OK",
        }

    trade_window_open = _is_market_alert_time()
    phase38_runtime_guard = refresh_phase38_test_mode_guard_safely(
        {
            "runtime_mode": os.getenv("TITAN_RUNTIME_MASTER_BRAIN_MODE") or "READ_ONLY",
            "current_mode": "MARKET_MODE" if trade_window_open else "RESEARCH_ONLY",
            "research_only": not trade_window_open,
            "live_execution_enabled": bool(send_telegram and trade_window_open),
            "telegram_enabled": bool(send_telegram and trade_window_open),
            "broker_enabled": False,
            "lifecycle_mutation_enabled": bool(run_outcome_tracker and trade_window_open),
        }
    )
    if isinstance(phase38_runtime_guard, dict) and not phase38_runtime_guard.get("phase38_runtime_allowed", False):
        print("[Phase38] Unsafe runtime combination blocked before live-side effects.")
        phase40_accuracy_validation_result = refresh_phase40_accuracy_validation_safely(context={})
        phase41_meta_learning_result = refresh_phase41_meta_learning_safely(
            accuracy_state=phase40_accuracy_validation_result,
            context={},
        )
        return {
            "mode": "BLOCKED_PHASE38_FAIL_CLOSED",
            "status": "BLOCKED",
            "reason": "Phase 38 blocked unsafe runtime/live capability combination.",
            "sent_packets": [],
            "trade_creation": False,
            "telegram_alerts": False,
            "supabase_writes": False,
            "journal_writes": False,
            "phase38_runtime_guard": phase38_runtime_guard,
            "phase40_accuracy_validation_result": phase40_accuracy_validation_result,
            "phase41_meta_learning_result": phase41_meta_learning_result,
        }

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
        phase43_meta_regime_result = refresh_phase43_meta_regime_safely(context={})
        phase14_meta_evolution_result = refresh_phase14_meta_evolution_safely(
            evaluated_setups=[],
            context={},
            final_decisions={},
            phase_results={
                "phase10_master_shadow_result": phase10_master_shadow_result,
                "phase11_promotion_gate_result": phase11_promotion_gate_result,
                "phase12_advanced_regime_result": phase12_advanced_regime_result,
                "phase13_strategy_genome_result": phase13_strategy_genome_result,
                "phase43_meta_regime_result": phase43_meta_regime_result,
            },
        )
        phase21_autonomous_research_result = refresh_phase21_autonomous_research_safely(
            context={},
            news_items=news_items,
            evaluated_setups=[],
            final_decisions={},
        )
        phase22_backtesting_validation_result = refresh_phase22_backtesting_validation_safely(
            autonomous_research_report=phase21_autonomous_research_result,
            context={},
        )
        phase23_paper_trading_result = refresh_phase23_paper_trading_safely(
            final_decisions={},
            context={},
        )
        phase24_execution_safety_result = refresh_phase24_execution_safety_safely(
            final_decisions={},
            context={},
        )
        phase25_smart_execution_result = refresh_phase25_smart_execution_safely(
            final_decisions={},
            paper_result=phase23_paper_trading_result,
            context={},
        )
        phase26_microstructure_result = refresh_phase26_microstructure_safely(
            final_decisions={},
            context={},
        )
        phase27_options_flow_result = refresh_phase27_options_flow_safely(
            final_decisions={},
            context={},
        )
        phase28_news_intelligence_result = refresh_phase28_news_intelligence_safely(
            final_decisions={},
            context={},
            news_items=news_items,
        )
        phase29_economic_calendar_result = refresh_phase29_economic_calendar_safely(
            final_decisions={},
            context={},
        )
        phase30_liquidity_map_result = refresh_phase30_liquidity_map_safely(
            final_decisions={},
            context={},
        )
        phase31_scenario_simulation_result = refresh_phase31_scenario_simulation_safely(
            final_decisions={},
            context={},
        )
        phase32_multi_agent_debate_result = refresh_phase32_multi_agent_debate_safely(
            final_decisions={},
            context={},
        )
        phase33_self_reflection_result = refresh_phase33_self_reflection_safely(
            final_decisions={},
            context={},
        )
        phase34_confidence_calibration_result = refresh_phase34_confidence_calibration_safely(
            final_decisions={},
            context={},
        )
        phase35_no_trade_intelligence_result = refresh_phase35_no_trade_intelligence_safely(
            final_decisions={},
            context={},
        )
        phase36_memory_consolidation_result = refresh_phase36_memory_consolidation_safely(
            context={},
        )
        phase37_auto_repair_result = refresh_phase37_auto_repair_safely(
            context={},
        )
        phase40_accuracy_validation_result = refresh_phase40_accuracy_validation_safely(context={})
        phase41_meta_learning_result = refresh_phase41_meta_learning_safely(
            accuracy_state=phase40_accuracy_validation_result,
            context={},
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
            "phase43_meta_regime_result": phase43_meta_regime_result,
            "phase14_meta_evolution_result": phase14_meta_evolution_result,
            "phase21_autonomous_research_result": phase21_autonomous_research_result,
            "phase22_backtesting_validation_result": phase22_backtesting_validation_result,
            "phase23_paper_trading_result": phase23_paper_trading_result,
            "phase24_execution_safety_result": phase24_execution_safety_result,
            "phase25_smart_execution_result": phase25_smart_execution_result,
            "phase26_microstructure_result": phase26_microstructure_result,
            "phase27_options_flow_result": phase27_options_flow_result,
            "phase28_news_intelligence_result": phase28_news_intelligence_result,
            "phase29_economic_calendar_result": phase29_economic_calendar_result,
            "phase30_liquidity_map_result": phase30_liquidity_map_result,
            "phase31_scenario_simulation_result": phase31_scenario_simulation_result,
            "phase32_multi_agent_debate_result": phase32_multi_agent_debate_result,
            "phase33_self_reflection_result": phase33_self_reflection_result,
            "phase34_confidence_calibration_result": phase34_confidence_calibration_result,
            "phase35_no_trade_intelligence_result": phase35_no_trade_intelligence_result,
            "phase36_memory_consolidation_result": phase36_memory_consolidation_result,
            "phase37_auto_repair_result": phase37_auto_repair_result,
            "phase38_runtime_guard": phase38_runtime_guard,
            "phase40_accuracy_validation_result": phase40_accuracy_validation_result,
            "phase41_meta_learning_result": phase41_meta_learning_result,
        }

    master_input = build_master_input()
    context = build_context(master_input)
    context["news_items"] = news_items or []

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

    phase23_paper_trading_result = refresh_phase23_paper_trading_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase24_execution_safety_result = refresh_phase24_execution_safety_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase25_smart_execution_result = refresh_phase25_smart_execution_safely(
        final_decisions=final_decisions,
        paper_result=phase23_paper_trading_result,
        context=context,
    )
    phase26_microstructure_result = refresh_phase26_microstructure_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase27_options_flow_result = refresh_phase27_options_flow_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase28_news_intelligence_result = refresh_phase28_news_intelligence_safely(
        final_decisions=final_decisions,
        context=context,
        news_items=news_items,
    )
    phase29_economic_calendar_result = refresh_phase29_economic_calendar_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase30_liquidity_map_result = refresh_phase30_liquidity_map_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase31_scenario_simulation_result = refresh_phase31_scenario_simulation_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase32_multi_agent_debate_result = refresh_phase32_multi_agent_debate_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase33_self_reflection_result = refresh_phase33_self_reflection_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase34_confidence_calibration_result = refresh_phase34_confidence_calibration_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase35_no_trade_intelligence_result = refresh_phase35_no_trade_intelligence_safely(
        final_decisions=final_decisions,
        context=context,
    )
    phase36_memory_consolidation_result = refresh_phase36_memory_consolidation_safely(
        context=context,
    )
    phase37_auto_repair_result = refresh_phase37_auto_repair_safely(
        context=context,
    )

    alert_filter_result = filter_alert_candidates(final_decisions)
    print_alert_filter_result(alert_filter_result)

    daily_alert_result = select_daily_alerts(alert_filter_result)
    print_daily_alert_selection(daily_alert_result)

    execution_result = prepare_execution_packets(daily_alert_result)
    execution_result = filter_duplicate_setup_packets(execution_result)
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
            if sync_paper_account_from_trade_results is not None:
                paper_sync_result = sync_paper_account_from_trade_results()
                if isinstance(outcome_result, dict):
                    outcome_result["paper_account_sync"] = paper_sync_result
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
    phase43_meta_regime_result = refresh_phase43_meta_regime_safely(context=context)
    phase14_meta_evolution_result = refresh_phase14_meta_evolution_safely(
        evaluated_setups=evaluated_setups,
        context=context,
        final_decisions=final_decisions,
        phase_results={
            "phase10_master_shadow_result": phase10_master_shadow_result,
            "phase11_promotion_gate_result": phase11_promotion_gate_result,
            "phase12_advanced_regime_result": phase12_advanced_regime_result,
            "phase13_strategy_genome_result": phase13_strategy_genome_result,
            "phase43_meta_regime_result": phase43_meta_regime_result,
            "phase5_memory_result": phase5_memory_result,
            "phase6_shadow_report_result": phase6_shadow_report_result,
            "phase8_market_narrative_result": phase8_market_narrative_result,
            "phase9_cross_setup_result": phase9_cross_setup_result,
            "outcome_result": outcome_result,
        },
    )
    phase21_autonomous_research_result = refresh_phase21_autonomous_research_safely(
        context=context,
        news_items=news_items,
        evaluated_setups=evaluated_setups,
        final_decisions=final_decisions,
    )
    phase22_backtesting_validation_result = refresh_phase22_backtesting_validation_safely(
        autonomous_research_report=phase21_autonomous_research_result,
        context=context,
    )
    phase40_accuracy_validation_result = refresh_phase40_accuracy_validation_safely(context=context)
    phase41_meta_learning_result = refresh_phase41_meta_learning_safely(
        accuracy_state=phase40_accuracy_validation_result,
        context=context,
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
        "phase43_meta_regime_result": phase43_meta_regime_result,
        "phase14_meta_evolution_result": phase14_meta_evolution_result,
        "phase21_autonomous_research_result": phase21_autonomous_research_result,
        "phase22_backtesting_validation_result": phase22_backtesting_validation_result,
        "phase23_paper_trading_result": phase23_paper_trading_result,
        "phase24_execution_safety_result": phase24_execution_safety_result,
        "phase25_smart_execution_result": phase25_smart_execution_result,
        "phase26_microstructure_result": phase26_microstructure_result,
        "phase27_options_flow_result": phase27_options_flow_result,
        "phase28_news_intelligence_result": phase28_news_intelligence_result,
        "phase29_economic_calendar_result": phase29_economic_calendar_result,
        "phase30_liquidity_map_result": phase30_liquidity_map_result,
        "phase31_scenario_simulation_result": phase31_scenario_simulation_result,
        "phase32_multi_agent_debate_result": phase32_multi_agent_debate_result,
        "phase33_self_reflection_result": phase33_self_reflection_result,
        "phase34_confidence_calibration_result": phase34_confidence_calibration_result,
        "phase35_no_trade_intelligence_result": phase35_no_trade_intelligence_result,
        "phase36_memory_consolidation_result": phase36_memory_consolidation_result,
        "phase37_auto_repair_result": phase37_auto_repair_result,
        "phase38_runtime_guard": phase38_runtime_guard,
        "phase40_accuracy_validation_result": phase40_accuracy_validation_result,
        "phase41_meta_learning_result": phase41_meta_learning_result,
    }


def run_master_brain(send_telegram=True, run_outcome_tracker=True, health_check=False):
    if health_check:
        return _run_master_brain_unlocked(
            send_telegram=send_telegram,
            run_outcome_tracker=run_outcome_tracker,
            health_check=health_check,
        )

    if not _is_market_alert_time():
        return _run_master_brain_unlocked(
            send_telegram=send_telegram,
            run_outcome_tracker=run_outcome_tracker,
            health_check=health_check,
        )

    lock_result = acquire_global_runtime_lock(mode="LIVE")
    if not lock_result.get("acquired"):
        return {
            "mode": "LIVE_SKIPPED_GLOBAL_LOCK",
            "status": "SKIPPED",
            "reason": lock_result.get("reason", "GLOBAL_LOCK_NOT_ACQUIRED"),
            "lock": lock_result,
        }

    try:
        return _run_master_brain_unlocked(
            send_telegram=send_telegram,
            run_outcome_tracker=run_outcome_tracker,
            health_check=health_check,
        )
    finally:
        release_global_runtime_lock(
            owner=lock_result.get("owner"),
            run_id=lock_result.get("run_id"),
        )


if __name__ == "__main__":
    run_master_brain()
