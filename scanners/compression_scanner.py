def compression_score(df, lookback=10):
    if len(df) < lookback:
        return 0

    recent = df.iloc[-lookback:]

    highest_high = recent["High"].max()
    lowest_low = recent["Low"].min()
    latest_close = recent["Close"].iloc[-1]

    if latest_close == 0:
        return 0

    range_percent = ((highest_high - lowest_low) / latest_close) * 100

    # Lower range = more compression
    score = max(0, 10 - range_percent)
    return round(float(score), 2)