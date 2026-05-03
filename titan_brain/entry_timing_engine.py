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

        required = ["open", "high", "low", "close"]

        for col in required:
            if col not in df.columns:
                return None

        for col in required:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=required)

        if len(df) < 10:
            return None

        return df

    except Exception:
        return None


def analyze_entry_timing(stock_data):
    stock = stock_data.get("stock")
    side = str(stock_data.get("side", "")).upper()

    if not stock:
        return {
            "adjustment": 0,
            "status": "NO_STOCK"
        }

    df = load_candles(stock)

    if df is None:
        return {
            "adjustment": 0,
            "status": "NO_DATA"
        }

    recent = df.tail(5)

    last_close = float(recent["close"].iloc[-1])
    prev_close = float(recent["close"].iloc[-2])
    prev_high = float(recent["high"].iloc[-2])
    prev_low = float(recent["low"].iloc[-2])

    adjustment = 0
    confirmations = []
    warnings = []

    if side == "LONG":
        if last_close > prev_high:
            adjustment -= 15
            warnings.append("Entry after breakout candle → possible late entry")

        elif last_close > prev_close:
            adjustment += 10
            confirmations.append("Momentum building → good early entry")

    elif side == "SHORT":
        if last_close < prev_low:
            adjustment -= 15
            warnings.append("Entry after breakdown candle → possible late entry")

        elif last_close < prev_close:
            adjustment += 10
            confirmations.append("Downside momentum building → good early entry")

    return {
        "adjustment": adjustment,
        "confirmations": confirmations,
        "warnings": warnings,
        "status": "OK"
    }