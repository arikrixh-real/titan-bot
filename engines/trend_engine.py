"""
TITAN Trend Engine - FINAL FILTER FIX
-------------------------------------
Purpose:
1. Prevents all stocks from automatically passing trend.
2. Returns only:
   - "BULLISH"
   - "BEARISH"
   - "SIDEWAYS"
3. setup_engine.py will only accept LONG/SHORT if trend is BULLISH/BEARISH.
4. SIDEWAYS stocks are rejected before structure/momentum/entry filters.
5. No external dependencies except pandas already used in TITAN.

How it works:
- Uses EMA 20 and EMA 50
- Checks close position against EMAs
- Checks EMA slope
- Checks recent price structure
"""

import pandas as pd


def _safe_series(df, column):
    try:
        if df is None or df.empty or column not in df.columns:
            return None

        s = pd.to_numeric(df[column], errors="coerce").dropna()

        if len(s) == 0:
            return None

        return s

    except Exception:
        return None


def _ema(series, period):
    try:
        return series.ewm(span=period, adjust=False).mean()
    except Exception:
        return None


def trend_direction(df):
    """
    Returns:
    - BULLISH
    - BEARISH
    - SIDEWAYS

    This is intentionally strict enough so all 101 stocks do NOT pass trend.
    """
    try:
        close = _safe_series(df, "Close")
        high = _safe_series(df, "High")
        low = _safe_series(df, "Low")

        if close is None or high is None or low is None:
            return "SIDEWAYS"

        if len(close) < 60:
            return "SIDEWAYS"

        ema20 = _ema(close, 20)
        ema50 = _ema(close, 50)

        if ema20 is None or ema50 is None:
            return "SIDEWAYS"

        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])

        ema20_now = float(ema20.iloc[-1])
        ema50_now = float(ema50.iloc[-1])
        ema20_prev = float(ema20.iloc[-5])
        ema50_prev = float(ema50.iloc[-5])

        recent_high_now = float(high.iloc[-1])
        recent_high_prev = float(high.iloc[-6:-1].max())

        recent_low_now = float(low.iloc[-1])
        recent_low_prev = float(low.iloc[-6:-1].min())

        ema20_slope_up = ema20_now > ema20_prev
        ema50_slope_up = ema50_now > ema50_prev

        ema20_slope_down = ema20_now < ema20_prev
        ema50_slope_down = ema50_now < ema50_prev

        bullish_conditions = [
            last_close > ema20_now,
            ema20_now > ema50_now,
            ema20_slope_up,
            ema50_slope_up,
            last_close >= prev_close,
            recent_high_now >= recent_high_prev,
        ]

        bearish_conditions = [
            last_close < ema20_now,
            ema20_now < ema50_now,
            ema20_slope_down,
            ema50_slope_down,
            last_close <= prev_close,
            recent_low_now <= recent_low_prev,
        ]

        bullish_score = sum(bool(x) for x in bullish_conditions)
        bearish_score = sum(bool(x) for x in bearish_conditions)

        if bullish_score >= 5:
            return "BULLISH"

        if bearish_score >= 5:
            return "BEARISH"

        return "SIDEWAYS"

    except Exception:
        return "SIDEWAYS"


def trade_side_from_trend(trend):
    """
    Maps trend to trade side.
    setup_engine.py expects LONG/SHORT only.
    SIDEWAYS returns None so stock gets rejected.
    """
    trend = str(trend or "").upper()

    if trend in ["BULLISH", "UPTREND", "UP", "LONG"]:
        return "LONG"

    if trend in ["BEARISH", "DOWNTREND", "DOWN", "SHORT"]:
        return "SHORT"

    return None