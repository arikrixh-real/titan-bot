from intelligence.news_engine import get_stock_news


POSITIVE_WORDS = [
    "rise", "rises", "gain", "gains", "jumps", "surges",
    "beats", "profit", "growth", "strong", "record",
    "wins", "order", "deal", "approval", "upgrade",
    "expansion", "dividend"
]

NEGATIVE_WORDS = [
    "fall", "falls", "decline", "declines", "drops",
    "loss", "weak", "cuts", "slow", "miss",
    "downgrade", "penalty", "probe", "fraud",
    "debt", "resigns", "impacting"
]

# 🚨 Words that indicate generic market news (we skip these)
GENERIC_MARKET_WORDS = [
    "market", "nifty", "sensex", "stocks", "indices",
    "shares", "market opens", "market closes"
]


def is_generic_news(title):
    text = title.lower()
    for word in GENERIC_MARKET_WORDS:
        if word in text:
            return True
    return False


def calculate_news_sentiment(title, summary=""):
    text = f"{title} {summary}".lower()

    positive_score = 0
    negative_score = 0

    for word in POSITIVE_WORDS:
        if word in text:
            positive_score += 1

    for word in NEGATIVE_WORDS:
        if word in text:
            negative_score += 1

    if positive_score > negative_score:
        return "BULLISH", positive_score - negative_score

    if negative_score > positive_score:
        return "BEARISH", negative_score - positive_score

    return "NEUTRAL", 0


def generate_news_signals():
    stock_news = get_stock_news()
    signals = []

    for item in stock_news:
        title = item.get("title", "")
        summary = item.get("summary", "")
        link = item.get("link", "")
        symbols = item.get("detected_symbols", [])

        # ❌ Skip generic news like "Market rises..."
        if is_generic_news(title):
            continue

        sentiment, strength = calculate_news_sentiment(title, summary)

        # ❌ Skip weak signals
        if sentiment == "NEUTRAL" or strength == 0:
            continue

        for symbol in symbols:
            signal = {
                "symbol": symbol,
                "sentiment": sentiment,
                "strength": strength,
                "title": title,
                "link": link,
            }

            signals.append(signal)

    return signals


def get_actionable_news_signals():
    signals = generate_news_signals()

    # 🔥 Deduplicate: keep strongest signal per stock
    best_signals = {}

    for signal in signals:
        symbol = signal["symbol"]

        if symbol not in best_signals:
            best_signals[symbol] = signal
        else:
            if signal["strength"] > best_signals[symbol]["strength"]:
                best_signals[symbol] = signal

    return list(best_signals.values())


if __name__ == "__main__":
    print("Testing TITAN News Signal Engine...\n")

    signals = get_actionable_news_signals()

    if not signals:
        print("No actionable signals found.")

    for signal in signals:
        print("\n-------------------------")
        print("Symbol:", signal["symbol"])
        print("Sentiment:", signal["sentiment"])
        print("Strength:", signal["strength"])
        print("Title:", signal["title"])
        print("Link:", signal["link"])