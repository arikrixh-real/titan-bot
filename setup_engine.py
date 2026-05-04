# ===================== IMPORTS =====================
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import pandas as pd
from supabase import create_client

# ===================== EXISTING IMPORTS =====================
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
from engines.elite_selector import rank_elite_setups
from engines.master_status import update_master_status

from journal.trade_journal import journal_eligible_setups
from journal.outcome_tracker import track_trade_outcomes

# ===================== NEWS ENGINE SAFE =====================
try:
    from intelligence.news_engine import run_news_engine
except:
    run_news_engine = None

# ===================== CONSTANTS =====================
IST = ZoneInfo("Asia/Kolkata")

# ===================== SUPABASE =====================
def get_supabase():
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            return None
        return create_client(url, key)
    except:
        return None

supabase = get_supabase()

# ===================== SUPABASE LOGGING (FIXED) =====================
def log_scan_to_supabase(scan_summary, scanned_count, eligible_setups):
    if supabase is None:
        print("⚠️ Supabase not connected")
        return

    try:
        now = datetime.now(IST).isoformat()

        # SAFE INSERT → scans
        supabase.table("scans").insert({
            "created_at": now
        }).execute()

        # SAFE INSERT → scan_health_logs
        supabase.table("scan_health_logs").insert({
            "created_at": now,
            "stocks_checked": scanned_count,
            "final_passed": len(eligible_setups)
        }).execute()

        print("✅ Scan logged to Supabase")

    except Exception as e:
        print(f"❌ Supabase logging error: {e}")

# ===================== SAFE HELPERS =====================
def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except:
        return default

# ===================== MAIN ENGINE =====================
def run_news_engine_safely():
    if run_news_engine is None:
        return
    try:
        run_news_engine()
    except:
        pass


def scan_for_setups():
    print("🚀 TITAN scan started...")

    run_news_engine_safely()

    scan_id = datetime.now(IST).strftime("%Y%m%d_%H%M%S")

    market_status = market_regime_status()

    eligible_setups = []
    scanned_count = 0

    for symbol in NSE_STOCKS:
        try:
            df = load_cached_stock_data(symbol)

            if df is None or df.empty:
                continue

            scanned_count += 1

            live_price = safe_float(get_live_price(symbol))
            if not live_price:
                continue

            trend = trend_direction(df)
            side = trade_side_from_trend(trend)

            if side not in ["LONG", "SHORT"]:
                continue

            if not structure_ok(df, side):
                continue

            if not strong_momentum(df, side):
                continue

            if not breakout_ready(df, side):
                continue

            entry, sl, target = calculate_trade_levels(df, side, live_price)

            entry = safe_float(entry)
            sl = safe_float(sl)
            target = safe_float(target)

            if not entry or not sl or not target:
                continue

            rr = safe_float(calculate_rr(entry, sl, target, side), 0)

            if rr <= 0:
                continue

            score = safe_float(final_signal_score(), 0)

            if not passes_quality_filters(score, rr, side, market_status):
                continue

            setup = {
                "symbol": symbol,
                "score": score,
                "rr": rr,
            }

            eligible_setups.append(setup)

        except Exception as e:
            print(f"Error {symbol}: {e}")

    eligible_setups = rank_elite_setups(eligible_setups)

    print(f"📊 Scanned: {scanned_count}")
    print(f"✅ Setups: {len(eligible_setups)}")

    journal_eligible_setups(
        eligible_setups=eligible_setups,
        scan_id=scan_id,
        alerted_symbols=[],
        market_status=market_status,
    )

    track_trade_outcomes(limit=50)
    run_evolution_engine()

    last_scan_summary = {
        "scan_id": scan_id,
        "market_status": market_status,
    }

    update_master_status(last_scan_summary=last_scan_summary)

    # ✅ FINAL CRITICAL LINE (THIS FIXES DASHBOARD)
    log_scan_to_supabase(
        scan_summary=last_scan_summary,
        scanned_count=scanned_count,
        eligible_setups=eligible_setups
    )

    return eligible_setups


if __name__ == "__main__":
    scan_for_setups()