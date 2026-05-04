from datetime import datetime, time


def is_premarket():
    now = datetime.now().time()
    return time(9, 0) <= now < time(9, 15)


def is_market_open():
    now = datetime.now().time()
    return time(9, 15) <= now <= time(15, 30)


def current_bot_mode():
    if is_premarket():
        return "PRE_MARKET_MODE"

    if is_market_open():
        return "MARKET_MODE"

    return "INTELLIGENCE_MODE"