import requests

from config.api_keys import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }

        response = requests.post(url, data=payload, timeout=10)

        if response.status_code != 200:
            print(f"Telegram alert failed: {response.text}")

    except Exception as e:
        print(f"Telegram error: {e}")