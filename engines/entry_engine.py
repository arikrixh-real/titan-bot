def breakout_ready(df, side=None):
    """
    Balanced entry readiness.
    If side is not provided, accepts either LONG or SHORT entry readiness.
    """

    if df is None or len(df) < 10:
        return False

    try:
        recent = df.iloc[-6:]

        highs = recent["High"]
        lows = recent["Low"]
        close = recent["Close"].iloc[-1]
        prev_close = recent["Close"].iloc[-2]

        resistance = highs.iloc[:-1].max()
        support = lows.iloc[:-1].min()

        # LONG readiness:
        # 1. Near resistance
        # 2. Breaking resistance
        # 3. Recovering upward
        long_near_breakout = close >= resistance * 0.99
        long_breakout = close > resistance
        long_recovery = close > prev_close and close > recent["Close"].mean()

        long_ready = long_near_breakout or long_breakout or long_recovery

        # SHORT readiness:
        # 1. Near support
        # 2. Breaking support
        # 3. Weakening downward
        short_near_breakdown = close <= support * 1.01
        short_breakdown = close < support
        short_weakness = close < prev_close and close < recent["Close"].mean()

        short_ready = short_near_breakdown or short_breakdown or short_weakness

        if side == "LONG":
            return long_ready

        if side == "SHORT":
            return short_ready

        return long_ready or short_ready

    except Exception:
        return False