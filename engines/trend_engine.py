def trend_direction(df):
    if df is None or len(df) < 50:
        return "SIDEWAYS"

    try:
        close = df["Close"]

        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]

        price = close.iloc[-1]

        # Strong trend
        if price > ema20 > ema50:
            return "UP"

        if price < ema20 < ema50:
            return "DOWN"

        # Weak / early trend
        if price > ema50:
            return "UP"

        if price < ema50:
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