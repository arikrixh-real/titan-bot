import yfinance as yf

from scanners.compression_scanner import compression_score
from scanners.strength_scanner import price_strength_score
from scanners.volume_scanner import volume_anomaly_score
from intelligence.confluence_engine import get_news_map
from intelligence.dynamic_stock_selector import get_dynamic_top_stocks


MIN_CONFIDENCE = 78
MIN_TECHNICAL_SCORE = 55
MIN_VOLUME_RATIO = 1.2


def clean_symbol(symbol):
    return symbol.replace(".NS", "")


def to_float(value):
    try:
        if hasattr(value, "iloc"):
            value = value.iloc[0]
        return float(value)
    except Exception:
        return 0.0


def fetch_stock_data(symbol, period="3mo", interval="1d"):
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            group_by="column",
        )

        if df.empty:
            return None

        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)

        return df

    except Exception:
        return None


def get_market_condition():
    df = fetch_stock_data("^NSEI", period="3mo", interval="1d")

    if df is None or len(df) < 50:
        return {
            "condition": "UNKNOWN",
            "score": 0,
            "reason": "Nifty data unavailable",
        }

    close = df["Close"]
    latest = to_float(close.iloc[-1])
    sma20 = to_float(close.tail(20).mean())
    sma50 = to_float(close.tail(50).mean())

    if latest > sma20 > sma50:
        return {
            "condition": "BULLISH",
            "score": 15,
            "reason": "Nifty above 20DMA and 50DMA",
        }

    if latest < sma20 < sma50:
        return {
            "condition": "BEARISH",
            "score": -15,
            "reason": "Nifty below 20DMA and 50DMA",
        }

    return {
        "condition": "NEUTRAL",
        "score": 0,
        "reason": "Nifty mixed",
    }


def calculate_rsi(df, period=14):
    close = df["Close"]
    delta = close.diff()

    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return round(to_float(rsi.iloc[-1]), 2)


def check_breakout(df):
    latest_close = to_float(df["Close"].iloc[-1])
    recent_high = to_float(df["High"].tail(20).iloc[:-1].max())

    if recent_high == 0:
        return False

    return latest_close > recent_high


def calculate_trade_levels(df, direction):
    current_price = to_float(df["Close"].iloc[-1])
    recent_low = to_float(df["Low"].tail(10).min())
    recent_high = to_float(df["High"].tail(10).max())

    if direction == "BUY":
        entry = round(current_price, 2)
        stop_loss = round(recent_low, 2)
        risk = entry - stop_loss

        if risk <= 0:
            stop_loss = round(entry * 0.985, 2)
            risk = entry - stop_loss

        target_1 = round(entry + risk * 1.5, 2)
        target_2 = round(entry + risk * 2.5, 2)

    else:
        entry = round(current_price, 2)
        stop_loss = round(recent_high, 2)
        risk = stop_loss - entry

        if risk <= 0:
            stop_loss = round(entry * 1.015, 2)
            risk = stop_loss - entry

        target_1 = round(entry - risk * 1.5, 2)
        target_2 = round(entry - risk * 2.5, 2)

    return {
        "current_price": round(current_price, 2),
        "entry": entry,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
    }


def get_fundamental_score(symbol):
    try:
        ticker = yf.Ticker(symbol + ".NS")
        info = ticker.info

        score = 0
        reasons = []

        pe = info.get("trailingPE")
        profit_margin = info.get("profitMargins")
        roe = info.get("returnOnEquity")
        debt_equity = info.get("debtToEquity")

        if pe and pe > 0 and pe < 60:
            score += 10
            reasons.append("PE acceptable")

        if profit_margin and profit_margin > 0:
            score += 10
            reasons.append("Profitable business")

        if roe and roe > 0.08:
            score += 10
            reasons.append("ROE healthy")

        if debt_equity is None or debt_equity < 200:
            score += 5
            reasons.append("Debt acceptable")

        if not reasons:
            reasons.append("Fundamental data limited")

        return {
            "score": score,
            "reason": ", ".join(reasons),
        }

    except Exception:
        return {
            "score": 0,
            "reason": "Fundamental data unavailable",
        }


def get_technical_signal(df):
    compression = compression_score(df)
    strength = price_strength_score(df)
    volume = volume_anomaly_score(df)
    rsi = calculate_rsi(df)
    breakout = check_breakout(df)

    score = 0
    reasons = []

    if compression >= 4:
        score += 15
        reasons.append("Compression")

    if strength >= 2:
        score += 20
        reasons.append("Price strength")

    if volume >= MIN_VOLUME_RATIO:
        score += 20
        reasons.append("Volume expansion")

    if 45 <= rsi <= 70:
        score += 15
        reasons.append("RSI healthy")

    if breakout:
        score += 25
        reasons.append("Breakout near current price")

    if strength <= -2:
        score -= 25
        reasons.append("Price weakness")

    if volume >= 1.5 and strength < 0:
        score -= 25
        reasons.append("Bearish volume pressure")

    if score >= MIN_TECHNICAL_SCORE:
        signal = "BUY"
    elif score <= -45:
        signal = "SELL"
    else:
        signal = "SKIP"

    return {
        "signal": signal,
        "technical_score": score,
        "compression": compression,
        "strength": strength,
        "volume": volume,
        "rsi": rsi,
        "breakout": breakout,
        "technical_reason": ", ".join(reasons) if reasons else "No strong setup",
    }


