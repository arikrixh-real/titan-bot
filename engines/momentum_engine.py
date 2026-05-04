def strong_momentum(df, side=None):
    """
    Adaptive momentum check.
    If side is not provided, accepts either LONG or SHORT momentum.
    """

    if df is None or len(df) < 3:
        return False

    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]

        body = abs(last["Close"] - last["Open"])
        range_candle = last["High"] - last["Low"]

        if range_candle == 0:
            return False

        body_ratio = body / range_candle

        long_momentum = (
            last["Close"] > last["Open"]
            and last["Close"] >= (last["Low"] + range_candle * 0.50)
            and last["Close"] >= prev["Close"]
            and body_ratio >= 0.25
        )

        short_momentum = (
            last["Close"] < last["Open"]
            and last["Close"] <= (last["High"] - range_candle * 0.50)
            and last["Close"] <= prev["Close"]
            and body_ratio >= 0.25
        )

        if side == "LONG":
            return long_momentum

        if side == "SHORT":
            return short_momentum

        return long_momentum or short_momentum

    except Exception:
        return False