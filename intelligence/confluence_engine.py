from intelligence.news_signal_engine import get_actionable_news_signals


def get_news_map():
    """
    Converts news signals into easy lookup format:
    {
        "KOTAKBANK": {
            "sentiment": "BULLISH",
            "strength": 4,
            "title": "...",
            "link": "..."
        }
    }
    """

    signals = get_actionable_news_signals()
    news_map = {}

    for signal in signals:
        symbol = signal["symbol"]

        news_map[symbol] = {
            "sentiment": signal["sentiment"],
            "strength": signal["strength"],
            "title": signal["title"],
            "link": signal["link"],
        }

    return news_map


def apply_news_confluence(symbol, technical_signal):
    """
    technical_signal should be:
    BUY / SELL / HOLD / SKIP
    """

    news_map = get_news_map()
    news = news_map.get(symbol)

    final_decision = technical_signal
    confluence_score = 0
    reason = "No news confluence"

    if not news:
        return {
            "symbol": symbol,
            "technical_signal": technical_signal,
            "news_sentiment": "NONE",
            "news_strength": 0,
            "final_decision": final_decision,
            "confluence_score": confluence_score,
            "reason": reason,
            "news_title": "",
            "news_link": "",
        }

    sentiment = news["sentiment"]
    strength = news["strength"]

    if technical_signal == "BUY" and sentiment == "BULLISH":
        final_decision = "STRONG_BUY"
        confluence_score = strength
        reason = "BUY signal confirmed by bullish news"

    elif technical_signal == "SELL" and sentiment == "BEARISH":
        final_decision = "STRONG_SELL"
        confluence_score = strength
        reason = "SELL signal confirmed by bearish news"

    elif technical_signal == "BUY" and sentiment == "BEARISH":
        final_decision = "SKIP"
        confluence_score = -strength
        reason = "BUY signal blocked by bearish news"

    elif technical_signal == "SELL" and sentiment == "BULLISH":
        final_decision = "SKIP"
        confluence_score = -strength
        reason = "SELL signal blocked by bullish news"

    else:
        final_decision = technical_signal
        confluence_score = 0
        reason = "News does not strongly affect this trade"

    return {
        "symbol": symbol,
        "technical_signal": technical_signal,
        "news_sentiment": sentiment,
        "news_strength": strength,
        "final_decision": final_decision,
        "confluence_score": confluence_score,
        "reason": reason,
        "news_title": news["title"],
        "news_link": news["link"],
    }


if __name__ == "__main__":
    print("Testing TITAN Confluence Engine...\n")

    test_trades = [
        {"symbol": "KOTAKBANK", "technical_signal": "BUY"},
        {"symbol": "HINDUNILVR", "technical_signal": "BUY"},
        {"symbol": "LT", "technical_signal": "BUY"},
        {"symbol": "RELIANCE", "technical_signal": "SELL"},
    ]

    for trade in test_trades:
        result = apply_news_confluence(
            trade["symbol"],
            trade["technical_signal"]
        )

        print("\n-------------------------")
        print("Symbol:", result["symbol"])
        print("Technical:", result["technical_signal"])
        print("News:", result["news_sentiment"])
        print("Strength:", result["news_strength"])
        print("Final Decision:", result["final_decision"])
        print("Reason:", result["reason"])