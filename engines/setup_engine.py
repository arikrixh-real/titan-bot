import os
from datetime import datetime

from supabase import create_client

from data.loader import load_cached_stock_data
from data.live_price import get_live_price

from scanners.volume_scanner import volume_anomaly_score
from scanners.strength_scanner import price_strength_score
from scanners.compression_scanner import compression_score

from engines.score_engine import final_signal_score
from engines.trade_levels import calculate_trade_levels
from engines.risk_engine import calculate_rr, position_sizing
from engines.filter_engine import passes_quality_filters
from engines.market_filter import market_regime_status
from engines.trend_engine import trend_direction, trade_side_from_trend
from engines.momentum_engine import strong_momentum
from engines.trap_engine import avoid_fake_breakout
from engines.relative_strength_engine import relative_strength_ok
from engines.entry_engine import breakout_ready
from engines.reason_engine import build_reason
from engines.trigger_engine import trigger_status
from engines.structure_engine import structure_ok

from journal.trade_journal import log_trade
from journal.scan_journal import log_scan

from titan_brain.db import (
    insert_scan,
    insert_scan_symbol,
    insert_trade,
    insert_setup,
)


# =========================================================
# TITAN SETUP ENGINE - FINAL STABLE CONFLUENCE VERSION
# =========================================================
# Permanent logic:
# 1. Uses Upstox live price first.
# 2. If Upstox price is unavailable, falls back to latest cached close.
# 3. Uses engines as confirmations, not one-by-one hard blockers.
# 4. Final setup requires:
#    - entry readiness
#    - quality filter pass
#    - minimum confluence confirmations
#    - valid levels
#    - RR >= MIN_RR
# =========================================================

MIN_CONFIRMATIONS = 3
MIN_RR = 1.5


def save_scan_health_log(
    stocks_checked,
    trend_passed,
    momentum_passed,
    structure_passed,
    entry_passed,
    final_passed,
    alerts_sent,
    market_status,
):
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            print("⚠️ Supabase secrets missing. Scan health not saved.")
            return

        supabase = create_client(supabase_url, supabase_key)

        supabase.table("scan_health_logs").insert({
            "scan_cycle_id": datetime.now().isoformat(),
            "stocks_checked": stocks_checked,
            "trend_passed": trend_passed,
            "momentum_passed": momentum_passed,
            "structure_passed": structure_passed,
            "entry_passed": entry_passed,
            "final_passed": final_passed,
            "alerts_sent": alerts_sent,
            "market_status": str(market_status),
            "status": "COMPLETED",
            "note": "Final stable confluence scan health saved",
        }).execute()

        print("✅ Scan health saved")

    except Exception as e:
        print(f"❌ Scan health save failed: {e}")


def safe_latest_close(data):
    try:
        return round(float(data["Close"].iloc[-1]), 2)
    except Exception:
        return None


def normalize_engine_side(side):
    if side in ["LONG", "BUY"]:
        return "LONG"
    if side in ["SHORT", "SELL"]:
        return "SHORT"
    return None


