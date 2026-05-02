import contextlib
import io
import yfinance as yf

from intelligence.news_signal_engine import get_actionable_news_signals


BAD_SYMBOLS = [
    "TATAMOTORS.NS",
]


BROAD_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "ITC.NS", "LT.NS", "KOTAKBANK.NS", "HINDUNILVR.NS",
    "AXISBANK.NS", "BHARTIARTL.NS", "BAJFINANCE.NS", "ASIANPAINT.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "WIPRO.NS",
    "ULTRACEMCO.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS",
    "COALINDIA.NS", "HCLTECH.NS", "TECHM.NS", "TITAN.NS",
    "NESTLEIND.NS", "BAJAJFINSV.NS", "JSWSTEEL.NS", "ADANIENT.NS",
    "ADANIPORTS.NS", "GRASIM.NS", "M&M.NS", "DRREDDY.NS",
    "CIPLA.NS", "DIVISLAB.NS", "EICHERMOT.NS", "HEROMOTOCO.NS",
    "BRITANNIA.NS", "HDFCLIFE.NS", "SBILIFE.NS", "APOLLOHOSP.NS",
    "BPCL.NS", "INDUSINDBK.NS", "UPL.NS", "TATACONSUM.NS",
    "BAJAJ-AUTO.NS", "HINDALCO.NS", "SHREECEM.NS", "DMART.NS",
    "PIDILITIND.NS", "GODREJCP.NS", "DABUR.NS", "BERGEPAINT.NS",
    "COLPAL.NS", "MARICO.NS", "ICICIPRULI.NS", "ICICIGI.NS",
    "SBICARD.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS", "BOSCHLTD.NS",
    "SIEMENS.NS", "ABB.NS", "HAL.NS", "BEL.NS", "IRCTC.NS",
    "INDIGO.NS", "NAUKRI.NS", "POLYCAB.NS", "TRENT.NS",
    "VOLTAS.NS", "AMBUJACEM.NS", "ACC.NS", "BANKBARODA.NS",
    "PNB.NS", "CANBK.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS",
    "AUBANK.NS", "LICHSGFIN.NS", "TVSMOTOR.NS", "ASHOKLEY.NS",
    "BALKRISIND.NS", "ESCORTS.NS", "JUBLFOOD.NS", "PAGEIND.NS",
    "BIOCON.NS", "TORNTPHARM.NS", "LUPIN.NS", "AUROPHARMA.NS",
    "ZYDUSLIFE.NS", "GLENMARK.NS", "SAIL.NS", "NMDC.NS",
    "VEDL.NS", "GAIL.NS", "IOC.NS", "HINDPETRO.NS",
    "PETRONET.NS", "CONCOR.NS",
]


def clean_symbol(symbol):
    return symbol.replace(".NS", "")


def to_float(value):
    try:
        if hasattr(value, "iloc"):
            value = value.iloc[0]
        return float(value)
    except Exception:
        return 0.0


def fetch_data(symbol):
    if symbol in BAD_SYMBOLS:
        return None

    try:
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            df = yf.download(
                symbol,
                period="1mo",
                interval="1d",
                progress=False,
                auto_adjust=False,
                group_by="column",
                threads=False,
            )

        if df is None or df.empty:
            return None

        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)

        required_cols = ["Close", "Volume", "High", "Low"]
        for col in required_cols:
            if col not in df.columns:
                return None

        return df

    except Exception:
        return None


def get_news_bonus():
    news_signals = get_actionable_news_signals()
    bonus_map = {}

    for signal in news_signals:
        symbol = signal["symbol"]
        sentiment = signal["sentiment"]
        strength = signal["strength"]

        if sentiment == "BULLISH":
            bonus_map[symbol] = strength * 10
        elif sentiment == "BEARISH":
            bonus_map[symbol] = strength * 5

    return bonus_map


def calculate_opportunity_score(symbol, df, news_bonus_map):
    if df is None or len(df) < 20:
        return None

    latest_close = to_float(df["Close"].iloc[-1])
    old_close = to_float(df["Close"].iloc[-10])
    latest_volume = to_float(df["Volume"].iloc[-1])
    avg_volume = to_float(df["Volume"].tail(20).mean())

    if latest_close == 0 or old_close == 0 or avg_volume == 0:
        return None

    price_strength = ((latest_close - old_close) / old_close) * 100
    volume_ratio = latest_volume / avg_volume

    score = 0
    reasons = []

    if price_strength > 2:
        score += 25
        reasons.append("Price strength building")

    if price_strength > 5:
        score += 15
        reasons.append("Strong momentum")

    if volume_ratio > 1.2:
        score += 25
        reasons.append("Volume activity rising")

    if volume_ratio > 1.8:
        score += 15
        reasons.append("Unusual volume")

    clean = clean_symbol(symbol)
    news_bonus = news_bonus_map.get(clean, 0)

    if news_bonus > 0:
        score += news_bonus
        reasons.append("News activity detected")

    return {
        "symbol": symbol,
        "clean_symbol": clean,
        "score": round(score, 2),
        "price_strength": round(price_strength, 2),
        "volume_ratio": round(volume_ratio, 2),
        "reason": ", ".join(reasons) if reasons else "Normal activity",
    }


def get_dynamic_top_stocks(limit=50):
    print("TITAN dynamic selector started...")

    selected = []
    news_bonus_map = get_news_bonus()

    for symbol in BROAD_UNIVERSE:
        if symbol in BAD_SYMBOLS:
            continue

        df = fetch_data(symbol)
        result = calculate_opportunity_score(symbol, df, news_bonus_map)

        if result:
            selected.append(result)

    selected = sorted(selected, key=lambda x: x["score"], reverse=True)
    top = selected[:limit]

    print(f"Selected top {len(top)} stocks for deep TITAN scan.")

    return [item["symbol"] for item in top]


if __name__ == "__main__":
    stocks = get_dynamic_top_stocks(limit=50)

    print("\nDynamic Top Stocks:")
    for stock in stocks:
        print(stock)