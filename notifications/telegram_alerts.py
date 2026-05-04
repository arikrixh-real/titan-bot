import requests

BOT_TOKEN = "8635406884:AAFojnnKVAZXc32OAGKYWN34mjlE9m9yGwk"
CHAT_ID = "5334390668"


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram Error:", e)