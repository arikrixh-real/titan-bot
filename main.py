import time
from datetime import datetime
from tabulate import tabulate

from engines.setup_engine import scan_for_setups
from utils.formatters import format_trade_output
from alerts.telegram_alert import send_telegram_message
from engines.time_filter import current_bot_mode


SCAN_INTERVAL_SECONDS = 120
last_alerts = {}


def build_message(setup):
    return (
        f"📈 <b>TITAN SIGNAL</b>\n\n"
        f"Stock: {setup['stock']}\n"
        f"Side: {setup['side']}\n"
        f"Status: {setup['status']}\n"
        f"Source: {setup['source']}\n"
        f"Price: {setup['price']}\n\n"
        f"Entry: {setup['entry']}\n"
        f"SL: {setup['sl']}\n"
        f"T1: {setup['t1']}\n"
        f"T2: {setup['t2']}\n\n"
        f"RR: {setup['rr']}\n"
        f"Score: {setup['score']}\n\n"
        f"Reason: {setup['reason']}"
    )


def run_once():
    global last_alerts

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

    for setup in setups:
        key = f"{setup['stock']}_{setup['side']}_{setup['status']}"

        if key not in last_alerts:
            send_telegram_message(build_message(setup))
            last_alerts[key] = True

    print("Scan complete.")


if __name__ == "__main__":
    print("=== TITAN SMART AUTO LOOP STARTED ===")
    print(f"Scanning every {SCAN_INTERVAL_SECONDS} seconds.")
    print("Press CTRL + C to stop.\n")

    while True:
        run_once()
        time.sleep(SCAN_INTERVAL_SECONDS)