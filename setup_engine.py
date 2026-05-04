"""
TITAN - Setup Engine (STEP 8: MASTER STATUS LAYER)
-------------------------------------------------
Flow:
Scan
→ Quality Filter
→ Evolution Score
→ Adaptive Score
→ Pattern Intelligence
→ Market Regime Intelligence
→ Evolution Filter
→ Elite Trade Selection
→ Journal
→ Outcome
→ Evolution
→ Master Status

SAFE:
- Telegram 3/day untouched
- GitHub automation untouched
- Dashboard not changed yet
- Master status only writes dashboard-ready status files

FIX:
- Prevents int/string comparison errors by cleaning OHLCV dataframe columns
- Safely converts live price, scores, entry, SL, target, and RR to float
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

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

# ✅ Optional News Engine import
# Safe: if news engine file/function is missing, TITAN will not crash.
try:
    from intelligence.news_engine import run_news_engine
except Exception:
    run_news_engine = None


IST = ZoneInfo("Asia/Kolkata")

BASE_EVOLUTION_THRESHOLD = 60.0
MIN_CLOSED_TRADES_FOR_EVOLUTION_FILTER = 10

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def safe_float(value, default=None):
    """
    Converts string/int/float values safely to float.
    Returns default if conversion fails.
    """
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def clean_market_dataframe(df):
    """
    Central safety fix:
    Converts OHLCV columns to numeric so engines do not compare int with str.
    Removes invalid rows after conversion.
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
    """
    Runs TITAN news engine without affecting trading scan stability.
    If the news engine fails, setup scan continues normally.
    """
    if run_news_engine is None:
        print("📰 News Engine: not connected / function not found")
        return

    try:
        print("📰 Running News Engine...")
        run_news_engine()
        print("✅ News Engine Completed")
    except Exception as e:
        print(f"⚠️ News Engine Error: {e}")

def scan_for_setups():
    print("🚀 TITAN scan started...")

    run_news_engine_safely()

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

    for symbol in NSE_STOCKS:
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

            if not structure_ok(df, side):
                continue

            if not strong_momentum(df, side):
                continue

            if not avoid_fake_breakout(df, side):
                continue

            if not relative_strength_ok(symbol):
                continue

            if not breakout_ready(df, side):
                continue

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
    alerted_symbols = [s["symbol"] for s in selected_alerts]

    if selected_alerts:
        print("🏆 Top 3 elite setups:")
        for i, setup in enumerate(selected_alerts, start=1):
            print(
                f"{i}. {setup.get('symbol')} | "
                f"Score: {setup.get('score')} | "
                f"RR: {setup.get('rr')} | "
                f"Elite: {setup.get('elite_probability_score')}"
            )

    journal_eligible_setups(
        eligible_setups=eligible_setups,
        scan_id=scan_id,
        alerted_symbols=alerted_symbols,
        market_status=market_status,
    )

    print("📘 Journal updated")

    track_trade_outcomes(limit=50)
    print("📊 Outcome tracker completed")

    run_evolution_engine()
    print("🧠 Evolution updated")

    last_scan_summary = {
        "scan_id": scan_id,
        "market_status": market_status,
        "stocks_scanned": scanned_count,
        "stocks_failed": error_count,
        "eligible_setups": len(eligible_setups),
        "rejected_by_evolution": rejected_by_evolution,
        "top_3_symbols": alerted_symbols,
        "closed_trades_at_scan_start": closed_trades,
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    }

    update_master_status(last_scan_summary=last_scan_summary)
    print("📡 Master status updated")

    return eligible_setups


if __name__ == "__main__":
    scan_for_setups()