import pandas as pd


def relative_strength_ok(stock_df, side="LONG"):
    try:
        market_df = pd.read_csv("data/cache/NIFTYBEES.csv")

        for df in [stock_df, market_df]:
            for col in ["Close"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

        stock_df = stock_df.dropna(subset=["Close"])
        market_df = market_df.dropna(subset=["Close"])

        if len(stock_df) < 20 or len(market_df) < 20:
            return False

        stock_recent = stock_df["Close"].iloc[-20:]
        market_recent = market_df["Close"].iloc[-20:]

        stock_change = ((stock_recent.iloc[-1] - stock_recent.iloc[0]) / stock_recent.iloc[0]) * 100
        market_change = ((market_recent.iloc[-1] - market_recent.iloc[0]) / market_recent.iloc[0]) * 100

        relative_score = stock_change - market_change

        if side == "LONG":
            return relative_score > 0.5

        if side == "SHORT":
            return relative_score < -0.5

        return False

    except Exception:
        return False