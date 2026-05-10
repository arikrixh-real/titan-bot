"""
TITAN - Setup Engine FINAL
--------------------------
Final stable version with:
1. Full 5-min scan flow
2. News engine safe run
3. Real scan-stage counters for dashboard
4. Supabase scan_health_logs update with real values
5. Trade journal
6. Trade execution layer
7. Outcome tracker
8. Evolution engine
9. Master status update

IMPORTANT:
- Telegram 3/day logic remains untouched.
- Trade execution layer handles duplicate open trades.
- This file does NOT place broker orders.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import os

import pandas as pd
from supabase import create_client

from config.universe import NSE_STOCKS
from data.loader import load_cached_stock_data
from data.live_price import get_live_price

from scanners.volume_scanner import volume_anomaly_score
from scanners.strength_scanner import price_strength_score
from scanners.compression_scanner import compression_score


from engines.score_engine import final_signal_score
from engines.trade_levels import calculate_trade_levels
from engines.risk_engine import calculate_rr
from engines.filter_engine import passes_quality_filters
from engines.market_filter import market_regime_status
from engines.trend_engine import trend_direction, trade_side_from_trend
from engines.momentum_engine import strong_momentum
from engines.trap_engine import avoid_fake_breakout
from engines.relative_strength_engine import relative_strength_ok
from engines.entry_engine import breakout_ready
from engines.reason_engine import build_reason
from engines.structure_engine import structure_ok

from engines.evolution_adapter import evolve_setup, passes_evolution_filter
from engines.evolution_engine import (
    run_evolution_engine,
    get_evolution_filter_threshold,
    get_evolution_state,
)
from engines.adaptive_scoring import adaptive_score_adjustment
from engines.pattern_intelligence import apply_pattern_intelligence
from engines.regime_intelligence import regime_score_adjustment
from engines.adaptive_intelligence import apply_adaptive_intelligence
from engines.meta_intelligence_engine import apply_meta_intelligence
from engines.elite_selector import rank_elite_setups
from engines.master_status import update_master_status
from utils.market_hours import is_trade_window, trade_window_text

from journal.trade_journal import journal_eligible_setups
from journal.outcome_tracker import track_trade_outcomes

try:
    from journal.trade_execution_layer import (
        add_good_setups_as_live_trades,
        update_live_trade_outcomes,
    )
except Exception:
    add_good_setups_as_live_trades = None
    update_live_trade_outcomes = None

try:
    from intelligence.news_engine import run_news_engine
except Exception:
    run_news_engine = None


IST = ZoneInfo("Asia/Kolkata")

BASE_EVOLUTION_THRESHOLD = 60.0
MIN_CLOSED_TRADES_FOR_EVOLUTION_FILTER = 10

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# Dynamic scan settings
DYNAMIC_SCAN_SIZE = 50
DYNAMIC_ROTATION_BUCKET_MINUTES = 5


# =========================================================
# SUPABASE
# =========================================================

def get_supabase():
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            return None

        return create_client(url, key)

    except Exception:
        return None


supabase = get_supabase()


def log_scan_to_supabase(
    scan_id,
    scanned_count,
    trend_passed,
    momentum_passed,
    structure_passed,
    entry_passed,
    final_passed,
    alerts_sent,
):
    """
    Logs real scan health counters to Supabase.
    Matches your scan_health_logs table columns:
    - created_at
    - scan_cycle_id
    - stocks_checked
    - trend_passed
    - momentum_passed
    - structure_passed
    - entry_passed
    - final_passed
    - alerts_sent
    """
    if supabase is None:
        print("⚠️ Supabase not connected for scan logging")
        return

    now_iso = datetime.now(IST).isoformat()

    try:
        # Minimal scans table update for dashboard last scan time
        supabase.table("scans").insert({
            "created_at": now_iso
        }).execute()

    except Exception as e:
        print(f"⚠️ scans table log skipped: {e}")

    try:
        supabase.table("scan_health_logs").insert({
            "created_at": now_iso,
            "scan_cycle_id": scan_id,
            "stocks_checked": int(scanned_count),
            "trend_passed": int(trend_passed),
            "momentum_passed": int(momentum_passed),
            "structure_passed": int(structure_passed),
            "entry_passed": int(entry_passed),
            "final_passed": int(final_passed),
            "alerts_sent": int(alerts_sent),
        }).execute()

        print("✅ Scan data logged to Supabase for dashboard")
        print(
            f"📊 Scan Health Logged | checked={scanned_count} | "
            f"trend={trend_passed} | momentum={momentum_passed} | "
            f"structure={structure_passed} | entry={entry_passed} | "
            f"final={final_passed} | alerts={alerts_sent}"
        )

    except Exception as e:
        print(f"❌ scan_health_logs insert failed: {e}")


# =========================================================
# HELPERS
# =========================================================

def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def clean_market_dataframe(df):
    """
    Converts OHLCV columns to numeric.
    Prevents string/int comparison errors in engines.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    for col in OHLCV_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    available_cols = [col for col in OHLCV_COLUMNS if col in df.columns]

    if available_cols:
        df = df.dropna(subset=available_cols)

    return df


