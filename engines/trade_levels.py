def calculate_trade_levels(df, side="LONG"):
    """
    Clean trade level calculation
    NO extra arguments like 'symbol'
    """

    try:
        last = df.iloc[-1]

        price = last["Close"]

        if side == "LONG":
            sl = price * 0.98
            target = price * 1.02

        elif side == "SHORT":
            sl = price * 1.02
            target = price * 0.98

        else:
            return None

        return {
            "entry": price,
            "sl": sl,
            "target": target
        }

    except Exception:
        return None