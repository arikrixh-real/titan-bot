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

        if risk_per_share <= 0:
            return {
                "qty": 0,
                "quantity": 0,
                "position_size": 0,
                "risk_amount": round(risk_amount, 2)
            }

        qty = int(risk_amount / risk_per_share)

        if qty * entry > capital:
            qty = int(capital / entry)

        if qty < 0:
            qty = 0

        return {
            "qty": qty,
            "quantity": qty,
            "position_size": round(qty * entry, 2),
            "risk_amount": round(risk_amount, 2)
        }

    except Exception:
        return {
            "qty": 0,
            "quantity": 0,
            "position_size": 0,
            "risk_amount": 0
        }
