def avoid_fake_breakout(df, side="LONG"):
    if len(df) < 2:
        return True

    last = df.iloc[-1]

    upper_wick = last["High"] - max(last["Close"], last["Open"])
    lower_wick = min(last["Close"], last["Open"]) - last["Low"]
    body = abs(last["Close"] - last["Open"])

    if body == 0:
        return False

    if side == "LONG":
        if upper_wick > body * 1.5:
            return False

    if side == "SHORT":
        if lower_wick > body * 1.5:
            return False

    return True