def run_news_engine_safely():
    if run_news_engine is None:
        print("📰 News Engine: not connected / function not found")
        return

    try:
        print("📰 Running News Engine...")
        run_news_engine()
        print("✅ News Engine Completed and news_memory updated")
    except Exception as e:
        print(f"⚠️ News Engine Error: {e}")



def _symbol_activity_score(symbol, scan_bucket):
    """
    Lightweight dynamic ranking score.
    Uses cached candles only, so it does not add extra API load.
    """
    try:
        df = load_cached_stock_data(symbol)
        df = clean_market_dataframe(df)

        if df is None or df.empty or len(df) < 30:
            return 0.0

        close = pd.to_numeric(df["Close"], errors="coerce").dropna()

        if len(close) < 30:
            return 0.0

        if "Volume" in df.columns:
            volume = pd.to_numeric(df["Volume"], errors="coerce").dropna()
        else:
            volume = pd.Series(dtype=float)

        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        old_close = float(close.iloc[-6]) if len(close) >= 6 else prev_close

        one_bar_move = abs((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0
        five_bar_move = abs((last_close - old_close) / old_close) * 100 if old_close else 0.0

        volume_score = 0.0
        if len(volume) >= 20:
            avg_vol = float(volume.iloc[-20:].mean())
            last_vol = float(volume.iloc[-1])
            if avg_vol > 0:
                volume_score = min(5.0, last_vol / avg_vol)

        rotation_score = ((abs(hash(f"{symbol}_{scan_bucket}")) % 1000) / 1000.0)

        return round((one_bar_move * 2.0) + five_bar_move + volume_score + rotation_score, 4)

    except Exception:
        return 0.0


def select_dynamic_scan_universe(scan_id):
    """
    Selects dynamic top 50 stocks every scan.
    """
    try:
        now = datetime.now(IST)
        scan_bucket = int(now.timestamp() // (DYNAMIC_ROTATION_BUCKET_MINUTES * 60))

        ranked = []
        for candidate_symbol in NSE_STOCKS:
            score = _symbol_activity_score(candidate_symbol, scan_bucket)
            ranked.append((score, candidate_symbol))

        ranked.sort(reverse=True, key=lambda x: x[0])
        selected = [symbol for score, symbol in ranked[:DYNAMIC_SCAN_SIZE]]

        if not selected:
            selected = list(NSE_STOCKS)[:DYNAMIC_SCAN_SIZE]

        print(f"🎯 Dynamic Scan Mode: selected {len(selected)} stocks from {len(NSE_STOCKS)} universe")
        print(f"🎯 Dynamic sample: {', '.join(selected[:10])}")

        return selected

    except Exception as e:
        print(f"⚠️ Dynamic scan selection failed, using first {DYNAMIC_SCAN_SIZE}: {e}")
        return list(NSE_STOCKS)[:DYNAMIC_SCAN_SIZE]



def save_selected_alerts_to_trade_results(selected_alerts, scan_id, market_status):
    """
    Saves only the final selected/alerted Titan trades to Supabase trade_results.
    Uses this file's Supabase client directly, so dashboard metrics update reliably.
    """
    if not selected_alerts:
        print("ℹ️ trade_results: no selected alerts to save")
        return 0

    if supabase is None:
        print("❌ trade_results: Supabase not connected")
        return 0

    saved_count = 0

    for setup in selected_alerts:
        try:
            symbol = setup.get("symbol")
            side = setup.get("side")
            entry = safe_float(setup.get("entry"))
            sl = safe_float(setup.get("sl"))
            tp = safe_float(setup.get("target") or setup.get("tp"))
            rr = safe_float(setup.get("rr"), 0.0)
            score = safe_float(setup.get("score"), 0.0)

            if not symbol or not side or entry is None or sl is None or tp is None:
                print(f"⚠️ trade_results skipped invalid setup: {setup}")
                continue

            now_iso = datetime.now(IST).isoformat()

            row = {
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "status": "LIVE",
                "result": None,
                "pnl": 0,
                "exit_price": None,
                "market_status": str(market_status),
                "scan_id": scan_id,
                "rr": rr,
                "score": score,
                "opened_at": now_iso,
                "created_at": now_iso,
                "updated_at": now_iso,
            }

            supabase.table("trade_results").insert(row).execute()
            saved_count += 1
            print(f"✅ trade_results saved: {symbol} | {side} | entry={entry} sl={sl} tp={tp}")

        except Exception as e:
            print(f"❌ trade_results insert failed for {setup.get('symbol')}: {e}")

    print(f"✅ trade_results final saved count: {saved_count}/{len(selected_alerts)}")
    return saved_count


# =========================================================
# MAIN SCANNER
# =========================================================

def scan_for_setups():
    print("🚀 TITAN scan started...")

    run_news_engine_safely()

    if not is_trade_window():
        print(f"🛡️ Outside trade window ({trade_window_text()}). Setup scan, journaling, and outcome tracking skipped.")
        return []

    scan_id = datetime.now(IST).strftime("%Y%m%d_%H%M%S")

    market_status = market_regime_status()
    print(f"📊 Market Status: {market_status}")

    try:
        evolution_state = get_evolution_state()
        closed_trades = int(evolution_state.get("total_closed_trades", 0))
    except Exception:
        closed_trades = 0

    try:
        adaptive_threshold = safe_float(
            get_evolution_filter_threshold(BASE_EVOLUTION_THRESHOLD),
            BASE_EVOLUTION_THRESHOLD,
        )
    except Exception:
        adaptive_threshold = BASE_EVOLUTION_THRESHOLD

    if closed_trades < MIN_CLOSED_TRADES_FOR_EVOLUTION_FILTER:
        print(
            f"🧠 Evolution Mode: LEARNING PHASE "
            f"({closed_trades}/{MIN_CLOSED_TRADES_FOR_EVOLUTION_FILTER} closed trades)"
        )
        print("🧠 Evolution Filter: OFF until enough outcome data is collected")
        print("🧠 Adaptive Scoring: NEUTRAL until enough outcome data is collected")
        print("🧩 Pattern Intelligence: NEUTRAL until enough outcome data is collected")
        print("🌐 Regime Intelligence: ACTIVE light score adjustment")
        print("🏆 Elite Selection: ACTIVE ranking mode")
    else:
        print("🧠 Evolution Mode: ACTIVE FILTERING")
        print(f"🧠 Evolution Filter Threshold: {adaptive_threshold}")
        print("🧠 Adaptive Scoring: ACTIVE")
        print("🧩 Pattern Intelligence: ACTIVE")
        print("🌐 Regime Intelligence: ACTIVE")
        print("🏆 Elite Selection: ACTIVE highest-probability mode")

    eligible_setups = []
    rejected_by_evolution = 0
    scanned_count = 0
    error_count = 0

    # ✅ REAL DASHBOARD STAGE COUNTERS
    trend_passed_count = 0
    structure_passed_count = 0
    momentum_passed_count = 0
    entry_passed_count = 0

    scan_universe = select_dynamic_scan_universe(scan_id)

    for symbol in scan_universe:
        try:
            df = load_cached_stock_data(symbol)
            df = clean_market_dataframe(df)

            if df is None or df.empty or len(df) < 30:
                continue

            scanned_count += 1

            live_price = safe_float(get_live_price(symbol))

            if live_price is None:
                live_price = safe_float(df["Close"].iloc[-1])

            if live_price is None or live_price <= 0:
                continue

            trend = trend_direction(df)
            side = trade_side_from_trend(trend)

            if side not in ["LONG", "SHORT"]:
                continue

            # ✅ Trend passed means a valid trade side was identified
            trend_passed_count += 1

            if not structure_ok(df, side):
                continue

            structure_passed_count += 1

            if not strong_momentum(df, side):
                continue

            momentum_passed_count += 1

            if not avoid_fake_breakout(df, side):
                continue

            if not relative_strength_ok(symbol):
                continue

            if not breakout_ready(df, side):
                continue

            entry_passed_count += 1

            volume_score = safe_float(volume_anomaly_score(df), 0.0)
            strength_score = safe_float(price_strength_score(df), 0.0)
            compression_value = safe_float(compression_score(df), 0.0)

            score = safe_float(
                final_signal_score(
                    volume_score=volume_score,
                    strength_score=strength_score,
                    compression_score=compression_value,
                    trend=trend,
                    side=side,
                ),
                0.0,
            )

            entry, sl, target = calculate_trade_levels(
                df=df,
                side=side,
                price=live_price,
            )

            entry = safe_float(entry)
            sl = safe_float(sl)
            target = safe_float(target)

            if entry is None or sl is None or target is None:
                continue

            rr = safe_float(
                calculate_rr(
                    entry=entry,
                    sl=sl,
                    target=target,
                    side=side,
                ),
                0.0,
            )

            if rr <= 0:
                continue

            if not passes_quality_filters(
                score=score,
                rr=rr,
                side=side,
                market_status=market_status,
            ):
                continue

            reason = build_reason(
                symbol=symbol,
                side=side,
                score=score,
                rr=rr,
                trend=trend,
                volume_score=volume_score,
                strength_score=strength_score,
                compression_score=compression_value,
                market_status=market_status,
            )

            setup = {
                "symbol": symbol,
                "side": side,
                "entry": round(entry, 2),
                "sl": round(sl, 2),
                "target": round(target, 2),
                "rr": round(rr, 2),
                "score": round(score, 2),
                "rank_score": round(score + (rr * 10), 2),
                "confirmations": [],
                "reason": reason,
                "market_status": market_status,
                "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            }

            setup = evolve_setup(setup)
            setup = adaptive_score_adjustment(setup)
            setup = apply_pattern_intelligence(setup)
            setup = regime_score_adjustment(setup)
            setup = apply_adaptive_intelligence(setup)
            setup = apply_meta_intelligence(setup)

            if closed_trades >= MIN_CLOSED_TRADES_FOR_EVOLUTION_FILTER:
                if not passes_evolution_filter(setup, BASE_EVOLUTION_THRESHOLD):
                    rejected_by_evolution += 1
                    continue

            setup["evolution_threshold"] = adaptive_threshold
            setup["evolution_closed_trades"] = closed_trades
            setup["evolution_filter_active"] = (
                closed_trades >= MIN_CLOSED_TRADES_FOR_EVOLUTION_FILTER
            )

            eligible_setups.append(setup)

        except Exception as e:
            error_count += 1
            print(f"⚠️ Error scanning {symbol}: {e}")
            continue

    eligible_setups = rank_elite_setups(eligible_setups)

    print(f"📊 Stocks scanned successfully: {scanned_count}")
    print(f"⚠️ Stocks failed: {error_count}")
    print(f"✅ Eligible setups found: {len(eligible_setups)}")
    print(f"🧠 Rejected by Evolution Filter: {rejected_by_evolution}")

    selected_alerts = eligible_setups[:3]
    alerted_symbols = [s.get("symbol") for s in selected_alerts if s.get("symbol")]

    # ✅ IMPORTANT:
    # trade_results insertion is now handled ONLY by:
    # titan_master_brain/master_controller.py
    #
    # This prevents duplicate LIVE trades and repeated dashboard inflation.

    if selected_alerts:
        print("🏆 Top 3 elite setups:")
        for i, setup in enumerate(selected_alerts, start=1):
            print(
                f"{i}. {setup.get('symbol')} | "
                f"Score: {setup.get('score')} | "
                f"RR: {setup.get('rr')} | "
                f"Elite: {setup.get('elite_probability_score')}"
            )

    # Journal all eligible setups
    journal_eligible_setups(
        eligible_setups=eligible_setups,
        scan_id=scan_id,
        alerted_symbols=alerted_symbols,
        market_status=market_status,
    )

    print("📘 Journal updated")

    # Good setups become internal live trades; duplicate protection lives in trade_execution_layer.py
    if add_good_setups_as_live_trades is not None:
        try:
            add_good_setups_as_live_trades(
                eligible_setups=eligible_setups,
                scan_id=scan_id,
                alerted_symbols=alerted_symbols,
                market_status=market_status,
            )
        except Exception as e:
            print(f"⚠️ Trade execution add error: {e}")
    else:
        print("⚠️ Trade execution layer not connected")

    # Track internal live trades for TP/SL
    if update_live_trade_outcomes is not None:
        try:
            update_live_trade_outcomes()
        except Exception as e:
            print(f"⚠️ Trade execution outcome error: {e}")
    else:
        print("⚠️ Trade execution outcome layer not connected")

    # Existing outcome tracker remains active
    try:
        track_trade_outcomes(limit=10)
        print("📊 Outcome tracker completed")
    except Exception as e:
        print(f"⚠️ Outcome tracker error: {e}")

    try:
        run_evolution_engine()
        print("🧠 Evolution updated")
    except Exception as e:
        print(f"⚠️ Evolution engine error: {e}")

    last_scan_summary = {
        "scan_id": scan_id,
        "market_status": market_status,
        "stocks_scanned": scanned_count,
        "stocks_failed": error_count,
        "trend_passed": trend_passed_count,
        "momentum_passed": momentum_passed_count,
        "structure_passed": structure_passed_count,
        "entry_passed": entry_passed_count,
        "eligible_setups": len(eligible_setups),
        "alerts_sent": len(selected_alerts),
        "rejected_by_evolution": rejected_by_evolution,
        "top_3_symbols": alerted_symbols,
        "closed_trades_at_scan_start": closed_trades,
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        update_master_status(last_scan_summary=last_scan_summary)
        print("📡 Master status updated")
    except Exception as e:
        print(f"⚠️ Master status update error: {e}")

    log_scan_to_supabase(
        scan_id=scan_id,
        scanned_count=scanned_count,
        trend_passed=trend_passed_count,
        momentum_passed=momentum_passed_count,
        structure_passed=structure_passed_count,
        entry_passed=entry_passed_count,
        final_passed=len(eligible_setups),
        alerts_sent=len(selected_alerts),
    )

    return eligible_setups


if __name__ == "__main__":
    scan_for_setups()
