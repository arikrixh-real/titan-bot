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
from engines.trigger_engine import trigger_status
from engines.structure_engine import structure_ok


def scan_for_setups():
    market_status = market_regime_status()

    direction = market_status.get("direction", "UNKNOWN")
    market_ok = market_status.get("market_ok", True)

    if not market_ok:
        print(f"Market filter blocked scan: {market_status.get('reason', '')}")
        return []

    stock_data = load_cached_stock_data()
    results = []

    total_scanned = 0
    qualified = 0

    for stock, df in stock_data.items():

        if stock == "NIFTYBEES":
            continue

        total_scanned += 1

        trend = trend_direction(df)
        side = trade_side_from_trend(trend)

        if side is None:
            continue

        if direction == "BULLISH" and side != "LONG":
            continue

        if direction == "BEARISH" and side != "SHORT":
            continue

        if not structure_ok(df, side):
            continue

        if not strong_momentum(df, side):
            continue

        if not avoid_fake_breakout(df, side):
            continue

        if not relative_strength_ok(df, side):
            continue

        if not breakout_ready(df, side):
            continue

        volume_score = volume_anomaly_score(df)
        strength_score = price_strength_score(df)
        compression_value = compression_score(df)

        if side == "SHORT":
            strength_score = abs(strength_score)

        final_score = final_signal_score(
            volume_score,
            strength_score,
            compression_value
        )

        entry, sl, t1, t2 = calculate_trade_levels(df, side)
        rr = calculate_rr(entry, sl, t1, side)

        historical_close = round(float(df["Close"].iloc[-1]), 2)

        symbol_ns = f"{stock}.NS"
        live_price = get_live_price(symbol_ns)

        if live_price is None:
            latest_price = historical_close
            price_source = "HIST"
        else:
            latest_price = live_price
            price_source = "LIVE"

        setup = {
            "stock": stock,
            "side": side,
            "price": latest_price,
            "entry": entry,
            "sl": sl,
            "t1": t1,
            "t2": t2,
            "rr": rr,
            "volume_x": volume_score,
            "strength_%": strength_score,
            "compression": compression_value,
            "score": final_score,
            "source": price_source
        }

        if not passes_quality_filters(setup):
            continue

        setup["reason"] = build_reason(setup)
        setup["status"] = trigger_status(latest_price, entry, side)

        results.append(setup)
        qualified += 1

    results = sorted(results, key=lambda x: x["score"], reverse=True)

    print(f"\nScanned: {total_scanned} stocks | Qualified: {qualified}")

    return results