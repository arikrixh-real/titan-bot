import json
import os
import hashlib

from intelligence.titan_decision_engine import scan_final_titan_picks
from notifications.telegram_alerts import send_telegram_message
from utils.market_hours import is_trade_window


STATE_FILE = "state/sent_signals.json"

def is_alert_time():
    return is_trade_window()


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def generate_signal_id(pick):
    raw = f"{pick['symbol']}_{pick['direction']}_{round(pick['entry'], 1)}_{round(pick['stop_loss'], 1)}"
    return hashlib.md5(raw.encode()).hexdigest()


def format_pick(pick):
    emoji = "🟢" if pick["direction"] == "BUY" else "🔴"

    return f"""
{emoji} <b>TITAN FINAL PICK</b>

Stock: <b>{pick['symbol']}</b>
Direction: <b>{pick['direction']}</b>
Decision: <b>{pick['final_decision']}</b>

Price: ₹{pick['current_price']}
Entry: ₹{pick['entry']}
SL: ₹{pick['stop_loss']}
TP1: ₹{pick['target_1']}
TP2: ₹{pick['target_2']}

Confidence: <b>{pick['confidence']}%</b>

Technicals: {pick['technical_reason']}
Market: {pick['market_reason']}
Fundamentals: {pick['fundamental_reason']}
News: {pick['news_short']}
""".strip()


def main():
    alert_allowed = is_alert_time()

    if not alert_allowed:
        print("Outside trade window. Silent study only.")
        return

    picks = scan_final_titan_picks()

    if not picks:
        print("No setups. Silent scan.")
        return

    state = load_state()
    updated = False

    for pick in picks[:3]:
        signal_id = generate_signal_id(pick)

        if signal_id not in state:
            print("Sending NEW setup:", pick["symbol"])
            send_telegram_message(format_pick(pick))
            state[signal_id] = True
            updated = True
        else:
            print("Duplicate skipped:", pick["symbol"])

    if updated:
        save_state(state)


if __name__ == "__main__":
    main()