def scan_for_setups():
    setups = []
    scanned_symbols = []
    setup_symbols = []
    errors = []

    # =========================
    # SCAN HEALTH COUNTERS
    # =========================
    stocks_checked = 0
    trend_passed = 0
    momentum_passed = 0
    structure_passed = 0
    entry_passed = 0
    final_passed = 0
    alerts_sent = 0

    # =========================
    # FAILURE BREAKDOWN
    # =========================
    no_live_price = 0
    no_valid_trend = 0
    structure_fail = 0
    momentum_fail = 0
    fake_breakout_fail = 0
    relative_weak = 0
    not_ready = 0
    quality_fail = 0
    confluence_fail = 0
    levels_fail = 0
    rr_fail = 0

    market_status = market_regime_status()
    symbols = load_cached_stock_data()
    total_symbols = len(symbols)

    print("========== SETUP ENGINE ACTIVE ==========")
    print(f"Market Status: {market_status}")
    print(f"Symbols received from loader: {total_symbols}")

    scan_record = {
        "total_symbols": total_symbols,
        "scanned_count": 0,
        "setup_count": 0,
        "errors": [],
    }

    scan_id = insert_scan(scan_record)

    for symbol, data in symbols.items():
        try:
            scanned_symbols.append(symbol)
            scan_record["scanned_count"] += 1
            stocks_checked += 1

            # =========================
            # PRICE: UPSTOX FIRST, CACHE FALLBACK
            # =========================
            live_price = get_live_price(symbol)
            live_source = "UPSTOX"

            if live_price is None:
                fallback_price = safe_latest_close(data)
                if fallback_price is None:
                    no_live_price += 1
                    print(f"SCAN DEBUG → {symbol} | BLOCKED=NO_PRICE")
                    insert_scan_symbol(scan_id, {
                        "symbol": symbol,
                        "price": 0,
                        "trend": "NA",
                        "volume_score": 0,
                        "strength_score": 0,
                        "compression_score": 0,
                        "final_score": 0,
                        "passed": False,
                        "reason": "NO_PRICE",
                    })
                    continue

                live_price = fallback_price
                live_source = "CACHE_CLOSE"

            # =========================
            # TREND / SIDE
            # =========================
            trend = trend_direction(data)
            side = trade_side_from_trend(trend)
            engine_side = normalize_engine_side(side)

            if side is None or engine_side is None:
                no_valid_trend += 1
                print(
                    f"SCAN DEBUG → {symbol} | price={live_price} | source={live_source} | "
                    f"BLOCKED=NO_VALID_TREND | trend={trend}"
                )
                insert_scan_symbol(scan_id, {
                    "symbol": symbol,
                    "price": live_price,
                    "trend": trend,
                    "volume_score": 0,
                    "strength_score": 0,
                    "compression_score": 0,
                    "final_score": 0,
                    "passed": False,
                    "reason": "NO_VALID_TREND",
                })
                continue

            trend_passed += 1

            # =========================
            # SCORES
            # =========================
            volume_score = volume_anomaly_score(data)
            strength_score = price_strength_score(data)
            comp_score = compression_score(data)
            final_score = final_signal_score(volume_score, strength_score, comp_score)

            # =========================
            # ENGINE CONFIRMATIONS
            # =========================
            structure_result = structure_ok(data, side=engine_side)
            momentum_result = strong_momentum(data, side=engine_side)
            fake_breakout_ok = avoid_fake_breakout(data)
            relative_strength_result = relative_strength_ok(data, side=engine_side)
            entry_result = breakout_ready(data, side=engine_side)

            # IMPORTANT: pass dictionary positionally to avoid signature mismatch.
            quality_result = passes_quality_filters({
                "score": final_score,
                "rr": MIN_RR,
                "volume_x": volume_score,
                "compression": comp_score,
            })

            if structure_result:
                structure_passed += 1
            else:
                structure_fail += 1

            if momentum_result:
                momentum_passed += 1
            else:
                momentum_fail += 1

            if not fake_breakout_ok:
                fake_breakout_fail += 1

            if not relative_strength_result:
                relative_weak += 1

            if entry_result:
                entry_passed += 1
            else:
                not_ready += 1

            if not quality_result:
                quality_fail += 1

            confirmations = [
                structure_result,
                momentum_result,
                fake_breakout_ok,
                relative_strength_result,
                entry_result,
            ]
            confirmation_count = sum(1 for item in confirmations if item)

            print(
                f"ENTRY DEBUG → {symbol} | price={live_price} | source={live_source} | "
                f"trend={trend} | side={side} | volume={volume_score} | strength={strength_score} | "
                f"compression={comp_score} | final_score={final_score} | "
                f"structure={structure_result} | momentum={momentum_result} | "
                f"fake_breakout_ok={fake_breakout_ok} | relative_strength={relative_strength_result} | "
                f"entry={entry_result} | quality={quality_result} | confirmations={confirmation_count}"
            )

            # =========================
            # FINAL CONFLUENCE DECISION
            # =========================
            passed = False
            fail_reason = "UNKNOWN"

            if not entry_result:
                fail_reason = "NOT_READY"
            elif not quality_result:
                fail_reason = "QUALITY_FAIL"
            elif confirmation_count < MIN_CONFIRMATIONS:
                confluence_fail += 1
                fail_reason = "CONFLUENCE_FAIL"
            else:
                # Trade levels and RR are part of the final setup decision.
                levels = calculate_trade_levels(
                    symbol=symbol,
                    side=side,
                    entry_price=live_price,
                    data=data,
                )

                if not levels:
                    levels_fail += 1
                    fail_reason = "LEVELS_FAIL"
                else:
                    entry = levels["entry"]
                    stop_loss = levels["stop_loss"]
                    target = levels["target"]

                    rr = calculate_rr(entry, stop_loss, target, side)

                    if rr < MIN_RR:
                        rr_fail += 1
                        fail_reason = "RR_FAIL"
                        print(
                            f"SETUP BLOCKED → {symbol} | RR_FAIL | "
                            f"entry={entry} | sl={stop_loss} | target={target} | rr={rr}"
                        )
                    else:
                        passed = True
                        fail_reason = "PASSED"
                        final_passed += 1

                        pos_data = position_sizing(entry, stop_loss)
                        position_size = pos_data.get("qty", 0)
                        risk_amount = pos_data.get("risk_amount", 0)

                        reason = build_reason(
                            symbol=symbol,
                            side=side,
                            volume_score=volume_score,
                            strength_score=strength_score,
                            compression_score=comp_score,
                            final_score=final_score,
                            trend=trend,
                            market_status=market_status,
                        )

                        trigger = trigger_status(symbol, side, entry, live_price)

                        trade_id = log_trade(
                            symbol=symbol,
                            side=side,
                            entry=entry,
                            stop_loss=stop_loss,
                            target=target,
                            position_size=position_size,
                            risk_amount=risk_amount,
                            rr=rr,
                            scores={
                                "volume_score": volume_score,
                                "strength_score": strength_score,
                                "compression_score": comp_score,
                                "final_score": final_score,
                            },
                            market_context={
                                "market_status": market_status,
                                "trend": trend,
                            },
                            setup_context={
                                "structure_ok": structure_result,
                                "momentum_ok": momentum_result,
                                "fake_breakout_ok": fake_breakout_ok,
                                "relative_strength_ok": relative_strength_result,
                                "entry_ready": entry_result,
                                "confirmations": confirmation_count,
                            },
                            reason=reason,
                            trigger_status=trigger,
                        )

                        insert_setup({
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "side": side,
                            "entry": entry,
                            "stop_loss": stop_loss,
                            "target": target,
                            "rr": rr,
                            "position_size": position_size,
                            "risk_amount": risk_amount,
                            "scores": {
                                "volume_score": volume_score,
                                "strength_score": strength_score,
                                "compression_score": comp_score,
                                "final_score": final_score,
                            },
                            "market_context": {
                                "market_status": market_status,
                                "trend": trend,
                            },
                            "setup_context": {
                                "structure_ok": structure_result,
                                "momentum_ok": momentum_result,
                                "fake_breakout_ok": fake_breakout_ok,
                                "relative_strength_ok": relative_strength_result,
                                "entry_ready": entry_result,
                                "confirmations": confirmation_count,
                            },
                            "reason": reason,
                            "trigger_status": trigger,
                            "status": "OPEN",
                        })

                        insert_trade({
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "side": side,
                            "entry": entry,
                            "stop_loss": stop_loss,
                            "target": target,
                            "rr": rr,
                            "position_size": position_size,
                            "risk_amount": risk_amount,
                            "scores": {
                                "volume_score": volume_score,
                                "strength_score": strength_score,
                                "compression_score": comp_score,
                                "final_score": final_score,
                            },
                            "market_context": market_status,
                            "setup_context": {"trend": trend, "confirmations": confirmation_count},
                            "reason": reason,
                            "trigger_status": trigger,
                            "status": "OPEN",
                        })

                        setups.append(symbol)
                        setup_symbols.append(symbol)
                        scan_record["setup_count"] += 1

            print(f"FILTER RESULT → {symbol} | {fail_reason}")

            insert_scan_symbol(scan_id, {
                "symbol": symbol,
                "price": live_price,
                "trend": trend,
                "volume_score": volume_score,
                "strength_score": strength_score,
                "compression_score": comp_score,
                "final_score": final_score,
                "passed": passed,
                "reason": fail_reason,
            })

        except Exception as e:
            errors.append(f"{symbol}: {e}")
            print(f"❌ SYMBOL ERROR → {symbol}: {e}")
            continue

    print("========== SCAN FAILURE BREAKDOWN ==========")
    print(f"Stocks Checked: {stocks_checked}")
    print(f"No Live Price: {no_live_price}")
    print(f"No Valid Trend: {no_valid_trend}")
    print(f"Structure Fail: {structure_fail}")
    print(f"Momentum Fail: {momentum_fail}")
    print(f"Fake Breakout: {fake_breakout_fail}")
    print(f"Relative Weak: {relative_weak}")
    print(f"Not Ready: {not_ready}")
    print(f"Quality Fail: {quality_fail}")
    print(f"Confluence Fail: {confluence_fail}")
    print(f"Levels Fail: {levels_fail}")
    print(f"RR Fail: {rr_fail}")
    print(f"Final Passed: {final_passed}")
    print("===========================================")

    log_scan(
        total_symbols=total_symbols,
        scanned_symbols=scanned_symbols,
        setup_symbols=setup_symbols,
        errors=errors,
    )

    save_scan_health_log(
        stocks_checked=stocks_checked,
        trend_passed=trend_passed,
        momentum_passed=momentum_passed,
        structure_passed=structure_passed,
        entry_passed=entry_passed,
        final_passed=final_passed,
        alerts_sent=alerts_sent,
        market_status=market_status,
    )

    if setups:
        print(f"✅ Valid setups found: {setups}")
    else:
        print("No valid setups found.")

    return setups