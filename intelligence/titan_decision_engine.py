import yfinance as yf

from scanners.compression_scanner import compression_score
from scanners.strength_scanner import price_strength_score
from scanners.volume_scanner import volume_anomaly_score
from intelligence.confluence_engine import apply_news_confluence


# ✅ CLEAN STOCK LIST (NO ERROR SYMBOLS)
STOCKS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "ITC.NS",
    "LT.NS",
    "KOTAKBANK.NS",
    "HINDUNILVR.NS",
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


def fetch_stock_data(symbol, period="3mo", interval="1d"):
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            group_by="column"
        )

        if df.empty:
            return None

        # Fix multi-index issue
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)

        return df

    except Exception as e:
        print(f"Data error for {symbol}: {e}")
        return None


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


def get_technical_signal(df):
    compression = compression_score(df)
    strength = price_strength_score(df)
    volume = volume_anomaly_score(df)

    score = 0
    reasons = []

    if compression >= 4:
        score += 20
        reasons.append("Compression setup")

    if strength >= 2:
        score += 25
        reasons.append("Price strength")

    if volume >= 1.5:
        score += 25
        reasons.append("Volume expansion")

    if strength <= -2:
        score -= 25
        reasons.append("Price weakness")

    if volume >= 1.5 and strength < 0:
        score -= 20
        reasons.append("Bearish volume pressure")

    if score >= 45:
        signal = "BUY"
    elif score <= -35:
        signal = "SELL"
    else:
        signal = "SKIP"

    return {
        "signal": signal,
        "technical_score": score,
        "compression": compression,
        "strength": strength,
        "volume": volume,
        "technical_reason": ", ".join(reasons) if reasons else "No strong setup",
    }


def calculate_final_confidence(technical_score, news_strength, final_decision):
    confidence = 50 + technical_score

    if final_decision in ["STRONG_BUY", "STRONG_SELL"]:
        confidence += news_strength * 5

    if final_decision == "SKIP":
        confidence = 0

    return round(max(0, min(95, confidence)), 2)


def shorten_news(title):
    if not title:
        return "No major news"

    if len(title) <= 90:
        return title

    return title[:87] + "..."


def scan_final_titan_picks():
    final_picks = []

    for yf_symbol in STOCKS:
        symbol = clean_symbol(yf_symbol)
        df = fetch_stock_data(yf_symbol)

        if df is None or len(df) < 30:
            continue

        technical = get_technical_signal(df)

        if technical["signal"] == "SKIP":
            continue

        confluence = apply_news_confluence(symbol, technical["signal"])

        if confluence["final_decision"] == "SKIP":
            continue

        levels = calculate_trade_levels(df, technical["signal"])

        confidence = calculate_final_confidence(
            technical["technical_score"],
            confluence["news_strength"],
            confluence["final_decision"],
        )

        if confidence < 65:
            continue

        final_picks.append({
            "symbol": symbol,
            "direction": technical["signal"],
            "final_decision": confluence["final_decision"],
            "confidence": confidence,
            "current_price": levels["current_price"],
            "entry": levels["entry"],
            "stop_loss": levels["stop_loss"],
            "target_1": levels["target_1"],
            "target_2": levels["target_2"],
            "technical_reason": technical["technical_reason"],
            "news_short": shorten_news(confluence["news_title"]),
        })

    return sorted(final_picks, key=lambda x: x["confidence"], reverse=True)


if __name__ == "__main__":
    print("Testing TITAN Final Decision Engine...\n")

    picks = scan_final_titan_picks()

    if not picks:
        print("No final TITAN picks found.")

    for pick in picks:
        print("\n-------------------------")
        print("Symbol:", pick["symbol"])
        print("Decision:", pick["final_decision"])
        print("Direction:", pick["direction"])
        print("Confidence:", pick["confidence"])
        print("Price:", pick["current_price"])
        print("Entry:", pick["entry"])
        print("SL:", pick["stop_loss"])
        print("TP1:", pick["target_1"])
        print("TP2:", pick["target_2"])
        print("Reason:", pick["technical_reason"])
        print("News:", pick["news_short"])