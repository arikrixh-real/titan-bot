def structure_ok(df, side="LONG", lookback=6):
    if len(df) < lookback:
        return False

    recent = df.iloc[-lookback:]

    highs = list(recent["High"])
    lows = list(recent["Low"])

    if side == "LONG":
        recent_highs_rising = highs[-1] > highs[-3]
        recent_lows_rising = lows[-1] > lows[-3]
        return recent_highs_rising and recent_lows_rising

    if side == "SHORT":
        recent_highs_falling = highs[-1] < highs[-3]
        recent_lows_falling = lows[-1] < lows[-3]
        return recent_highs_falling and recent_lows_falling

    return False