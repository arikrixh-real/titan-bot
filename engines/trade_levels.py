"""
TITAN - Trade Levels Engine
---------------------------
Always returns exactly 3 values:
entry, sl, target
"""


def calculate_trade_levels(df, side, price=None):
    try:
        if df is None or df.empty:
            return None, None, None

        for col in ["High", "Low", "Close"]:
            if col not in df.columns:
                print(f"⚠️ Missing column in trade_levels.py: {col}")
                return None, None, None

        last_candle = df.iloc[-1]

        if price is None:
            price = float(last_candle["Close"])

        entry = float(price)
        side = str(side).upper().strip()

        if side == "LONG":
            sl = float(last_candle["Low"])
            risk = entry - sl

            if risk <= 0:
                return None, None, None

            target = entry + (risk * 2)

        elif side == "SHORT":
            sl = float(last_candle["High"])
            risk = sl - entry

            if risk <= 0:
                return None, None, None

            target = entry - (risk * 2)

        else:
            return None, None, None

        return round(entry, 2), round(sl, 2), round(target, 2)

    except Exception as e:
        print(f"⚠️ Trade level calculation failed: {e}")
        return None, None, None