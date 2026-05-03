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
    insert_setup
)


def scan_for_setups():
    setups = []

    scanned_symbols = []
    setup_symbols = []
    errors = []

    market_status = market_regime_status()
    symbols = load_cached_stock_data()
    total_symbols = len(symbols)

    scan_record = {
        "total_symbols": total_symbols,
        "scanned_count": 0,
        "setup_count": 0,
        "errors": []
    }

    scan_id = insert_scan(scan_record)

    for symbol, data in symbols.items():
        try:
            scanned_symbols.append(symbol)
            scan_record["scanned_count"] += 1

            # ---------- DEFAULT ----------
            live_price = get_live_price(symbol)
            if live_price is None:
                insert_scan_symbol(scan_id, {
                    "symbol": symbol,
                    "price": 0,
                    "trend": "NA",
                    "volume_score": 0,
                    "strength_score": 0,
                    "compression_score": 0,
                    "final_score": 0,
                    "passed": False,
                    "reason": "NO_LIVE_PRICE"
                })
                continue

            trend = trend_direction(data)
            side = trade_side_from_trend(trend)

            if side is None:
                insert_scan_symbol(scan_id, {
                    "symbol": symbol,
                    "price": live_price,
                    "trend": trend,
                    "volume_score": 0,
                    "strength_score": 0,
                    "compression_score": 0,
                    "final_score": 0,
                    "passed": False,
                    "reason": "NO_VALID_TREND"
                })
                continue

            volume_score = volume_anomaly_score(data)
            strength_score = price_strength_score(data)
            comp_score = compression_score(data)

            final_score = final_signal_score(
                volume_score,
                strength_score,
                comp_score
            )

            passed = False
            fail_reason = "UNKNOWN"

            if not structure_ok(data):
                fail_reason = "STRUCTURE_FAIL"

            elif not strong_momentum(data):
                fail_reason = "MOMENTUM_FAIL"

            elif not avoid_fake_breakout(data):
                fail_reason = "FAKE_BREAKOUT"

            elif not relative_strength_ok(symbol):
                fail_reason = "RELATIVE_WEAK"

            elif not breakout_ready(data):
                fail_reason = "NOT_READY"

            elif not passes_quality_filters(
                final_score=final_score,
                volume_score=volume_score,
                strength_score=strength_score,
                compression_score=comp_score
            ):
                fail_reason = "QUALITY_FAIL"

            else:
                passed = True
                fail_reason = "PASSED"

            insert_scan_symbol(scan_id, {
                "symbol": symbol,
                "price": live_price,
                "trend": trend,
                "volume_score": volume_score,
                "strength_score": strength_score,
                "compression_score": comp_score,
                "final_score": final_score,
                "passed": passed,
                "reason": fail_reason
            })

            if not passed:
                continue

            # ---------- VALID SETUP ----------
            levels = calculate_trade_levels(
                symbol=symbol,
                side=side,
                entry_price=live_price,
                data=data
            )

            if not levels:
                continue

            entry = levels["entry"]
            stop_loss = levels["stop_loss"]
            target = levels["target"]

            rr = calculate_rr(entry, stop_loss, target, side)
            if rr < 2:
                continue

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
                market_status=market_status
            )

            trigger = trigger_status(symbol, side, entry, live_price)

            # ---------- TRADE ----------
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
                    "final_score": final_score
                },
                market_context={
                    "market_status": market_status,
                    "trend": trend
                },
                setup_context={},
                reason=reason,
                trigger_status=trigger
            )

            # ---------- SETUP MEMORY ----------
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
                    "final_score": final_score
                },
                "market_context": {
                    "market_status": market_status,
                    "trend": trend
                },
                "setup_context": {
                    "structure_ok": True,
                    "momentum_ok": True,
                    "breakout_ready": True
                },
                "reason": reason,
                "trigger_status": trigger,
                "status": "OPEN"
            })

            # ---------- TRADE MEMORY ----------
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
                    "final_score": final_score
                },
                "market_context": market_status,
                "setup_context": {"trend": trend},
                "reason": reason,
                "trigger_status": trigger,
                "status": "OPEN"
            })

            setups.append(symbol)
            setup_symbols.append(symbol)
            scan_record["setup_count"] += 1

        except Exception as e:
            errors.append(f"{symbol}: {e}")
            continue

    log_scan(
        total_symbols=total_symbols,
        scanned_symbols=scanned_symbols,
        setup_symbols=setup_symbols,
        errors=errors
    )

    return setups