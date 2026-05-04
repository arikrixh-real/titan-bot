def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def trigger_status(
    price=None,
    entry=None,
    side="LONG",
    symbol=None,
    score=None,
    rr=None,
    market_status=None,
    **kwargs
):
    """
    TITAN trigger engine (COMPATIBLE VERSION)

    Works with BOTH:
    - Old style: trigger_status(price, entry, side)
    - New style: trigger_status(symbol=..., score=..., rr=..., ...)

    Prevents crashes from unexpected arguments.
    """

    try:
        price = safe_float(price)
        entry = safe_float(entry)

        # If price/entry not available → fallback logic
        if price is None or entry is None:
            if score is not None and rr is not None:
                if score >= 1.5 and rr >= 1.5:
                    return "READY"
                return "WAITING"
            return "WAITING"

        side = str(side).upper()

        if side == "LONG":
            if price >= entry:
                return "TRIGGERED"
            return "WAITING"

        if side == "SHORT":
            if price <= entry:
                return "TRIGGERED"
            return "WAITING"

        return "UNKNOWN"

    except Exception:
        return "WAITING"