from datetime import datetime, time
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
TRADE_WINDOW_START = time(9, 20)
TRADE_WINDOW_END = time(15, 20)


def as_ist_datetime(value=None):
    if value is None:
        return datetime.now(IST)

    if value.tzinfo is None:
        return value.replace(tzinfo=IST)

    return value.astimezone(IST)


def is_trading_day(value=None):
    now = as_ist_datetime(value)
    return now.weekday() < 5


def is_trade_window(value=None):
    now = as_ist_datetime(value)
    return is_trading_day(now) and TRADE_WINDOW_START <= now.time() <= TRADE_WINDOW_END


def trade_window_text():
    return "09:20-15:20 IST"