def shorten_news(title):
    if not title:
        return "No major stock-specific news"

    if len(title) <= 80:
        return title

    return title[:77] + "..."


def apply_news_filter(symbol, technical_signal, news_map):
    news = news_map.get(symbol)

    if not news:
        return {
            "allowed": True,
            "news_score": 0,
            "news_sentiment": "NONE",
            "news_strength": 0,
            "news_short": "No major stock-specific news",
        }

    sentiment = news["sentiment"]
    strength = news["strength"]
    title = news["title"]

    if technical_signal == "BUY" and sentiment == "BEARISH":
        return {
            "allowed": False,
            "news_score": -strength * 10,
            "news_sentiment": sentiment,
            "news_strength": strength,
            "news_short": shorten_news(title),
        }

    if technical_signal == "SELL" and sentiment == "BULLISH":
        return {
            "allowed": False,
            "news_score": -strength * 10,
            "news_sentiment": sentiment,
            "news_strength": strength,
            "news_short": shorten_news(title),
        }

    if technical_signal == "BUY" and sentiment == "BULLISH":
        news_score = strength * 8
    elif technical_signal == "SELL" and sentiment == "BEARISH":
        news_score = strength * 8
    else:
        news_score = 0

    return {
        "allowed": True,
        "news_score": news_score,
        "news_sentiment": sentiment,
        "news_strength": strength,
        "news_short": shorten_news(title),
    }


def scan_final_titan_picks():
    final_picks = []

    print("TITAN selecting dynamic top 50 stocks...")
    stocks = get_dynamic_top_stocks(limit=50)

    market = get_market_condition()
    news_map = get_news_map()

    print(f"TITAN deep scanning {len(stocks)} selected stocks...")

    for yf_symbol in stocks:
        symbol = clean_symbol(yf_symbol)

        df = fetch_stock_data(yf_symbol)

        if df is None or len(df) < 50:
            continue

        technical = get_technical_signal(df)

        if technical["signal"] == "SKIP":
            continue

        news = apply_news_filter(symbol, technical["signal"], news_map)

        if not news["allowed"]:
            continue

        fundamentals = get_fundamental_score(symbol)
        levels = calculate_trade_levels(df, technical["signal"])

        confidence = (
            40
            + technical["technical_score"]
            + market["score"]
            + news["news_score"]
            + fundamentals["score"]
        )

        confidence = round(max(0, min(95, confidence)), 2)

        if confidence < MIN_CONFIDENCE:
            continue

        if technical["volume"] < MIN_VOLUME_RATIO:
            continue

        final_decision = "STRONG_BUY" if technical["signal"] == "BUY" else "STRONG_SELL"

        final_picks.append({
            "symbol": symbol,
            "direction": technical["signal"],
            "final_decision": final_decision,
            "confidence": confidence,

            "current_price": levels["current_price"],
            "entry": levels["entry"],
            "stop_loss": levels["stop_loss"],
            "target_1": levels["target_1"],
            "target_2": levels["target_2"],

            "technical_reason": technical["technical_reason"],
            "technical_score": technical["technical_score"],
            "rsi": technical["rsi"],
            "volume": technical["volume"],
            "strength": technical["strength"],
            "compression": technical["compression"],

            "market_condition": market["condition"],
            "market_reason": market["reason"],

            "fundamental_score": fundamentals["score"],
            "fundamental_reason": fundamentals["reason"],

            "news_sentiment": news["news_sentiment"],
            "news_strength": news["news_strength"],
            "news_short": news["news_short"],
        })

    return sorted(final_picks, key=lambda x: x["confidence"], reverse=True)


if __name__ == "__main__":
    print("TITAN dynamic final engine started...\n")

    picks = scan_final_titan_picks()

    if not picks:
        print("No high-quality setup aligned right now.")

    for pick in picks:
        print("\n-------------------------")
        print("FINAL PICK:", pick["symbol"])
        print("Direction:", pick["direction"])
        print("Confidence:", pick["confidence"])
        print("Price:", pick["current_price"])
        print("Entry:", pick["entry"])
        print("SL:", pick["stop_loss"])
        print("TP1:", pick["target_1"])
        print("TP2:", pick["target_2"])
        print("Technicals:", pick["technical_reason"])
        print("Market:", pick["market_reason"])
        print("Fundamentals:", pick["fundamental_reason"])
        print("News:", pick["news_short"])