def breakout_ready(df, side="LONG"):
    if len(df) < 10:
        return False

    recent = df.iloc[-5:]

    highs = recent["High"]
    lows = recent["Low"]
    close = recent["Close"].iloc[-1]

    resistance = highs.max()
    support = lows.min()

    if side == "LONG":
        # Must be close to breakout, not too far
        distance = (close - resistance) / resistance

        if close < resistance * 0.995:
            return False  # not near breakout

        if distance > 0.01:
            return False  # already moved too far

        return True

    if side == "SHORT":
        distance = (support - close) / support

        if close > support * 1.005:
            return False

        if distance > 0.01:
            return False

        return True

    return False