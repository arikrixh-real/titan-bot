from intelligence.confluence_engine import apply_news_confluence
from notifications.telegram_alerts import send_telegram_message

# 🔥 Replace this with your real scanner later
# For now we simulate technical signals
TECHNICAL_SIGNALS = [
    {"symbol": "KOTAKBANK", "signal": "BUY"},
    {"symbol": "HINDUNILVR", "signal": "BUY"},
    {"symbol": "LT", "signal": "BUY"},
    {"symbol": "RELIANCE", "signal": "SELL"},
]


def format_trade_alert(result):
    decision = result["final_decision"]

    if decision in ["STRONG_BUY"]:
        emoji = "🟢🔥"
    elif decision in ["STRONG_SELL"]:
        emoji = "🔴🔥"
    elif decision == "BUY":
        emoji = "🟢"
    elif decision == "SELL":
        emoji = "🔴"
    else:
        emoji = "⚪"

    message = f"""
{emoji} <b>{result['symbol']}</b>

Decision: <b>{decision}</b>
Technical: {result['technical_signal']}
News: {result['news_sentiment']} (Strength {result['news_strength']})

Reason: {result['reason']}
"""

    if result["news_title"]:
        message += f"\n📰 {result['news_title']}\n🔗 {result['news_link']}"

    return message.strip()


def main():
    for trade in TECHNICAL_SIGNALS:
        result = apply_news_confluence(
            trade["symbol"],
            trade["signal"]
        )

        # ❌ Skip useless trades
        if result["final_decision"] == "SKIP":
            continue

        msg = format_trade_alert(result)

        print("\nSending:", result["symbol"])
        send_telegram_message(msg)


if __name__ == "__main__":
    main()