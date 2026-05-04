def calculate_position_size(stock_data, risk_management):
    capital = 100000  # you can change later

    entry = float(stock_data.get("entry", 0))
    sl = float(stock_data.get("sl", 0))

    if entry <= 0 or sl <= 0:
        return {
            "qty": 0,
            "capital": capital,
            "risk_amount": 0,
            "status": "INVALID_DATA"
        }

    risk_per_share = abs(entry - sl)

    risk_percent = risk_management.get("suggested_risk_percent", 0.5)

    risk_amount = capital * (risk_percent / 100)

    if risk_per_share == 0:
        return {
            "qty": 0,
            "capital": capital,
            "risk_amount": risk_amount,
            "status": "ZERO_RISK"
        }

    qty = int(risk_amount / risk_per_share)

    return {
        "qty": qty,
        "capital": capital,
        "risk_amount": round(risk_amount, 2),
        "risk_per_share": round(risk_per_share, 2),
        "status": "OK"
    }