def calculate_rr(entry, sl, target):
    """
    Safe RR calculation
    """

    try:
        if entry is None or sl is None or target is None:
            return 0

        risk = abs(entry - sl)
        reward = abs(target - entry)

        if risk == 0:
            return 0

        rr = reward / risk

        return round(rr, 2)

    except Exception:
        return 0