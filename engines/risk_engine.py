def calculate_rr(entry, sl, target, side="LONG"):
    if side == "LONG":
        risk = entry - sl
        reward = target - entry

    elif side == "SHORT":
        risk = sl - entry
        reward = entry - target

    else:
        return 0

    if risk <= 0:
        return 0

    rr = reward / risk
    return round(rr, 2)