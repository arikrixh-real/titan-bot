import os
import requests
from dotenv import load_dotenv

from alerts.daily_alert_state import (
    DAILY_ALERT_STATE_FILE,
    load_daily_alert_state,
    save_daily_alert_state,
    today_ist,
)

# Load .env file
load_dotenv()

# Fetch environment variables AFTER loading .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Maximum Telegram trade setup alerts per trading day
DAILY_ALERT_LIMIT = 3

# Stores daily alert count locally
ALERT_STATE_FILE = str(DAILY_ALERT_STATE_FILE)


def _mask_secret(value):
    text = str(value or "")
    if len(text) <= 8:
        return "***" if text else "missing"
    return f"{text[:4]}...{text[-4:]}"


def _today_ist():
    return today_ist()


def _ensure_state_folder():
    DAILY_ALERT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_alert_state():
    try:
        return load_daily_alert_state()

    except Exception as e:
        print(f"Alert state load error: {e}")
        return {
            "date": _today_ist(),
            "alerts_sent": 0,
            "messages": [],
            "alerted_keys": [],
        }


def _save_alert_state(state):
    try:
        save_daily_alert_state(state)

    except Exception as e:
        print(f"Alert state save error: {e}")


def can_send_trade_alert(message=None):
    """
    Allows only 3 Telegram alerts per day.
    Also blocks exact duplicate messages on the same day.
    """

    state = _load_alert_state()

    if state.get("alerts_sent", 0) >= DAILY_ALERT_LIMIT:
        print(
            f"Daily Telegram alert limit reached "
            f"({state.get('alerts_sent', 0)}/{DAILY_ALERT_LIMIT})"
        )
        return False

    if message and message in state.get("messages", []):
        print("Duplicate Telegram alert blocked")
        return False

    return True


def _mark_alert_sent(message):
    state = _load_alert_state()

    state["alerts_sent"] = min(
        DAILY_ALERT_LIMIT,
        int(state.get("alerts_sent", 0)) + 1,
    )
    state.setdefault("messages", []).append(message)

    _save_alert_state(state)

    print(
        f"Daily Telegram alerts used: "
        f"{state['alerts_sent']}/{DAILY_ALERT_LIMIT}"
    )


def send_telegram_message(message):
    """
    Sends Telegram message with daily alert protection.

    IMPORTANT:
    - TITAN can still scan every 5 minutes.
    - TITAN can still journal all eligible setups.
    - TITAN can still track TP/SL and evolve.
    - Telegram will send only 3 setup alerts per day.
    """

    if not can_send_trade_alert(message):
        return False

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets missing. Alert not sent.")
        print(f"BOT_TOKEN: {_mask_secret(TELEGRAM_BOT_TOKEN)}")
        print(f"CHAT_ID: {_mask_secret(TELEGRAM_CHAT_ID)}")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }

        response = requests.post(url, data=payload, timeout=10)

        if response.status_code == 200:
            print("Telegram alert sent successfully")
            _mark_alert_sent(message)
            return True
        else:
            print(f"Telegram alert failed: {response.text}")
            return False

    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def get_daily_alert_status():
    """
    Dashboard/helper function.
    Shows how many Telegram alerts were used today.
    """

    state = _load_alert_state()

    return {
        "date": state.get("date"),
        "alerts_sent": int(state.get("alerts_sent", 0)),
        "daily_limit": DAILY_ALERT_LIMIT,
        "remaining": max(0, DAILY_ALERT_LIMIT - int(state.get("alerts_sent", 0))),
    }
