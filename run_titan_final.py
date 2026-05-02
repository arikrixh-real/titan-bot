from intelligence.titan_decision_engine import scan_final_titan_picks
from notifications.telegram_alerts import send_telegram_message


def format_final_pick(pick):
    emoji = "🟢" if pick["direction"] == "BUY" else "🔴"

    message = f"""
{emoji} <b>TITAN FINAL PICK</b>

Stock: <b>{pick['symbol']}</b>
Direction: <b>{pick['direction']}</b>
Decision: <b>{pick['final_decision']}</b>

Current Price: ₹{pick['current_price']}
Entry: ₹{pick['entry']}
SL: ₹{pick['stop_loss']}
TP1: ₹{pick['target_1']}
TP2: ₹{pick['target_2']}

Confidence: <b>{pick['confidence']}%</b>

Technicals: {pick['technical_reason']}
News: {pick['news_short']}
"""

    return message.strip()


def main():
    picks = scan_final_titan_picks()

    if not picks:
        print("No final TITAN picks found.")
        return

    for pick in picks[:3]:
        print("Sending final pick:", pick["symbol"])
        send_telegram_message(format_final_pick(pick))


if __name__ == "__main__":
    main()