def to_float(value):
    try:
        if hasattr(value, "iloc"):
            return float(value.iloc[0])
        return float(value)
    except Exception:
        return 0.0


def price_strength_score(df, lookback=10):
    if len(df) < lookback + 1:
        return 0

    latest_close = to_float(df["Close"].iloc[-1])
    old_close = to_float(df["Close"].iloc[-lookback])

    if old_close == 0:
        return 0

    percent_change = ((latest_close - old_close) / old_close) * 100
    return round(float(percent_change), 2)