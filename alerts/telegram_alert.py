import os
import requests
from dotenv import load_dotenv

# ✅ Load .env file
load_dotenv()

# ✅ Fetch environment variables AFTER loading .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_message(message):
    # 🔍 Debug print (you can remove later)
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram secrets missing. Alert not sent.")
        print(f"BOT_TOKEN: {TELEGRAM_BOT_TOKEN}")
        print(f"CHAT_ID: {TELEGRAM_CHAT_ID}")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }

        response = requests.post(url, data=payload, timeout=10)

        if response.status_code == 200:
            print("✅ Telegram alert sent successfully")
        else:
            print(f"❌ Telegram alert failed: {response.text}")

    except Exception as e:
        print(f"❌ Telegram error: {e}")