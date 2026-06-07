from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
TRADE_WINDOW_START = time(9, 20)
TRADE_WINDOW_END = time(15, 20)
MARKET_CLOSE = time(15, 30)


def as_ist_datetime(value=None):
    if value is None:
        return datetime.now(IST)

    if value.tzinfo is None:
        return value.replace(tzinfo=IST)

    return value.astimezone(IST)


def is_trading_day(value=None):
    now = as_ist_datetime(value)
    return now.weekday() < 5


def is_market_session_day(value=None, holidays=None):
    now = as_ist_datetime(value)
    holiday_dates = {
        item if isinstance(item, date) else date.fromisoformat(str(item))
        for item in (holidays or [])
    }
    return now.weekday() < 5 and now.date() not in holiday_dates


def is_trade_window(value=None):
    now = as_ist_datetime(value)
    return is_trading_day(now) and TRADE_WINDOW_START <= now.time() <= TRADE_WINDOW_END


def trade_window_text():
    return "09:20-15:20 IST"


def previous_market_session_day(value=None, holidays=None):
    current = as_ist_datetime(value).date() - timedelta(days=1)
    while True:
        probe = datetime.combine(current, MARKET_CLOSE, tzinfo=IST)
        if is_market_session_day(probe, holidays=holidays):
            return current
        current -= timedelta(days=1)


def last_valid_market_session(value=None, holidays=None):
    now = as_ist_datetime(value)
    if is_market_session_day(now, holidays=holidays) and now.time() >= MARKET_CLOSE:
        session_day = now.date()
    elif is_market_session_day(now, holidays=holidays) and now.time() >= TRADE_WINDOW_START:
        session_day = now.date()
    else:
        session_day = previous_market_session_day(now, holidays=holidays)
    return datetime.combine(session_day, MARKET_CLOSE, tzinfo=IST)


def market_state(value=None, holidays=None):
    now = as_ist_datetime(value)
    if not is_market_session_day(now, holidays=holidays):
        return "MARKET_CLOSED"
    if is_trade_window(now):
        return "MARKET_OPEN"
    return "OFF_HOURS"
