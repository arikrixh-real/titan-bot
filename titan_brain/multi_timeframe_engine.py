import os
import pandas as pd


def load_candles(stock):
    file_path = f"data/cache/{stock}.csv"

    if not os.path.exists(file_path):
        return None

    try:
        df = pd.read_csv(file_path)

        if df.empty:
            return None

        df.columns = [str(col).lower().strip() for col in df.columns]

        required = ["open", "high", "low", "close", "volume"]

        for col in required:
            if col not in df.columns:
                return None

        for col in required:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=required)

        if len(df) < 30:
            return None

        return df

    except Exception:
        return None


def calculate_trend(df, candles):
    recent = df.tail(candles)

    first_close = float(recent["close"].iloc[0])
    last_close = float(recent["close"].iloc[-1])

    if last_close > first_close:
        return "BULLISH"
    elif last_close < first_close:
        return "BEARISH"
    else:
        return "NEUTRAL"


def analyze_multi_timeframe(stock_data):
    stock = stock_data.get("stock")
    side = str(stock_data.get("side", "")).upper()

    if not stock:
        return {
            "adjustment": 0,
            "status": "NO_STOCK",
            "reason": "Stock name missing"
        }

    df = load_candles(stock)

    if df is None:
        return {
            "adjustment": 0,
            "status": "NO_DATA",
            "reason": "Not enough candle data for multi-timeframe analysis"
        }

    short_trend = calculate_trend(df, 5)
    medium_trend = calculate_trend(df, 15)
    long_trend = calculate_trend(df, 30)

    adjustment = 0
    confirmations = []
    warnings = []

    if side == "LONG":
        if short_trend == "BULLISH":
            adjustment += 10
            confirmations.append("Short-term trend supports LONG")

        if medium_trend == "BULLISH":
            adjustment += 15
            confirmations.append("Medium-term trend supports LONG")

        if long_trend == "BULLISH":
            adjustment += 15
            confirmations.append("Longer-term trend supports LONG")

        if medium_trend == "BEARISH" or long_trend == "BEARISH":
            adjustment -= 20
            warnings.append("Higher timeframe trend is against LONG")

    elif side == "SHORT":
        if short_trend == "BEARISH":
            adjustment += 10
            confirmations.append("Short-term trend supports SHORT")

        if medium_trend == "BEARISH":
            adjustment += 15
            confirmations.append("Medium-term trend supports SHORT")

        if long_trend == "BEARISH":
            adjustment += 15
            confirmations.append("Longer-term trend supports SHORT")

        if medium_trend == "BULLISH" or long_trend == "BULLISH":
            adjustment -= 20
            warnings.append("Higher timeframe trend is against SHORT")

    adjustment = max(-40, min(adjustment, 40))

    return {
        "adjustment": adjustment,
        "status": "OK",
        "short_trend": short_trend,
        "medium_trend": medium_trend,
        "long_trend": long_trend,
        "confirmations": confirmations,
        "warnings": warnings
    }