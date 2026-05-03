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

        if len(df) < 20:
            return None

        return df

    except Exception:
        return None


def optimize_stop_loss(stock_data):
    stock = stock_data.get("stock")
    side = str(stock_data.get("side", "")).upper()

    entry = float(stock_data.get("entry", 0))
    current_sl = float(stock_data.get("sl", 0))

    if not stock or entry <= 0 or current_sl <= 0:
        return {
            "status": "INVALID_DATA",
            "optimized_sl": current_sl,
            "adjustment": 0,
            "reason": "Invalid stock/entry/SL data"
        }

    df = load_candles(stock)

    if df is None:
        return {
            "status": "NO_DATA",
            "optimized_sl": current_sl,
            "adjustment": 0,
            "reason": "Not enough candle data for SL optimization"
        }

    recent = df.tail(20)

    swing_low = float(recent["low"].min())
    swing_high = float(recent["high"].max())

    optimized_sl = current_sl
    adjustment = 0
    reason = "Original SL retained"

    if side == "LONG":
        structure_sl = round(swing_low, 2)

        if structure_sl < entry and structure_sl > current_sl:
            optimized_sl = structure_sl
            adjustment += 10
            reason = "SL improved closer to recent swing low"

        elif structure_sl < current_sl:
            optimized_sl = current_sl
            adjustment += 5
            reason = "Original SL already safer than structure SL"

    elif side == "SHORT":
        structure_sl = round(swing_high, 2)

        if structure_sl > entry and structure_sl < current_sl:
            optimized_sl = structure_sl
            adjustment += 10
            reason = "SL improved closer to recent swing high"

        elif structure_sl > current_sl:
            optimized_sl = current_sl
            adjustment += 5
            reason = "Original SL already safer than structure SL"

    optimized_sl = round(optimized_sl, 2)

    return {
        "status": "OK",
        "optimized_sl": optimized_sl,
        "original_sl": current_sl,
        "adjustment": adjustment,
        "reason": reason
    }