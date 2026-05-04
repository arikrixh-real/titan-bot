import os
import pandas as pd


def load_stock_candles(stock):
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

        if df.empty:
            return None

        return df

    except Exception:
        return None


def analyze_real_structure(stock_data):
    stock = stock_data.get("stock")

    if not stock:
        return {
            "adjustment": 0,
            "status": "NO_STOCK",
            "reason": "Stock name missing"
        }

    df = load_stock_candles(stock)

    if df is None or len(df) < 20:
        return {
            "adjustment": 0,
            "status": "NO_DATA",
            "reason": "Not enough candle data for real structure analysis"
        }

    recent = df.tail(20)

    last_close = float(recent["close"].iloc[-1])
    last_high = float(recent["high"].iloc[-1])
    last_low = float(recent["low"].iloc[-1])
    last_volume = float(recent["volume"].iloc[-1])

    previous_high = float(recent["high"].iloc[:-1].max())
    previous_low = float(recent["low"].iloc[:-1].min())
    avg_volume = float(recent["volume"].iloc[:-1].mean())

    adjustment = 0
    confirmations = []
    warnings = []

    if last_close > previous_high and last_volume > avg_volume:
        adjustment += 20
        confirmations.append("Real breakout confirmed above recent high with volume")

    if last_high > previous_high and last_close < previous_high:
        adjustment -= 30
        warnings.append("Price swept above resistance but closed below → fake breakout risk")

    if last_close < previous_low and last_volume > avg_volume:
        adjustment += 20
        confirmations.append("Real breakdown confirmed below recent low with volume")

    if last_low < previous_low and last_close > previous_low:
        adjustment -= 30
        warnings.append("Price swept below support but closed back above → liquidity sweep")

    if last_volume < avg_volume:
        adjustment -= 10
        warnings.append("Latest move has below-average volume")

    adjustment = max(-40, min(adjustment, 40))

    return {
        "adjustment": adjustment,
        "status": "OK",
        "last_close": last_close,
        "previous_high": previous_high,
        "previous_low": previous_low,
        "avg_volume": round(avg_volume, 2),
        "last_volume": last_volume,
        "confirmations": confirmations,
        "warnings": warnings
    }