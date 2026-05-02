def price_strength_score(df, lookback=10):
    if len(df) < lookback + 1:
        return 0

    latest_close = df["Close"].iloc[-1]
    old_close = df["Close"].iloc[-lookback]

    if old_close == 0:
        return 0

    percent_change = ((latest_close - old_close) / old_close) * 100
    return round(float(percent_change), 2)