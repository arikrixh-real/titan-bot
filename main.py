import time
from datetime import datetime
from tabulate import tabulate

from engines.setup_engine import scan_for_setups
from utils.formatters import format_trade_output
from alerts.telegram_alert import send_telegram_message
from engines.time_filter import current_bot_mode


SCAN_INTERVAL_SECONDS = 120
last_alerts = {}
premarket_sent = False


def run_once():
    global last_alerts, premarket_sent

    mode = current_bot_mode()

    print("\n" + "=" * 80)
    print(f"TITAN MODE: {mode} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    setups = scan_for_setups()

    if not setups:
        print("No setups found.")
        return

    formatted = format_trade_output(setups)
    print(tabulate(formatted, headers="keys", tablefmt="grid"))

    # 🔥 PRE-MARKET ALERT (only once)
    if mode == "PRE_MARKET_MODE" and not premarket_sent:
        msg = "📊 PRE-MARKET WATCHLIST\n\n"
        for s in setups[:5]:
            msg += f"{s['stock']} ({s['side']})\n"
        send_telegram_message(msg)
        premarket_sent = True

    # 🔥 MARKET MODE ALERTS
    if mode == "MARKET_MODE":
        for setup in setups:
            key = f"{setup['stock']}_{setup['side']}"
            prev_status = last_alerts.get(key)
            current_status = setup["status"]

            if prev_status != current_status:
                message = build_message(setup)
                send_telegram_message(message)
                last_alerts[key] = current_status

    print("Scan complete.")


def build_message(setup):
    if setup["status"] == "TRIGGERED":
        return (
            f"🚨 <b>TITAN TRIGGERED</b>\n\n"
            f"Stock: {setup['stock']}\n"
            f"Side: {setup['side']}\n"
            f"Entry Hit: {setup['entry']}\n"
            f"SL: {setup['sl']}\n"
            f"T1: {setup['t1']}\n"
            f"T2: {setup['t2']}"
        )
    else:
        return (
            f"📊 <b>TITAN SETUP</b>\n\n"
            f"Stock: {setup['stock']}\n"
            f"Side: {setup['side']}\n"
            f"Status: {setup['status']}\n"
            f"Entry: {setup['entry']}\n"
            f"SL: {setup['sl']}\n"
            f"T1: {setup['t1']}\n"
            f"T2: {setup['t2']}"
        )


if __name__ == "__main__":
    print("=== TITAN SMART AUTO LOOP STARTED ===")
    print(f"Scanning every {SCAN_INTERVAL_SECONDS} seconds.")
    print("Press CTRL + C to stop.\n")

    while True:
        run_once()
        time.sleep(SCAN_INTERVAL_SECONDS)