def calculate_trade_levels(df, side="LONG"):
    latest = df.iloc[-1]

    high = latest["High"]
    low = latest["Low"]

    if side == "LONG":
        entry = round(high * 1.001, 2)
        sl = round(low * 0.999, 2)
        risk = entry - sl
        t1 = round(entry + (risk * 1.5), 2)
        t2 = round(entry + (risk * 2.5), 2)

    elif side == "SHORT":
        entry = round(low * 0.999, 2)
        sl = round(high * 1.001, 2)
        risk = sl - entry
        t1 = round(entry - (risk * 1.5), 2)
        t2 = round(entry - (risk * 2.5), 2)

    else:
        return None

    return entry, sl, t1, t2