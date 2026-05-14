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


def position_sizing(entry, stop_loss, capital=1000, risk_percent=1):
    try:
        entry = float(entry)
        stop_loss = float(stop_loss)
        capital = float(capital)
        risk_percent = float(risk_percent)
        risk_amount = capital * (risk_percent / 100)
        risk_per_share = abs(entry - stop_loss)

        if entry <= 0 or stop_loss <= 0 or capital <= 0 or risk_percent <= 0 or risk_percent > 10 or risk_per_share <= 0:
            return {
                "qty": 0,
                "quantity": 0,
                "position_size": 0,
                "capital_used": 0,
                "risk_amount": round(max(risk_amount, 0), 2),
                "skip_reason": "INVALID_RISK_INPUT"
            }

        qty = int(risk_amount / risk_per_share)

        if qty < 1:
            skip_reason = "QTY_LESS_THAN_1"
            qty = 0
        elif qty * entry > capital:
            skip_reason = "INSUFFICIENT_CAPITAL"
            qty = 0
        else:
            skip_reason = ""

        return {
            "qty": qty,
            "quantity": qty,
            "position_size": round(qty * entry, 2),
            "capital_used": round(qty * entry, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_per_share": round(risk_per_share, 4),
            "skip_reason": skip_reason
        }

    except Exception:
        return {
            "qty": 0,
            "quantity": 0,
            "position_size": 0,
            "capital_used": 0,
            "risk_amount": 0,
            "skip_reason": "SIZING_ERROR"
        }
