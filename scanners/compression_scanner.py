def to_float(value):
    try:
        if hasattr(value, "iloc"):
            return float(value.iloc[0])
        return float(value)
    except Exception:
        return 0.0


def compression_score(df, lookback=10):
    if len(df) < lookback:
        return 0

    recent = df.iloc[-lookback:]

    highest_high = to_float(recent["High"].max())
    lowest_low = to_float(recent["Low"].min())
    latest_close = to_float(df["Close"].iloc[-1])

    if latest_close == 0:
        return 0

    range_percent = ((highest_high - lowest_low) / latest_close) * 100

    score = max(0, 10 - range_percent)
    return round(float(score), 2)