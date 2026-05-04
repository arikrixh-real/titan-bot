def calculate_rr(entry, sl, target, side=None):
    try:
        if entry is None or sl is None or target is None:
            return 0

        risk = abs(entry - sl)
        reward = abs(target - entry)

        if risk == 0:
            return 0

        return round(reward / risk, 2)

    except Exception:
        return 0


def position_sizing(entry, stop_loss, capital=100000, risk_percent=1):
    try:
        risk_amount = capital * (risk_percent / 100)
        risk_per_share = abs(entry - stop_loss)

        if risk_per_share == 0:
            return {
                "qty": 0,
                "risk_amount": risk_amount
            }

        qty = int(risk_amount / risk_per_share)

        return {
            "qty": qty,
            "risk_amount": risk_amount
        }

    except Exception:
        return {
            "qty": 0,
            "risk_amount": 0
        }