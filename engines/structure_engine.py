def structure_ok(df, side=None, lookback=8):
    """
    Adaptive structure check.
    If side is not provided, accepts either LONG-like or SHORT-like structure.
    """

    if df is None or len(df) < lookback:
        return False

    try:
        recent = df.iloc[-lookback:]

        highs = list(recent["High"])
        lows = list(recent["Low"])
        closes = list(recent["Close"])

        current_close = closes[-1]
        previous_close = closes[-2]

        recent_high = max(highs[:-1])
        recent_low = min(lows[:-1])

        long_breakout = current_close > recent_high
        long_recovery = current_close > previous_close and lows[-1] >= min(lows[-3:])

        short_breakdown = current_close < recent_low
        short_weakness = current_close < previous_close and highs[-1] <= max(highs[-3:])

        if side == "LONG":
            return long_breakout or long_recovery

        if side == "SHORT":
            return short_breakdown or short_weakness

        return long_breakout or long_recovery or short_breakdown or short_weakness

    except Exception:
        return False