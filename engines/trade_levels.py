def calculate_trade_levels(df, side="LONG"):
    """
    Improved levels → ensures good RR
    """

    try:
        last = df.iloc[-1]

        price = last["Close"]

        if side == "LONG":
            sl = price * 0.99      # tight SL
            target = price * 1.03  # bigger target

        elif side == "SHORT":
            sl = price * 1.01
            target = price * 0.97

        else:
            return None

        return {
            "entry": price,
            "sl": sl,
            "target": target
        }

    except Exception:
        return None