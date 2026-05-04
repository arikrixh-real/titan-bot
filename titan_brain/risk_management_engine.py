def analyze_risk_management(stock_data, brain_result=None):
    adjustment = 0
    warnings = []
    confirmations = []

    rr = float(stock_data.get("rr", 0))
    setup_score = float(stock_data.get("score", 0))
    side = str(stock_data.get("side", "")).upper()

    entry = float(stock_data.get("entry", 0))
    sl = float(stock_data.get("sl", 0))
    price = float(stock_data.get("price", 0))

    risk_per_share = abs(entry - sl)

    if entry <= 0 or sl <= 0 or price <= 0:
        return {
            "adjustment": 0,
            "status": "INVALID_DATA",
            "risk_per_share": None,
            "risk_level": "UNKNOWN",
            "suggested_risk_percent": 0,
            "warnings": ["Invalid price/entry/SL data"],
            "confirmations": []
        }

    risk_percent = (risk_per_share / entry) * 100

    if rr >= 2:
        adjustment += 15
        confirmations.append("Strong risk-reward setup")
    elif rr >= 1.5:
        adjustment += 5
        confirmations.append("Acceptable risk-reward setup")
    else:
        adjustment -= 20
        warnings.append("Risk-reward is below ideal level")

    if risk_percent <= 0.5:
        risk_level = "LOW"
        adjustment += 10
        confirmations.append("Tight and controlled stop-loss")
    elif risk_percent <= 1.2:
        risk_level = "NORMAL"
        adjustment += 5
        confirmations.append("Risk is within normal range")
    elif risk_percent <= 2:
        risk_level = "HIGH"
        adjustment -= 10
        warnings.append("Stop-loss distance is slightly high")
    else:
        risk_level = "VERY_HIGH"
        adjustment -= 25
        warnings.append("Stop-loss distance is too wide")

    if setup_score >= 80:
        suggested_risk_percent = 1.0
    elif setup_score >= 70:
        suggested_risk_percent = 0.75
    elif setup_score >= 60:
        suggested_risk_percent = 0.5
    else:
        suggested_risk_percent = 0.25

    if brain_result:
        conviction = brain_result.get("conviction", "LOW")

        if conviction == "HIGH":
            suggested_risk_percent += 0.25
        elif conviction == "LOW":
            suggested_risk_percent -= 0.25

    suggested_risk_percent = max(0.25, min(suggested_risk_percent, 1.25))

    if side not in ["LONG", "SHORT"]:
        warnings.append("Trade direction unclear")

    adjustment = max(-40, min(adjustment, 40))

    return {
        "adjustment": adjustment,
        "status": "OK",
        "risk_per_share": round(risk_per_share, 2),
        "risk_percent": round(risk_percent, 2),
        "risk_level": risk_level,
        "suggested_risk_percent": round(suggested_risk_percent, 2),
        "warnings": warnings,
        "confirmations": confirmations
    }