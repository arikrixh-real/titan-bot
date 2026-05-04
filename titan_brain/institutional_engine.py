def analyze_institutional(stock_data):
    score = 0
    bias = "NEUTRAL"
    reasons = []

    # 1. Base score from setup quality (your existing score)
    setup_score = stock_data.get("score", 0)

    if setup_score >= 80:
        score += 30
        reasons.append("High setup score (institutional interest likely)")
    elif setup_score >= 70:
        score += 20
        reasons.append("Good setup score")
    elif setup_score >= 60:
        score += 10
        reasons.append("Moderate setup score")

    # 2. Volume spike detection (from reason text)
    reason_text = stock_data.get("reason", "").lower()

    if "volume" in reason_text:
        score += 25
        reasons.append("Volume activity detected (possible accumulation)")

    if "spike" in reason_text:
        score += 15
        reasons.append("Volume spike (strong participation)")

    # 3. Compression + breakout logic (smart money behavior)
    if "compression" in reason_text:
        score += 15
        reasons.append("Price compression (institutional buildup)")

    if "breakout" in reason_text:
        score += 20
        reasons.append("Breakout condition (possible expansion phase)")

    # 4. Trend alignment (important for institutions)
    if "trend aligned" in reason_text or "trend" in reason_text:
        score += 10
        reasons.append("Trend aligned")

    # 5. Relative strength (institutions prefer leaders)
    if "relative strength" in reason_text:
        score += 15
        reasons.append("Relative strength confirmed")

    # 6. Bias based on trade direction
    side = stock_data.get("side", "").upper()

    if side == "LONG":
        bias = "BULLISH"
    elif side == "SHORT":
        bias = "BEARISH"

    # Cap score at 100
    score = min(score, 100)

    return {
        "score": score,
        "bias": bias,
        "reason": ", ".join(reasons) if reasons else "No strong institutional signals"
    }