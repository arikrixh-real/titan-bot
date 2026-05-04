def safe_float(value):
    try:
        return float(value)
    except:
        return None


def get_live_price(symbol):
    try:
        # your existing API logic here
        price = fetch_price_from_upstox(symbol)

        price = safe_float(price)

        if price is None:
            return None

        return price

    except Exception as e:
        print(f"Live price error {symbol}: {e}")
        return None