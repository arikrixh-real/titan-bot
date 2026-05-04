def analyze_sector(stock_data):
    score = 0
    bias = "NEUTRAL"
    reasons = []

    reason_text = stock_data.get("reason", "").lower()

    # 1. Relative strength = strong sector proxy
    if "relative strength" in reason_text:
        score += 40
        reasons.append("Stock showing relative strength (sector likely strong)")

    # 2. Trend alignment helps sector confirmation
    if "trend aligned" in reason_text or "trend" in reason_text:
        score += 20
        reasons.append("Trend aligned with broader move")

    # 3. Breakout indicates sector participation
    if "breakout" in reason_text:
        score += 20
        reasons.append("Breakout suggests sector momentum")

    # 4. Weakness detection
    if "weak" in reason_text or "rejection" in reason_text:
        score -= 20
        reasons.append("Weak price action (sector may be weak)")

    # 5. Bias based on trade direction
    side = stock_data.get("side", "").upper()

    if side == "LONG":
        bias = "BULLISH"
    elif side == "SHORT":
        bias = "BEARISH"

    # Clamp score between 0 and 100
    score = max(0, min(score, 100))

    return {
        "score": score,
        "bias": bias,
        "reason": ", ".join(reasons) if reasons else "No strong sector signals"
    }