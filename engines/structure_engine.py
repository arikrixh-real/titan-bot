def structure_ok(df, side="LONG", lookback=8):
    """
    Checks whether price structure is acceptable.
    Balanced version:
    - Not too strict
    - Allows clean pullbacks
    - Still avoids messy sideways structure
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

        # LONG structure:
        # Either price breaks above recent high
        # OR price is recovering with higher close
        if side == "LONG":
            breakout_structure = current_close > recent_high
            recovery_structure = current_close > previous_close and lows[-1] >= min(lows[-3:])

            return breakout_structure or recovery_structure

        # SHORT structure:
        # Either price breaks below recent low
        # OR price is weakening with lower close
        if side == "SHORT":
            breakdown_structure = current_close < recent_low
            weakness_structure = current_close < previous_close and highs[-1] <= max(highs[-3:])

            return breakdown_structure or weakness_structure

        return False

    except Exception:
        return False