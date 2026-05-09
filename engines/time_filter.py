from datetime import datetime, time

from utils.market_hours import IST, TRADE_WINDOW_END, TRADE_WINDOW_START, is_trade_window


def is_premarket():
    now = datetime.now(IST).time()
    return time(9, 0) <= now < TRADE_WINDOW_START


def is_market_open():
    return is_trade_window()


def current_bot_mode():
    if is_premarket():
        return "PRE_MARKET_MODE"

    if is_market_open():
        return "MARKET_MODE"

    return "INTELLIGENCE_MODE"
