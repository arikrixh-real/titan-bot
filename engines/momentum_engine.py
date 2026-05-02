def strong_momentum(df, side="LONG"):
    if len(df) < 3:
        return False

    last = df.iloc[-1]
    prev = df.iloc[-2]

    body = abs(last["Close"] - last["Open"])
    range_candle = last["High"] - last["Low"]

    if range_candle == 0:
        return False

    body_ratio = body / range_candle

    if side == "LONG":
        bullish_close = last["Close"] > last["Open"]
        close_near_high = last["Close"] >= (last["Low"] + range_candle * 0.55)
        close_above_prev = last["Close"] > prev["Close"]

        return bullish_close and close_near_high and close_above_prev and body_ratio > 0.35

    if side == "SHORT":
        bearish_close = last["Close"] < last["Open"]
        close_near_low = last["Close"] <= (last["High"] - range_candle * 0.55)
        close_below_prev = last["Close"] < prev["Close"]

        return bearish_close and close_near_low and close_below_prev and body_ratio > 0.35

    return False