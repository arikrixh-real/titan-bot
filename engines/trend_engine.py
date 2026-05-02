def trend_direction(df, lookback=20):
    if len(df) < lookback:
        return "SIDEWAYS"

    recent = df["Close"].iloc[-lookback:]

    start = recent.iloc[0]
    end = recent.iloc[-1]

    change = ((end - start) / start) * 100

    if change > 2:
        return "UP"
    elif change < -2:
        return "DOWN"
    else:
        return "SIDEWAYS"


def trade_side_from_trend(trend):
    if trend == "UP":
        return "LONG"
    elif trend == "DOWN":
        return "SHORT"
    return None