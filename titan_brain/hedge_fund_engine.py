def analyze_hedge_fund_logic(stock_data):
    score = 0
    bias = "NEUTRAL"
    reasons = []

    reason_text = stock_data.get("reason", "").lower()
    side = stock_data.get("side", "").upper()
    rr = float(stock_data.get("rr", 0))

    # 1. Compression before breakout = liquidity buildup
    if "compression" in reason_text:
        score += 25
        reasons.append("Tight compression detected before move")

    # 2. Breakout ready = possible liquidity expansion
    if "breakout" in reason_text:
        score += 25
        reasons.append("Breakout ready condition detected")

    # 3. Volume spike = participation confirmation
    if "volume" in reason_text or "spike" in reason_text:
        score += 20
        reasons.append("Volume participation supports move")

    # 4. Risk-reward check
    if rr >= 2:
        score += 20
        reasons.append("Strong risk-reward setup")
    elif rr >= 1.5:
        score += 10
        reasons.append("Acceptable risk-reward setup")
    else:
        score -= 15
        reasons.append("Weak risk-reward setup")

    # 5. Trap / rejection warning
    if "rejection" in reason_text or "fakeout" in reason_text or "trap" in reason_text:
        score -= 30
        reasons.append("Possible trap or rejection detected")

    if side == "LONG":
        bias = "BULLISH"
    elif side == "SHORT":
        bias = "BEARISH"

    score = max(0, min(score, 100))

    return {
        "score": score,
        "bias": bias,
        "reason": ", ".join(reasons) if reasons else "No clear hedge fund logic"
    }