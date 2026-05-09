import os
from dotenv import load_dotenv
from alerts.telegram_alert import send_telegram_message
from utils.market_hours import is_trade_window, trade_window_text

# ✅ Load .env file
load_dotenv()

def run_test_trade():
    if not is_trade_window():
        print(f"Outside trade window ({trade_window_text()}). Test Telegram trade skipped.")
        return

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("❌ Telegram ENV not loaded properly")
        return

    test_signal = {
        "stock": "RELIANCE",
        "side": "BUY",
        "entry": 2500,
        "sl": 2480,
        "target": 2550,
        "score": 85,
        "reason": "TEST TRADE - Telegram pipeline check"
    }

    message = f"""
🚀 TITAN TEST TRADE

Stock: {test_signal['stock']}
Side: {test_signal['side']}
Entry: {test_signal['entry']}
SL: {test_signal['sl']}
Target: {test_signal['target']}
Score: {test_signal['score']}
Reason: {test_signal['reason']}
"""

    send_telegram_message(message)
    print("✅ TEST TRADE SENT SUCCESSFULLY")


if __name__ == "__main__":
    run_test_trade()
