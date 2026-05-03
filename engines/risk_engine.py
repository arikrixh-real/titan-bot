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
def position_sizing(entry, stop_loss, capital=100000, risk_percent=1.0):
    """
    Calculates position size based on fixed risk %.
    """

    risk_amount = capital * (risk_percent / 100)

    risk_per_share = abs(entry - stop_loss)

    if risk_per_share == 0:
        return {
            "qty": 0,
            "risk_amount": 0
        }

    qty = risk_amount / risk_per_share

    return {
        "qty": round(qty, 2),
        "risk_amount": round(risk_amount, 2)
    }
def position_sizing(entry, stop_loss, capital=100000, risk_percent=1.0):
    risk_amount = capital * (risk_percent / 100)
    risk_per_share = abs(entry - stop_loss)

    if risk_per_share == 0:
        return {
            "qty": 0,
            "risk_amount": 0
        }

    qty = risk_amount / risk_per_share

    return {
        "qty": round(qty, 2),
        "risk_amount": round(risk_amount, 2)
    }