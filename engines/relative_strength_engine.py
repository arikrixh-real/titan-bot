import pandas as pd


def relative_strength_ok(stock_df, side=None):
    """
    Adaptive relative strength check.
    If side is not provided, accepts either relative strength or relative weakness.
    """

    try:
        market_df = pd.read_csv("data/cache/NIFTYBEES.csv")

        for df in [stock_df, market_df]:
            if "Close" in df.columns:
                df["Close"] = pd.to_numeric(df["Close"], errors="coerce")

        stock_df = stock_df.dropna(subset=["Close"])
        market_df = market_df.dropna(subset=["Close"])

        if len(stock_df) < 20 or len(market_df) < 20:
            return False

        stock_recent = stock_df["Close"].iloc[-20:]
        market_recent = market_df["Close"].iloc[-20:]

        stock_change = ((stock_recent.iloc[-1] - stock_recent.iloc[0]) / stock_recent.iloc[0]) * 100
        market_change = ((market_recent.iloc[-1] - market_recent.iloc[0]) / market_recent.iloc[0]) * 100

        relative_score = stock_change - market_change

        long_ok = relative_score > -0.25
        short_ok = relative_score < 0.25

        if side == "LONG":
            return long_ok

        if side == "SHORT":
            return short_ok

        return long_ok or short_ok

    except Exception:
        return False