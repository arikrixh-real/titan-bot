def trend_direction(df, lookback=20):
    if df is None or len(df) < lookback:
        return "SIDEWAYS"

    try:
        close = df["Close"]

        recent = close.iloc[-lookback:]
        start = recent.iloc[0]
        end = recent.iloc[-1]

        change = ((end - start) / start) * 100

        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        price = close.iloc[-1]

        # Strong trend
        if change > 2:
            return "UP"

        if change < -2:
            return "DOWN"

        # Moderate trend support
        if price > ema20 and ema20 > ema50 and change > 0.5:
            return "UP"

        if price < ema20 and ema20 < ema50 and change < -0.5:
            return "DOWN"

        return "SIDEWAYS"

    except Exception:
        return "SIDEWAYS"


def trade_side_from_trend(trend):
    if trend == "UP":
        return "LONG"

    if trend == "DOWN":
        return "SHORT"

    return None