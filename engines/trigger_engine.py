def trigger_status(price, entry, side="LONG"):
    if side == "LONG":
        if price >= entry:
            return "TRIGGERED"
        return "WAITING"

    if side == "SHORT":
        if price <= entry:
            return "TRIGGERED"
        return "WAITING"

    return "UNKNOWN"