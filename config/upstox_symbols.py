"""
TITAN - Upstox Instrument Map
-----------------------------
Manual safe map.

IMPORTANT:
- No Upstox search API here.
- Unknown symbols return None silently.
- setup_engine.py falls back to cached price.
"""

_cached_map = {}


MANUAL_INSTRUMENT_KEYS = {
    "RELIANCE": "NSE_EQ|INE002A01018",
    "TCS": "NSE_EQ|INE467B01029",
    "INFY": "NSE_EQ|INE009A01021",
    "HDFCBANK": "NSE_EQ|INE040A01034",
    "ICICIBANK": "NSE_EQ|INE090A01021",
    "SBIN": "NSE_EQ|INE062A01020",
    "AXISBANK": "NSE_EQ|INE238A01034",
    "KOTAKBANK": "NSE_EQ|INE237A01028",
    "LT": "NSE_EQ|INE018A01030",
    "ITC": "NSE_EQ|INE154A01025",
    "BHARTIARTL": "NSE_EQ|INE397D01024",
    "HINDUNILVR": "NSE_EQ|INE030A01027",
    "MARUTI": "NSE_EQ|INE585B01010",
    "TATAMOTORS": "NSE_EQ|INE155A01022",
    "TATASTEEL": "NSE_EQ|INE081A01020",
    "ADANIENT": "NSE_EQ|INE423A01024",
    "ADANIPORTS": "NSE_EQ|INE742F01042",
    "GRASIM": "NSE_EQ|INE047A01021",
    "NTPC": "NSE_EQ|INE733E01010",
    "ONGC": "NSE_EQ|INE213A01029",
    "PFC": "NSE_EQ|INE134E01011",
    "COALINDIA": "NSE_EQ|INE522F01014",
    "POWERGRID": "NSE_EQ|INE752E01010",
    "SUNPHARMA": "NSE_EQ|INE044A01036",
    "HCLTECH": "NSE_EQ|INE860A01027",
    "TECHM": "NSE_EQ|INE669C01036",
    "WIPRO": "NSE_EQ|INE075A01022",
    "ULTRACEMCO": "NSE_EQ|INE481G01011",
    "BAJAJ-AUTO": "NSE_EQ|INE917I01010",
    "BAJFINANCE": "NSE_EQ|INE296A01024",
    "BAJAJFINSV": "NSE_EQ|INE918I01026",
    "BRITANNIA": "NSE_EQ|INE216A01030",
    "CIPLA": "NSE_EQ|INE059A01026",
    "DRREDDY": "NSE_EQ|INE089A01023",
    "EICHERMOT": "NSE_EQ|INE066A01021",
    "HEROMOTOCO": "NSE_EQ|INE158A01026",
    "HINDALCO": "NSE_EQ|INE038A01020",
    "INDUSINDBK": "NSE_EQ|INE095A01012",
    "JSWSTEEL": "NSE_EQ|INE019A01038",
    "M&M": "NSE_EQ|INE101A01026",
    "NESTLEIND": "NSE_EQ|INE239A01024",
    "TITAN": "NSE_EQ|INE280A01028",
    "UPL": "NSE_EQ|INE628A01036",
}


def normalize_symbol(stock):
    stock = str(stock).upper().strip()

    if stock.endswith(".NS"):
        stock = stock[:-3]

    stock = stock.replace("NSE:", "")
    stock = stock.replace("NSE_EQ:", "")
    stock = stock.replace("NSE_EQ|", "")
    stock = stock.strip()

    return stock


def get_instrument_key(stock):
    stock = normalize_symbol(stock)

    if stock in _cached_map:
        return _cached_map[stock]

    key = MANUAL_INSTRUMENT_KEYS.get(stock)

    if key:
        _cached_map[stock] = key
        return key

    return None