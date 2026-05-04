def breakout_ready(df, side="LONG"):
    """
    RELAXED ENTRY LOGIC

    Old version was too strict → no signals
    New version detects:
    - near breakout
    - momentum move
    """

    if df is None or len(df) < 10:
        return False

    recent = df.iloc[-5:]

    highs = recent["High"]
    lows = recent["Low"]

    last_close = df["Close"].iloc[-1]

    resistance = highs.max()
    support = lows.min()

    # 🔥 RELAXED LOGIC

    if side == "LONG":
        # breakout OR near breakout (within 0.5%)
        if last_close >= resistance * 0.995:
            return True

        # momentum push
        if last_close > df["Close"].iloc[-2]:
            return True

    elif side == "SHORT":
        if last_close <= support * 1.005:
            return True

        if last_close < df["Close"].iloc[-2]:
            return True

    return False
def get_evolution_filter_threshold(base_threshold=60.0):
    try:
        state = get_evolution_state()

        score_boost = float(state.get("score_boost", 1.0))

        # Adjust threshold slightly based on learning
        adjusted = base_threshold * score_boost

        # Clamp between safe range
        return max(50.0, min(adjusted, 80.0))

    except:
        return base_threshold